#!/usr/bin/env python3
"""
UNIFIED EVALUATION SCRIPT: V1 vs V9 (Mixed Fallback Framework Edition) - V5 COMPATIBLE
Fully customized to validate the rules of the second prompt generation without format bias.
Supports command-line arguments for judge and generator models.
Generates CSV, TXT, and Markdown reports natively from consolidated loop data.
Execução única: cada caso é testado 1 vez (sem repetições).
COM PLANILHA DE CÁLCULOS PASSO A PASSO (Total, Positivos, Fórmula, Operação)
E VERBOSE LOGS COMPLETOS NO TXT E MD
"""

import os

# Configura o timeout por caso de teste para 60 minutos (2400 segundos)
os.environ["DEEPEVAL_PER_TASK_TIMEOUT_SECONDS_OVERRIDE"] = "36000"

# Configura o timeout de cada tentativa individual ao Ollama para 10 minutos (300 segundos)
os.environ["DEEPEVAL_PER_ATTEMPT_TIMEOUT_SECONDS_OVERRIDE"] = "36000"


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
    base_path: Path = VETORIZATION_DATA / 'base_vetorizada' / 'base_conhecimento_multilingueV9.json'
    evaluator_model: str = "qwen3:4b-instruct"
    cache_dir: Path = AVALIACAO_DATA / "cache"
    embedding_cache_size: int = 1000
    vanilla_use_expansion: bool = False
    temporal_use_expansion: bool = False
    temporal_variant: str = "V9_HYBRID_MIXED_AUDITOR"
    model_name: str = "phi3.5:latest"
    temperature: float = 0.0
    search_top_k: int = 50
    mode: str = "sem_repeticao"  # Identificador para pasta

    @property
    def timestamp(self) -> str:
        return datetime.now().strftime("%Y%m%d_%H%M")

    @property
    def output_dir(self) -> Path:
        dir_path = AVALIACAO_DATA / "testes_com_modelos_diferentes" / self.mode
        dir_path.mkdir(parents=True, exist_ok=True)
        return dir_path

    @property
    def combination_id(self) -> str:
        """Identificador curto da combinação avaliador+gerador."""
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
# NATIVE METRICS FACTORY & G-EVAL GUARDRAILS (V5 UNIFIED)
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
# RAG MANAGER & ORCHESTRATION (SEM REPETIÇÃO)
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
        print(f"🔍 Ingerindo {len(TEST_SUITE)} casos de teste (1 execução)...")
        
        for tc in TEST_SUITE:
            query = tc["input"]
            ref_date = tc.get("reference_date", "2026-06-23")
            
            v1_task = asyncio.create_task(self.vanilla.search(query))
            v9_task = asyncio.create_task(self.temporal.search(query, ref_date))
            res_v1, res_v9 = await asyncio.gather(v1_task, v9_task)
            
            meta = {
                "id": tc["id"],
                "original_id": tc["id"],
                "run_index": 1,
                "test_type": tc.get("test_type", "traditional")
            }
            
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

        res_v1_trad, res_v1_behav, res_v1_temp = [], [], []
        res_v9_trad, res_v9_behav, res_v9_temp = [], [], []

        # ====================================================================
        # AVALIAÇÃO RAG V1
        # ====================================================================
        if d_v1_trad.test_cases:
            print(f"\n🏆 Avaliando V1 MIXED Tradicional ({len(d_v1_trad.test_cases)} interações total)...")
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
            print(f"\n🏆 Avaliando V1 MIXED Comportamental ({len(d_v1_behav.test_cases)} interações total)...")
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
            print(f"\n⏳ Avaliando V1 MIXED Temporal ({len(d_v1_temp.test_cases)} interações total)...")
            geval_temp_v1 = create_temporal_geval(self.evaluator_v1)
            batch_res = evaluate(d_v1_temp.test_cases, [geval_temp_v1], async_config=AsyncConfig(max_concurrent=1))
            res_v1_temp = batch_res.test_results

        # ====================================================================
        # AVALIAÇÃO RAG V9
        # ====================================================================
        if d_v9_trad.test_cases:
            print(f"\n🏆 Avaliando V9 MIXED Tradicional ({len(d_v9_trad.test_cases)} interações total)...")
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

        if d_v9_behav.test_cases:
            print(f"\n🏆 Avaliando V9 MIXED Comportamental ({len(d_v9_behav.test_cases)} interações total)...")
            geval_v9 = create_unified_behavioral_geval(self.evaluator_v9)
            geval_rerank_v9 = create_strict_temporal_reranking_geval(self.evaluator_v9)
            geval_fallback_v9 = create_intelligent_fallback_geval(self.evaluator_v9)
            
            batch_res = evaluate(
                d_v9_behav.test_cases,
                [geval_v9, geval_rerank_v9, geval_fallback_v9],
                async_config=AsyncConfig(max_concurrent=1)
            )
            res_v9_behav = batch_res.test_results

        if d_v9_temp.test_cases:
            print(f"\n⏳ Avaliando V9 MIXED Temporal ({len(d_v9_temp.test_cases)} interações total)...")
            geval_temp_v9 = create_temporal_geval(self.evaluator_v9)
            batch_res = evaluate(d_v9_temp.test_cases, [geval_temp_v9], async_config=AsyncConfig(max_concurrent=1))
            res_v9_temp = batch_res.test_results

        self._build_and_save_reports(
            res_v1_trad, res_v1_behav, res_v1_temp,
            res_v9_trad, res_v9_behav, res_v9_temp
        )

    def _build_and_save_reports(self, r1_t, r1_b, r1_temp, r9_t, r9_b, r9_temp):
        rows = []
        
        v1_t_ref = [c for c in self.v1_cases_backup if c.metadata["test_type"] == "traditional"]
        v1_b_ref = [c for c in self.v1_cases_backup if c.metadata["test_type"] == "behavioral"]
        v1_temp_ref = [c for c in self.v1_cases_backup if c.metadata["test_type"] == "temporal"]
        v9_t_ref = [c for c in self.v9_cases_backup if c.metadata["test_type"] == "traditional"]
        v9_b_ref = [c for c in self.v9_cases_backup if c.metadata["test_type"] == "behavioral"]
        v9_temp_ref = [c for c in self.v9_cases_backup if c.metadata["test_type"] == "temporal"]

        # ------------------------------------------------------------
        # Função interna com mapeamento melhorado
        # ------------------------------------------------------------
        def process_results(results, version_prefix, source_cases_ref):
            # Dicionário de mapeamento: substring -> nome padronizado
            name_mapping = {
                "Mixed Guardrails": "Behavioral_Guardrails",
                "Behavioral": "Behavioral_Guardrails",
                "Temporal Consistency": "Temporal_Consistency",   # <-- agora captura mesmo com sufixo
                "Temporal Reranking": "Temporal_Reranking",
                "Reranking": "Temporal_Reranking",
                "Smart Fallback": "Intelligent_Fallback",
                "Fallback": "Intelligent_Fallback"
            }

            for idx, test_result in enumerate(results):
                if idx < len(source_cases_ref):
                    tc = source_cases_ref[idx]
                else:
                    tc = getattr(test_result, 'test_case', None)
                
                if tc is None:
                    continue
                
                row_id = tc.metadata["id"] if (tc and tc.metadata) else f"TC_{idx}"
                orig_id = tc.metadata.get("original_id", row_id) if (tc and tc.metadata) else row_id
                run_idx = tc.metadata.get("run_index", 1) if (tc and tc.metadata) else 1
                query_text = tc.input if tc else "Unknown"
                test_type = tc.metadata["test_type"] if (tc and tc.metadata) else "traditional"
                actual_output = tc.actual_output if tc else ""

                existing = next((r for r in rows if r["ID"] == row_id), None)
                if not existing:
                    existing = {
                        "ID": row_id, 
                        "Original_ID": orig_id,
                        "Repetition": run_idx,
                        "Query": query_text, 
                        "Test_Type": test_type
                    }
                    rows.append(existing)
                
                existing[f"{version_prefix}_Answer"] = actual_output
                
                metrics_list = getattr(test_result, 'metrics_data', [])
                for metric_obj in metrics_list:
                    original_name = metric_obj.name

                    # Aplica o mapeamento por substring
                    mapped_name = None
                    for key, mapped in name_mapping.items():
                        if key in original_name:
                            mapped_name = mapped
                            break
                    if mapped_name is None:
                        # Fallback: substitui espaços por underscore
                        mapped_name = original_name.replace(" ", "_")

                    name = mapped_name  # nome padronizado

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

        # Aplica o processamento para cada grupo
        process_results(r1_t, "V1", v1_t_ref)
        process_results(r1_b, "V1", v1_b_ref)
        process_results(r1_temp, "V1", v1_temp_ref)
        process_results(r9_t, "V9", v9_t_ref)
        process_results(r9_b, "V9", v9_b_ref)
        process_results(r9_temp, "V9", v9_temp_ref)

        # ------------------------------------------------------------
        # Criação do DataFrame e exportação (sem alterações)
        # ------------------------------------------------------------
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
        csv_out = self.config.output_dir / f"DEEPEVAL_MIXED_NATIVE_COMPARATIVE_COM_REPETICAO_{combo_id}_{self.config.timestamp}.csv"
        df.to_csv(csv_out, index=False)
        
        txt_out = self.config.output_dir / f"RELATORIO_COMPARATIVO_COM_REPETICAO_{combo_id}_{self.config.timestamp}.txt"
        self._write_txt_report(txt_out, rows)

        md_out = self.config.output_dir / f"RELATORIO_COMPARATIVO_COM_REPETICAO_{combo_id}_{self.config.timestamp}.md"
        self._write_md_report(md_out, rows)

        print(f"\n🚀 Pipeline com repetição concluído com sucesso.")
        print(f"📊 Planilha CSV:  {csv_out}")
        print(f"📝 Relatório TXT: {txt_out}")
        print(f"📝 Relatório MD:  {md_out}")


    # ========================================================================
    # RELATÓRIO TXT COM FÓRMULA, OPERAÇÃO E VERBOSE LOGS COMPLETOS
    # ========================================================================
    def _write_txt_report(self, path: Path, rows: List[Dict]):
        with open(path, 'w', encoding='utf-8') as f:
            f.write("=" * 90 + "\n")
            f.write(f"RELATÓRIO QUANTITATIVO COMPARATIVO DE CORRIDA NATIVA (DEEPEVAL) - {self.config.timestamp}\n")
            f.write("=" * 90 + "\n")
            f.write(f"Modelo Avaliador (Juiz): {self.config.evaluator_model}\n")
            f.write(f"Modelo Base RAG (Gerador): {self.config.model_name}\n")
            f.write(f"Total Interações: {len(rows)}\n")
            f.write("-" * 90 + "\n\n")

            for r in rows:
                f.write(f"▶️ ID: {r['ID']} [Original: {r['Original_ID']} | Tentativa: {r['Repetition']}] | Tipo: {r['Test_Type'].upper()}\n")
                f.write(f" 💬 Query: {r['Query']}\n\n")
                
                f.write(" [🤖 RESPOSTA - RAG V1 VANILLA Mixed]:\n")
                f.write(f"   {str(r.get('V1_Answer', 'N/A')).strip()}\n")
                
                f.write("\n [🧠 RESPOSTA - RAG V9 TEMPORAL Mixed]:\n")
                f.write(f"   {str(r.get('V9_Answer', 'N/A')).strip()}\n")
                
                # Exibe métricas com cálculos para cada versão
                for version in ['V1', 'V9']:
                    f.write(f"\n 📊 Métricas {version} (com cálculo passo a passo e verbose logs):\n")
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
                            
                            f.write(f"   {metric_name}: {score}\n")
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
                                f.write(f"      Razão: {reason}\n")
                            if verbose:
                                f.write(f"      Verbose Logs (completo):\n")
                                for line in verbose.split('\n'):
                                    f.write(f"        {line}\n")
                
                # Resumo comparativo
                f.write("\n 📈 COMPARAÇÃO RÁPIDA ENTRE V1 E V9:\n")
                all_metrics = ['Faithfulness', 'Answer_Relevancy', 'Contextual_Relevancy', 
                               'Contextual_Precision', 'Contextual_Recall', 'Behavioral_Guardrails', 
                               'Temporal_Consistency', 'Temporal_Reranking', 'Intelligent_Fallback']
                for metric in all_metrics:
                    v1_score = r.get(f'V1_{metric}_Score', None)
                    v9_score = r.get(f'V9_{metric}_Score', None)
                    if v1_score is not None and v9_score is not None:
                        diff = v9_score - v1_score
                        arrow = "↑" if diff > 0.02 else "↓" if diff < -0.02 else "→"
                        f.write(f"   {metric:<22}: V1={v1_score:.3f} {arrow} V9={v9_score:.3f} (Δ {diff:+.3f})\n")
                f.write("\n" + "-" * 80 + "\n")

            # Resumo consolidado das médias
            f.write("\n" + "=" * 90 + "\n")
            f.write("📊 RESUMO CONSOLIDADO DAS MÉTRICAS (MÉDIAS GERAIS)\n")
            f.write("=" * 90 + "\n")
            
            trad_rows = [r for r in rows if r["Test_Type"] == "traditional"]
            if trad_rows:
                f.write("\n📈 MÉTRICAS TRADICIONAIS MÉDIAS (DeepEval):\n")
                for m in ["Faithfulness", "Answer_Relevancy", "Contextual_Relevancy", "Contextual_Precision", "Contextual_Recall"]:
                    v1_scores = [r[f"V1_{m}_Score"] for r in trad_rows if f"V1_{m}_Score" in r and not pd.isna(r[f"V1_{m}_Score"])]
                    v9_scores = [r[f"V9_{m}_Score"] for r in trad_rows if f"V9_{m}_Score" in r and not pd.isna(r[f"V9_{m}_Score"])]
                    v1_avg = np.mean(v1_scores) if v1_scores else 0.0
                    v9_avg = np.mean(v9_scores) if v9_scores else 0.0
                    diff = v9_avg - v1_avg
                    arrow = "↑" if diff > 0 else "↓" if diff < 0 else "→"
                    f.write(f"  ├── {m:<22}: V1={v1_avg:.3f} {arrow} V9={v9_avg:.3f} (Δ {diff:+.3f})\n")
            
            behav_rows = [r for r in rows if r["Test_Type"] == "behavioral"]
            if behav_rows:
                f.write("\n📈 ACURÁCIA COMPORTAMENTAL (G-Eval Guardrails):\n")
                # Behavioral Guardrails
                v1_b_scores = [r["V1_Behavioral_Guardrails_Score"] for r in behav_rows if "V1_Behavioral_Guardrails_Score" in r and not pd.isna(r["V1_Behavioral_Guardrails_Score"])]
                v9_b_scores = [r["V9_Behavioral_Guardrails_Score"] for r in behav_rows if "V9_Behavioral_Guardrails_Score" in r and not pd.isna(r["V9_Behavioral_Guardrails_Score"])]
                v1_b_avg = np.mean(v1_b_scores) if v1_b_scores else 0.0
                v9_b_avg = np.mean(v9_b_scores) if v9_b_scores else 0.0
                diff_b = v9_b_avg - v1_b_avg
                arrow_b = "↑" if diff_b > 0 else "↓" if diff_b < 0 else "→"
                f.write(f"  ├── Behavioral Guardrails V1    : {v1_b_avg:.3f}\n")
                f.write(f"  ├── Behavioral Guardrails V9    : {v9_b_avg:.3f} (Δ {diff_b:+.3f})\n")
                
                # Temporal Reranking
                v1_tr_scores = [r["V1_Temporal_Reranking_Score"] for r in behav_rows if "V1_Temporal_Reranking_Score" in r and not pd.isna(r["V1_Temporal_Reranking_Score"])]
                v9_tr_scores = [r["V9_Temporal_Reranking_Score"] for r in behav_rows if "V9_Temporal_Reranking_Score" in r and not pd.isna(r["V9_Temporal_Reranking_Score"])]
                if v1_tr_scores and v9_tr_scores:
                    v1_tr_avg = np.mean(v1_tr_scores)
                    v9_tr_avg = np.mean(v9_tr_scores)
                    diff_tr = v9_tr_avg - v1_tr_avg
                    arrow_tr = "↑" if diff_tr > 0 else "↓" if diff_tr < 0 else "→"
                    f.write(f"  ├── Temporal Reranking V1      : {v1_tr_avg:.3f}\n")
                    f.write(f"  ├── Temporal Reranking V9      : {v9_tr_avg:.3f} (Δ {diff_tr:+.3f})\n")
                
                # Intelligent Fallback
                v1_if_scores = [r["V1_Intelligent_Fallback_Score"] for r in behav_rows if "V1_Intelligent_Fallback_Score" in r and not pd.isna(r["V1_Intelligent_Fallback_Score"])]
                v9_if_scores = [r["V9_Intelligent_Fallback_Score"] for r in behav_rows if "V9_Intelligent_Fallback_Score" in r and not pd.isna(r["V9_Intelligent_Fallback_Score"])]
                if v1_if_scores and v9_if_scores:
                    v1_if_avg = np.mean(v1_if_scores)
                    v9_if_avg = np.mean(v9_if_scores)
                    diff_if = v9_if_avg - v1_if_avg
                    arrow_if = "↑" if diff_if > 0 else "↓" if diff_if < 0 else "→"
                    f.write(f"  └── Intelligent Fallback V1     : {v1_if_avg:.3f}\n")
                    f.write(f"      Intelligent Fallback V9     : {v9_if_avg:.3f} (Δ {diff_if:+.3f})\n")

            temp_rows = [r for r in rows if r["Test_Type"] == "temporal"]
            if temp_rows:
                f.write("\n📈 ACURÁCIA TEMPORAL (Temporal Consistency):\n")
                v1_t_scores = [r["V1_Temporal_Consistency_Score"] for r in temp_rows if "V1_Temporal_Consistency_Score" in r and not pd.isna(r["V1_Temporal_Consistency_Score"])]
                v9_t_scores = [r["V9_Temporal_Consistency_Score"] for r in temp_rows if "V9_Temporal_Consistency_Score" in r and not pd.isna(r["V9_Temporal_Consistency_Score"])]
                v1_t_avg = np.mean(v1_t_scores) if v1_t_scores else 0.0
                v9_t_avg = np.mean(v9_t_scores) if v9_t_scores else 0.0
                diff_t = v9_t_avg - v1_t_avg
                arrow_t = "↑" if diff_t > 0 else "↓" if diff_t < 0 else "→"
                f.write(f"  ├── Consistência Temporal V1 : {v1_t_avg:.3f}\n")
                f.write(f"  └── Consistência Temporal V9 : {v9_t_avg:.3f} (Δ {diff_t:+.3f})\n")

    # ========================================================================
    # RELATÓRIO MD COM FÓRMULA, OPERAÇÃO E VERBOSE LOGS
    # ========================================================================
    def _write_md_report(self, path: Path, rows: List[Dict]):
        with open(path, 'w', encoding='utf-8') as f:
            f.write(f"# Relatório de Auditoria Comparativa Nativa (DeepEval) - SEM REPETIÇÃO (1x)\n\n")
            f.write(f"- **Data de Execução:** {self.config.timestamp}\n")
            f.write(f"- **Modelo Avaliador (Juiz):** `{self.config.evaluator_model}`\n")
            f.write(f"- **Modelo Base RAG (Gerador):** `{self.config.model_name}`\n")
            f.write(f"- **Total Interações Avaliadas:** {len(rows)}\n\n")
            
            f.write("## 📊 Tabela Resumo das Médias Consolidadas\n\n")
            f.write("| Métrica Base | Média V1 (Vanilla) | Média V9 (Temporal) | Variação Líquida |\n")
            f.write("|---|---|---|---|\n")
            
            # Médias tradicionais
            trad_rows = [r for r in rows if r["Test_Type"] == "traditional"]
            if trad_rows:
                for m in ["Faithfulness", "Answer_Relevancy", "Contextual_Relevancy", "Contextual_Precision", "Contextual_Recall"]:
                    v1_scores = [r[f"V1_{m}_Score"] for r in trad_rows if f"V1_{m}_Score" in r and not pd.isna(r[f"V1_{m}_Score"])]
                    v9_scores = [r[f"V9_{m}_Score"] for r in trad_rows if f"V9_{m}_Score" in r and not pd.isna(r[f"V9_{m}_Score"])]
                    v1_avg = np.mean(v1_scores) if v1_scores else 0.0
                    v9_avg = np.mean(v9_scores) if v9_scores else 0.0
                    diff = v9_avg - v1_avg
                    emoji = "🟢" if diff > 0.02 else "🔴" if diff < -0.02 else "⚪"
                    f.write(f"| {m} | {v1_avg:.3f} | {v9_avg:.3f} | {emoji} {diff:+.3f} |\n")
            
            # Médias comportamentais
            behav_rows = [r for r in rows if r["Test_Type"] == "behavioral"]
            if behav_rows:
                # Behavioral Guardrails
                v1_b_scores = [r["V1_Behavioral_Guardrails_Score"] for r in behav_rows if "V1_Behavioral_Guardrails_Score" in r and not pd.isna(r["V1_Behavioral_Guardrails_Score"])]
                v9_b_scores = [r["V9_Behavioral_Guardrails_Score"] for r in behav_rows if "V9_Behavioral_Guardrails_Score" in r and not pd.isna(r["V9_Behavioral_Guardrails_Score"])]
                v1_b_avg = np.mean(v1_b_scores) if v1_b_scores else 0.0
                v9_b_avg = np.mean(v9_b_scores) if v9_b_scores else 0.0
                diff_b = v9_b_avg - v1_b_avg
                emoji_b = "🟢" if diff_b > 0.02 else "🔴" if diff_b < -0.02 else "⚪"
                f.write(f"| **Behavioral Guardrails (G-Eval)** | {v1_b_avg:.3f} | {v9_b_avg:.3f} | {emoji_b} {diff_b:+.3f} |\n")
                
                # Temporal Reranking
                v1_tr_scores = [r["V1_Temporal_Reranking_Score"] for r in behav_rows if "V1_Temporal_Reranking_Score" in r and not pd.isna(r["V1_Temporal_Reranking_Score"])]
                v9_tr_scores = [r["V9_Temporal_Reranking_Score"] for r in behav_rows if "V9_Temporal_Reranking_Score" in r and not pd.isna(r["V9_Temporal_Reranking_Score"])]
                if v1_tr_scores and v9_tr_scores:
                    v1_tr_avg = np.mean(v1_tr_scores)
                    v9_tr_avg = np.mean(v9_tr_scores)
                    diff_tr = v9_tr_avg - v1_tr_avg
                    emoji_tr = "🟢" if diff_tr > 0.02 else "🔴" if diff_tr < -0.02 else "⚪"
                    f.write(f"| **Temporal Reranking** | {v1_tr_avg:.3f} | {v9_tr_avg:.3f} | {emoji_tr} {diff_tr:+.3f} |\n")
                
                # Intelligent Fallback
                v1_if_scores = [r["V1_Intelligent_Fallback_Score"] for r in behav_rows if "V1_Intelligent_Fallback_Score" in r and not pd.isna(r["V1_Intelligent_Fallback_Score"])]
                v9_if_scores = [r["V9_Intelligent_Fallback_Score"] for r in behav_rows if "V9_Intelligent_Fallback_Score" in r and not pd.isna(r["V9_Intelligent_Fallback_Score"])]
                if v1_if_scores and v9_if_scores:
                    v1_if_avg = np.mean(v1_if_scores)
                    v9_if_avg = np.mean(v9_if_scores)
                    diff_if = v9_if_avg - v1_if_avg
                    emoji_if = "🟢" if diff_if > 0.02 else "🔴" if diff_if < -0.02 else "⚪"
                    f.write(f"| **Intelligent Fallback** | {v1_if_avg:.3f} | {v9_if_avg:.3f} | {emoji_if} {diff_if:+.3f} |\n")
            
            # Médias temporais
            temp_rows = [r for r in rows if r["Test_Type"] == "temporal"]
            if temp_rows:
                v1_t_scores = [r["V1_Temporal_Consistency_Score"] for r in temp_rows if "V1_Temporal_Consistency_Score" in r and not pd.isna(r["V1_Temporal_Consistency_Score"])]
                v9_t_scores = [r["V9_Temporal_Consistency_Score"] for r in temp_rows if "V9_Temporal_Consistency_Score" in r and not pd.isna(r["V9_Temporal_Consistency_Score"])]
                v1_t_avg = np.mean(v1_t_scores) if v1_t_scores else 0.0
                v9_t_avg = np.mean(v9_t_scores) if v9_t_scores else 0.0
                diff_t = v9_t_avg - v1_t_avg
                emoji_t = "🟢" if diff_t > 0.02 else "🔴" if diff_t < -0.02 else "⚪"
                f.write(f"| **Temporal Consistency** | {v1_t_avg:.3f} | {v9_t_avg:.3f} | {emoji_t} {diff_t:+.3f} |\n")
            
            f.write("\n## 📋 Detalhamento por Caso (com Cálculo Passo a Passo)\n\n")
            for r in rows:
                f.write(f"### {r['ID']} (Original: {r['Original_ID']}, Tentativa: {r['Repetition']})\n")
                f.write(f"**Tipo:** {r['Test_Type'].upper()}\n\n")
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
                    for metric in all_metrics:
                        verbose = r.get(f'{version}_{metric}_Verbose', '')
                        if verbose:
                            f.write(f"**{version} - {metric}:**\n\n")
                            f.write("```\n")
                            f.write(str(verbose))
                            f.write("\n```\n\n")
                f.write("\n---\n")


# ============================================================================
# MAIN ASYNC COM FILA DE COMBINAÇÕES (SEM REPETIÇÃO - 1 VEZ)
# ============================================================================

async def main_queue():
    import time
    from itertools import product

    # Modelos disponíveis
    judge_models = [
        # "qwen3:4b-instruct",
        "mistral:7b-instruct",
        # "granite3.2:8b",
        "phi3.5:latest"
    ]
    generator_models = [
        "phi3.5:latest",
        "mistral:7b-instruct",
        "qwen3.5:9b",
        "phi3:14b"
    ]

    # Mapeamento de modelo para família
    def get_family(model: str) -> str:
        model_lower = model.lower()
        if model_lower.startswith("qwen"): return "qwen"
        if model_lower.startswith("mistral"): return "mistral"
        if model_lower.startswith("granite"): return "granite"
        if model_lower.startswith("phi"): return "phi"
        return "unknown"

    # Gerar e filtrar combinações sem conflito de família
    all_combinations = list(product(judge_models, generator_models))
    filtered_combinations = [
        (judge, gen) for judge, gen in all_combinations
        if get_family(judge) != get_family(gen)
    ]

    print(f"🚀 Total de combinações possíveis: {len(all_combinations)}")
    print(f"✅ Combinações sem mesma família: {len(filtered_combinations)}")
    print(f"🔁 Executando fila com execução única (sem repetição)...\n")

    for i, (judge, generator) in enumerate(filtered_combinations, 1):
        print(f"\n{'='*60}")
        print(f"🔁 Combinação {i}/{len(filtered_combinations)}: Juiz={judge} | Gerador={generator}")
        print(f"{'='*60}")

        pipeline = None
        try:
            pipeline = NativeComparativePipeline()
            pipeline.config = EvalConfig(evaluator_model=judge, model_name=generator)
            pipeline.evaluator_v1 = OllamaEvaluator(model_name=judge, prompt_version="V1")
            pipeline.evaluator_v9 = OllamaEvaluator(model_name=judge, prompt_version="V9")

            # Executa sem repetições (1 vez)
            await pipeline.run()
            print(f"✅ Combinação concluída: {judge} / {generator}")
        except Exception as e:
            import traceback
            print(f"❌ Erro catastrófico: {e}")
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

        if i < len(filtered_combinations):
            temp: int = 60 
            print("⏳ Aguardando", temp, "segundos para liberar recursos...")
            await asyncio.sleep(temp)

    print("\n🎉 Todas as combinações sem repetição foram executadas com sucesso.")

if __name__ == "__main__":
    asyncio.run(main_queue())