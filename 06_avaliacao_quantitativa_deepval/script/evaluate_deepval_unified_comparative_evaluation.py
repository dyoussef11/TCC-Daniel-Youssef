#!/usr/bin/env python3
"""unified_comparative_evaluation.py - Avaliação comparativa V1 (Vanilla) vs V9 (Temporal)
   Script unificado com todas as classes e funções necessárias.
"""

import asyncio
import hashlib
import pickle
import re
import time
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from contextlib import asynccontextmanager

import pandas as pd
import numpy as np
from tqdm import tqdm

# Dependências externas (assumidas disponíveis)
from deepeval.test_case import LLMTestCase
from deepeval.metrics import (
    ContextualPrecisionMetric,
    ContextualRelevancyMetric,
    ContextualRecallMetric,
    FaithfulnessMetric,
    AnswerRelevancyMetric,
)
from custom_evaluatorV2Backup import OllamaEvaluator
from dataset_avaliacaoV4 import TEST_SUITE
from core.paths import VALIDACAO_SCRIPT, AVALIACAO_SCRIPT
import sys
sys.path.append(str(VALIDACAO_SCRIPT))
sys.path.append(str(AVALIACAO_SCRIPT))
from RAG_BaseLine import VanillaRAG
from RAG_Temporal_V9_3 import SpecialistTimeAwareRAG

# ============================================================================
# Configuração
# ============================================================================
@dataclass
class EvalConfig:
    """Configuração centralizada para avaliação comparativa"""
    base_path: Path = Path(__file__).parent / "base_conhecimento_multilingueV9.json"
    evaluator_model: str = "qwen3:4b-instruct"
    cache_dir: Path = Path("./cache")
    embedding_cache_size: int = 1000
    vanilla_use_expansion: bool = False
    temporal_use_expansion: bool = True
    temporal_variant: str = "V9_HYBRID_MIXED_AUDITOR"
    model_name: str = "phi3.5:latest"
    temperature: float = 0.0
    top_p: float = 0.9
    search_top_k: int = 20
    concurrent_metrics: int = 3
    metric_thresholds: Dict[str, float] = field(default_factory=lambda: {
        "C_Precision": 0.8,
        "C_Relevancia": 0.8,
        "C_Recall": 0.8,
        "Faithfulness": 0.9,
        "Answer_Rel": 0.8
    })

    @property
    def timestamp(self) -> str:
        return datetime.now().strftime("%Y%m%d_%H%M")

    @property
    def output_dir(self) -> Path:
        dir_path = Path("./resultados")
        dir_path.mkdir(parents=True, exist_ok=True)
        return dir_path


# ============================================================================
# Helpers
# ============================================================================
def extract_sku_from_query(query: str) -> Optional[str]:
    patterns = [
        r'[A-Z]{2,3}[-]?\d{3}[-]?\d{2,4}',
        r'[A-Z]{2,3}\s\d{3}\s\d{4}',
        r'[A-Z]{2,3}\d{3}[A-Z]?\d{2,4}',
    ]
    for pattern in patterns:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            return match.group(0)
    return None


def format_duration(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    parts = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if secs > 0 or not parts:
        parts.append(f"{secs}s")
    return " ".join(parts)


# ============================================================================
# Cache de embeddings
# ============================================================================
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

    def _load_existing(self) -> None:
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

    def set(self, query: str, embedding: np.ndarray) -> None:
        key = self._get_key(query)
        if len(self._cache) >= self.max_size:
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
            (self.cache_dir / f"{oldest_key}.pkl").unlink(missing_ok=True)
        self._cache[key] = embedding.copy()
        with open(self._get_path(key), 'wb') as f:
            pickle.dump(embedding, f)

    def stats(self) -> Dict:
        return {"size": len(self._cache), "max_size": self.max_size, "directory": str(self.cache_dir)}


# ============================================================================
# Analisador comportamental
# ============================================================================
class BehavioralTestAnalyzer:
    def analyze(self, test_case: Dict, response_v1: str, response_v9: str) -> Tuple[bool, bool, str, str]:
        expected = test_case.get("expected_behavior", "should_admit_unavailability")
        forbidden = test_case.get("forbidden_patterns", [])
        required = test_case.get("required_patterns", [])
        min_required = test_case.get("min_required_matches", len(required))

        def check(response: str) -> Tuple[bool, str]:
            resp_lower = response.casefold()
            forbidden_found = [p for p in forbidden if p.lower() in resp_lower]
            required_found = [p for p in required if p.lower() in resp_lower]

            behaviors = {
                "should_admit_unavailability": lambda: (len(required_found) >= min_required) and not forbidden_found,
                "should_admit_unavailability_or_fallback": lambda: (
                    (len(required_found) >= min_required) and
                    not any(sku in resp_lower for sku in ["an515-57", "an515-58", "g7 7590", "15ach6h"])
                ),
                "should_ask_for_sku": lambda: (len(required_found) >= min_required) and not forbidden_found,
                "should_explain_concept": lambda: len(required_found) >= min_required,
                "should_admit_cannot_compare": lambda: (len(required_found) >= min_required) and not forbidden_found,
                "should_acknowledge_future_or_unavailable": lambda: (len(required_found) >= min_required) and not forbidden_found
            }
            passed = behaviors.get(expected, lambda: False)()
            reason = f"Required: {required_found[:3]}. Forbidden: {forbidden_found[:3] if forbidden_found else 'none'}"
            return passed, reason

        passed_v1, reason_v1 = check(response_v1)
        passed_v9, reason_v9 = check(response_v9)

        # Verificação adicional de integridade do SKU
        target_sku = extract_sku_from_query(test_case["input"])
        found_sku_v9 = extract_sku_from_query(response_v9)
        if target_sku and found_sku_v9 and target_sku.lower() != found_sku_v9.lower():
            passed_v9 = False
            reason_v9 += " | CRITICAL FAILURE: SKU Mismatch detected."

        return passed_v1, passed_v9, reason_v1, reason_v9


# ============================================================================
# Avaliador de métricas DeepEval
# ============================================================================
class ComparativeMetricEvaluator:
    def __init__(self, config: EvalConfig):
        self.config = config
        self.semaphore = asyncio.Semaphore(config.concurrent_metrics)
        self.evaluator_v1 = OllamaEvaluator(prompt_version="V1")
        self.evaluator_v9 = OllamaEvaluator(prompt_version="V9")
        self._init_metrics()

    def _init_metrics(self):
        self.metrics_v1 = {
            "Faithfulness": FaithfulnessMetric(threshold=self.config.metric_thresholds["Faithfulness"],
                                               model=self.evaluator_v1, include_reason=True),
            "Answer_Rel": AnswerRelevancyMetric(threshold=self.config.metric_thresholds["Answer_Rel"],
                                               model=self.evaluator_v1, include_reason=True),
            "C_Relevancia": ContextualRelevancyMetric(threshold=self.config.metric_thresholds["C_Relevancia"],
                                                     model=self.evaluator_v1, include_reason=True),
            "C_Precision": ContextualPrecisionMetric(threshold=self.config.metric_thresholds["C_Precision"],
                                                    model=self.evaluator_v1, include_reason=True),
            "C_Recall": ContextualRecallMetric(threshold=self.config.metric_thresholds["C_Recall"],
                                              model=self.evaluator_v1, include_reason=True)
        }
        self.metrics_v9 = {
            "Faithfulness": FaithfulnessMetric(threshold=self.config.metric_thresholds["Faithfulness"],
                                               model=self.evaluator_v9, include_reason=True),
            "Answer_Rel": AnswerRelevancyMetric(threshold=self.config.metric_thresholds["Answer_Rel"],
                                               model=self.evaluator_v9, include_reason=True),
            "C_Relevancia": ContextualRelevancyMetric(threshold=self.config.metric_thresholds["C_Relevancia"],
                                                     model=self.evaluator_v9, include_reason=True),
            "C_Precision": ContextualPrecisionMetric(threshold=self.config.metric_thresholds["C_Precision"],
                                                    model=self.evaluator_v9, include_reason=True),
            "C_Recall": ContextualRecallMetric(threshold=self.config.metric_thresholds["C_Recall"],
                                              model=self.evaluator_v9, include_reason=True)
        }

    async def evaluate_both(self, case_v1: LLMTestCase, case_v9: LLMTestCase,
                            pbar: Optional[tqdm] = None) -> Tuple[Dict, Dict]:
        results_v1 = {}
        results_v9 = {}
        tasks = []
        metric_names = list(self.metrics_v1.keys())
        for name in metric_names:
            tasks.append(self._measure(self.metrics_v1[name], case_v1, pbar))
            tasks.append(self._measure(self.metrics_v9[name], case_v9, pbar))
        raw_results = await asyncio.gather(*tasks)
        for i, name in enumerate(metric_names):
            v1_idx = i * 2
            v9_idx = i * 2 + 1
            results_v1[name] = {"score": raw_results[v1_idx][0], "reason": raw_results[v1_idx][1]}
            results_v9[name] = {"score": raw_results[v9_idx][0], "reason": raw_results[v9_idx][1]}
        return results_v1, results_v9

    async def _measure(self, metric, test_case: LLMTestCase, pbar=None) -> Tuple[float, str]:
        async with self.semaphore:
            metric_name = metric.__class__.__name__
            version = getattr(metric.model, 'prompt_version', 'Unknown')
            if pbar:
                pbar.write(f"   [RUNNING] {metric_name} for {version}...")
            try:
                await asyncio.to_thread(metric.measure, test_case)
                reason = self._extract_reason(metric)
                if "validation error" in reason.lower() or "field required" in reason.lower():
                    return 0.0, f"Erro de validação: {reason[:200]}"
                return float(metric.score), reason
            except Exception as e:
                error_msg = str(e)
                if "validation error" in error_msg:
                    return 0.0, f"Erro de validação DeepEval: {error_msg[:200]}"
                return 0.0, f"Erro: {error_msg[:100]}"

    def _extract_reason(self, metric) -> str:
        if hasattr(metric, 'reason') and metric.reason:
            return str(metric.reason).replace('\n', ' ')
        if hasattr(metric, 'verdicts') and metric.verdicts:
            reasons = []
            for v in metric.verdicts[:3]:
                r = getattr(v, 'reason', None)
                if r:
                    reasons.append(str(r)[:200])
            return " | ".join(reasons) if reasons else "No reason"
        return "No reason available"


# ============================================================================
# Gerenciador de RAGs (V1 e V9)
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
            print("🔄 Carregando RAG Vanilla (V1 - SEM expansão)...")
            self._vanilla = VanillaRAG(self.base_path, embedding_cache=self.embedding_cache,
                                       use_expansion=self.config.vanilla_use_expansion)
        return self._vanilla

    @property
    def temporal(self) -> SpecialistTimeAwareRAG:
        if self._temporal is None:
            print("🔄 Carregando RAG Temporal (V9 - COM expansão)...")
            self._temporal = SpecialistTimeAwareRAG(self.base_path, variant_name=self.config.temporal_variant,
                                                    embedding_cache=self.embedding_cache,
                                                    use_expansion=self.config.temporal_use_expansion)
            self._temporal.current_model = self.config.model_name
            self._temporal.temperature = self.config.temperature
            self._temporal.search_top_k = self.config.search_top_k
        return self._temporal

    async def search_both(self, query: str, ref_date: str) -> tuple:
        v1_task = self.vanilla.search(query)
        v9_task = self.temporal.search(query, ref_date)
        results = await asyncio.gather(v1_task, v9_task)
        return results[0], results[1]


# ============================================================================
# Carregador do suite de testes (wrapper para TEST_SUITE)
# ============================================================================
class TestSuiteLoader:
    @staticmethod
    def get_traditional_tests() -> List[Dict]:
        return [t for t in TEST_SUITE if t.get("test_type") != "behavioral"]

    @staticmethod
    def get_behavioral_tests() -> List[Dict]:
        return [t for t in TEST_SUITE if t.get("test_type") == "behavioral"]

    @staticmethod
    def get_stats() -> Dict:
        traditional = TestSuiteLoader.get_traditional_tests()
        behavioral = TestSuiteLoader.get_behavioral_tests()
        return {
            "total": len(TEST_SUITE),
            "traditional": len(traditional),
            "behavioral": len(behavioral),
        }


# ============================================================================
# Gerador de relatórios
# ============================================================================
class ReportGenerator:
    def __init__(self, output_dir: Path, timestamp: str):
        self.output_dir = output_dir
        self.timestamp = timestamp
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_all_reports(self, results_table: List[Dict], config: EvalConfig, test_suite_stats: Dict) -> Dict:
        return {
            "csv": self._generate_csv(results_table),
            "txt": self._generate_txt(results_table, config, test_suite_stats),
        }

    def _generate_csv(self, results_table: List[Dict]) -> Path:
        csv_path = self.output_dir / f"COMPARATIVO_V1_VS_V9_{self.timestamp}.csv"
        pd.DataFrame(results_table).to_csv(csv_path, index=False)
        return csv_path

    def _generate_txt(self, results_table: List[Dict], config: EvalConfig, test_suite_stats: Dict) -> Path:
        txt_path = self.output_dir / f"RELATORIO_COMPARATIVO_{self.timestamp}.txt"
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("RELATÓRIO COMPARATIVO: V1 (Vanilla) vs V9 (Temporal)\n")
            f.write("=" * 80 + "\n")
            f.write(f"Data: {self.timestamp}\n")
            f.write(f"Base: {config.base_path}\n")
            f.write(f"Avaliador: {config.evaluator_model}\n")
            f.write(f"Modelo LLM: {config.model_name}\n")
            f.write(f"Temperature: {config.temperature}\n")
            f.write("-" * 80 + "\n")
            f.write(f"Total de casos: {test_suite_stats['total']}\n")
            f.write(f"├── Tradicionais: {test_suite_stats['traditional']}\n")
            f.write(f"└── Comportamentais: {test_suite_stats['behavioral']}\n")
            f.write("=" * 80 + "\n\n")

            for row in results_table:
                self._write_txt_case(f, row)

            # Resumo final
            traditional = [r for r in results_table if r.get("Test_Type") != "behavioral"]
            if traditional:
                f.write("\n📊 MÉTRICAS MÉDIAS:\n")
                for metric in ["Faithfulness", "Answer_Rel", "C_Relevancia", "C_Precision", "C_Recall"]:
                    v1_scores = [r.get(f"V1_{metric}_Score", 0) for r in traditional if isinstance(r.get(f"V1_{metric}_Score"), (int, float))]
                    v9_scores = [r.get(f"V9_{metric}_Score", 0) for r in traditional if isinstance(r.get(f"V9_{metric}_Score"), (int, float))]
                    if v1_scores and v9_scores:
                        v1_avg = sum(v1_scores) / len(v1_scores)
                        v9_avg = sum(v9_scores) / len(v9_scores)
                        variation = v9_avg - v1_avg
                        arrow = "↑" if variation > 0 else "↓" if variation < 0 else "→"
                        f.write(f"  {metric}: V1={v1_avg:.3f} {arrow} V9={v9_avg:.3f} (Δ {variation:+.3f})\n")
            f.write("\n🎯 RECOMENDAÇÃO:\n   ✅ Use V9 para precisão com SKU; use V1 para chat geral.\n")
        return txt_path

    def _write_txt_case(self, f, row: Dict):
        f.write(f"\n{'='*60}\n")
        f.write(f"ID: {row.get('ID', 'unknown')}\n")
        f.write(f"Test Type: {row.get('Test_Type', 'traditional')}\n")
        f.write(f"Query: {row.get('Query', '')}\n")
        f.write(f"\n--- V1 (VANILLA) ---\n")
        f.write(f"Answer: {row.get('V1_Answer', '')[:800]}\n")
        if row.get('Test_Type') == 'behavioral':
            f.write(f"Behavioral Passed: {row.get('V1_Behavioral_Passed', False)}\n")
            f.write(f"Behavioral Reason: {row.get('V1_Behavioral_Reason', '')}\n")
        else:
            f.write("\n--- V1 MÉTRICAS ---\n")
            for metric in ["Faithfulness", "Answer_Rel", "C_Relevancia", "C_Precision", "C_Recall"]:
                score = row.get(f"V1_{metric}_Score", 0)
                reason = row.get(f"V1_{metric}_Reason", "No reason")
                f.write(f"{metric}: {score:.3f}\n  Reason: {reason[:500]}\n")
        f.write(f"\n--- V9 (TEMPORAL) ---\n")
        f.write(f"Answer: {row.get('V9_Answer', '')[:800]}\n")
        if row.get('Test_Type') == 'behavioral':
            f.write(f"Behavioral Passed: {row.get('V9_Behavioral_Passed', False)}\n")
            f.write(f"Behavioral Reason: {row.get('V9_Behavioral_Reason', '')}\n")
        else:
            f.write("\n--- V9 MÉTRICAS ---\n")
            for metric in ["Faithfulness", "Answer_Rel", "C_Relevancia", "C_Precision", "C_Recall"]:
                score = row.get(f"V9_{metric}_Score", 0)
                reason = row.get(f"V9_{metric}_Reason", "No reason")
                f.write(f"{metric}: {score:.3f}\n  Reason: {reason}\n")
        f.write("-" * 60 + "\n")


# ============================================================================
# Impressão de resumo no console
# ============================================================================
class SummaryPrinter:
    @staticmethod
    def print_summary(results_table: List[Dict]):
        print("\n" + "=" * 80)
        print("✅ AVALIAÇÃO COMPARATIVA CONCLUÍDA")
        print("=" * 80)

        traditional = [r for r in results_table if r.get("Test_Type") != "behavioral"]
        if traditional:
            print("\n📊 ANÁLISE DE GANHO DO V9 SOBRE V1:")
            for metric in ["Faithfulness", "Answer_Rel", "C_Relevancia"]:
                v1_scores = [r.get(f"V1_{metric}_Score", 0) for r in traditional if isinstance(r.get(f"V1_{metric}_Score"), (int, float))]
                v9_scores = [r.get(f"V9_{metric}_Score", 0) for r in traditional if isinstance(r.get(f"V9_{metric}_Score"), (int, float))]
                if v1_scores and v9_scores:
                    v1_avg = sum(v1_scores) / len(v1_scores)
                    v9_avg = sum(v9_scores) / len(v9_scores)
                    gain = v9_avg - v1_avg
                    gain_pct = (gain / v1_avg * 100) if v1_avg > 0 else 0
                    symbol = "🟢" if gain > 0.05 else "🔴" if gain < -0.05 else "⚪"
                    print(f"   {symbol} {metric}: V1={v1_avg:.3f} → V9={v9_avg:.3f} ({gain:+.3f} / {gain_pct:+.1f}%)")

        behavioral = [r for r in results_table if r.get("Test_Type") == "behavioral"]
        if behavioral:
            v1_passed = sum(1 for r in behavioral if r.get("V1_Behavioral_Passed"))
            v9_passed = sum(1 for r in behavioral if r.get("V9_Behavioral_Passed"))
            print(f"\n📊 TESTES COMPORTAMENTAIS ({len(behavioral)} casos):")
            print(f"   V1 (Vanilla): {v1_passed}/{len(behavioral)} ({v1_passed/len(behavioral)*100:.0f}%)")
            print(f"   V9 (Temporal): {v9_passed}/{len(behavioral)} ({v9_passed/len(behavioral)*100:.0f}%)")

        print("\n🎯 RECOMENDAÇÃO:")
        print("   ✅ Use V9 (Temporal) para: suporte com SKU, e-commerce, precisão")
        print("   ✅ Use V1 (Vanilla) para: chat geral, troubleshooting conceitual")


# ============================================================================
# Pipeline principal unificado
# ============================================================================
class ComparativeEvaluationPipeline:
    def __init__(self):
        self.config = EvalConfig()
        self.embedding_cache = EmbeddingCache(self.config.cache_dir, self.config.embedding_cache_size)
        self.rag_manager = ComparativeRAGManager(self.config.base_path, self.config, self.embedding_cache)
        self.metric_evaluator = ComparativeMetricEvaluator(self.config)
        self.behavioral_analyzer = BehavioralTestAnalyzer()
        self.csv_path = self.config.output_dir / f"COMPARATIVO_V1_VS_V9_{self.config.timestamp}.csv"
        self.txt_path = self.config.output_dir / f"RELATORIO_COMPARATIVO_{self.config.timestamp}.txt"

    async def run(self):
        self._print_header()
        results_table = []
        test_suite_stats = TestSuiteLoader.get_stats()

        with open(self.txt_path, 'w', encoding='utf-8') as f_report:
            self._write_report_header(f_report)
            with tqdm(TEST_SUITE, desc="Avaliando") as pbar:
                for test_case in pbar:
                    row = await self._process_case(test_case, f_report, pbar)
                    results_table.append(row)
                    pd.DataFrame(results_table).to_csv(self.csv_path, index=False)
            self._write_recommendation(f_report)

        SummaryPrinter.print_summary(results_table)
        print(f"\n📁 CSV: {self.csv_path}")
        print(f"📁 Relatório: {self.txt_path}")

    async def _process_case(self, test_case: Dict, f_report, pbar) -> Dict:
        query = test_case["input"]
        ref_date = test_case.get("reference_date", "2026-03-12")
        test_type = test_case.get("test_type", "traditional")

        pbar.write(f"\n📝 {test_case['id']}: {query}...")
        res_v1, res_v9 = await self.rag_manager.search_both(query, ref_date)

        case_v1 = LLMTestCase(input=query, actual_output=res_v1["answer"],
                              retrieval_context=res_v1.get("sources", [])[:5],
                              expected_output=test_case.get("expected_output"))
        case_v9 = LLMTestCase(input=query, actual_output=res_v9["answer"],
                              retrieval_context=res_v9.get("sources", [])[:5],
                              expected_output=test_case.get("expected_output"))

        try:
            metrics_v1, metrics_v9 = await self.metric_evaluator.evaluate_both(case_v1, case_v9, pbar)
        except Exception as e:
            pbar.write(f"   ⚠️ ERRO nas métricas: {str(e)}")
            metrics_v1 = {name: {"score": 0.0, "reason": f"Erro: {str(e)}"}
                          for name in ["Faithfulness", "Answer_Rel", "C_Relevancia", "C_Precision", "C_Recall"]}
            metrics_v9 = metrics_v1.copy()

        behav_v1, behav_v9, reason_v1, reason_v9 = self.behavioral_analyzer.analyze(test_case, res_v1["answer"], res_v9["answer"])

        row = self._build_result_row(test_case, test_type, query, res_v1, res_v9,
                                     behav_v1, behav_v9, reason_v1, reason_v9,
                                     metrics_v1, metrics_v9)
        self._write_case_report(f_report, test_case, query, ref_date,
                                res_v1, res_v9, test_type,
                                behav_v1, behav_v9, reason_v1, reason_v9,
                                metrics_v1, metrics_v9)
        return row

    def _build_result_row(self, test_case, test_type, query,
                          res_v1, res_v9,
                          behav_v1, behav_v9, reason_v1, reason_v9,
                          metrics_v1, metrics_v9) -> Dict:
        row = {
            "ID": test_case.get("id", "unknown"),
            "Test_Type": test_type,
            "Query": query,
            "V1_Answer": res_v1["answer"],
            "V1_Behavioral_Passed": behav_v1,
            "V1_Behavioral_Reason": reason_v1,
            "V9_Answer": res_v9["answer"],
            "V9_Behavioral_Passed": behav_v9,
            "V9_Behavioral_Reason": reason_v9,
            "Expected_Behavior": test_case.get("expected_behavior", "")
        }
        for name, data in metrics_v1.items():
            row[f"V1_{name}_Score"] = data["score"]
            row[f"V1_{name}_Reason"] = data["reason"]
        for name, data in metrics_v9.items():
            row[f"V9_{name}_Score"] = data["score"]
            row[f"V9_{name}_Reason"] = data["reason"]
        return row

    def _print_header(self):
        print("\n" + "=" * 80)
        print("🚀 AVALIAÇÃO COMPARATIVA: V1 (Vanilla) vs V9 (Temporal)")
        print(f"📍 Data: {self.config.timestamp}")
        print(f"📊 Casos: {len(TEST_SUITE)}")
        stats = TestSuiteLoader.get_stats()
        print(f"   - Tradicionais: {stats['traditional']}")
        print(f"   - Comportamentais: {stats['behavioral']}")
        print("=" * 80)

    def _write_report_header(self, f_report):
        f_report.write(f"RELATÓRIO COMPARATIVO V1 vs V9\nData: {self.config.timestamp}\nBase: {self.config.base_path}\n")
        f_report.write("=" * 80 + "\n\n")

    def _write_recommendation(self, f_report):
        f_report.write("\n" + "=" * 80 + "\nRECOMENDAÇÃO FINAL\n" + "=" * 80 + "\n")
        f_report.write("✅ V9 (Temporal) → Use para: suporte com SKU, e-commerce, precisão\n")
        f_report.write("✅ V1 (Vanilla) → Use para: chat geral, troubleshooting, conceitos\n")

    def _write_case_report(self, f_report, test_case, query, ref_date,
                           res_v1, res_v9, test_type,
                           behav_v1, behav_v9, reason_v1, reason_v9,
                           metrics_v1, metrics_v9):
        f_report.write(f"\n{'='*80}\nID: {test_case.get('id')}\nQuery: {query}\nReference Date: {ref_date}\n")
        f_report.write(f"\n--- V1 (VANILLA) ---\nRESPONSE:\n{res_v1['answer']}\n")
        f_report.write(f"\n--- V9 (TEMPORAL) ---\nRESPONSE:\n{res_v9['answer']}\n")
        if test_type == "behavioral":
            f_report.write(f"\n--- COMPORTAMENTAL ---\nV1 Passed: {behav_v1} | Reason: {reason_v1}\nV9 Passed: {behav_v9} | Reason: {reason_v9}\n")
        else:
            f_report.write("\n--- MÉTRICAS (DeepEval) ---\n")
            for name in metrics_v1.keys():
                f_report.write(f"{name}:\n  V1: {metrics_v1[name]['score']:.3f}\n  V1 Reason: {metrics_v1[name]['reason']}\n")
                f_report.write(f"  V9: {metrics_v9[name]['score']:.3f}\n  V9 Reason: {metrics_v9[name]['reason']}\n\n")
        f_report.flush()


# ============================================================================
# Ponto de entrada
# ============================================================================
async def main():
    pipeline = ComparativeEvaluationPipeline()
    await pipeline.run()

if __name__ == "__main__":
    asyncio.run(main())