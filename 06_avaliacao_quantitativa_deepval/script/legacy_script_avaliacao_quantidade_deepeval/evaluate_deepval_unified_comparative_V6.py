#!/usr/bin/env python3
"""
UNIFIED EVALUATION SCRIPT: V1 vs V9 (Mixed Fallback Framework Edition) - V5 COMPATIBLE
Fully customized to validate the rules of the second prompt generation without format bias.
Generates CSV, TXT summary, and Markdown reports natively from consolidated loop data.
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
from deepeval.test_case import SingleTurnParams

# Custom external modules
from core.paths import VALIDACAO_SCRIPT, AVALIACAO_SCRIPT, VETORIZATION_DATA, AVALIACAO_DATA
from dataset_avaliacaoV4 import TEST_SUITE

for path in [VALIDACAO_SCRIPT, AVALIACAO_SCRIPT]:
    if str(path) not in sys.path:
        sys.path.append(str(path))

from RAG_BaseLineV2 import VanillaRAG
# Alterado para importar a versão EQUAL que remove os prefixos rígidos de blocos de auditoria
from RAG_Temporal_V9_4 import SpecialistTimeAwareRAG
from custom_evaluatorV4 import OllamaEvaluator


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
    temporal_use_expansion: bool = True
    temporal_variant: str = "V9_HYBRID_MIXED_AUDITOR"
    model_name: str = "phi3.5:latest"
    temperature: float = 0.0
    search_top_k: int = 50
    
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
# NATIVE METRICS FACTORY & G-EVAL GUARDRAILS (V5 UNIFIED)
# ============================================================================

def create_native_metrics(evaluator: OllamaEvaluator) -> List[Any]:
    return [
        FaithfulnessMetric(threshold=0.85, model=evaluator, include_reason=True),
        AnswerRelevancyMetric(threshold=0.8, model=evaluator, include_reason=True),
        ContextualRelevancyMetric(threshold=0.8, model=evaluator, include_reason=True),
        ContextualPrecisionMetric(threshold=0.8, model=evaluator, include_reason=True),
        ContextualRecallMetric(threshold=0.8, model=evaluator, include_reason=True)
    ]

def create_unified_behavioral_geval(evaluator: OllamaEvaluator) -> GEval:
    """
    Métrica G-Eval unificada da V5. Avalia a aderência comportamental às regras
    de negócio sem penalizar o RAG por diferenças de tags ou formato visual.
    """
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
            
            # Execução assíncrona concorrente das engines de RAG
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
        
        d_v1_trad = EvaluationDataset()
        d_v1_trad.test_cases = [c for c in v1_cases if c.metadata["test_type"] == "traditional"]
        
        d_v1_behav = EvaluationDataset()
        d_v1_behav.test_cases = [c for c in v1_cases if c.metadata["test_type"] == "behavioral"]
        
        d_v9_trad = EvaluationDataset()
        d_v9_trad.test_cases = [c for c in v9_cases if c.metadata["test_type"] == "traditional"]
        
        d_v9_behav = EvaluationDataset()
        d_v9_behav.test_cases = [c for c in v9_cases if c.metadata["test_type"] == "behavioral"]

        res_v1_trad, res_v1_behav = [], []
        res_v9_trad, res_v9_behav = [], []

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

        if d_v9_behav.test_cases:
            print("\n🏆 Avaliando V9 MIXED Comportamental (GEval Unificado)...")
            # Substituída a métrica legada pela versão unificada para evitar viés de cabeçalho
            geval_v9 = create_unified_behavioral_geval(self.evaluator_v9)
            batch_res = evaluate(d_v9_behav.test_cases, [geval_v9], async_config=AsyncConfig(max_concurrent=1))
            res_v9_behav = batch_res.test_results

        # Compila e grava todos os relatórios estruturados (CSV, TXT e MD)
        self._build_and_save_reports(res_v1_trad, res_v1_behav, res_v9_trad, res_v9_behav)

    def _build_and_save_reports(self, r1_t, r1_b, r9_t, r9_b):
        rows = []
        
        v1_t_ref = [c for c in self.v1_cases_backup if c.metadata["test_type"] == "traditional"]
        v1_b_ref = [c for c in self.v1_cases_backup if c.metadata["test_type"] == "behavioral"]
        v9_t_ref = [c for c in self.v9_cases_backup if c.metadata["test_type"] == "traditional"]
        v9_b_ref = [c for c in self.v9_cases_backup if c.metadata["test_type"] == "behavioral"]

        def process_results(results, version_prefix, source_cases_ref):
            for idx, test_result in enumerate(results):
                if idx < len(source_cases_ref):
                    tc = source_cases_ref[idx]
                else:
                    tc = getattr(test_result, 'test_case', None)
                
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
                for metric_obj in metrics_list:
                    name = metric_obj.name.replace(" ", "_")
                    # Normalização do nome para unificar as colunas do relatório final
                    if "Mixed_Guardrails" in name or "Behavioral" in name:
                        name = "Behavioral_Guardrails"
                    existing[f"{version_prefix}_{name}_Score"] = metric_obj.score
                    existing[f"{version_prefix}_{name}_Reason"] = metric_obj.reason

        process_results(r1_t, "V1", v1_t_ref)
        process_results(r1_b, "V1", v1_b_ref)
        process_results(r9_t, "V9", v9_t_ref)
        process_results(r9_b, "V9", v9_b_ref)

        # 1. Exportação do CSV Principal
        df = pd.DataFrame(rows)
        csv_out = self.config.output_dir / f"DEEPEVAL_MIXED_NATIVE_COMPARATIVE_{self.config.timestamp}.csv"
        df.to_csv(csv_out, index=False)
        
        # 2. Geração da Versão TXT Detalhada
        txt_out = self.config.output_dir / f"RELATORIO_COMPARATIVO_{self.config.timestamp}.txt"
        self._write_txt_report(txt_out, rows, v1_t_ref, v1_b_ref)

        # 3. Geração da Versão Markdown (MD) para Visualização Limpa
        md_out = self.config.output_dir / f"RELATORIO_COMPARATIVO_{self.config.timestamp}.md"
        self._write_md_report(md_out, rows, v1_t_ref, v1_b_ref)

        print(f"\n🚀 Pipeline adaptado para os Prompts MIXED concluído com sucesso.")
        print(f"📊 Planilha CSV:  {csv_out}")
        print(f"📝 Relatório TXT: {txt_out}")
        print(f"📝 Relatório MD:  {md_out}")

    def _write_txt_report(self, path: Path, rows: List[Dict], trad_ref, behav_ref):
        with open(path, 'w', encoding='utf-8') as f:
            f.write("=" * 90 + "\n")
            f.write(f"RELATÓRIO QUANTITATIVO COMPARATIVO DE CORRIDA NATIVA (DEEPEVAL) - {self.config.timestamp}\n")
            f.write("=" * 90 + "\n")
            f.write(f"Modelo Avaliador: {self.config.evaluator_model}\n")
            f.write(f"Modelo Base RAG:  {self.config.model_name}\n")
            f.write(f"Total Casos Teste: {len(rows)} (Tradicionais: {len(trad_ref)} | Comportamentais: {len(behav_ref)})\n")
            f.write("-" * 90 + "\n\n")

            for r in rows:
                f.write(f"▶️ ID: {r['ID']} | Tipo: {r['Test_Type'].upper()}\n")
                f.write(f" 💬 Query: {r['Query']}\n\n")
                
                f.write(" [🤖 RESPOSTA - RAG V1 VANILLA Mixed]:\n")
                f.write(f"   {str(r.get('V1_Answer', 'N/A')).strip()}\n")
                if r['Test_Type'] == "behavioral":
                    f.write(f"   📊 Score Comportamental V1: {r.get('V1_Behavioral_Guardrails_Score', 0.0)}\n")
                    f.write(f"   ℹ️ Motivo Auditoria: {r.get('V1_Behavioral_Guardrails_Reason', '')}\n")
                else:
                    f.write("   📊 Métricas Detalhadas:\n")
                    for m in ["Faithfulness", "Answer_Relevancy", "Contextual_Relevancy", "Contextual_Precision", "Contextual_Recall"]:
                        f.write(f"      ├── {m}: {r.get(f'V1_{m}_Score', 0.0):.2f} | Reason: {r.get(f'V1_{m}_Reason', 'N/A')}\n")
                
                f.write("\n [🧠 RESPOSTA - RAG V9 TEMPORAL Mixed]:\n")
                f.write(f"   {str(r.get('V9_Answer', 'N/A')).strip()}\n")
                if r['Test_Type'] == "behavioral":
                    f.write(f"   📊 Score Comportamental V9: {r.get('V9_Behavioral_Guardrails_Score', 0.0)}\n")
                    f.write(f"   ℹ️ Motivo Auditoria: {r.get('V9_Behavioral_Guardrails_Reason', '')}\n")
                else:
                    f.write("   📊 Métricas Detalhadas:\n")
                    for m in ["Faithfulness", "Answer_Relevancy", "Contextual_Relevancy", "Contextual_Precision", "Contextual_Recall"]:
                        f.write(f"      ├── {m}: {r.get(f'V9_{m}_Score', 0.0):.2f} | Reason: {r.get(f'V9_{m}_Reason', 'N/A')}\n")
                f.write("\n" + "-" * 80 + "\n")

            f.write("\n" + "=" * 90 + "\n")
            f.write("📊 RESUMO CONSOLIDADO DAS MÉTRICAS\n")
            f.write("=" * 90 + "\n")
            
            trad_rows = [r for r in rows if r["Test_Type"] == "traditional"]
            if trad_rows:
                f.write("\n📈 MÉTRICAS TRADICIONAIS MÉDIAS (DeepEval):\n")
                for m in ["Faithfulness", "Answer_Relevancy", "Contextual_Relevancy", "Contextual_Precision", "Contextual_Recall"]:
                    v1_scores = [r[f"V1_{m}_Score"] for r in trad_rows if f"V1_{m}_Score" in r]
                    v9_scores = [r[f"V9_{m}_Score"] for r in trad_rows if f"V9_{m}_Score" in r]
                    v1_avg = np.mean(v1_scores) if v1_scores else 0.0
                    v9_avg = np.mean(v9_scores) if v9_scores else 0.0
                    diff = v9_avg - v1_avg
                    arrow = "↑" if diff > 0 else "↓" if diff < 0 else "→"
                    f.write(f"  ├── {m:<22}: V1={v1_avg:.3f} {arrow} V9={v9_avg:.3f} (Δ {diff:+.3f})\n")
            
            behav_rows = [r for r in rows if r["Test_Type"] == "behavioral"]
            if behav_rows:
                f.write("\n📈 ACURÁCIA COMPORTAMENTAL (G-Eval Guardrails):\n")
                v1_b_scores = [r["V1_Behavioral_Guardrails_Score"] for r in behav_rows if "V1_Behavioral_Guardrails_Score" in r]
                v9_b_scores = [r["V9_Behavioral_Guardrails_Score"] for r in behav_rows if "V9_Behavioral_Guardrails_Score" in r]
                v1_b_avg = np.mean(v1_b_scores) if v1_b_scores else 0.0
                v9_b_avg = np.mean(v9_b_scores) if v9_b_scores else 0.0
                f.write(f"  ├── Adesão Regras V1 (Vanilla) : {v1_b_avg*100:.1f}%\n")
                f.write(f"  └── Adesão Regras V9 (Temporal): {v9_b_avg*100:.1f}%\n")

    def _write_md_report(self, path: Path, rows: List[Dict], trad_ref, behav_ref):
        with open(path, 'w', encoding='utf-8') as f:
            f.write(f"# Relatório de Auditoria Comparativa Nativa (DeepEval)\n\n")
            f.write(f"- **Data de Execução:** {self.config.timestamp}\n")
            f.write(f"- **Fase Contextual:** Tradicionais ({len(trad_ref)}) | Comportamentais ({len(behav_ref)})\n\n")
            
            f.write("## 📊 Tabela Resumo das Médias\n\n")
            f.write("| Métrica Base | Média V1 (Vanilla) | Média V9 (Temporal) | Variação Líquida |\n")
            f.write("|---|---|---|---|\n")
            
            trad_rows = [r for r in rows if r["Test_Type"] == "traditional"]
            if trad_rows:
                for m in ["Faithfulness", "Answer_Relevancy", "Contextual_Relevancy", "Contextual_Precision", "Contextual_Recall"]:
                    v1_scores = [r[f"V1_{m}_Score"] for r in trad_rows if f"V1_{m}_Score" in r]
                    v9_scores = [r[f"V9_{m}_Score"] for r in trad_rows if f"V9_{m}_Score" in r]
                    v1_avg = np.mean(v1_scores) if v1_scores else 0.0
                    v9_avg = np.mean(v9_scores) if v9_scores else 0.0
                    diff = v9_avg - v1_avg
                    emoji = "🟢" if diff > 0.02 else "🔴" if diff < -0.02 else "⚪"
                    f.write(f"| {m} | {v1_avg:.3f} | {v9_avg:.3f} | {emoji} {diff:+.3f} |\n")
            
            behav_rows = [r for r in rows if r["Test_Type"] == "behavioral"]
            if behav_rows:
                v1_b_scores = [r["V1_Behavioral_Guardrails_Score"] for r in behav_rows if "V1_Behavioral_Guardrails_Score" in r]
                v9_b_scores = [r["V9_Behavioral_Guardrails_Score"] for r in behav_rows if "V9_Behavioral_Guardrails_Score" in r]
                v1_b_avg = np.mean(v1_b_scores) if v1_b_scores else 0.0
                v9_b_avg = np.mean(v9_b_scores) if v9_b_scores else 0.0
                diff_b = v9_b_avg - v1_b_avg
                emoji_b = "🟢" if diff_b > 0.02 else "🔴" if diff_b < -0.02 else "⚪"
                f.write(f"| **Behavioral Guardrails (G-Eval)** | {v1_b_avg:.3f} | {v9_b_avg:.3f} | {emoji_b} {diff_b:+.3f} |\n")


if __name__ == "__main__":
    asyncio.run(NativeComparativePipeline().run())