#!/usr/bin/env python3
"""
UNIFIED EVALUATION SCRIPT: V1 vs V9 (Mixed Fallback Framework Edition) - V5 COMPATIBLE
Versão com timeouts robustos e controle de concorrência, mantendo a estrutura original.
"""

import os

# ============================================================================
# CONFIGURAÇÃO DE TIMEOUTS (valores realistas)
# ============================================================================
os.environ["DEEPEVAL_PER_TASK_TIMEOUT_SECONDS_OVERRIDE"] = "1200"      # 10 min por tarefa
os.environ["DEEPEVAL_PER_ATTEMPT_TIMEOUT_SECONDS_OVERRIDE"] = "15"    # 1 min por tentativa
os.environ["DEEPEVAL_TASK_GATHER_BUFFER_SECONDS_OVERRIDE"] = "30"
os.environ["DEEPEVAL_RETRY_MAX_ATTEMPTS"] = "2"
os.environ["DEEPEVAL_VERBOSE_MODE"] = "1"
os.environ["LOG_LEVEL"] = "DEBUG"

import asyncio
import gc
import hashlib
import json
import pickle
import sys
import time
import argparse
import re
import logging
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
from deepeval.test_case import SingleTurnParams
from deepeval.metrics.g_eval import Rubric

# Custom external modules
from core.paths import VALIDACAO_SCRIPT, AVALIACAO_SCRIPT, VETORIZATION_DATA, AVALIACAO_DATA
from dataset_avaliacaoV4 import TEST_SUITE

for path in [VALIDACAO_SCRIPT, AVALIACAO_SCRIPT]:
    if str(path) not in sys.path:
        sys.path.append(str(path))

from RAG_BaseLineV2 import VanillaRAG
from RAG_Temporal_V9_3 import SpecialistTimeAwareRAG
from custom_evaluatorV4 import OllamaEvaluator

# Configura logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
    mode: str = "com_repeticaoV7"  # Identificador para pasta
    evaluator_timeout: int = 120   # timeout para o OllamaEvaluator

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
# RAG MANAGER & ORCHESTRATION (WITH REPETITIONS E CONTROLE DE CONCORRÊNCIA)
# ============================================================================

class ComparativeRAGManager:
    def __init__(self, base_path: Path, config: EvalConfig, embedding_cache=None):
        self.base_path = base_path
        self.config = config
        self.embedding_cache = embedding_cache
        self._vanilla: Optional[VanillaRAG] = None
        self._temporal: Optional[SpecialistTimeAwareRAG] = None
        # Semáforo para limitar buscas simultâneas
        self._search_semaphore = asyncio.Semaphore(3)

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

    async def _search_with_timeout(self, rag, query: str, ref_date: Optional[str] = None, timeout: int = 180):
        """Executa a busca com timeout e limite de concorrência."""
        async with self._search_semaphore:
            try:
                if ref_date:
                    return await asyncio.wait_for(rag.search(query, ref_date), timeout=timeout)
                else:
                    return await asyncio.wait_for(rag.search(query), timeout=timeout)
            except asyncio.TimeoutError:
                logger.warning(f"⏰ Timeout na busca para: {query[:50]}...")
                return {"answer": "[TIMEOUT] Busca excedeu o tempo limite.", "sources": []}
            except Exception as e:
                logger.error(f"❌ Erro na busca: {e}")
                return {"answer": f"[ERRO] {e}", "sources": []}

    async def generate_test_cases(self, num_repeats: int = 10) -> Tuple[List[LLMTestCase], List[LLMTestCase]]:
        v1_cases, v9_cases = [], []
        logger.info(f"🔍 Ingerindo {len(TEST_SUITE)} casos de teste com {num_repeats} repetições...")
        
        for idx, tc in enumerate(TEST_SUITE, 1):
            query = tc["input"]
            ref_date = tc.get("reference_date", "2026-06-23")
            
            logger.debug(f"  Processando caso {idx}/{len(TEST_SUITE)}: {query[:60]}...")
            
            # Cria tarefas com timeout
            v1_tasks = [self._search_with_timeout(self.vanilla, query, timeout=180) for _ in range(num_repeats)]
            v9_tasks = [self._search_with_timeout(self.temporal, query, ref_date, timeout=180) for _ in range(num_repeats)]
            
            # Executa com gather, mas já com timeout interno em cada tarefa
            res_v1_list = await asyncio.gather(*v1_tasks, return_exceptions=True)
            res_v9_list = await asyncio.gather(*v9_tasks, return_exceptions=True)
            
            for run_idx in range(num_repeats):
                res_v1 = res_v1_list[run_idx]
                res_v9 = res_v9_list[run_idx]
                
                # Se for exceção, converte para dicionário padrão
                if isinstance(res_v1, Exception):
                    res_v1 = {"answer": f"[ERRO] {res_v1}", "sources": []}
                if isinstance(res_v9, Exception):
                    res_v9 = {"answer": f"[ERRO] {res_v9}", "sources": []}
                
                # Identificação única por iteração/tentativa no metadado
                meta = {
                    "id": f"{tc['id']}_run_{run_idx + 1}", 
                    "original_id": tc["id"],
                    "run_index": run_idx + 1,
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
        # Cria avaliadores com timeout configurado
        self.evaluator_v1 = OllamaEvaluator(model_name=self.config.evaluator_model, 
                                            prompt_version="V1", 
                                            timeout=self.config.evaluator_timeout)
        self.evaluator_v9 = OllamaEvaluator(model_name=self.config.evaluator_model, 
                                            prompt_version="V9", 
                                            timeout=self.config.evaluator_timeout)

        self.v1_cases_backup: List[LLMTestCase] = []
        self.v9_cases_backup: List[LLMTestCase] = []

        self.name_mapping = {
            "Mixed Guardrails": "Behavioral_Guardrails",
            "Behavioral": "Behavioral_Guardrails",
            "Temporal Consistency": "Temporal_Consistency",
            "Temporal Reranking": "Temporal_Reranking",
            "Reranking": "Temporal_Reranking",
            "Smart Fallback": "Intelligent_Fallback",
            "Fallback": "Intelligent_Fallback"
        }

    async def _safe_evaluate(self, test_cases_list, metrics, description: str, timeout: int = 300):
        """
        Executa evaluate de forma síncrona, confiando nos timeouts do DeepEval e do Ollama.
        """
        if not test_cases_list:
            logger.warning(f"⚠️ Lista de casos vazia para {description}, pulando.")
            return None

        dataset = EvaluationDataset()
        dataset.test_cases = test_cases_list

        try:
            logger.info(f"  Iniciando {description}...")
            # Chamada síncrona – os timeouts são gerenciados pelas variáveis de ambiente e pelo cliente Ollama
            result = evaluate(
                dataset.test_cases,
                metrics,
                async_config=AsyncConfig(max_concurrent=1)
            )
            logger.info(f"  ✅ {description} concluído.")
            return result.test_results
        except Exception as e:
            logger.error(f"❌ Erro na avaliação {description}: {e}")
            return None


    async def run(self, num_repeats: int = 10):
        logger.info("🚀 Iniciando pipeline de avaliação...")
        start_time = time.time()
        
        # Geração dos casos
        v1_cases, v9_cases = await self.rag_manager.generate_test_cases(num_repeats=num_repeats)
        self.v1_cases_backup = v1_cases
        self.v9_cases_backup = v9_cases
        logger.info(f"✅ Gerados {len(v1_cases)} casos V1 e {len(v9_cases)} casos V9.")
        
        # Separar por tipo (usando listas, como no original)
        v1_trad = [c for c in v1_cases if c.metadata["test_type"] == "traditional"]
        v1_behav = [c for c in v1_cases if c.metadata["test_type"] == "behavioral"]
        v1_temp = [c for c in v1_cases if c.metadata["test_type"] == "temporal"]
        
        v9_trad = [c for c in v9_cases if c.metadata["test_type"] == "traditional"]
        v9_behav = [c for c in v9_cases if c.metadata["test_type"] == "behavioral"]
        v9_temp = [c for c in v9_cases if c.metadata["test_type"] == "temporal"]

        res_v1_trad, res_v1_behav, res_v1_temp = [], [], []
        res_v9_trad, res_v9_behav, res_v9_temp = [], [], []

        # ====================================================================
        # AVALIAÇÃO RAG V1
        # ====================================================================
        if v1_trad:
            logger.info(f"🏆 Avaliando V1 Tradicional ({len(v1_trad)} iterações)...")
            for metric in create_native_metrics(self.evaluator_v1):
                logger.info(f"  🎯 Métrica: {metric.__class__.__name__}")
                batch_res = await self._safe_evaluate(
                    test_cases_list=v1_trad,
                    metrics=[metric],
                    description=f"V1 Trad - {metric.__class__.__name__}",
                    timeout=300
                )
                if batch_res is not None:
                    if not res_v1_trad:
                        res_v1_trad = batch_res
                    else:
                        for idx, single_res in enumerate(batch_res):
                            res_v1_trad[idx].metrics_data.extend(single_res.metrics_data)
                            if not single_res.success:
                                res_v1_trad[idx].success = False

        # V1 - Comportamental (com novos GEvals)
        if v1_behav:
            logger.info(f"🏆 Avaliando V1 Comportamental ({len(v1_behav)} iterações)...")
            geval_v1 = create_unified_behavioral_geval(self.evaluator_v1)
            geval_rerank_v1 = create_strict_temporal_reranking_geval(self.evaluator_v1)
            geval_fallback_v1 = create_intelligent_fallback_geval(self.evaluator_v1)
            batch_res = await self._safe_evaluate(
                test_cases_list=v1_behav,
                metrics=[geval_v1, geval_rerank_v1, geval_fallback_v1],
                description="V1 Comportamental",
                timeout=600
            )
            if batch_res is not None:
                res_v1_behav = batch_res

        if v1_temp:
            logger.info(f"⏳ Avaliando V1 Temporal ({len(v1_temp)} iterações)...")
            geval_temp_v1 = create_temporal_geval(self.evaluator_v1)
            batch_res = await self._safe_evaluate(
                test_cases_list=v1_temp,
                metrics=[geval_temp_v1],
                description="V1 Temporal",
                timeout=600
            )
            if batch_res is not None:
                res_v1_temp = batch_res

        # ====================================================================
        # AVALIAÇÃO RAG V9
        # ====================================================================
        if v9_trad:
            logger.info(f"🏆 Avaliando V9 Tradicional ({len(v9_trad)} iterações)...")
            for metric in create_native_metrics(self.evaluator_v9):
                logger.info(f"  🎯 Métrica: {metric.__class__.__name__}")
                batch_res = await self._safe_evaluate(
                    test_cases_list=v9_trad,
                    metrics=[metric],
                    description=f"V9 Trad - {metric.__class__.__name__}",
                    timeout=300
                )
                if batch_res is not None:
                    if not res_v9_trad:
                        res_v9_trad = batch_res
                    else:
                        for idx, single_res in enumerate(batch_res):
                            res_v9_trad[idx].metrics_data.extend(single_res.metrics_data)
                            if not single_res.success:
                                res_v9_trad[idx].success = False

        # V9 - Comportamental (com novos GEvals)
        if v9_behav:
            logger.info(f"🏆 Avaliando V9 Comportamental ({len(v9_behav)} iterações)...")
            geval_v9 = create_unified_behavioral_geval(self.evaluator_v9)
            geval_rerank_v9 = create_strict_temporal_reranking_geval(self.evaluator_v9)
            geval_fallback_v9 = create_intelligent_fallback_geval(self.evaluator_v9)
            batch_res = await self._safe_evaluate(
                test_cases_list=v9_behav,
                metrics=[geval_v9, geval_rerank_v9, geval_fallback_v9],
                description="V9 Comportamental",
                timeout=600
            )
            if batch_res is not None:
                res_v9_behav = batch_res

        if v9_temp:
            logger.info(f"⏳ Avaliando V9 Temporal ({len(v9_temp)} iterações)...")
            geval_temp_v9 = create_temporal_geval(self.evaluator_v9)
            batch_res = await self._safe_evaluate(
                test_cases_list=v9_temp,
                metrics=[geval_temp_v9],
                description="V9 Temporal",
                timeout=600
            )
            if batch_res is not None:
                res_v9_temp = batch_res

        elapsed = time.time() - start_time
        logger.info(f"⏱️  Avaliação concluída em {elapsed:.2f} segundos.")

        self._build_and_save_reports(
            res_v1_trad, res_v1_behav, res_v1_temp,
            res_v9_trad, res_v9_behav, res_v9_temp
        )

    # ========================================================================
    # MÉTODOS DE RELATÓRIO (idênticos ao original)
    # ========================================================================
    def _build_and_save_reports(self, r1_t, r1_b, r1_temp, r9_t, r9_b, r9_temp):
        rows = []
        
        v1_t_ref = [c for c in self.v1_cases_backup if c.metadata["test_type"] == "traditional"]
        v1_b_ref = [c for c in self.v1_cases_backup if c.metadata["test_type"] == "behavioral"]
        v1_temp_ref = [c for c in self.v1_cases_backup if c.metadata["test_type"] == "temporal"]
        v9_t_ref = [c for c in self.v9_cases_backup if c.metadata["test_type"] == "traditional"]
        v9_b_ref = [c for c in self.v9_cases_backup if c.metadata["test_type"] == "behavioral"]
        v9_temp_ref = [c for c in self.v9_cases_backup if c.metadata["test_type"] == "temporal"]

        def process_results(results, version_prefix, source_cases_ref):
            if not results:
                return
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

                # Extrair retrieval context (fontes)
                retrieval_context = tc.retrieval_context if (tc and hasattr(tc, 'retrieval_context')) else []
                if isinstance(retrieval_context, list):
                    retrieval_context_str = '; '.join(str(item) for item in retrieval_context)
                else:
                    retrieval_context_str = str(retrieval_context)

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
                existing[f"{version_prefix}_Retrieval_Context"] = retrieval_context_str
                
                metrics_list = getattr(test_result, 'metrics_data', [])
                for metric_obj in metrics_list:
                    original_name = metric_obj.name
                    mapped_name = None
                    for key, mapped in self.name_mapping.items():
                        if key in original_name:
                            mapped_name = mapped
                            break
                    if mapped_name is None:
                        mapped_name = original_name.replace(" ", "_")
                    name = mapped_name

                    score_key = f"{version_prefix}_{name}_Score"
                    reason_key = f"{version_prefix}_{name}_Reason"
                    verbose_key = f"{version_prefix}_{name}_Verbose"
                    total_key = f"{version_prefix}_{name}_Total"
                    positive_key = f"{version_prefix}_{name}_Positive"
                    
                    existing[score_key] = metric_obj.score
                    existing[reason_key] = metric_obj.reason
                    
                    verbose_log = getattr(metric_obj, 'verbose_logs', "")
                    existing[verbose_key] = verbose_log
                    
                    if verbose_log:
                        counts = parse_verbose_log(verbose_log)
                        existing[total_key] = counts.get('total', 0)
                        existing[positive_key] = counts.get('positive', 0)
                    else:
                        existing[total_key] = 0
                        existing[positive_key] = 0

        process_results(r1_t, "V1", v1_t_ref)
        process_results(r1_b, "V1", v1_b_ref)
        process_results(r1_temp, "V1", v1_temp_ref)
        process_results(r9_t, "V9", v9_t_ref)
        process_results(r9_b, "V9", v9_b_ref)
        process_results(r9_temp, "V9", v9_temp_ref)

        # Criação do DataFrame e exportação (idêntico ao original)
        df = pd.DataFrame(rows)
        
        for col in ["V1_Retrieval_Context", "V9_Retrieval_Context"]:
            if col not in df.columns:
                df[col] = ""

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

        logger.info(f"\n🚀 Pipeline concluído. Relatórios salvos em:\n  CSV: {csv_out}\n  TXT: {txt_out}\n  MD: {md_out}")

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
                
                # Exibe as fontes consultadas
                f.write(" [📚 FONTES CONSULTADAS - RAG V1 Vanilla]:\n")
                f.write(f"   {str(r.get('V1_Retrieval_Context', 'N/A')).strip()}\n\n")
                f.write(" [📚 FONTES CONSULTADAS - RAG V9 Temporal]:\n")
                f.write(f"   {str(r.get('V9_Retrieval_Context', 'N/A')).strip()}\n\n")
                
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
                            # Pula as colunas de contexto
                            if metric_name == "Retrieval_Context":
                                continue
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
            f.write(f"# Relatório de Auditoria Comparativa Nativa (DeepEval) - COM REPETIÇÃO (10x)\n\n")
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
# MAIN ASYNC COM FILA DE COMBINAÇÕES (COM REPETIÇÃO)
# ============================================================================

# async def main_queue():
#     from itertools import product
#     repeticao: int = 3   # ajuste conforme necessário

#     modelos_unicos = [
#         "phi3.5:latest",
#         "qwen3:4b-instruct",
#         "mistral:7b-instruct",
#         "granite3.2:8b",
#         "qwen3.5:9b",
#         "phi3:14b"
#     ]
    
#     judge_models = modelos_unicos
#     generator_models = modelos_unicos

#     def get_family(model: str) -> str:
#         model_lower = model.lower()
#         if model_lower.startswith("qwen"): return "qwen"
#         if model_lower.startswith("mistral"): return "mistral"
#         if model_lower.startswith("granite"): return "granite"
#         if model_lower.startswith("phi"): return "phi"
#         return "unknown"

#     all_combinations = list(product(judge_models, generator_models))
#     filtered_combinations = [
#         (judge, gen) for judge, gen in all_combinations
#         if get_family(judge) != get_family(gen)
#     ]

#     logger.info(f"🚀 Total de combinações possíveis: {len(all_combinations)}")
#     logger.info(f"✅ Combinações sem mesma família: {len(filtered_combinations)}")
#     logger.info(f"🔁 Executando fila com repetição ({repeticao} por caso)...\n")

#     for i, (judge, generator) in enumerate(filtered_combinations, 1):
#         logger.info(f"\n{'='*60}")
#         logger.info(f"🔁 Combinação {i}/{len(filtered_combinations)}: Juiz={judge} | Gerador={generator}")
#         logger.info(f"{'='*60}")

#         pipeline = None
#         try:
#             pipeline = NativeComparativePipeline()
#             pipeline.config = EvalConfig(evaluator_model=judge, model_name=generator)
#             pipeline.evaluator_v1 = OllamaEvaluator(model_name=judge, prompt_version="V1", timeout=pipeline.config.evaluator_timeout)
#             pipeline.evaluator_v9 = OllamaEvaluator(model_name=judge, prompt_version="V9", timeout=pipeline.config.evaluator_timeout)

#             await pipeline.run(num_repeats=repeticao)
#             logger.info(f"✅ Combinação concluída: {judge} / {generator}")
#         except Exception as e:
#             import traceback
#             logger.error(f"❌ Erro catastrófico: {e}")
#             traceback.print_exc()
#         finally:
#             if pipeline and hasattr(pipeline, 'rag_manager'):
#                 try:
#                     if pipeline.rag_manager._vanilla:
#                         await pipeline.rag_manager.vanilla.close()
#                     if pipeline.rag_manager._temporal:
#                         await pipeline.rag_manager.temporal.close()
#                 except:
#                     pass
#             del pipeline
#             gc.collect()

#         if i < len(filtered_combinations):
#             temp: int = 60 
#             logger.info(f"⏳ Aguardando {temp} segundos para liberar recursos...")
#             await asyncio.sleep(temp)

#     logger.info("\n🎉 Todas as combinações com repetição foram executadas com sucesso.")


async def main_queue():
    from itertools import product
    import re
    from pathlib import Path

    repeticao: int = 3   # ajuste conforme necessário

    modelos_unicos = [
        "phi3.5:latest",
        "qwen3:4b-instruct",
        "mistral:7b-instruct",
        "granite3.2:8b",
        "qwen3.5:9b",
        "phi3:14b"
    ]

    judge_models = modelos_unicos
    generator_models = modelos_unicos

    def get_family(model: str) -> str:
        model_lower = model.lower()
        if model_lower.startswith("qwen"): return "qwen"
        if model_lower.startswith("mistral"): return "mistral"
        if model_lower.startswith("granite"): return "granite"
        if model_lower.startswith("phi"): return "phi"
        return "unknown"

    # ========================================================================
    # 1. GERA LISTA COMPLETA DE COMBINAÇÕES ESPERADAS
    # ========================================================================
    all_combinations = list(product(judge_models, generator_models))
    filtered_combinations = [
        (judge, gen) for judge, gen in all_combinations
        if get_family(judge) != get_family(gen)
    ]

    logger.info(f"🚀 Total de combinações possíveis: {len(all_combinations)}")
    logger.info(f"✅ Combinações elegíveis (famílias diferentes): {len(filtered_combinations)}")

    # ========================================================================
    # 2. ESCANEIA A PASTA PARA IDENTIFICAR AS JÁ FINALIZADAS
    # ========================================================================
    output_dir = AVALIACAO_DATA / "testes_com_modelos_diferentes" / "com_repeticaoV7"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Conjunto para armazenar as combinações já salvas no formato (judge, generator)
    completed = set()

    # Padrão do nome do arquivo (sem o timestamp e extensão)
    # Exemplo: DEEPEVAL_MIXED_NATIVE_COMPARATIVE_COM_REPETICAO_J_granite3.2_8b_G_mistral_7b-instruct
    pattern = re.compile(r"^DEEPEVAL_MIXED_NATIVE_COMPARATIVE_COM_REPETICAO_J_(.*?)_G_(.*?)_\d{8}_\d{4}\.csv$")

    for file_path in output_dir.glob("DEEPEVAL_MIXED_NATIVE_COMPARATIVE_COM_REPETICAO_*.csv"):
        match = pattern.match(file_path.name)
        if match:
            judge_str = match.group(1)  # ex: "granite3.2_8b"
            gen_str = match.group(2)    # ex: "mistral_7b-instruct"

            # Reconverte o nome do arquivo para o formato original do modelo (troca _ por :)
            # Atenção: isso só funciona porque os modelos não têm underscore no nome.
            judge_original = judge_str.replace("_", ":")
            gen_original = gen_str.replace("_", ":")

            completed.add((judge_original, gen_original))

    logger.info(f"📂 Arquivos encontrados na pasta: {len(completed)} combinações já finalizadas.")

    # ========================================================================
    # 3. FILTRA APENAS AS COMBINAÇÕES FALTANTES
    # ========================================================================
    missing_combinations = [
        (judge, gen) for judge, gen in filtered_combinations
        if (judge, gen) not in completed
    ]

    logger.info(f"⏳ Combinações pendentes: {len(missing_combinations)}")

    if not missing_combinations:
        logger.info("🎉 Todas as combinações elegíveis já foram executadas! Nada a fazer.")
        return

    # Exibe as pendentes para conferência
    for j, g in missing_combinations:
        logger.info(f"  ⏳ Pendente: Juiz={j} | Gerador={g}")

    logger.info(f"🔁 Executando fila com repetição ({repeticao} por caso) apenas para as pendentes...\n")

    # ========================================================================
    # 4. EXECUTA SOMENTE AS PENDENTES
    # ========================================================================
    for i, (judge, generator) in enumerate(missing_combinations, 1):
        logger.info(f"\n{'='*60}")
        logger.info(f"🔁 Combinação {i}/{len(missing_combinations)}: Juiz={judge} | Gerador={generator}")
        logger.info(f"{'='*60}")

        pipeline = None
        try:
            pipeline = NativeComparativePipeline()
            pipeline.config = EvalConfig(evaluator_model=judge, model_name=generator)
            pipeline.evaluator_v1 = OllamaEvaluator(model_name=judge, prompt_version="V1", timeout=pipeline.config.evaluator_timeout)
            pipeline.evaluator_v9 = OllamaEvaluator(model_name=judge, prompt_version="V9", timeout=pipeline.config.evaluator_timeout)

            await pipeline.run(num_repeats=repeticao)
            logger.info(f"✅ Combinação concluída: {judge} / {generator}")
        except Exception as e:
            import traceback
            logger.error(f"❌ Erro catastrófico: {e}")
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

        # Pausa entre combinações (exceto na última)
        if i < len(missing_combinations):
            temp: int = 60
            logger.info(f"⏳ Aguardando {temp} segundos para liberar recursos...")
            await asyncio.sleep(temp)

    logger.info("\n🎉 Todas as combinações pendentes foram executadas com sucesso.")


if __name__ == "__main__":
    asyncio.run(main_queue())