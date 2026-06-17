#!/usr/bin/env python3
"""
UNIFIED EVALUATION SCRIPT: V1 vs V9 (Mixed Fallback Framework Edition) - V5 COMPATIBLE
Fully customized to validate the rules of the second prompt generation without format bias.
Supports command-line arguments for judge and generator models.
Generates CSV, TXT, and Markdown reports natively from consolidated loop data.

DEBUG MODE: roda apenas 1 caso (o primeiro) para depuração.
"""

import asyncio
import gc
import hashlib
import json
import pickle
import sys
import time
import argparse
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
DEBUG_ONE_CASE = True   # <-- Se True, roda apenas o primeiro caso de TEST_SUITE
# ============================================================================


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
        dir_path = AVALIACAO_DATA / "testes_com_modelos_diferentes"
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
        "Evaluate the response based on the following rules:\n"
        "1. For a SPECIFIC SKU query with missing external documentation, the response MUST explicitly state "
        "   that no external documentation was found before providing fallback information.\n"
        "2. For a SERIES query (product line without SKU, e.g., 'Nitro 5'), the response MUST NOT provide specifications. "
        "   It MUST ask for the specific model number (SKU).\n"
        "3. For a COMPARISON query with missing data on one or both SKUs, the response may use fallback but must indicate.\n"
        "4. The response MUST be clean and natural, without any raw system tags like [RAG], [INTERNAL], or structural audit blocks. "
        "   No 'AUDIT:' or 'ANSWER:' headers are allowed."
    )
    return GEval(
        name="Mixed Guardrails (Unified)",
        model=evaluator,
        criteria=criteria,
        evaluation_params=[
            SingleTurnParams.INPUT,
            SingleTurnParams.ACTUAL_OUTPUT
        ],
        evaluation_steps=[
            "Determine query type (SKU, series, comparison, general).",
            "Check compliance with the specific operational rule for that type.",
            "Verify no forbidden raw tags or system processing blocks pollute the text output."
        ],
        threshold=0.8
    )

def create_temporal_geval(evaluator: OllamaEvaluator) -> GEval:
    criteria = (
        "Evaluate the response based on temporal reasoning rules:\n"
        "1. For queries with a reference date, the response should prefer documents from that date or later.\n"
        "2. For future dates (e.g., 2026+), the response must not invent specifications; it should say 'not available' or 'unconfirmed'.\n"
        "3. For comparisons across models/generations, the response must correctly distinguish specifications (e.g., DDR4 vs DDR5).\n"
        "4. For atemporal concepts (thermal throttling, memory types), the response may use general knowledge regardless of document date.\n"
        "5. The response must not hallucinate BIOS versions, future hardware, or outdated specs."
    )
    return GEval(
        name="Temporal Consistency",
        model=evaluator,
        criteria=criteria,
        evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT],
        evaluation_steps=[
            "Check if the response uses the appropriate document recency based on the reference date.",
            "Verify that future-dated queries are handled with caution (no speculation).",
            "Ensure that comparisons respect chronological evolution of specifications.",
            "Penalize hallucinated versions or specs that contradict the temporal context."
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
        # ---------- DEBUG: usa apenas o primeiro caso ----------
        if DEBUG_ONE_CASE:
            test_suite_iter = TEST_SUITE[:1]
            print(f"🐞 DEBUG: rodando apenas 1 caso (primeiro da lista)")
        else:
            test_suite_iter = TEST_SUITE
        # -------------------------------------------------------

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
            batch_res = evaluate(d_v1_behav.test_cases, [geval_v1], async_config=AsyncConfig(max_concurrent=1))
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
            batch_res = evaluate(d_v9_behav.test_cases, [geval_v9], async_config=AsyncConfig(max_concurrent=1))
            res_v9_behav = batch_res.test_results
            print(f"   ✅ V9 comportamental avaliado. Nº resultados: {len(res_v9_behav)}")

        if d_v9_temp.test_cases:
            print("\n⏳ Avaliando V9 MIXED Temporal (GEval Temporal)...")
            geval_temp_v9 = create_temporal_geval(self.evaluator_v9)
            batch_res = evaluate(d_v9_temp.test_cases, [geval_temp_v9], async_config=AsyncConfig(max_concurrent=1))
            res_v9_temp = batch_res.test_results
            print(f"   ✅ V9 temporal avaliado. Nº resultados: {len(res_v9_temp)}")

        # DEBUG: imprimir resumo dos resultados V9
        print("\n🔎 RESUMO DOS RESULTADOS V9:")
        print(f"   res_v9_trad: {len(res_v9_trad)} itens")
        print(f"   res_v9_behav: {len(res_v9_behav)} itens")
        print(f"   res_v9_temp: {len(res_v9_temp)} itens")

        # Compila e grava todos os relatórios
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
                # Tenta obter o caso de referência
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
                    name = metric_obj.name.replace(" ", "_")
                    if "Mixed_Guardrails" in name or "Behavioral" in name:
                        name = "Behavioral_Guardrails"
                    if "Temporal_Consistency" in name:
                        name = "Temporal_Consistency"
                    score_key = f"{version_prefix}_{name}_Score"
                    reason_key = f"{version_prefix}_{name}_Reason"
                    existing[score_key] = metric_obj.score
                    existing[reason_key] = metric_obj.reason
                    print(f"         ✅ {score_key} = {metric_obj.score}")

        process_results(r1_t, "V1", v1_t_ref)
        process_results(r1_b, "V1", v1_b_ref)
        process_results(r1_temp, "V1", v1_temp_ref)
        process_results(r9_t, "V9", v9_t_ref)
        process_results(r9_b, "V9", v9_b_ref)
        process_results(r9_temp, "V9", v9_temp_ref)

        # ====================================================================
        # 🆕 BLOCO DE IMPRESSÃO DETALHADA NO CONSOLE (com verbose completo)
        # ====================================================================
        print("\n" + "=" * 90)
        print("📊 DETALHES POR CASO (CONSOLE) - INCLUINDO VERBOSE COMPLETO")
        print("=" * 90)
        for r in rows:
            print(f"\n🔹 [{r['ID']}] - Tipo: {r['Test_Type']}")
            # Mostra a pergunta (truncada para não poluir muito)
            q = r.get('Query', '')
            if len(q) > 150:
                print(f"   Pergunta: {q[:150]}...")
            else:
                print(f"   Pergunta: {q}")
            # Mostra as respostas (truncadas)
            v1_ans = str(r.get('V1_Answer', 'N/A'))
            v9_ans = str(r.get('V9_Answer', 'N/A'))
            print(f"   V1 Resposta: {v1_ans[:200]}{'...' if len(v1_ans) > 200 else ''}")
            print(f"   V9 Resposta: {v9_ans[:200]}{'...' if len(v9_ans) > 200 else ''}")
            # Para cada versão e métrica, imprime score e razão (verbose) completo
            for version in ['V1', 'V9']:
                print(f"  {version}:")
                for metric in ['Faithfulness', 'Answer_Relevancy', 'Contextual_Relevancy',
                               'Contextual_Precision', 'Contextual_Recall',
                               'Behavioral_Guardrails', 'Temporal_Consistency']:
                    score = r.get(f'{version}_{metric}_Score', 'N/A')
                    reason = r.get(f'{version}_{metric}_Reason', '')
                    if score != 'N/A':
                        print(f"    {metric}: {score:.3f}")
                        if reason:
                            # Exibe o verbose (razão) completo, sem truncamento
                            print(f"      Verbose: {reason}")
            print("-" * 80)

        # Cria DataFrame e salva
        df = pd.DataFrame(rows)
        # Garante colunas para todas as métricas
        ALL_METRICS = [
            'Faithfulness', 'Answer_Relevancy', 'Contextual_Relevancy',
            'Contextual_Precision', 'Contextual_Recall', 'Behavioral_Guardrails',
            'Temporal_Consistency'
        ]
        for version in ['V1', 'V9']:
            for metric in ALL_METRICS:
                col_score = f"{version}_{metric}_Score"
                col_reason = f"{version}_{metric}_Reason"
                if col_score not in df.columns:
                    df[col_score] = np.nan
                if col_reason not in df.columns:
                    df[col_reason] = ""

        combo_id = self.config.combination_id  # se não existir, use timestamp
        csv_out = self.config.output_dir / f"DEEPEVAL_MIXED_NATIVE_DEBUG_{self.config.timestamp}.csv"
        df.to_csv(csv_out, index=False)
        
        # Relatórios TXT e MD (opcionais para debug)
        txt_out = self.config.output_dir / f"RELATORIO_DEBUG_{self.config.timestamp}.txt"
        self._write_txt_report(txt_out, rows, v1_t_ref, v1_b_ref, v1_temp_ref)

        md_out = self.config.output_dir / f"RELATORIO_DEBUG_{self.config.timestamp}.md"
        self._write_md_report(md_out, rows, v1_t_ref, v1_b_ref, v1_temp_ref)

        print(f"\n🚀 Pipeline de debug concluído.")
        print(f"📊 Planilha CSV:  {csv_out}")
        print(f"📝 Relatório TXT: {txt_out}")
        print(f"📝 Relatório MD:  {md_out}")

    # Métodos de escrita (idênticos aos anteriores, apenas adaptados para incluir temp_ref)
    def _write_txt_report(self, path: Path, rows: List[Dict], trad_ref, behav_ref, temp_ref):
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
                f.write("\n Métricas V1:\n")
                for key in sorted(r.keys()):
                    if key.startswith('V1_') and 'Score' in key:
                        f.write(f"   {key}: {r[key]}\n")
                f.write("\n Métricas V9:\n")
                for key in sorted(r.keys()):
                    if key.startswith('V9_') and 'Score' in key:
                        f.write(f"   {key}: {r[key]}\n")
                f.write("\n" + "-" * 80 + "\n")

    def _write_md_report(self, path: Path, rows: List[Dict], trad_ref, behav_ref, temp_ref):
        with open(path, 'w', encoding='utf-8') as f:
            f.write(f"# Relatório Debug\n\n")
            f.write(f"- Data: {self.config.timestamp}\n")
            f.write(f"- Juiz: {self.config.evaluator_model}\n")
            f.write(f"- Gerador: {self.config.model_name}\n")
            f.write("\n## Resultados Individuais\n\n")
            for r in rows:
                f.write(f"### {r['ID']} ({r['Test_Type']})\n")
                f.write(f"**Query:** {r['Query']}\n\n")
                f.write("**V1 Answer:**\n```\n" + str(r.get('V1_Answer', 'N/A')) + "\n```\n")
                f.write("**V9 Answer:**\n```\n" + str(r.get('V9_Answer', 'N/A')) + "\n```\n")
                f.write("**Métricas:**\n")
                f.write("| Métrica | V1 | V9 |\n")
                f.write("|---|---|---|\n")
                for m in ['Faithfulness', 'Answer_Relevancy', 'Contextual_Relevancy', 
                          'Contextual_Precision', 'Contextual_Recall', 'Behavioral_Guardrails', 'Temporal_Consistency']:
                    v1_val = r.get(f'V1_{m}_Score', '')
                    v9_val = r.get(f'V9_{m}_Score', '')
                    f.write(f"| {m} | {v1_val} | {v9_val} |\n")
                f.write("\n---\n")


# ============================================================================
# MAIN ASYNC COM FILA DE COMBINAÇÕES (opcional)
# ============================================================================

async def main_queue():
    import time
    from itertools import product

    # Para debug, podemos rodar apenas uma combinação fixa
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