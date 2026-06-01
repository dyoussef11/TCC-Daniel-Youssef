"""
evaluate_rag_unified_with_reasons.py
Avaliação unificada com métricas DeepEval + razões detalhadas.
"""

import asyncio
import json
import gc
import hashlib
import pickle
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import pynvml
from tqdm import tqdm

from core.paths import VETORIZATION_DATA, AVALIACAO_DATA, VALIDACAO_SCRIPT
import sys
sys.path.append(str(VALIDACAO_SCRIPT))

# Importa do V4 (comportamental + tradicional)
from dataset_avaliacaoV4 import TEST_SUITE, get_traditional_tests, get_behavioral_tests
# from RAG_Temporal_V8_CPUMode_CacheReady import SpecialistTimeAwareRAG
from RAG_Temporal_V9 import SpecialistTimeAwareRAG
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
    max_temp: int = 78
    cooldown_temp: int = 69
    concurrent_metrics: int = 5
    cache_dir: Path = AVALIACAO_DATA / "cache"
    embedding_cache_size: int = 1000
    evaluator_model: str = "qwen3:4b-instruct"
    base_path: Path = VETORIZATION_DATA / 'base_conhecimento_multilingueV8.json'
    
    metric_thresholds: Dict[str, float] = field(default_factory=lambda: {
        "C_Precision": 0.7,
        "C_Relevancia": 0.7,
        "C_Recall": 0.6,
        "Faithfulness": 0.8,
        "Answer_Rel": 0.7
    })


@dataclass
class EvalStats:
    total_cases: int = 0
    completed: int = 0
    cache_hits: int = 0
    thermal_pauses: int = 0
    total_time_seconds: float = 0.0


class EmbeddingCache:
    def __init__(self, cache_dir: Path, max_size: int = 1000):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_size = max_size
        self._cache: Dict[str, np.ndarray] = {}
        self._load_existing()
    
    def _get_key(self, query: str) -> str:
        return hashlib.md5(query.encode()).hexdigest()
    
    def _get_path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.pkl"
    
    def _load_existing(self):
        for path in self.cache_dir.glob("*.pkl"):
            if len(self._cache) >= self.max_size:
                break
            try:
                with open(path, 'rb') as f:
                    self._cache[path.stem] = pickle.load(f)
            except:
                pass
    
    def get(self, query: str) -> Optional[np.ndarray]:
        key = self._get_key(query)
        if key in self._cache:
            return self._cache[key].copy()
        return None
    
    def set(self, query: str, embedding: np.ndarray):
        key = self._get_key(query)
        if len(self._cache) >= self.max_size:
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
            (self.cache_dir / f"{oldest_key}.pkl").unlink(missing_ok=True)
        self._cache[key] = embedding.copy()
        with open(self._get_path(key), 'wb') as f:
            pickle.dump(embedding, f)
    
    def stats(self) -> Dict:
        return {
            "size": len(self._cache),
            "max_size": self.max_size,
            "directory": str(self.cache_dir)
        }


class RAGManager:
    def __init__(self, base_path: Path, embedding_cache=None):
        self.base_path = base_path
        self._vanilla = None
        self._temporal = None
        self.embedding_cache = embedding_cache
    
    @property
    def temporal(self):
        if self._temporal is None:
            print("🔄 Carregando RAG Temporal (BGE-M3 na CPU)...")
            self._temporal = SpecialistTimeAwareRAG(
                self.base_path, 
                # variant_name="V9_HYBRID_AUDITOR",  # Usando V9 multi-marca
                variant_name="V9_HYBRID_MIXED_AUDITOR",  # Usando V9 multi-marca
                embedding_cache=self.embedding_cache
            )
            # Configurações otimizadas
            self._temporal.current_model = "phi3.5:latest"
            self._temporal.temperature = 0.0
            self._temporal.search_top_k = 10
            self._temporal.similarity_threshold = 1.2
        return self._temporal


class MetricEvaluator:
    def __init__(self, config: EvalConfig, monitor):
        self.config = config
        self.monitor = monitor
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
    
    async def evaluate(self, test_case: LLMTestCase, pbar: Optional[tqdm] = None) -> Dict:
        """Avalia um caso em todas as métricas e retorna scores com reasons."""
        results = {}
        
        for name, metric in self.metrics.items():
            score, reason = await self._measure_single(metric, test_case, pbar)
            results[name] = {"score": score, "reason": reason}
        
        return results
    
    async def _measure_single(self, metric, test_case: LLMTestCase, pbar=None) -> Tuple[float, str]:
        async with self.semaphore:
            if self.monitor:
                await self.monitor.ensure_thermal_safety(pbar)
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
                    reasons.append(str(r))
            return " | ".join(reasons) if reasons else "No reason provided"
        return "No reason available"


class BehavioralTestAnalyzer:
    """Analisa testes comportamentais e gera justificativa."""
    
    def analyze(self, test_case: Dict, response: str) -> Tuple[bool, str, Dict]:
        expected = test_case.get("expected_behavior", "should_admit_unavailability")
        forbidden = test_case.get("forbidden_patterns", [])
        required = test_case.get("required_patterns", [])
        pattern_type = test_case.get("pattern_type", "literal")
        
        response_lower = response.lower()
        
        forbidden_found = []
        for pattern in forbidden:
            if pattern_type == "regex":
                import re
                if re.search(pattern, response, re.IGNORECASE):
                    forbidden_found.append(pattern)
            else:
                if pattern.lower() in response_lower:
                    forbidden_found.append(pattern)
        
        required_found = []
        for pattern in required:
            if pattern_type == "regex":
                import re
                if re.search(pattern, response, re.IGNORECASE):
                    required_found.append(pattern)
            else:
                if pattern.lower() in response_lower:
                    required_found.append(pattern)
        
        min_required = test_case.get("min_required_matches", len(required))
        
        # Gera justificativa
        if expected == "should_admit_unavailability":
            passed = (len(required_found) >= min_required) and len(forbidden_found) == 0
            reason = f"Required patterns found: {required_found[:3]}. Forbidden patterns found: {forbidden_found[:3] if forbidden_found else 'none'}"
        
        elif expected == "should_ask_for_sku":
            passed = (len(required_found) >= min_required) and len(forbidden_found) == 0
            reason = f"Required (asking for SKU): {required_found[:3]}. Forbidden (direct answers): {forbidden_found[:3] if forbidden_found else 'none'}"
        
        elif expected == "should_explain_concept":
            passed = len(required_found) >= min_required
            reason = f"Explanatory concepts found: {required_found[:4]}"
        
        elif expected == "should_admit_cannot_compare":
            passed = (len(required_found) >= min_required) and len(forbidden_found) == 0
            reason = f"Admits cannot compare: {required_found[:3]}. No false comparison: {forbidden_found[:3] if forbidden_found else 'none'}"
        
        elif expected == "should_acknowledge_future_or_unavailable":
            passed = (len(required_found) >= min_required) and len(forbidden_found) == 0
            reason = f"Temporal awareness: {required_found[:3]}. No hallucinated future data: {forbidden_found[:3] if forbidden_found else 'none'}"
        
        else:
            passed = False
            reason = f"Unknown expected_behavior: {expected}"
        
        return passed, reason, {
            "forbidden_found": forbidden_found,
            "required_found": required_found,
            "expected": expected
        }


class EvaluationPipeline:
    def __init__(self):
        self.config = EvalConfig()
        self.stats = EvalStats(total_cases=len(TEST_SUITE))
        self.monitor = None  # Opcional: HardwareMonitor(self.config)
        self.embedding_cache = EmbeddingCache(self.config.cache_dir, self.config.embedding_cache_size)
        self.rag_manager = RAGManager(self.config.base_path, embedding_cache=self.embedding_cache)
        self.metric_evaluator = MetricEvaluator(self.config, self.monitor)
        self.behavioral_analyzer = BehavioralTestAnalyzer()
        
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        
        # Criar diretórios explicitamente
        self.resultados_dir = AVALIACAO_DATA / "resultados_temporal"
        self.resultados_dir.mkdir(parents=True, exist_ok=True)
        
        self.csv_path = self.resultados_dir / f"METRICAS_COMPLETAS_{self.timestamp}.csv"
        self.txt_path = self.resultados_dir / f"RELATORIO_COMPLETO_{self.timestamp}.txt"
    
    async def run(self):
        print("\n" + "=" * 80)
        print("🚀 AVALIAÇÃO COMPLETA COM REASONS")
        print("=" * 80)
        print(f"📁 Base: {self.config.base_path.name}")
        print(f"📊 Casos: {len(TEST_SUITE)}")
        print(f"   - Tradicionais: {len([t for t in TEST_SUITE if t.get('test_type') != 'behavioral'])}")
        print(f"   - Comportamentais: {len([t for t in TEST_SUITE if t.get('test_type') == 'behavioral'])}")
        print(f"🧠 Avaliador: {self.config.evaluator_model}")
        print(f"💾 Cache: {self.embedding_cache.stats()['size']} embeddings")
        print(f"📁 Output dir: {self.resultados_dir}")
        print("-" * 80)
        
        results_table = []
        
        with open(self.txt_path, 'w', encoding='utf-8') as f_report:
            f_report.write(f"RELATÓRIO DE AVALIAÇÃO COMPLETA\n")
            f_report.write(f"Data: {self.timestamp}\n")
            f_report.write(f"Base: {self.config.base_path}\n")
            f_report.write(f"Avaliador: {self.config.evaluator_model}\n")
            f_report.write("=" * 80 + "\n\n")
            
            pbar = tqdm(TEST_SUITE, desc="Avaliando")
            for test_case in pbar:
                result_row = await self._process_case(test_case, f_report, pbar)
                results_table.append(result_row)
                
                # Salva CSV incrementalmente
                pd.DataFrame(results_table).to_csv(self.csv_path, index=False)
        
        self._print_summary(results_table)
    
    async def _process_case(self, test_case: Dict, f_report, pbar) -> Dict:
        query = test_case["input"]
        ref_date = test_case.get("reference_date", "2026-03-12")
        test_type = test_case.get("test_type", "traditional")
        
        pbar.write(f"\n📝 {test_case['id']}: {query[:60]}...")
        
        # Executa RAG
        result = await self.rag_manager.temporal.search(query, ref_date)
        
        # Prepara caso DeepEval (só para testes tradicionais)
        if test_type != "behavioral":
            deep_case = LLMTestCase(
                input=query,
                actual_output=result["answer"],
                retrieval_context=result.get("sources", [])[:5],
                expected_output=test_case.get("expected_output")
            )
            metrics_results = await self.metric_evaluator.evaluate(deep_case, pbar)
        else:
            metrics_results = {}
        
        # Análise comportamental (para todos, mas especialmente para behavioral)
        behavioral_passed, behavioral_reason, behavioral_details = self.behavioral_analyzer.analyze(
            test_case, result["answer"]
        )
        
        # Monta linha do CSV COM REASONS
        row = {
            "ID": test_case.get("id", "unknown"),
            "Test_Type": test_type,
            "Query": query[:100],
            "Behavioral_Passed": behavioral_passed,
            "Behavioral_Reason": behavioral_reason[:500],
            "Expected_Behavior": test_case.get("expected_behavior", ""),
            "Audit_Trail": result.get("audit_trail", "")[:500],
        }
        
        # Adiciona scores e reasons das métricas
        for name, data in metrics_results.items():
            row[f"{name}_Score"] = data["score"]
            row[f"{name}_Reason"] = data["reason"][:500]
        
        # Log no relatório
        f_report.write(f"\n{'='*60}\n")
        f_report.write(f"ID: {test_case.get('id')}\n")
        f_report.write(f"Test Type: {test_type}\n")
        f_report.write(f"Query: {query}\n")
        f_report.write(f"Reference Date: {ref_date}\n")
        f_report.write(f"\n--- RESPOSTA ---\n{result['answer'][:1000]}\n")
        f_report.write(f"\n--- AUDIT ---\n{result.get('audit_trail', '')[:500]}\n")
        
        if test_type == "behavioral":
            f_report.write(f"\n--- COMPORTAMENTAL ---\n")
            f_report.write(f"Expected: {test_case.get('expected_behavior')}\n")
            f_report.write(f"Passed: {behavioral_passed}\n")
            f_report.write(f"Reason: {behavioral_reason}\n")
            f_report.write(f"Details: {behavioral_details}\n")
        else:
            f_report.write(f"\n--- MÉTRICAS (DeepEval) ---\n")
            for name, data in metrics_results.items():
                f_report.write(f"{name}: {data['score']:.3f}\n")
                f_report.write(f"  Reason: {data['reason']}\n")
        
        f_report.flush()
        
        return row
    
    def _print_summary(self, results_table: List[Dict]):
        print("\n" + "=" * 80)
        print("✅ AVALIAÇÃO CONCLUÍDA")
        print("=" * 80)
        
        # Comportamentais
        behavioral = [r for r in results_table if r.get("Test_Type") == "behavioral"]
        if behavioral:
            passed = sum(1 for r in behavioral if r.get("Behavioral_Passed"))
            print(f"\n📊 TESTES COMPORTAMENTAIS: {passed}/{len(behavioral)} passaram ({passed/len(behavioral)*100:.0f}%)")
            for r in behavioral:
                status = "✅" if r.get("Behavioral_Passed") else "❌"
                print(f"   {status} {r['ID']}: {r.get('Behavioral_Reason', '')[:80]}")
        
        # Tradicionais
        traditional = [r for r in results_table if r.get("Test_Type") != "behavioral"]
        if traditional:
            print(f"\n📊 MÉTRICAS MÉDIAS (DeepEval):")
            metrics_names = [k for k in traditional[0].keys() if "_Score" in k and k not in ["Behavioral_Score"]]
            for metric in metrics_names:
                scores = [r.get(metric, 0) for r in traditional if isinstance(r.get(metric), (int, float))]
                if scores:
                    avg = sum(scores) / len(scores)
                    print(f"   {metric}: {avg:.3f} (média sobre {len(scores)} casos)")
        
        print(f"\n📁 CSV: {self.csv_path}")
        print(f"📁 Relatório: {self.txt_path}")


async def main():
    pipeline = EvaluationPipeline()
    await pipeline.run()


if __name__ == "__main__":
    asyncio.run(main())