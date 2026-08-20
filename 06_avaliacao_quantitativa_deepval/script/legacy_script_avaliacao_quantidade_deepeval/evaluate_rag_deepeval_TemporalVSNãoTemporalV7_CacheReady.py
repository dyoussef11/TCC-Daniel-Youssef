# evaluate_rag_deepeval_V6_OTIMIZADO.py
"""
Avaliação comparativa entre RAG Vanilla e RAG Temporal.
Otimizado para bases grandes com cache de embeddings e carregamento lazy.
VERSÃO: BGE-M3 na CPU
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

# ⭐ IMPORTANDO AS VERSÕES COM CPU (já está correto)
from RAGNaoTemporal_CPUMode import VanillaRAG
from RAG_Temporal_V8_CPUMode import SpecialistTimeAwareRAG
from custom_evaluatorV2Backup import OllamaEvaluator
from dataset_avaliacaoV3 import TEST_SUITE
from deepeval.test_case import LLMTestCase
from deepeval.metrics import (
    ContextualPrecisionMetric,
    ContextualRelevancyMetric,
    ContextualRecallMetric,
    FaithfulnessMetric,
    AnswerRelevancyMetric
)

# ============================================================================
# CONFIGURAÇÕES
# ============================================================================

@dataclass
class EvalConfig:
    """Configurações centralizadas da avaliação."""
    
    # Hardware
    max_temp: int = 77
    cooldown_temp: int = 69
    concurrent_metrics: int = 5
    
    # Cache
    cache_dir: Path = AVALIACAO_DATA / "cache"
    embedding_cache_size: int = 1000
    
    # Modelos
    evaluator_model: str = "qwen3:4b-instruct"
    # ⭐ ATUALIZADO: Use a base V6 que você tem (ou mantenha V7)
    base_path: Path =  VETORIZATION_DATA / 'base_conhecimento_multilingueV7.json'
    
    # Métricas
    metric_thresholds: Dict[str, float] = field(default_factory=lambda: {
        "C_Precision": 0.7,
        "C_Relevancia": 0.7,
        "C_Recall": 0.6,
        "Faithfulness": 0.8,
        "Answer_Rel": 0.7
    })


@dataclass
class EvalStats:
    """Estatísticas da avaliação."""
    
    total_cases: int = 0
    completed: int = 0
    cache_hits: int = 0
    thermal_pauses: int = 0
    total_time_seconds: float = 0.0
    
    def progress(self) -> str:
        return f"{self.completed}/{self.total_cases} casos"


# ============================================================================
# MONITOR DE HARDWARE
# ============================================================================

class HardwareMonitor:
    """Monitor de temperatura e VRAM da GPU."""
    
    def __init__(self, config: EvalConfig):
        self.config = config
        self.enabled = self._init_nvml()
    
    def _init_nvml(self) -> bool:
        try:
            pynvml.nvmlInit()
            self.handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            return True
        except Exception as e:
            print(f"⚠️ NVML não disponível: {e}")
            print("   Continuando sem monitoramento de GPU...")
            return False
    
    def get_stats(self) -> Tuple[int, float]:
        """Retorna (temperatura, vram_usada_gb)."""
        if not self.enabled:
            return 0, 0.0
        
        try:
            temp = pynvml.nvmlDeviceGetTemperature(self.handle, pynvml.NVML_TEMPERATURE_GPU)
            mem = pynvml.nvmlDeviceGetMemoryInfo(self.handle)
            return temp, mem.used / 1024**3
        except:
            return 0, 0.0
    
    async def ensure_thermal_safety(self, pbar: Optional[tqdm] = None) -> None:
        """Pausa se temperatura estiver alta."""
        if not self.enabled:
            return
        
        temp, _ = self.get_stats()
        if temp >= self.config.max_temp:
            msg = f"🌡️ GPU a {temp}°C! Aguardando {self.config.cooldown_temp}°C..."
            if pbar:
                pbar.write(msg)
            else:
                print(msg)
            
            # Incrementa contador de pausas térmicas
            if hasattr(self, 'stats') and self.stats:
                self.stats.thermal_pauses += 1
            
            while temp > self.config.cooldown_temp:
                await asyncio.sleep(5)
                temp, _ = self.get_stats()
            
            if pbar:
                pbar.write(f"❄️ GPU resfriada para {temp}°C. Retomando...")
    
    def shutdown(self) -> None:
        if self.enabled:
            pynvml.nvmlShutdown()


# ============================================================================
# CACHE DE EMBEDDINGS
# ============================================================================

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


# ============================================================================
# GERENCIADOR DE RAGS (Singleton Pattern)
# ============================================================================

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


# ============================================================================
# AVALIADOR DE MÉTRICAS
# ============================================================================

class MetricEvaluator:
    """Avalia métricas do DeepEval com segurança térmica."""
    
    def __init__(self, config: EvalConfig, monitor: HardwareMonitor):
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
    
    async def evaluate(
        self,
        case_v1: LLMTestCase,
        case_v8: LLMTestCase,
        pbar: Optional[tqdm] = None
    ) -> Tuple[Dict, Dict]:
        """
        Avalia ambos os casos em todas as métricas.
        
        Returns:
            Tupla (results_v1, results_v8) com scores e reasons
        """
        results_v1 = {}
        results_v8 = {}
        
        for name, metric in self.metrics.items():
            # Avalia V8 primeiro (mais importante)
            score_v8, reason_v8 = await self._measure_single(metric, case_v8, pbar)
            results_v8[name] = (score_v8, reason_v8)
            
            # Avalia V1
            score_v1, reason_v1 = await self._measure_single(metric, case_v1, pbar)
            results_v1[name] = (score_v1, reason_v1)
        
        return results_v1, results_v8
    
    async def _measure_single(
        self,
        metric,
        test_case: LLMTestCase,
        pbar: Optional[tqdm] = None
    ) -> Tuple[float, str]:
        """Mede uma única métrica com segurança térmica."""
        async with self.semaphore:
            await self.monitor.ensure_thermal_safety(pbar)
            
            try:
                await asyncio.to_thread(metric.measure, test_case)
                score = float(metric.score)
                reason = self._extract_reason(metric)
                return score, reason
            except Exception as e:
                return 0.0, f"Erro: {str(e)[:100]}"
    
    def _extract_reason(self, metric) -> str:
        """Extrai reason da métrica de forma segura."""
        if hasattr(metric, 'reason') and metric.reason:
            # return str(metric.reason).replace('\n', ' ')[:500]
            return str(metric.reason).replace('\n', ' ')
        
        if hasattr(metric, 'verdicts') and metric.verdicts:
            reasons = []
            for v in metric.verdicts:
                r = getattr(v, 'reason', None)
                if not r and isinstance(v, dict):
                    r = v.get('reason')
                if r:
                    reasons.append(str(r))
            # return " | ".join(reasons)[:500] if reasons else "No reason provided"
            return " | ".join(reasons) if reasons else "No reason provided"
        
        return "No reason available"


# ============================================================================
# ORQUESTRADOR DA AVALIAÇÃO
# ============================================================================

class EvaluationPipeline:
    """Orquestra todo o processo de avaliação."""
    
    def __init__(self):
        self.config = EvalConfig()
        self.stats = EvalStats(total_cases=len(TEST_SUITE))
        self.monitor = HardwareMonitor(self.config)
        
        # Conecta stats ao monitor para contabilizar pausas
        self.monitor.stats = self.stats
        
        self.embedding_cache = EmbeddingCache(
            self.config.cache_dir,
            self.config.embedding_cache_size
        )
        # ⭐ PASSA O CACHE PARA O RAGManager
        self.rag_manager = RAGManager(self.config.base_path, embedding_cache=self.embedding_cache)
        self.evaluator = MetricEvaluator(self.config, self.monitor)
        
        # Prepara saídas
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        self.csv_path = AVALIACAO_DATA / f"METRICAS_{self.timestamp}_CPU_BGE_M3.csv"
        self.txt_path = AVALIACAO_DATA / f"RELATORIO_{self.timestamp}_CPU_BGE_M3.txt"
    
    async def run(self) -> None:
        """Executa avaliação completa."""
        self._print_header()
        
        results_table = []
        start_time = datetime.now()
        
        with open(self.txt_path, 'w', encoding='utf-8') as f_report:
            self._write_report_header(f_report)
            
            pbar = tqdm(TEST_SUITE, desc="Avaliando")
            for idx, test_case in enumerate(pbar):
                # Atualiza progresso
                temp, vram = self.monitor.get_stats()
                pbar.set_postfix({
                    "GPU": f"{temp}°C",
                    "VRAM": f"{vram:.1f}GB",
                    "Case": f"{idx+1}/{self.stats.total_cases}"
                })
                
                # Processa caso
                try:
                    row = await self._process_case(test_case, f_report, pbar)
                    results_table.append(row)
                    
                    # Salva CSV incremental
                    pd.DataFrame(results_table).to_csv(self.csv_path, index=False)
                    
                except Exception as e:
                    error_msg = f"❌ Erro no caso {test_case.get('id', 'unknown')}: {e}"
                    pbar.write(error_msg)
                    f_report.write(f"\n{error_msg}\n")
                    f_report.flush()
                
                self.stats.completed += 1
                gc.collect()
        
        self.stats.total_time_seconds = (datetime.now() - start_time).total_seconds()
        
        # Mostra estatísticas de cache dos RAGs
        cache_stats = self.rag_manager.get_cache_stats()
        if cache_stats:
            print(f"\n📊 Cache stats dos RAGs:")
            for rag_name, stats in cache_stats.items():
                print(f"   {rag_name}: {stats}")
        
        self._print_summary()
        self.monitor.shutdown()
    
    async def _process_case(
        self,
        test_case: Dict,
        f_report,
        pbar: tqdm
    ) -> Dict:
        """Processa um único caso de teste."""
        query = test_case["input"]
        ref_date = test_case.get("reference_date", "2026-03-12")
        
        pbar.write(f"\n📝 Processando: {query[:80]}...")
        
        # Gera respostas
        pbar.write("   🔍 VanillaRAG...")
        res_v1 = await self.rag_manager.vanilla.search(query)
        await self.monitor.ensure_thermal_safety(pbar)
        
        pbar.write("   🔍 TemporalRAG...")
        res_v8 = await self.rag_manager.temporal.search(query, ref_date)
        await self.monitor.ensure_thermal_safety(pbar)
        
        # Prepara casos DeepEval
        case_v1 = LLMTestCase(
            input=query,
            actual_output=res_v1["answer"],
            retrieval_context=res_v1.get("sources", [])[:5],
            expected_output=test_case.get("expected_output"),
            expected_context=test_case.get("expected_context", [])  # ⭐ NOVO
        )

        case_v8 = LLMTestCase(
            input=query,
            actual_output=res_v1["answer"],
            retrieval_context=res_v1.get("sources", [])[:5],
            expected_output=test_case.get("expected_output"),
            expected_context=test_case.get("expected_context", [])  # ⭐ NOVO
        )
        
        # Avalia
        pbar.write("   📊 Avaliando métricas...")
        results_v1, results_v8 = await self.evaluator.evaluate(case_v1, case_v8, pbar)
        
        # Prepara linha do CSV
        temp, vram = self.monitor.get_stats()
        row = {
            "ID": test_case.get('id', 'unknown'),
            "Query": query[:100],
            "GPU_Temp": temp,
            "GPU_VRAM_GB": round(vram, 2)
        }
        
        # Adiciona diagnósticos se disponíveis
        if "diagnostic" in res_v1:
            row["V1_Docs_Retrieved"] = res_v1["diagnostic"].get("num_documents_retrieved", 0)
        if "diagnostic" in res_v8:
            row["V8_Docs_Retrieved"] = res_v8["diagnostic"].get("num_documents_retrieved", 0)
        
        # Log no relatório
        f_report.write(f"\n{'='*60}\n")
        f_report.write(f"ID: {test_case.get('id', 'unknown')} | Query: {query}\n")
        f_report.write(f"GPU: {temp}°C | VRAM: {vram:.2f}GB\n")
        
        for name in self.evaluator.metrics.keys():
            s1, r1 = results_v1[name]
            s8, r8 = results_v8[name]
            row[f"V1_{name}"] = s1
            row[f"V8_{name}"] = s8
            
            f_report.write(f"\n{name}:\n")
            f_report.write(f"  V1: {s1:.3f} | {r1}\n")
            # f_report.write(f"  V1: {s1:.3f} | {r1[:200]}\n")
            f_report.write(f"  V8: {s8:.3f} | {r8}\n")
            # f_report.write(f"  V8: {s8:.3f} | {r8[:200]}\n")
        
        f_report.flush()
        
        return row
    
    def _print_header(self) -> None:
        print("\n" + "=" * 70)
        print("🚀 DUELO TÉCNICO: RAG VANILLA vs RAG TEMPORAL")
        print("📍 BGE-M3 rodando na CPU")
        print("=" * 70)
        print(f"📁 Base: {self.config.base_path.name}")
        print(f"📊 Casos de teste: {self.stats.total_cases}")
        print(f"🧠 Avaliador: {self.config.evaluator_model}")
        print(f"💾 Cache embeddings: {self.embedding_cache.stats()['directory']}")
        print(f"🌡️ Limite térmico: {self.config.max_temp}°C")
        print("-" * 70)
    
    def _write_report_header(self, f) -> None:
        f.write(f"RELATÓRIO DE AVALIAÇÃO RAG\n")
        f.write(f"Data: {self.timestamp}\n")
        f.write(f"Base: {self.config.base_path}\n")
        f.write(f"Avaliador: {self.config.evaluator_model}\n")
        f.write(f"Modo: BGE-M3 na CPU\n")
        f.write("=" * 70 + "\n")
    
    def _print_summary(self) -> None:
        print("\n" + "=" * 70)
        print("✅ AVALIAÇÃO CONCLUÍDA")
        print("=" * 70)
        print(f"   Casos processados: {self.stats.completed}/{self.stats.total_cases}")
        print(f"   Tempo total: {self.stats.total_time_seconds/60:.1f} minutos")
        print(f"   Cache embeddings: {self.embedding_cache.stats()['size']} queries")
        print(f"   Pausas térmicas: {self.stats.thermal_pauses}")
        print(f"\n📊 Resultados:")
        print(f"   CSV: {self.csv_path}")
        print(f"   Relatório: {self.txt_path}")
        print("\n💡 Dica: BGE-M3 está rodando na CPU, economizando VRAM")
        print("   para outros processos!")


# ============================================================================
# PONTO DE ENTRADA
# ============================================================================

async def main():
    print("\n" + "=" * 70)
    print("🔧 INICIANDO AVALIAÇÃO - BGE-M3 na CPU")
    print("=" * 70)
    
    # Verifica se os arquivos existem
    from core.paths import VETORIZATION_DATA
    
    base_path = VETORIZATION_DATA / 'base_conhecimento_multilingueV7.json'
    if not base_path.exists():
        print(f"❌ Base não encontrada: {base_path}")
        print("   Verifique o caminho ou ajuste o EvalConfig.base_path")
        return
    
    print(f"✅ Base encontrada: {base_path}")
    
    pipeline = EvaluationPipeline()
    await pipeline.run()


if __name__ == "__main__":
    asyncio.run(main())