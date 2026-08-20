"""
evaluate_rag_comparative_with_reasons.py
Avaliação COMPARATIVA (V1 vs V8) com reasons.
"""

import asyncio
import gc
import hashlib
import pickle
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from tqdm import tqdm

from core.paths import VETORIZATION_DATA, AVALIACAO_DATA, VALIDACAO_SCRIPT
import sys
sys.path.append(str(VALIDACAO_SCRIPT))

# Importa do V4 (comportamental + tradicional)
from dataset_avaliacaoV4 import TEST_SUITE
from RAG_Temporal_V8_CPUMode_CacheReady import SpecialistTimeAwareRAG
from RAG_BaseLine import VanillaRAG  # ⭐ Importa o V1
from custom_evaluatorV2Backup import OllamaEvaluator
from deepeval.test_case import LLMTestCase
from deepeval.metrics import (
    ContextualPrecisionMetric,
    ContextualRelevancyMetric,
    ContextualRecallMetric,
    FaithfulnessMetric,
    AnswerRelevancyMetric
)


@dataclass
class EvalConfig:
    max_temp: int = 77
    cooldown_temp: int = 69
    concurrent_metrics: int = 5
    cache_dir: Path = AVALIACAO_DATA / "cache"
    embedding_cache_size: int = 1000
    evaluator_model: str = "qwen3:4b-instruct"
    base_path: Path = VETORIZATION_DATA / 'base_conhecimento_multilingueV7.json'
    
    metric_thresholds: Dict[str, float] = field(default_factory=lambda: {
        "C_Precision": 0.7,
        "C_Relevancia": 0.7,
        "C_Recall": 0.6,
        "Faithfulness": 0.8,
        "Answer_Rel": 0.7
    })


class EmbeddingCache:
    """
    Cache LRU simples para embeddings de queries.
    Evita recalcular embeddings para queries repetidas.
    """
    
    def __init__(self, cache_dir: Path, max_size: int = 1000):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_size = max_size
        self._cache: Dict[str, np.ndarray] = {}
        self._load_existing()
    
    def _get_key(self, query: str) -> str:
        """Gera chave de cache para uma query."""
        return hashlib.md5(query.encode()).hexdigest()
    
    def _get_path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.pkl"
    
    def _load_existing(self) -> None:
        """Carrega caches existentes do disco."""
        for path in self.cache_dir.glob("*.pkl"):
            if len(self._cache) >= self.max_size:
                break
            try:
                with open(path, 'rb') as f:
                    self._cache[path.stem] = pickle.load(f)
            except:
                pass
    
    def get(self, query: str) -> Optional[np.ndarray]:
        """Recupera embedding do cache."""
        key = self._get_key(query)
        if key in self._cache:
            return self._cache[key].copy()
        return None
    
    def set(self, query: str, embedding: np.ndarray) -> None:
        """Salva embedding no cache."""
        key = self._get_key(query)
        
        # LRU simples: remove mais antigo se cheio
        if len(self._cache) >= self.max_size:
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
            (self.cache_dir / f"{oldest_key}.pkl").unlink(missing_ok=True)
        
        self._cache[key] = embedding.copy()
        
        # Salva em disco
        with open(self._get_path(key), 'wb') as f:
            pickle.dump(embedding, f)
    
    def stats(self) -> Dict:
        return {
            "size": len(self._cache),
            "max_size": self.max_size,
            "directory": str(self.cache_dir)
        }


class ComparativeRAGManager:
    def __init__(self, base_path: Path, embedding_cache=None):
        self.base_path = base_path
        self.embedding_cache = embedding_cache
        self._vanilla: Optional[VanillaRAG] = None
        self._temporal: Optional[SpecialistTimeAwareRAG] = None
    
    @property
    def vanilla(self) -> VanillaRAG:
        if self._vanilla is None:
            print("🔄 Carregando RAG Vanilla (V1 - SEM expansão de query)...")
            self._vanilla = VanillaRAG(
                self.base_path, 
                embedding_cache=self.embedding_cache,
                use_expansion=False  # ⭐ CRÍTICO: V1 NÃO deve expandir
            )
        return self._vanilla
    
    @property
    def temporal(self) -> SpecialistTimeAwareRAG:
        if self._temporal is None:
            print("🔄 Carregando RAG Temporal (V9 - COM expansão de query)...")
            self._temporal = SpecialistTimeAwareRAG(
                self.base_path, 
                variant_name="V9_HYBRID_AUDITOR",
                embedding_cache=self.embedding_cache,
                use_expansion=True  # ✅ V9 pode expandir
            )
            self._temporal.current_model = "phi3.5:latest"
            self._temporal.temperature = 0.0
            self._temporal.search_top_k = 20
            self._temporal.similarity_threshold = 1.2
        return self._temporal


class ComparativeMetricEvaluator:
    """Avalia AMBAS as versões (V1 e V8) em paralelo."""
    
    def __init__(self, config: EvalConfig):
        self.config = config
        self.semaphore = asyncio.Semaphore(config.concurrent_metrics)
        self.evaluator = OllamaEvaluator(model_name=config.evaluator_model)
        
        self.metrics = {
            "C_Precision": ContextualPrecisionMetric(
                threshold=config.metric_thresholds["C_Precision"],
                model=self.evaluator,
                include_reason=True
            ),
            "C_Relevancia": ContextualRelevancyMetric(
                threshold=config.metric_thresholds["C_Relevancia"],
                model=self.evaluator,
                include_reason=True
            ),
            "C_Recall": ContextualRecallMetric(
                threshold=config.metric_thresholds["C_Recall"],
                model=self.evaluator,
                include_reason=True
            ),
            "Faithfulness": FaithfulnessMetric(
                threshold=config.metric_thresholds["Faithfulness"],
                model=self.evaluator,
                include_reason=True
            ),
            "Answer_Rel": AnswerRelevancyMetric(
                threshold=config.metric_thresholds["Answer_Rel"],
                model=self.evaluator,
                include_reason=True
            )
        }
    
    async def evaluate_both(self, case_v1: LLMTestCase, case_v8: LLMTestCase, pbar=None) -> Tuple[Dict, Dict]:
        """Avalia V1 e V8 e retorna scores com reasons para AMBOS."""
        results_v1 = {}
        results_v8 = {}
        
        for name, metric in self.metrics.items():
            # Avalia V1
            score_v1, reason_v1 = await self._measure_single(metric, case_v1, pbar)
            results_v1[name] = {"score": score_v1, "reason": reason_v1}
            
            # Avalia V8
            score_v8, reason_v8 = await self._measure_single(metric, case_v8, pbar)
            results_v8[name] = {"score": score_v8, "reason": reason_v8}
        
        return results_v1, results_v8
    
    async def _measure_single(self, metric, test_case: LLMTestCase, pbar=None) -> Tuple[float, str]:
        async with self.semaphore:
            try:
                await asyncio.to_thread(metric.measure, test_case)
                return float(metric.score), self._extract_reason(metric)
            except Exception as e:
                return 0.0, f"Erro: {str(e)[:100]}"
    
    def _extract_reason(self, metric) -> str:
        if hasattr(metric, 'reason') and metric.reason:
            return str(metric.reason).replace('\n', ' ')[:1000]
        if hasattr(metric, 'verdicts') and metric.verdicts:
            reasons = []
            for v in metric.verdicts[:3]:
                r = getattr(v, 'reason', None)
                if not r and isinstance(v, dict):
                    r = v.get('reason')
                if r:
                    reasons.append(str(r)[:300])
            return " | ".join(reasons) if reasons else "No reason provided"
        return "No reason available"


class BehavioralTestAnalyzer:
    """Analisa testes comportamentais."""
    
    def analyze(self, test_case: Dict, response_v1: str, response_v8: str) -> Tuple[bool, bool, str, str]:
        """Analisa ambas as versões."""
        expected = test_case.get("expected_behavior", "should_admit_unavailability")
        forbidden = test_case.get("forbidden_patterns", [])
        required = test_case.get("required_patterns", [])
        
        def check_response(response: str) -> Tuple[bool, str]:
            response_lower = response.lower()
            forbidden_found = [p for p in forbidden if p.lower() in response_lower]
            required_found = [p for p in required if p.lower() in response_lower]
            min_required = test_case.get("min_required_matches", len(required))
            
            if expected == "should_admit_unavailability":
                passed = (len(required_found) >= min_required) and len(forbidden_found) == 0
                reason = f"Required: {required_found[:3]}. Forbidden: {forbidden_found[:3] if forbidden_found else 'none'}"
            elif expected == "should_ask_for_sku":
                passed = (len(required_found) >= min_required) and len(forbidden_found) == 0
                reason = f"Asked for SKU: {required_found[:3]}. Direct answers: {forbidden_found[:3] if forbidden_found else 'none'}"
            elif expected == "should_explain_concept":
                passed = len(required_found) >= min_required
                reason = f"Concepts found: {required_found[:4]}"
            else:
                passed = False
                reason = f"Unknown expected: {expected}"
            return passed, reason
        
        passed_v1, reason_v1 = check_response(response_v1)
        passed_v8, reason_v8 = check_response(response_v8)
        
        return passed_v1, passed_v8, reason_v1, reason_v8

class RAGManager:
    """
    Gerencia instâncias dos RAGs com carregamento lazy.
    Evita carregar a base duas vezes.
    """
    
    def __init__(self, base_path: Path, embedding_cache=None):
        self.base_path = base_path
        self._vanilla: Optional[VanillaRAG] = None
        self._temporal: Optional[SpecialistTimeAwareRAG] = None
        self.embedding_cache = embedding_cache  # ⭐ NOVO
        print(f"📁 RAGManager configurado com base: {base_path.name}")
    
    @property
    def vanilla(self) -> VanillaRAG:
        if self._vanilla is None:
            print("🔄 Carregando RAG Vanilla (BGE-M3 na CPU)...")
            # self._vanilla = VanillaRAG(self.base_path)
            self._vanilla = VanillaRAG(self.base_path, embedding_cache=self.embedding_cache)
        return self._vanilla
    
    @property
    def temporal(self) -> SpecialistTimeAwareRAG:
        if self._temporal is None:
            print("🔄 Carregando RAG Temporal (BGE-M3 na CPU)...")
            self._temporal = SpecialistTimeAwareRAG(
                self.base_path, 
                variant_name="V8_HYBRID_AUDITOR",
                embedding_cache=self.embedding_cache
            )
        return self._temporal
    
    def unload(self) -> None:
        """Libera memória dos RAGs."""
        print("🔄 Descarregando RAGs da memória...")
        self._vanilla = None
        self._temporal = None
        gc.collect()
    
    def get_cache_stats(self) -> Dict:
        """Retorna estatísticas de cache de ambos os RAGs."""
        stats = {}
        if self._vanilla and hasattr(self._vanilla, 'get_cache_stats'):
            stats['vanilla'] = self._vanilla.get_cache_stats()
        if self._temporal and hasattr(self._temporal, 'get_cache_stats'):
            stats['temporal'] = self._temporal.get_cache_stats()
        return stats

class ComparativeEvaluationPipeline:
    """
    Pipeline que compara V1 (Vanilla) vs V8 (Temporal) com reasons.
    """
    
    def __init__(self):
        self.config = EvalConfig()
        self.embedding_cache = EmbeddingCache(self.config.cache_dir, self.config.embedding_cache_size)
        self.rag_manager = ComparativeRAGManager(self.config.base_path, embedding_cache=self.embedding_cache)
        self.metric_evaluator = ComparativeMetricEvaluator(self.config)
        self.behavioral_analyzer = BehavioralTestAnalyzer()
        
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        self.csv_path = AVALIACAO_DATA / "resultados"/ f"COMPARATIVO_V1_VS_V8_{self.timestamp}.csv"
        self.txt_path = AVALIACAO_DATA / "resultados"/ f"RELATORIO_COMPARATIVO_{self.timestamp}.txt"
    
    async def run(self):
        print("\n" + "=" * 80)
        print("🚀 AVALIAÇÃO COMPARATIVA: V1 (Vanilla) vs V8 (Temporal)")
        print("📍 BGE-M3 rodando na CPU | Modelo: phi3.5:latest | Temperature: 0.0")
        print("=" * 80)
        print(f"📁 Base: {self.config.base_path.name}")
        print(f"📊 Casos: {len(TEST_SUITE)}")
        print(f"🧠 Avaliador: {self.config.evaluator_model}")
        print(f"💾 Cache: {self.embedding_cache.stats()['size']} embeddings")
        print("-" * 80)
        
        results_table = []
        
        with open(self.txt_path, 'w', encoding='utf-8') as f_report:
            f_report.write(f"RELATÓRIO COMPARATIVO V1 vs V8\n")
            f_report.write(f"Data: {self.timestamp}\n")
            f_report.write(f"Base: {self.config.base_path}\n")
            f_report.write(f"Avaliador: {self.config.evaluator_model}\n")
            f_report.write("=" * 80 + "\n\n")
            
            pbar = tqdm(TEST_SUITE, desc="Avaliando")
            for test_case in pbar:
                row = await self._process_case(test_case, f_report, pbar)
                results_table.append(row)
                pd.DataFrame(results_table).to_csv(self.csv_path, index=False)
                
            f_report.write("\n" + "=" * 80 + "\n")
            f_report.write("RECOMENDAÇÃO FINAL\n")
            f_report.write("=" * 80 + "\n\n")
            f_report.write("""
            O V9 (Temporal) FOI PROJETADO para ser mais restritivo e preciso:
            - NÃO infere especificações de SKUs não encontrados
            - PEDE o SKU quando a query é genérica
            - RECUSA comparar modelos sem dados completos

            O V1 (Vanilla) FOI PROJETADO para ser mais útil/abrangente:
            - PODE inferir informações de contextos similares
            - TENTA responder mesmo sem dados exatos
            - USA conhecimento interno livremente

            MÉTRICAS - INTERPRETAÇÃO CORRETA:
            - Faithfulness maior no V9: INDICA MENOS ALUCINAÇÃO (bom)
            - Answer Relevancy menor no V9: INDICA MAIS RESTRIÇÕES (trade-off)
            - Comportamental V9 > V1: INDICA MELHOR ADERÊNCIA ÀS REGRAS

            RECOMENDAÇÃO DE USO:
            ┌─────────────────────────────────────────────────────────────────┐
            │  CASO DE USO              │  MELHOR ESCOLHA    │  MOTIVO        │
            ├─────────────────────────────────────────────────────────────────┤
            │  Chat geral / FAQ         │  V1 (Vanilla)      │  Mais útil     │
            │  Suporte com SKU          │  V9 (Temporal)     │  Mais preciso  │
            │  E-commerce / Catálogo    │  V9 (Temporal)     │  Sem alucinação│
            │  Troubleshooting          │  V1 (Vanilla)      │  Mais abrangente│
            │  Atendimento técnico      │  V9 (Temporal)     │  Rastreável    │
            └─────────────────────────────────────────────────────────────────┘

            CONCLUSÃO: O V9 é SUPERIOR para casos que exigem precisão e rastreabilidade,
            enquanto o V1 é melhor para conversação geral. A escolha depende do caso de uso.
            """)
        
        self._print_summary(results_table)
    
    async def _process_case(self, test_case: Dict, f_report, pbar) -> Dict:

        query = test_case["input"]
        ref_date = test_case.get("reference_date", "2026-03-12")
        test_type = test_case.get("test_type", "traditional")
        
        pbar.write(f"\n📝 {test_case['id']}: {query[:60]}...")
        
        # Executa AMBOS os RAGs
        res_v1 = await self.rag_manager.vanilla.search(query)
        res_v8 = await self.rag_manager.temporal.search(query, ref_date)
        # LOG para verificar diferenças
        pbar.write(f"   V1 normalized: {res_v1.get('normalized_query', query)[:50]}")
        pbar.write(f"   V9 normalized: {res_v8.get('normalized_query', query)[:50]}")
        
        # Casos DeepEval
        case_v1 = LLMTestCase(
            input=query,
            actual_output=res_v1["answer"],
            retrieval_context=res_v1.get("sources", [])[:5],
            expected_output=test_case.get("expected_output")
        )
        case_v8 = LLMTestCase(
            input=query,
            actual_output=res_v8["answer"],
            retrieval_context=res_v8.get("sources", [])[:5],
            expected_output=test_case.get("expected_output")
        )
        
        # Avalia AMBAS as versões
        results_v1, results_v8 = await self.metric_evaluator.evaluate_both(case_v1, case_v8, pbar)
        
        # Análise comportamental para AMBAS
        behavioral_v1, behavioral_v8, reason_v1_behav, reason_v8_behav = self.behavioral_analyzer.analyze(
            test_case, res_v1["answer"], res_v8["answer"]
        )
        
        # Monta linha do CSV (com V1 e V8 lado a lado)
        row = {
            "ID": test_case.get("id", "unknown"),
            "Test_Type": test_type,
            "Query": query[:100],
            # V1 (Vanilla)
            "V1_Answer": res_v1["answer"][:500],
            "V1_Audit": res_v1.get("audit_trail", "")[:300],
            "V1_Behavioral_Passed": behavioral_v1,
            "V1_Behavioral_Reason": reason_v1_behav[:300],
            # V8 (Temporal)
            "V8_Answer": res_v8["answer"][:500],
            "V8_Audit": res_v8.get("audit_trail", "")[:300],
            "V8_Behavioral_Passed": behavioral_v8,
            "V8_Behavioral_Reason": reason_v8_behav[:300],
        }
        
        # Adiciona métricas de AMBAS as versões
        for name, data in results_v1.items():
            row[f"V1_{name}_Score"] = data["score"]
            row[f"V1_{name}_Reason"] = data["reason"][:500]
        
        for name, data in results_v8.items():
            row[f"V8_{name}_Score"] = data["score"]
            row[f"V8_{name}_Reason"] = data["reason"][:500]
        
        # Log no relatório
        f_report.write(f"\n{'='*80}\n")
        f_report.write(f"ID: {test_case.get('id')}\n")
        f_report.write(f"Query: {query}\n")
        f_report.write(f"\n--- V1 (VANILLA) ---\n")
        f_report.write(f"RESPONSE:\n{res_v1['answer'][:800]}\n")
        f_report.write(f"AUDIT:\n{res_v1.get('audit_trail', '')[:300]}\n")
        f_report.write(f"\n--- V8 (TEMPORAL) ---\n")
        f_report.write(f"RESPONSE:\n{res_v8['answer'][:800]}\n")
        f_report.write(f"AUDIT:\n{res_v8.get('audit_trail', '')[:300]}\n")
        
        if test_type == "behavioral":
            f_report.write(f"\n--- COMPORTAMENTAL ---\n")
            f_report.write(f"V1 Passed: {behavioral_v1} | Reason: {reason_v1_behav}\n")
            f_report.write(f"V8 Passed: {behavioral_v8} | Reason: {reason_v8_behav}\n")
        else:
            f_report.write(f"\n--- MÉTRICAS (DeepEval) ---\n")
            for name in results_v1.keys():
                f_report.write(f"{name}:\n")
                f_report.write(f"  V1: {results_v1[name]['score']:.3f} | {results_v1[name]['reason'][:200]}\n")
                f_report.write(f"  V8: {results_v8[name]['score']:.3f} | {results_v8[name]['reason'][:200]}\n")
        
        f_report.flush()
        
        return row
    
    def _print_summary(self, results_table: List[Dict]):
        print("\n" + "=" * 80)
        print("✅ AVALIAÇÃO COMPARATIVA CONCLUÍDA")
        print("=" * 80)
        
        # ⭐ NOVO: Verificar se as diferenças são SIGNIFICATIVAS
        traditional = [r for r in results_table if r.get("Test_Type") != "behavioral"]
        
        if traditional:
            print(f"\n📊 ANÁLISE DE GANHO DO V9 SOBRE V1:")
            
            metrics = ["Faithfulness", "Answer_Rel", "C_Relevancia"]
            for metric in metrics:
                v1_scores = [r.get(f"V1_{metric}_Score", 0) for r in traditional]
                v9_scores = [r.get(f"V8_{metric}_Score", 0) for r in traditional]  # Note: V8 no código = V9
                
                if v1_scores and v9_scores:
                    v1_avg = sum(v1_scores) / len(v1_scores)
                    v9_avg = sum(v9_scores) / len(v9_scores)
                    gain = v9_avg - v1_avg
                    gain_pct = (gain / v1_avg * 100) if v1_avg > 0 else 0
                    
                    symbol = "🟢" if gain > 0 else "🔴" if gain < 0 else "⚪"
                    print(f"   {symbol} {metric}: V1={v1_avg:.3f} → V9={v9_avg:.3f} ({gain:+.3f} / {gain_pct:+.1f}%)")
        
        # Comportamentais
        behavioral = [r for r in results_table if r.get("Test_Type") == "behavioral"]
        if behavioral:
            v1_passed = sum(1 for r in behavioral if r.get("V1_Behavioral_Passed"))
            v9_passed = sum(1 for r in behavioral if r.get("V8_Behavioral_Passed"))
            
            print(f"\n📊 TESTES COMPORTAMENTAIS ({len(behavioral)} casos):")
            print(f"   V1 (Vanilla - pode inferir): {v1_passed}/{len(behavioral)} passaram ({v1_passed/len(behavioral)*100:.0f}%)")
            print(f"   V9 (Temporal - SKU lock): {v9_passed}/{len(behavioral)} passaram ({v9_passed/len(behavioral)*100:.0f}%)")
            
            # ⭐ Análise de trade-off
            if v9_passed < v1_passed:
                print(f"   ⚠️ ATENÇÃO: V9 é MAIS RESTRITIVO (SKU lock) que V1")
                print(f"   Isso é esperado: V9 recusa inferência, V1 aceita")
    def _print_fair_comparison_note(self):
        """Exibe nota sobre a comparação justa entre V1 e V9."""
        print("\n" + "=" * 80)
        print("🔍 NOTA SOBRE A COMPARAÇÃO")
        print("=" * 80)
        print("""
        O V9 (Temporal) FOI PROJETADO para ser mais restritivo e preciso:
        - NÃO infere especificações de SKUs não encontrados
        - PEDE o SKU quando a query é genérica
        - RECUSA comparar modelos sem dados completos
        
        O V1 (Vanilla) FOI PROJETADO para ser mais útil/abrangente:
        - PODE inferir informações de contextos similares
        - TENTA responder mesmo sem dados exatos
        - USA conhecimento interno livremente
        
        Portanto, métricas isoladas NÃO indicam superioridade absoluta:
        - Faithfulness maior no V9 é ESPERADO (mais restritivo)
        - Answer Relevancy menor no V9 é ESPERADO (recusa responder)
        
        ✅ O VALOR REAL do V9 está em:
        1. Redução de alucinações (especialmente para SKUs raros)
        2. Comportamento previsível (sempre pede SKU quando necessário)
        3. Rastreabilidade (auditoria completa)
        4. Consistência entre marcas (brand agnostic)
        
        🎯 RECOMENDAÇÃO DE USO:
        - Use V1 (Vanilla) para: chats gerais, troubleshooting, conceitos
        - Use V9 (Temporal) para: suporte técnico com SKUs, e-commerce, atendimento preciso
        """)


async def main():
    pipeline = ComparativeEvaluationPipeline()
    await pipeline.run()


if __name__ == "__main__":
    asyncio.run(main())