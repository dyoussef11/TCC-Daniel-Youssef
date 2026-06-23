#!/usr/bin/env python3
"""
UNIFIED EVALUATION SCRIPT: V1 vs V9 (Mixed Fallback Framework Edition) - V5 COMPATIBLE
Fully customized to validate the rules of the second prompt generation without format bias.
Supports command-line arguments for judge and generator models.
Generates CSV, TXT, and Markdown reports natively from consolidated loop data.

DEBUG MODE: roda apenas 1 caso (o primeiro) para depuração.
COM PLANILHA DE CÁLCULOS PASSO A PASSO (Total, Positivos, Fórmula e operação)
E VERBOSE LOGS COMPLETOS NO TXT
"""

import os

# Configura o timeout por caso de teste para 20 minutos (2400 segundos)
os.environ["DEEPEVAL_PER_TASK_TIMEOUT_SECONDS_OVERRIDE"] = "2400"

# Configura o timeout de cada tentativa individual ao Ollama para 10 minutos (300 segundos)
os.environ["DEEPEVAL_PER_ATTEMPT_TIMEOUT_SECONDS_OVERRIDE"] = "600"

import asyncio
import gc
import hashlib
import json
import pickle
import sys
import time
import argparse
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from deepeval.metrics.g_eval import Rubric

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
from deepeval.test_case import SingleTurnParams

# Custom external modules
from core.paths import VALIDACAO_SCRIPT, AVALIACAO_SCRIPT, VETORIZATION_DATA, AVALIACAO_DATA
from dataset_avaliacaoV4 import TEST_SUITE

for path in [VALIDACAO_SCRIPT, AVALIACAO_SCRIPT]:
    if str(path) not in sys.path:
        sys.path.append(str(path))

from RAG_BaseLineV2 import VanillaRAG
from RAG_Temporal_V9_3 import SpecialistTimeAwareRAG
from custom_evaluatorV4 import OllamaEvaluator


# ========================== DEBUG CONFIG ====================================
DEBUG_ONE_CASE = False  # <-- Se True, roda apenas o primeiro caso de TEST_SUITE
# ============================================================================


# ============================================================================
# FUNÇÃO PARA PARSEAR VERBOSE LOG E EXTRAIR CONTAGENS
# ============================================================================

def parse_verbose_log(verbose_text: str) -> Dict[str, int]:
    """
    Extrai o número total de itens avaliados e quantos foram positivos (veredito 'yes')
    do verbose log de métricas do DeepEval.
    Retorna um dicionário com {'total': int, 'positive': int}.
    Se não conseguir parsear, retorna {'total': 0, 'positive': 0}.
    """
    if not verbose_text:
        return {'total': 0, 'positive': 0}
    
    # Estratégia 1: procurar por padrão JSON de veredictos
    total_yes = len(re.findall(r'"verdict"\s*:\s*"yes"', verbose_text, re.IGNORECASE))
    total_no = len(re.findall(r'"verdict"\s*:\s*"no"', verbose_text, re.IGNORECASE))
    total = total_yes + total_no
    
    # Estratégia 2: se não encontrou no formato JSON, procurar por "yes"/"no" isolados
    if total == 0:
        yes_matches = re.findall(r'verdict\s*[:=]\s*yes', verbose_text, re.IGNORECASE)
        no_matches = re.findall(r'verdict\s*[:=]\s*no', verbose_text, re.IGNORECASE)
        total_yes = len(yes_matches)
        total_no = len(no_matches)
        total = total_yes + total_no
    
    # Estratégia 3: fallback
    if total == 0:
        yes_matches = re.findall(r'"yes"', verbose_text)
        no_matches = re.findall(r'"no"', verbose_text)
        total_yes = len(yes_matches)
        total_no = len(no_matches)
        total = total_yes + total_no
    
    return {'total': total, 'positive': total_yes}


# ============================================================================
# EVAL CONFIG & CACHE
# ============================================================================

@dataclass
class EvalConfig:
    base_path: Path = VETORIZATION_DATA / 'base_conhecimento_multilingueV9.json'
    evaluator_model: str = "qwen3:4b-instruct"
    cache_dir: Path = AVALIACAO_DATA / "cache"
    embedding_cache_size: int = 1000
    vanilla_use_expansion: bool = False
    temporal_use_expansion: bool = False
    temporal_variant: str = "V9_HYBRID_MIXED_AUDITOR"
    model_name: str = "phi3.5:latest"
    temperature: float = 0.0
    search_top_k: int = 50

    @property
    def timestamp(self) -> str:
        return datetime.now().strftime("%Y%m%d_%H%M")

    @property
    def output_dir(self) -> Path:
        dir_path = AVALIACAO_DATA / "testes_com_modelos_diferentes" / "sem_repeticao"
        dir_path.mkdir(parents=True, exist_ok=True)
        return dir_path

    @classmethod
    def from_args(cls, args):
        return cls(
            evaluator_model=args.judge_model,
            model_name=args.generator_model
        )

    @property
    def combination_id(self) -> str:
        judge = self.evaluator_model.replace(":", "_")
        gen = self.model_name.replace(":", "_")
        return f"J_{judge}_G_{gen}"


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
# NATIVE METRICS FACTORY & G-EVAL GUARDRAILS
# ============================================================================

def create_native_metrics(evaluator: OllamaEvaluator) -> List[Any]:
    return [
        FaithfulnessMetric(threshold=0.80, model=evaluator, include_reason=True, verbose_mode=True),
        AnswerRelevancyMetric(threshold=0.85, model=evaluator, include_reason=True, verbose_mode=True),
        ContextualRelevancyMetric(threshold=0.8, model=evaluator, include_reason=True, verbose_mode=True),
        ContextualPrecisionMetric(threshold=0.8, model=evaluator, include_reason=True, verbose_mode=True),
        ContextualRecallMetric(threshold=0.8, model=evaluator, include_reason=True, verbose_mode=True)
    ]

def create_unified_behavioral_geval(evaluator: OllamaEvaluator) -> GEval:
    criteria = (
        "Evaluate compliance with mixed operational guardrails (SKU presence, series queries, missing data, and output cleanliness)."
    )
    rubric = [
        Rubric(
            score_range=(0, 3),
            expected_outcome=(
                "Critical Violation: Provided specific hardware specs for a generic SERIES query, OR "
                "failed to state that external documentation was missing for an unknown SKU, OR "
                "polluted the text output with forbidden system tags/headers like [RAG], [INTERNAL], 'AUDIT:', or 'ANSWER:'."
            )
        ),
        Rubric(
            score_range=(4, 6),
            expected_outcome=(
                "Partial Compliance: Kept the output clean without tags, but violated one of the routing logic rules "
                "(e.g., provided partial specs for a line series instead of demanding the SKU)."
            )
        ),
        Rubric(
            score_range=(7, 10),
            expected_outcome=(
                "Full Compliance: Perfect execution. Detected query type accurately, triggered the required disclaimer "
                "for missing SKUs, correctly refused specs for series queries, and delivered a completely clean, natural response paragraph."
            )
        )
    ]
    return GEval(
        name="Mixed Guardrails (Unified)",
        model=evaluator,
        criteria=criteria,
        rubric=rubric,
        evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT, SingleTurnParams.RETRIEVAL_CONTEXT],
        evaluation_steps=[
            "Determine query type (SKU, series, comparison, general).",
            "Check compliance with the specific operational rule for that type.",
            "Verify no forbidden raw tags or system processing blocks pollute the text output."
        ],
        threshold=0.8,
        verbose_mode=True
    )

def create_temporal_geval(evaluator: OllamaEvaluator) -> GEval:
    criteria = (
        "Evaluate response compliance with temporal reasoning rules and specification accuracy across generations."
    )
    rubric = [
        Rubric(
            score_range=(0, 3),
            expected_outcome=(
                "Temporal Failure: Invented specifications for future dates (2026+), hallucinated hardware versions, "
                "or completely mixed up historical specs (e.g., stating a DDR4 model uses DDR5 based on outdated/incorrect documentation)."
            )
        ),
        Rubric(
            score_range=(4, 6),
            expected_outcome=(
                "Minor Temporal Inconsistency: Preferred older documents over newer ones when both were present in context, "
                "but did not boldly invent non-existent versions or future hardware."
            )
        ),
        Rubric(
            score_range=(7, 10),
            expected_outcome=(
                "Chronological Excellence: Correctly respected the reference date, handled future-dated queries with strict "
                "caution ('not available'/'unconfirmed'), and accurately separated component generations (DDR4 vs DDR5)."
            )
        )
    ]
    return GEval(
        name="Temporal Consistency",
        model=evaluator,
        criteria=criteria,
        rubric=rubric,
        evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT, SingleTurnParams.RETRIEVAL_CONTEXT],
        evaluation_steps=[
            "Check if the response uses the appropriate document recency based on the reference date.",
            "Verify that future-dated queries are handled with caution (no speculation).",
            "Ensure that comparisons respect chronological evolution of specifications.",
            "Penalize hallucinated versions or specs that contradict the temporal context."
        ],
        threshold=0.8,
        verbose_mode=True
    )

def create_strict_temporal_reranking_geval(evaluator: OllamaEvaluator) -> GEval:
    criteria = (
        "Analyze if the engine suffered from temporal obsolescence by favoring outdated context documents over the chronological requested timeline."
    )
    rubric = [
        Rubric(
            score_range=(0, 4),
            expected_outcome=(
                "Obsolete Output: The response fell victim to a lack of temporal awareness. It incorporated features, "
                "components, or BIOS versions that were already replaced or obsolete by the time of the reference date, "
                "meaning it favored older documentation present in the context (typical vanilla vector search error)."
            )
        ),
        Rubric(
            score_range=(5, 10),
            expected_outcome=(
                "Dynamic Recency Alignment: The response shows absolute chronological alignment. It successfully "
                "deprioritized obsolete data and strictly used current/newer specifications relevant to the anchor year."
            )
        )
    ]
    return GEval(
        name="Temporal Reranking Enforcement",
        model=evaluator,
        criteria=criteria,
        rubric=rubric,
        evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT, SingleTurnParams.RETRIEVAL_CONTEXT],
        evaluation_steps=[
            "Identify the reference date or chronological anchor in the user input.",
            "Check if the actual output used specifications that are accurate only for past contexts.",
            "Determine if the system failed to deprioritize obsolete technical documentation."
        ],
        threshold=0.8,
        verbose_mode=True
    )

def create_intelligent_fallback_geval(evaluator: OllamaEvaluator) -> GEval:
    criteria = (
        "Evaluate the response's defensive fallback triggering and resistance to context-driven hallucinations."
    )
    rubric = [
        Rubric(
            score_range=(0, 3),
            expected_outcome=(
                "Hallucinated Mapping: The response hallucinated or forcefully mapped specs from a completely different "
                "product line just because it appeared in the retrieval context, OR gave precise hardware specs for an unknown SKU/Series."
            )
        ),
        Rubric(
            score_range=(4, 6),
            expected_outcome=(
                "Insufficient Disclaimer: Attempted a generic fallback response but forgot to explicitly state the mandatory "
                "disclaimer that no current official documentation was found for that specific SKU."
            )
        ),
        Rubric(
            score_range=(7, 10),
            expected_outcome=(
                "Smart Defense: Perfect fallback activation. For missing/unknown data, it openly admitted the lack of "
                "external documentation first, and then provided safe, generic architectural constraints using clean internal knowledge."
            )
        )
    ]
    return GEval(
        name="Smart Fallback Triggering",
        model=evaluator,
        criteria=criteria,
        rubric=rubric,
        evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT, SingleTurnParams.RETRIEVAL_CONTEXT],
        evaluation_steps=[
            "Identify if the query is a Series query, an unknown SKU, or a future-dated product.",
            "Verify if the response successfully triggered a fallback/disclaimer or a request for clarification.",
            "Penalize with 0.0 if the response boldly states specifications that belong to a generic or different model."
        ],
        threshold=0.8,
        verbose_mode=True
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
        if DEBUG_ONE_CASE:
            test_suite_iter = TEST_SUITE[:1]
            print(f"🐞 DEBUG: rodando apenas 1 caso (primeiro da lista)")
        else:
            test_suite_iter = TEST_SUITE

        v1_cases, v9_cases = [], []
        print(f"🔍 Ingerindo {len(test_suite_iter)} caso(s) de teste nos RAGs Mixed...")
        
        for tc in test_suite_iter:
            query = tc["input"]
            ref_date = tc.get("reference_date", "2026-03-12")
            
            print(f"   ➤ Query: {query[:60]}...")
            v1_task = asyncio.create_task(self.vanilla.search(query))
            v9_task = asyncio.create_task(self.temporal.search(query, ref_date))
            res_v1, res_v9 = await asyncio.gather(v1_task, v9_task)
            
            print(f"   ➤ V1 answer length: {len(res_v1['answer'])}")
            print(f"   ➤ V9 answer length: {len(res_v9['answer'])}")
            
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


# ============================================================================
# MAIN EVALUATION PIPELINE
# ============================================================================

class NativeComparativePipeline:
    def __init__(self):
        self.config = EvalConfig()
        self.cache = EmbeddingCache(self.config.cache_dir, self.config.embedding_cache_size)
        self.rag_manager = ComparativeRAGManager(self.config.base_path, self.config, self.cache)
        self.evaluator_v1 = OllamaEvaluator(model_name=self.config.evaluator_model, prompt_version="V1")
        self.evaluator_v9 = OllamaEvaluator(model_name=self.config.evaluator_model, prompt_version="V9")
        
        self.v1_cases_backup: List[LLMTestCase] = []
        self.v9_cases_backup: List[LLMTestCase] = []

    async def run(self):
        v1_cases, v9_cases = await self.rag_manager.generate_test_cases()

        self.v1_cases_backup = v1_cases
        self.v9_cases_backup = v9_cases

        print(f"V1 cases: {len(v1_cases)}")
        print(f"V9 cases: {len(v9_cases)}")
        
        # Separar por tipo
        d_v1_trad = EvaluationDataset()
        d_v1_trad.test_cases = [c for c in v1_cases if c.metadata["test_type"] == "traditional"]
        d_v1_behav = EvaluationDataset()
        d_v1_behav.test_cases = [c for c in v1_cases if c.metadata["test_type"] == "behavioral"]
        d_v1_temp = EvaluationDataset()
        d_v1_temp.test_cases = [c for c in v1_cases if c.metadata["test_type"] == "temporal"]

        d_v9_trad = EvaluationDataset()
        d_v9_trad.test_cases = [c for c in v9_cases if c.metadata["test_type"] == "traditional"]
        d_v9_behav = EvaluationDataset()
        d_v9_behav.test_cases = [c for c in v9_cases if c.metadata["test_type"] == "behavioral"]
        d_v9_temp = EvaluationDataset()
        d_v9_temp.test_cases = [c for c in v9_cases if c.metadata["test_type"] == "temporal"]

        print(f"V9 trad: {len(d_v9_trad.test_cases)}")
        print(f"V9 behav: {len(d_v9_behav.test_cases)}")
        print(f"V9 temp:  {len(d_v9_temp.test_cases)}")

        res_v1_trad, res_v1_behav, res_v1_temp = [], [], []
        res_v9_trad, res_v9_behav, res_v9_temp = [], [], []

        # ====================================================================
        # AVALIAÇÃO RAG V1
        # ====================================================================
        if d_v1_trad.test_cases:
            print("\n🏆 Avaliando V1 MIXED Tradicional (Métrica por Métrica)...")
            for metric in create_native_metrics(self.evaluator_v1):
                print(f" 🎯 Rodando {metric.__class__.__name__} de forma linear...")
                batch_res = evaluate(d_v1_trad.test_cases, [metric], async_config=AsyncConfig(max_concurrent=1))
                
                if not res_v1_trad:
                    res_v1_trad = batch_res.test_results
                else:
                    for idx, single_res in enumerate(batch_res.test_results):
                        res_v1_trad[idx].metrics_data.extend(single_res.metrics_data)
                        if not single_res.success:
                            res_v1_trad[idx].success = False

        if d_v1_behav.test_cases:
            print("\n🏆 Avaliando V1 MIXED Comportamental (GEval Unificado)...")
            geval_v1 = create_unified_behavioral_geval(self.evaluator_v1)
            geval_rerank_v1 = create_strict_temporal_reranking_geval(self.evaluator_v1)
            geval_fallback_v1 = create_intelligent_fallback_geval(self.evaluator_v1)
            
            batch_res = evaluate(
                d_v1_behav.test_cases,
                [geval_v1, geval_rerank_v1, geval_fallback_v1],
                async_config=AsyncConfig(max_concurrent=1)
            )
            res_v1_behav = batch_res.test_results

        if d_v1_temp.test_cases:
            print("\n⏳ Avaliando V1 MIXED Temporal (GEval Temporal)...")
            geval_temp_v1 = create_temporal_geval(self.evaluator_v1)
            batch_res = evaluate(d_v1_temp.test_cases, [geval_temp_v1], async_config=AsyncConfig(max_concurrent=1))
            res_v1_temp = batch_res.test_results

        # ====================================================================
        # AVALIAÇÃO RAG V9
        # ====================================================================
        if d_v9_trad.test_cases:
            print("\n🏆 Avaliando V9 MIXED Tradicional (Métrica por Métrica)...")
            for metric in create_native_metrics(self.evaluator_v9):
                print(f" 🎯 Rodando {metric.__class__.__name__} de forma linear...")
                batch_res = evaluate(d_v9_trad.test_cases, [metric], async_config=AsyncConfig(max_concurrent=1))
                
                if not res_v9_trad:
                    res_v9_trad = batch_res.test_results
                else:
                    for idx, single_res in enumerate(batch_res.test_results):
                        res_v9_trad[idx].metrics_data.extend(single_res.metrics_data)
                        if not single_res.success:
                            res_v9_trad[idx].success = False
            print(f"   ✅ V9 tradicional avaliado. Nº resultados: {len(res_v9_trad)}")
            if res_v9_trad:
                print(f"   📊 Primeiro resultado tem {len(res_v9_trad[0].metrics_data)} métricas")
                for m in res_v9_trad[0].metrics_data:
                    print(f"      - {m.name}: {m.score}")

        if d_v9_behav.test_cases:
            print("\n🏆 Avaliando V9 MIXED Comportamental (GEval Unificado)...")
            geval_v9 = create_unified_behavioral_geval(self.evaluator_v9)
            geval_rerank_v9 = create_strict_temporal_reranking_geval(self.evaluator_v9)
            geval_fallback_v9 = create_intelligent_fallback_geval(self.evaluator_v9)
            
            batch_res = evaluate(
                d_v9_behav.test_cases,
                [geval_v9, geval_rerank_v9, geval_fallback_v9],
                async_config=AsyncConfig(max_concurrent=1)
            )
            res_v9_behav = batch_res.test_results
            print(f"   ✅ V9 comportamental avaliado. Nº resultados: {len(res_v9_behav)}")

        if d_v9_temp.test_cases:
            print("\n⏳ Avaliando V9 MIXED Temporal (GEval Temporal)...")
            geval_temp_v9 = create_temporal_geval(self.evaluator_v9)
            batch_res = evaluate(d_v9_temp.test_cases, [geval_temp_v9], async_config=AsyncConfig(max_concurrent=1))
            res_v9_temp = batch_res.test_results
            print(f"   ✅ V9 temporal avaliado. Nº resultados: {len(res_v9_temp)}")

        print("\n🔎 RESUMO DOS RESULTADOS V9:")
        print(f"   res_v9_trad: {len(res_v9_trad)} itens")
        print(f"   res_v9_behav: {len(res_v9_behav)} itens")
        print(f"   res_v9_temp: {len(res_v9_temp)} itens")

        self._build_and_save_reports(res_v1_trad, res_v1_behav, res_v1_temp,
                                     res_v9_trad, res_v9_behav, res_v9_temp)

    def _build_and_save_reports(self, r1_t, r1_b, r1_temp, r9_t, r9_b, r9_temp):
        rows = []
        
        v1_t_ref = [c for c in self.v1_cases_backup if c.metadata["test_type"] == "traditional"]
        v1_b_ref = [c for c in self.v1_cases_backup if c.metadata["test_type"] == "behavioral"]
        v1_temp_ref = [c for c in self.v1_cases_backup if c.metadata["test_type"] == "temporal"]
        v9_t_ref = [c for c in self.v9_cases_backup if c.metadata["test_type"] == "traditional"]
        v9_b_ref = [c for c in self.v9_cases_backup if c.metadata["test_type"] == "behavioral"]
        v9_temp_ref = [c for c in self.v9_cases_backup if c.metadata["test_type"] == "temporal"]

        print("\n📋 REFERÊNCIAS PARA PROCESSAMENTO:")
        print(f"   v1_t_ref: {len(v1_t_ref)} | v1_b_ref: {len(v1_b_ref)} | v1_temp_ref: {len(v1_temp_ref)}")
        print(f"   v9_t_ref: {len(v9_t_ref)} | v9_b_ref: {len(v9_b_ref)} | v9_temp_ref: {len(v9_temp_ref)}")

        def process_results(results, version_prefix, source_cases_ref):
            print(f"\n🔧 process_results({version_prefix}) - results={len(results)}, source_cases={len(source_cases_ref)}")
            for idx, test_result in enumerate(results):
                print(f"   Processando resultado {idx} para {version_prefix}")
                if idx < len(source_cases_ref):
                    tc = source_cases_ref[idx]
                else:
                    tc = getattr(test_result, 'test_case', None)
                    if tc is None:
                        print(f"      ⚠️ Sem caso de referência para índice {idx}, pulando...")
                        continue
                
                row_id = tc.metadata["id"] if (tc and tc.metadata) else f"TC_{idx}"
                query_text = tc.input if tc else "Unknown"
                test_type = tc.metadata["test_type"] if (tc and tc.metadata) else "traditional"
                actual_output = tc.actual_output if tc else ""

                existing = next((r for r in rows if r["ID"] == row_id), None)
                if not existing:
                    existing = {"ID": row_id, "Query": query_text, "Test_Type": test_type}
                    rows.append(existing)
                
                existing[f"{version_prefix}_Answer"] = actual_output
                
                metrics_list = getattr(test_result, 'metrics_data', [])
                print(f"      Métricas encontradas: {len(metrics_list)}")
                for metric_obj in metrics_list:
                    # Mapeamento de nomes
                    original_name = metric_obj.name
                    if "Mixed_Guardrails" in original_name or "Behavioral" in original_name:
                        name = "Behavioral_Guardrails"
                    elif "Temporal_Consistency" in original_name:
                        name = "Temporal_Consistency"
                    elif "Temporal Reranking" in original_name or "Reranking" in original_name:
                        name = "Temporal_Reranking"
                    elif "Smart Fallback" in original_name or "Fallback" in original_name:
                        name = "Intelligent_Fallback"
                    else:
                        name = original_name.replace(" ", "_")
                    
                    score_key = f"{version_prefix}_{name}_Score"
                    reason_key = f"{version_prefix}_{name}_Reason"
                    verbose_key = f"{version_prefix}_{name}_Verbose"
                    total_key = f"{version_prefix}_{name}_Total"
                    positive_key = f"{version_prefix}_{name}_Positive"
                    
                    existing[score_key] = metric_obj.score
                    existing[reason_key] = metric_obj.reason
                    
                    if hasattr(metric_obj, 'verbose_logs'):
                        verbose_log = metric_obj.verbose_logs
                    else:
                        verbose_log = ""
                    existing[verbose_key] = verbose_log
                    
                    if verbose_log:
                        counts = parse_verbose_log(verbose_log)
                        existing[total_key] = counts.get('total', 0)
                        existing[positive_key] = counts.get('positive', 0)
                    else:
                        existing[total_key] = 0
                        existing[positive_key] = 0
                    
                    print(f"         ✅ {score_key} = {metric_obj.score} (Total={existing[total_key]}, Pos={existing[positive_key]})")

        process_results(r1_t, "V1", v1_t_ref)
        process_results(r1_b, "V1", v1_b_ref)
        process_results(r1_temp, "V1", v1_temp_ref)
        process_results(r9_t, "V9", v9_t_ref)
        process_results(r9_b, "V9", v9_b_ref)
        process_results(r9_temp, "V9", v9_temp_ref)

        # ====================================================================
        # IMPRESSÃO DETALHADA NO CONSOLE
        # ====================================================================
        print("\n" + "=" * 90)
        print("📊 DETALHES POR CASO (CONSOLE) - COM CÁLCULO PASSO A PASSO")
        print("=" * 90)
        for r in rows:
            print(f"\n🔹 [{r['ID']}] - Tipo: {r['Test_Type']}")
            q = r.get('Query', '')
            if len(q) > 150:
                print(f"   Pergunta: {q[:150]}...")
            else:
                print(f"   Pergunta: {q}")
            
            v1_ans = str(r.get('V1_Answer', 'N/A'))
            v9_ans = str(r.get('V9_Answer', 'N/A'))
            print(f"   V1 Resposta: {v1_ans[:200]}{'...' if len(v1_ans) > 200 else ''}")
            print(f"   V9 Resposta: {v9_ans[:200]}{'...' if len(v9_ans) > 200 else ''}")
            
            for version in ['V1', 'V9']:
                print(f"  {version}:")
                all_metrics = ['Faithfulness', 'Answer_Relevancy', 'Contextual_Relevancy',
                               'Contextual_Precision', 'Contextual_Recall',
                               'Behavioral_Guardrails', 'Temporal_Consistency',
                               'Temporal_Reranking', 'Intelligent_Fallback']
                for metric in all_metrics:
                    score = r.get(f'{version}_{metric}_Score', 'N/A')
                    reason = r.get(f'{version}_{metric}_Reason', '')
                    verbose = r.get(f'{version}_{metric}_Verbose', '')
                    total = r.get(f'{version}_{metric}_Total', 0)
                    positive = r.get(f'{version}_{metric}_Positive', 0)
                    
                    if score != 'N/A':
                        print(f"    {metric}: {score:.3f}")
                        print(f"      Total de itens analisados: {total}")
                        print(f"      Itens positivos (veredito yes): {positive}")
                        if total > 0:
                            calc = positive / total
                            print(f"      Fórmula: {positive} / {total} = {calc:.3f} (Score reportado: {score:.3f})")
                            if abs(calc - score) > 0.01:
                                print(f"      ⚠️ Diferença entre cálculo ({calc:.3f}) e score reportado ({score:.3f})")
                        if reason:
                            print(f"      Razão: {reason[:300]}{'...' if len(reason) > 300 else ''}")
                        if verbose:
                            print(f"      Verbose Logs:")
                            if len(verbose) > 800:
                                print(f"        {verbose[:800]}...")
                            else:
                                for line in verbose.split('\n'):
                                    print(f"        {line}")
            print("-" * 80)

        # ====================================================================
        # CRIA DATAFRAME
        # ====================================================================
        df = pd.DataFrame(rows)
        ALL_METRICS = [
            'Faithfulness', 'Answer_Relevancy', 'Contextual_Relevancy',
            'Contextual_Precision', 'Contextual_Recall', 'Behavioral_Guardrails',
            'Temporal_Consistency', 'Temporal_Reranking', 'Intelligent_Fallback'
        ]
        for version in ['V1', 'V9']:
            for metric in ALL_METRICS:
                col_score = f"{version}_{metric}_Score"
                col_reason = f"{version}_{metric}_Reason"
                col_verbose = f"{version}_{metric}_Verbose"
                col_total = f"{version}_{metric}_Total"
                col_positive = f"{version}_{metric}_Positive"
                for col in [col_score, col_reason, col_verbose, col_total, col_positive]:
                    if col not in df.columns:
                        if col.endswith('_Score'):
                            df[col] = np.nan
                        elif col.endswith('_Total') or col.endswith('_Positive'):
                            df[col] = 0
                        else:
                            df[col] = ""

        combo_id = self.config.combination_id
        csv_out = self.config.output_dir / f"DEEPEVAL_MIXED_NATIVE_DEBUG_{combo_id}_{self.config.timestamp}.csv"
        df.to_csv(csv_out, index=False)

        # ====================================================================
        # RELATÓRIOS TXT E MD COM FÓRMULA, OPERAÇÃO E VERBOSE LOGS COMPLETOS
        # ====================================================================
        txt_out = self.config.output_dir / f"RELATORIO_DEBUG_{combo_id}_{self.config.timestamp}.txt"
        self._write_txt_report(txt_out, rows)

        md_out = self.config.output_dir / f"RELATORIO_DEBUG_{combo_id}_{self.config.timestamp}.md"
        self._write_md_report(md_out, rows)

        print(f"\n🚀 Pipeline de debug concluído.")
        print(f"📊 Planilha CSV:  {csv_out}")
        print(f"📝 Relatório TXT: {txt_out}")
        print(f"📝 Relatório MD:  {md_out}")

    # ========================================================================
    # RELATÓRIO TXT COM FÓRMULA, OPERAÇÃO E VERBOSE LOGS COMPLETOS
    # ========================================================================
    def _write_txt_report(self, path: Path, rows: List[Dict]):
        with open(path, 'w', encoding='utf-8') as f:
            f.write("=" * 90 + "\n")
            f.write(f"RELATÓRIO DEBUG - {self.config.timestamp}\n")
            f.write("=" * 90 + "\n")
            f.write(f"Modelo Avaliador: {self.config.evaluator_model}\n")
            f.write(f"Modelo Gerador: {self.config.model_name}\n")
            f.write(f"Total Casos: {len(rows)}\n")
            f.write("-" * 90 + "\n\n")
            
            for r in rows:
                f.write(f"▶️ ID: {r['ID']} | Tipo: {r['Test_Type'].upper()}\n")
                f.write(f" 💬 Query: {r['Query']}\n\n")
                f.write(" [V1 Answer]:\n")
                f.write(f"   {str(r.get('V1_Answer', 'N/A')).strip()}\n")
                f.write("\n [V9 Answer]:\n")
                f.write(f"   {str(r.get('V9_Answer', 'N/A')).strip()}\n")
                
                for version in ['V1', 'V9']:
                    f.write(f"\n Métricas {version} (com cálculo passo a passo e verbose logs):\n")
                    for key in sorted(r.keys()):
                        if key.startswith(f'{version}_') and key.endswith('_Score'):
                            metric_name = key.replace(f'{version}_', '').replace('_Score', '')
                            total_key = f"{version}_{metric_name}_Total"
                            positive_key = f"{version}_{metric_name}_Positive"
                            reason_key = f"{version}_{metric_name}_Reason"
                            verbose_key = f"{version}_{metric_name}_Verbose"
                            
                            score = r.get(key, 'N/A')
                            total = r.get(total_key, 0)
                            positive = r.get(positive_key, 0)
                            reason = r.get(reason_key, '')
                            verbose = r.get(verbose_key, '')
                            
                            f.write(f"   {key}: {score}\n")
                            f.write(f"      Total de itens: {total}\n")
                            f.write(f"      Positivos (yes): {positive}\n")
                            if total > 0:
                                calc = positive / total
                                f.write(f"      Fórmula: Pontuação = Positivos / Total = {positive} / {total} = {calc:.3f}\n")
                                if abs(calc - float(score)) > 0.01:
                                    f.write(f"      ⚠️ Diferença: {calc:.3f} vs score reportado {score}\n")
                            else:
                                f.write(f"      Fórmula: Não disponível (Total = 0)\n")
                            if reason:
                                f.write(f"      Razão: {reason}\n")  # sem truncamento no TXT
                            if verbose:
                                f.write(f"      Verbose Logs (completo, incluindo Statements/Truths/Verdicts):\n")
                                # Escreve cada linha do verbose log com indentação
                                for line in verbose.split('\n'):
                                    f.write(f"        {line}\n")
                f.write("\n" + "-" * 80 + "\n")

    # ========================================================================
    # RELATÓRIO MD COM FÓRMULA, OPERAÇÃO E VERBOSE LOGS
    # ========================================================================
    def _write_md_report(self, path: Path, rows: List[Dict]):
        with open(path, 'w', encoding='utf-8') as f:
            f.write(f"# Relatório Debug com Planilha de Cálculos\n\n")
            f.write(f"- Data: {self.config.timestamp}\n")
            f.write(f"- Juiz: {self.config.evaluator_model}\n")
            f.write(f"- Gerador: {self.config.model_name}\n")
            f.write("\n## Resultados Individuais\n\n")
            
            for r in rows:
                f.write(f"### {r['ID']} ({r['Test_Type']})\n")
                f.write(f"**Query:** {r['Query']}\n\n")
                f.write("**V1 Answer:**\n```\n" + str(r.get('V1_Answer', 'N/A')) + "\n```\n")
                f.write("**V9 Answer:**\n```\n" + str(r.get('V9_Answer', 'N/A')) + "\n```\n")
                
                f.write("**Métricas e Cálculos:**\n\n")
                f.write("| Métrica | Versão | Score | Total | Positivos | Fórmula | Operação |\n")
                f.write("|---------|--------|-------|-------|-----------|---------|----------|\n")
                
                all_metrics = ['Faithfulness', 'Answer_Relevancy', 'Contextual_Relevancy', 
                               'Contextual_Precision', 'Contextual_Recall', 'Behavioral_Guardrails', 
                               'Temporal_Consistency', 'Temporal_Reranking', 'Intelligent_Fallback']
                for metric in all_metrics:
                    for version in ['V1', 'V9']:
                        score = r.get(f'{version}_{metric}_Score', '')
                        total = r.get(f'{version}_{metric}_Total', 0)
                        positive = r.get(f'{version}_{metric}_Positive', 0)
                        if score != '':
                            if total > 0:
                                calc = positive / total
                                formula = f"{positive} / {total}"
                                operacao = f"{positive} ÷ {total} = {calc:.3f}"
                            else:
                                formula = "N/A"
                                operacao = "N/A"
                            f.write(f"| {metric} | {version} | {score:.3f} | {total} | {positive} | {formula} | {operacao} |\n")
                
                f.write("\n**Verbose Logs (detalhados):**\n\n")
                for version in ['V1', 'V9']:
                    f.write(f"#### {version} Verbose Logs\n\n")
                    for metric in all_metrics:
                        verbose = r.get(f'{version}_{metric}_Verbose', '')
                        if verbose:
                            f.write(f"**{metric}:**\n\n")
                            f.write("```\n")
                            f.write(str(verbose))
                            f.write("\n```\n\n")
                f.write("\n---\n")


# ============================================================================
# MAIN ASYNC
# ============================================================================

async def main_queue():
    judge = "qwen3:4b-instruct"
    generator = "phi3.5:latest"
    print(f"🔁 Executando combinação: Juiz={judge} | Gerador={generator}")
    
    pipeline = None
    try:
        pipeline = NativeComparativePipeline()
        pipeline.config = EvalConfig(evaluator_model=judge, model_name=generator)
        pipeline.evaluator_v1 = OllamaEvaluator(model_name=judge, prompt_version="V1")
        pipeline.evaluator_v9 = OllamaEvaluator(model_name=judge, prompt_version="V9")
        await pipeline.run()
        print(f"✅ Concluído.")
    except Exception as e:
        print(f"❌ Erro: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if pipeline and hasattr(pipeline, 'rag_manager'):
            try:
                if pipeline.rag_manager._vanilla:
                    await pipeline.rag_manager.vanilla.close()
                if pipeline.rag_manager._temporal:
                    await pipeline.rag_manager.temporal.close()
            except:
                pass
        del pipeline
        gc.collect()

if __name__ == "__main__":
    asyncio.run(main_queue())