#!/usr/bin/env python3
"""
UNIFIED EVALUATION SCRIPT: V1 vs V9 (Mixed Fallback Framework Edition)
Fully customized to validate the rules of the second prompt generation.
"""

import asyncio
import hashlib
import json
import pickle
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

import numpy as np
import pandas as pd
from deepeval import evaluate
from deepeval.dataset import EvaluationDataset
from deepeval.test_case import LLMTestCase
from deepeval.metrics import (
    ContextualPrecisionMetric,
    ContextualRelevancyMetric,
    ContextualRecallMetric,
    FaithfulnessMetric,
    AnswerRelevancyMetric,
    GEval
)
from deepeval.evaluate import AsyncConfig, ErrorConfig


# Custom external modules
from core.paths import VALIDACAO_SCRIPT, AVALIACAO_SCRIPT, VETORIZATION_DATA, AVALIACAO_DATA
from dataset_avaliacaoV4 import TEST_SUITE

for path in [VALIDACAO_SCRIPT, AVALIACAO_SCRIPT]:
    if str(path) not in sys.path:
        sys.path.append(str(path))

from RAG_BaseLineV2 import VanillaRAG
from RAG_Temporal_V9_4 import SpecialistTimeAwareRAG
from custom_evaluatorV3 import OllamaEvaluator


# ============================================================================
# EVAL CONFIG & CACHE
# ============================================================================

@dataclass
class EvalConfig:
    base_path: Path = VETORIZATION_DATA / 'base_conhecimento_multilingueV9.json'
    evaluator_model: str = "qwen3.5:9b"
    cache_dir: Path = AVALIACAO_DATA / "cache"
    embedding_cache_size: int = 1000
    vanilla_use_expansion: bool = False
    temporal_use_expansion: bool = True
    temporal_variant: str = "V9_HYBRID_MIXED_AUDITOR"
    model_name: str = "mistral:7b-instruct"
    temperature: float = 0.0
    search_top_k: int = 20
    
    @property
    def timestamp(self) -> str:
        return datetime.now().strftime("%Y%m%d_%H%M")

    @property
    def output_dir(self) -> Path:
        dir_path = AVALIACAO_DATA / "resultados"
        dir_path.mkdir(parents=True, exist_ok=True)
        return dir_path


class EmbeddingCache:
    def __init__(self, cache_dir: Path, max_size: int = 1000):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_size = max_size
        self._cache: Dict[str, np.ndarray] = {}
        self._load_existing()

    def _get_key(self, query: str) -> str:
        return hashlib.md5(query.encode()).hexdigest()

    def _load_existing(self) -> None:
        for path in self.cache_dir.glob("*.pkl"):
            if len(self._cache) >= self.max_size: break
            try:
                with open(path, 'rb') as f:
                    self._cache[path.stem] = pickle.load(f)
            except Exception: pass

    def get(self, query: str) -> Optional[np.ndarray]:
        key = self._get_key(query)
        return self._cache[key].copy() if key in self._cache else None

    def set(self, query: str, embedding: np.ndarray) -> None:
        key = self._get_key(query)
        if len(self._cache) >= self.max_size:
            oldest = next(iter(self._cache))
            del self._cache[oldest]
            (self.cache_dir / f"{oldest}.pkl").unlink(missing_ok=True)
        self._cache[key] = embedding.copy()
        try:
            with open(self.cache_dir / f"{key}.pkl", 'wb') as f:
                pickle.dump(embedding, f)
        except IOError: pass


# ============================================================================
# G-EVAL FOR MIXED GUARDRAILS (SECOND PROMPT SPECIFICATION)
# ============================================================================

def create_native_metrics(evaluator: OllamaEvaluator) -> List[Any]:
    return [
        FaithfulnessMetric(threshold=0.85, model=evaluator, include_reason=True),
        AnswerRelevancyMetric(threshold=0.8, model=evaluator, include_reason=True),
        ContextualRelevancyMetric(threshold=0.8, model=evaluator, include_reason=True),
        ContextualPrecisionMetric(threshold=0.8, model=evaluator, include_reason=True),
        ContextualRecallMetric(threshold=0.8, model=evaluator, include_reason=True)
    ]

def create_mixed_behavioral_geval(evaluator: OllamaEvaluator, version: str) -> GEval:
    """
    Métrica G-Eval customizada especificamente para validar as regras do segundo prompt.
    Analisa a transparência do fallback e as restrições de formatação de tags/auditoria.
    """
    if version == "V9":
        criteria = (
            "Evaluate response based on V9_HYBRID_MIXED_AUDITOR guidelines:\n"
            "1. FALLBACK RULE: For a specific SKU query, if RAG is missing, the model may use INTERNAL knowledge, "
            "   but it MUST clearly state that external documentation was not found before providing the numbers.\n"
            "2. SERIES LOCK: For a generic series query (e.g., Nitro 5), the model MUST NOT answer; it must request the SKU.\n"
            "3. MANDATORY AUDIT: The response MUST contain an 'AUDIT:' block tagging sources as [RAG:id] or [INTERNAL:domain:YYYY].\n"
            "4. ANSWER CLEANLINESS: The 'ANSWER:' block itself must be clear of any raw source tags like [RAG] or [INTERNAL]."
        )
    else:  # V1
        criteria = (
            "Evaluate response based on V1_VANILLA_MIXED_EQUITABLE guidelines:\n"
            "1. FALLBACK RULE: For a specific SKU query, if external docs are missing, the model may use INTERNAL knowledge, "
            "   but it MUST explicitely state that external documentation was not found first.\n"
            "2. SERIES LOCK: For a generic series query, it must strictly ask for the specific SKU and refuse to answer specs.\n"
            "3. STRICT FORMATTING: The output MUST NOT contain any audit section, tags like [RAG] or [INTERNAL], or block headers. "
            "   It must be a clean, natural customer-facing response. Any special format block drops the score to 0."
        )

    return GEval(
        name=f"Mixed Guardrails Audit ({version})",
        model=evaluator,
        criteria=criteria,
        evaluation_steps=[
            "Determine the query classification (SKU, Technical Concept, Comparison, or Series).",
            "If it is a Series query, verify if the model successfully refused to answer specs and requested the SKU.",
            "If it is a SKU query with missing RAG, verify if the model stated that external docs were not found before providing fallback specs.",
            "Inspect formatting: V9 must have an AUDIT section; V1 must be completely bare of tags, labels, or audit structures."
        ],
        threshold=0.8
    )


# ============================================================================
# RAG MANAGER & ORCHESTRATION
# ============================================================================

class ComparativeRAGManager:
    def __init__(self, base_path: Path, config: EvalConfig, embedding_cache=None):
        self.base_path = base_path
        self.config = config
        self.embedding_cache = embedding_cache
        self._vanilla: Optional[VanillaRAG] = None
        self._temporal: Optional[SpecialistTimeAwareRAG] = None

    @property
    def vanilla(self) -> VanillaRAG:
        if self._vanilla is None:
            self._vanilla = VanillaRAG(self.base_path, embedding_cache=self.embedding_cache, use_expansion=self.config.vanilla_use_expansion)
        return self._vanilla

    @property
    def temporal(self) -> SpecialistTimeAwareRAG:
        if self._temporal is None:
            self._temporal = SpecialistTimeAwareRAG(self.base_path, variant_name=self.config.temporal_variant, embedding_cache=self.embedding_cache, use_expansion=self.config.temporal_use_expansion)
            self._temporal.current_model = self.config.model_name
            self._temporal.temperature = self.config.temperature
            self._temporal.search_top_k = self.config.search_top_k
        return self._temporal

    
    async def generate_test_cases(self) -> Tuple[List[LLMTestCase], List[LLMTestCase]]:
        v1_cases, v9_cases = [], []
        print(f"🔍 Ingerindo {len(TEST_SUITE)} casos de teste nos RAGs Mixed...")
        
        for tc in TEST_SUITE:
            query = tc["input"]
            ref_date = tc.get("reference_date", "2026-03-12")
            
            # CORREÇÃO: Removido o asyncio.to_thread, pois as funções já são async def
            v1_task = asyncio.create_task(self.vanilla.search(query))
            v9_task = asyncio.create_task(self.temporal.search(query, ref_date))
            
            res_v1, res_v9 = await asyncio.gather(v1_task, v9_task)
            
            meta = {"id": tc["id"], "test_type": tc.get("test_type", "traditional")}
            
            v1_cases.append(LLMTestCase(
                input=query, actual_output=res_v1["answer"],
                retrieval_context=res_v1.get("sources", [])[:5],
                expected_output=tc.get("expected_output"), 
                metadata=meta
            ))
            v9_cases.append(LLMTestCase(
                input=query, actual_output=res_v9["answer"],
                retrieval_context=res_v9.get("sources", [])[:5],
                expected_output=tc.get("expected_output"), 
                metadata=meta
            ))
            
        return v1_cases, v9_cases

class NativeComparativePipeline:
    def __init__(self):
        self.config = EvalConfig()
        self.cache = EmbeddingCache(self.config.cache_dir, self.config.embedding_cache_size)
        self.rag_manager = ComparativeRAGManager(self.config.base_path, self.config, self.cache)
        self.evaluator_v1 = OllamaEvaluator(model_name=self.config.evaluator_model, prompt_version="V1")
        self.evaluator_v9 = OllamaEvaluator(model_name=self.config.evaluator_model, prompt_version="V9")

    async def run(self):
        v1_cases, v9_cases = await self.rag_manager.generate_test_cases()
        
        # Instanciação dos contêineres de dados
        d_v1_trad = EvaluationDataset()
        d_v1_trad.test_cases = [c for c in v1_cases if c.metadata["test_type"] == "traditional"]
        
        d_v1_behav = EvaluationDataset()
        d_v1_behav.test_cases = [c for c in v1_cases if c.metadata["test_type"] == "behavioral"]
        
        d_v9_trad = EvaluationDataset()
        d_v9_trad.test_cases = [c for c in v9_cases if c.metadata["test_type"] == "traditional"]
        
        d_v9_behav = EvaluationDataset()
        d_v9_behav.test_cases = [c for c in v9_cases if c.metadata["test_type"] == "behavioral"]

        # Listas para consolidar os objetos de resultado finais
        res_v1_trad, res_v1_behav = [], []
        res_v9_trad, res_v9_behav = [], []

        # ====================================================================
        # EXECUÇÃO DO RAG V1 (VANILLA)
        # ====================================================================
        if d_v1_trad.test_cases:
            print("\n🏆 Avaliando V1 MIXED Tradicional (Métrica por Métrica)...")
            # Força o isolamento total de hardware avaliando uma métrica de cada vez
            for metric in create_native_metrics(self.evaluator_v1):
                print(f" 🎯 Rodando {metric.__class__.__name__} de forma linear...")
                batch_res = evaluate(d_v1_trad.test_cases, [metric], async_config=AsyncConfig(max_concurrent=1))
                if not res_v1_trad:
                    res_v1_trad = batch_res
                else:
                    # Faz o merge dos resultados das métricas no objeto correto
                    for idx, single_res in enumerate(batch_res):
                        res_v1_trad[idx].metrics_results.extend(single_res.metrics_results)

        if d_v1_behav.test_cases:
            print("\n🏆 Avaliando V1 MIXED Comportamental (GEval)...")
            geval_v1 = create_mixed_behavioral_geval(self.evaluator_v1, "V1")
            res_v1_behav = evaluate(d_v1_behav.test_cases, [geval_v1], async_config=AsyncConfig(max_concurrent=1))

        # ====================================================================
        # EXECUÇÃO DO RAG V9 (TEMPORAL)
        # ====================================================================
        if d_v9_trad.test_cases:
            print("\n🏆 Avaliando V9 MIXED Tradicional (Métrica por Métrica)...")
            for metric in create_native_metrics(self.evaluator_v9):
                print(f" 🎯 Rodando {metric.__class__.__name__} de forma linear...")
                batch_res = evaluate(d_v9_trad.test_cases, [metric], async_config=AsyncConfig(max_concurrent=1))
                if not res_v9_trad:
                    res_v9_trad = batch_res
                else:
                    # Faz o merge dos resultados das métricas no objeto correto
                    for idx, single_res in enumerate(batch_res):
                        res_v9_trad[idx].metrics_results.extend(single_res.metrics_results)

        if d_v9_behav.test_cases:
            print("\n🏆 Avaliando V9 MIXED Comportamental (GEval)...")
            geval_v9 = create_mixed_behavioral_geval(self.evaluator_v9, "V9")
            res_v9_behav = evaluate(d_v9_behav.test_cases, [geval_v9], async_config=AsyncConfig(max_concurrent=1))

        # Compila os relatórios unificados no DataFrame e exporta para CSV
        self._build_and_save_reports(res_v1_trad, res_v1_behav, res_v9_trad, res_v9_behav)

    def _build_and_save_reports(self, r1_t, r1_b, r9_t, r9_b):
        rows = []
        
        def process_results(results, version_prefix):
            for test_result in results:
                tc = test_result.test_case
                row_id = tc.metadata["id"]  # Alterado aqui de additional_metadata para metadata
                
                existing = next((r for r in rows if r["ID"] == row_id), None)
                if not existing:
                    existing = {"ID": row_id, "Query": tc.input, "Type": tc.metadata["test_type"]} # Alterado aqui
                    rows.append(existing)
                
                existing[f"{version_prefix}_Answer"] = tc.actual_output
                for metric_obj in test_result.metrics_results:
                    name = metric_obj.name.replace(" ", "_")
                    existing[f"{version_prefix}_{name}_Score"] = metric_obj.score
                    existing[f"{version_prefix}_{name}_Reason"] = metric_obj.reason

        process_results(r1_t, "V1")
        process_results(r1_b, "V1")
        process_results(r9_t, "V9")
        process_results(r9_b, "V9")

        df = pd.DataFrame(rows)
        csv_out = self.config.output_dir / f"DEEPEVAL_MIXED_NATIVE_COMPARATIVE_{self.config.timestamp}.csv"
        df.to_csv(csv_out, index=False)
        
        print(f"\n🚀 Pipeline adaptado para os Prompts MIXED concluído.")
        print(f"📊 Dados salvos em: {csv_out}")


if __name__ == "__main__":
    asyncio.run(NativeComparativePipeline().run())