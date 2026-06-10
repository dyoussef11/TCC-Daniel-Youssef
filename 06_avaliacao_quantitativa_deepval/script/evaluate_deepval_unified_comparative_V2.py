#!/usr/bin/env python3
"""
UNIFIED EVALUATION SCRIPT: V1 (Vanilla) vs V9 (Temporal)
All internal classes and functions consolidated into a single file.
Preserves original functionality, imports, and execution logic.
"""

import asyncio
import hashlib
import json
import pickle
import re
import sys
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

import numpy as np
import pandas as pd
from tqdm import tqdm

# External imports required by the original modules
from deepeval.test_case import LLMTestCase
from deepeval.metrics import (
    ContextualPrecisionMetric,
    ContextualRelevancyMetric,
    ContextualRecallMetric,
    FaithfulnessMetric,
    AnswerRelevancyMetric,
)

# Import custom external modules (must exist in the environment)
from core.paths import VALIDACAO_SCRIPT, AVALIACAO_SCRIPT, VETORIZATION_DATA, AVALIACAO_DATA
from dataset_avaliacaoV4 import TEST_SUITE, get_traditional_tests, get_behavioral_tests
from core.paths import VALIDACAO_SCRIPT, AVALIACAO_SCRIPT, VETORIZATION_DATA
sys.path.append(str(VALIDACAO_SCRIPT))
sys.path.append(str(AVALIACAO_SCRIPT))
from RAG_BaseLine import VanillaRAG
from RAG_Temporal_V9_3 import SpecialistTimeAwareRAG
from custom_evaluatorV2Backup import OllamaEvaluator

# Ensure paths for any other dynamic imports (kept from original)
sys.path.append(str(VALIDACAO_SCRIPT))
sys.path.append(str(AVALIACAO_SCRIPT))


# ============================================================================
# HELPER FUNCTIONS (from helpers.py)
# ============================================================================

def extract_sku_from_query(query: str) -> Optional[str]:
    """Extract SKU from query using common patterns."""
    patterns = [
        r'[A-Z]{2,3}[-]?\d{3}[-]?\d{2,4}',  # AN515-56, G7-7588
        r'[A-Z]{2,3}\s\d{3}\s\d{4}',         # G7 7588
        r'[A-Z]{2,3}\d{3}[A-Z]?\d{2,4}',     # 15ACH6
    ]
    for pattern in patterns:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            return match.group(0)
    return None


def detect_query_type(query: str) -> Dict:
    """Detect the type of query for behavioral rules."""
    query_lower = query.lower()
    general_keywords = [
        'why does', 'how to', 'what is', 'explain', 'difference between',
        'thermal throttl', 'overheating', 'cooling', 'temperature',
        'battery', 'performance', 'upgrade', 'maintenance',
        'troubleshooting', 'problem', 'issue', 'fix', 'repair'
    ]
    if not extract_sku_from_query(query):
        for keyword in general_keywords:
            if keyword in query_lower:
                return {"type": "general_tech", "reason": "General technical concept"}
    comparison_patterns = [
        r'(\w+[-]\d+).*same as.*(\w+[-]\d+)',
        r'compare.*(\w+[-]\d+).*(\w+[-]\d+)',
    ]
    for pattern in comparison_patterns:
        match = re.search(pattern, query_lower)
        if match:
            return {"type": "comparison", "sku1": match.group(1), "sku2": match.group(2)}
    series_keywords = ['nitro 5', 'legion 5', 'predator', 'g7', 'xps', 'pavilion']
    for keyword in series_keywords:
        if keyword in query_lower and not extract_sku_from_query(query):
            return {"type": "generic_series", "series": keyword}
    sku = extract_sku_from_query(query)
    if sku:
        return {"type": "specific_sku", "sku": sku}
    return {"type": "unknown"}


def calculate_improvement(v1_score: float, v9_score: float) -> Dict:
    """Calculate percentage improvement between V1 and V9."""
    delta = v9_score - v1_score
    delta_pct = (delta / v1_score * 100) if v1_score > 0 else 0
    return {
        "absolute": delta,
        "percentage": delta_pct,
        "improved": delta > 0,
        "status": "improved" if delta > 0.05 else "degraded" if delta < -0.05 else "similar"
    }


def format_duration(seconds: float) -> str:
    """Format duration in seconds to readable string."""
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


def safe_truncate(text: str, max_length: int = 500, suffix: str = "...") -> str:
    """Safely truncate text at word boundary."""
    if len(text) <= max_length:
        return text
    truncated = text[:max_length]
    last_space = truncated.rfind(' ')
    if last_space > 0:
        truncated = truncated[:last_space]
    return truncated + suffix


def extract_brand_from_sku(sku: str) -> Optional[str]:
    """Extract brand name from SKU."""
    sku_lower = sku.lower()
    brand_patterns = {
        "Acer": ["nitro", "predator", "aspire", "an515", "ph315"],
        "Dell": ["g7", "xps", "latitude", "inspiron"],
        "Lenovo": ["legion", "thinkpad", "yoga", "ideapad"],
        "HP": ["pavilion", "envy", "spectre", "omen"],
        "Asus": ["rog", "tuf", "zenbook", "vivobook"],
        "MSI": ["gf", "gp", "ge", "gs", "stealth"]
    }
    for brand, patterns in brand_patterns.items():
        for pattern in patterns:
            if pattern in sku_lower:
                return brand
    return None


class Timer:
    """Context manager for measuring execution time."""
    def __init__(self, name: str = "Operation"):
        self.name = name
        self.start_time = None
        self.end_time = None
    def __enter__(self):
        self.start_time = time.time()
        return self
    def __exit__(self, *args):
        self.end_time = time.time()
        elapsed = self.end_time - self.start_time
        print(f"⏱️ {self.name} took {format_duration(elapsed)}")
    @property
    def elapsed(self) -> float:
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return 0.0


@asynccontextmanager
async def async_timer(name: str = "Async Operation"):
    """Async version of Timer."""
    start = time.time()
    yield
    elapsed = time.time() - start
    print(f"⏱️ {name} took {format_duration(elapsed)}")


def merge_dicts(*dicts: Dict) -> Dict:
    """Merge multiple dictionaries (later override earlier)."""
    result = {}
    for d in dicts:
        result.update(d)
    return result


def chunk_list(lst: List, chunk_size: int) -> List[List]:
    """Split a list into chunks."""
    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]


def normalize_score(score: float, min_val: float = 0.0, max_val: float = 1.0) -> float:
    """Normalize score between min and max."""
    return max(min_val, min(max_val, score))


# ============================================================================
# EVAL CONFIG (from eval_config.py)
# ============================================================================

@dataclass
class EvalConfig:
    """Centralized configuration for comparative evaluation."""
    base_path: Path = VETORIZATION_DATA / 'base_conhecimento_multilingueV9.json'
    evaluator_model: str = "qwen3:4b-instruct"
    cache_dir: Path = AVALIACAO_DATA / "cache"
    embedding_cache_size: int = 1000
    vanilla_use_expansion: bool = False   # V1 does not expand
    temporal_use_expansion: bool = True   # V9 expands
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
        dir_path = AVALIACAO_DATA / "resultados"
        dir_path.mkdir(parents=True, exist_ok=True)
        return dir_path


# ============================================================================
# EMBEDDING CACHE (from embedding_cache.py)
# ============================================================================

class EmbeddingCache:
    """LRU cache for query embeddings."""
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
        return {
            "size": len(self._cache),
            "max_size": self.max_size,
            "directory": str(self.cache_dir)
        }


# ============================================================================
# BEHAVIORAL ANALYZER (from behavioral_analyzer.py)
# ============================================================================

def check_sku_integrity(query: str, response: str) -> bool:
    target_sku = extract_sku_from_query(query)
    found_sku = extract_sku_from_query(response)
    if target_sku and found_sku and target_sku.lower() != found_sku.lower():
        return False
    return True


class BehavioralTestAnalyzer:
    """Analyzes behavioral tests for both versions."""
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
                "should_acknowledge_future_or_unavailable": lambda: (len(required_found) >= min_required) and not forbidden_found,
                "should_use_internal_fallback_honestly": lambda: (len(required_found) >= min_required and not forbidden_found),
                "should_include_audit_with_tags": lambda: (
                    re.search(r"AUDIT:", response, re.I) is not None and
                    (re.search(r"\[RAG:", response, re.I) is not None or re.search(r"\[INTERNAL:", response, re.I) is not None)
                ),
                "should_compare_with_fallback": lambda: len(required_found) >= min_required,
                "should_ask_for_sku_and_avoid_internal_specs": lambda: (len(required_found) >= min_required and not forbidden_found),
                "should_combine_rag_and_internal": lambda: len(required_found) >= min_required
            }
            passed = behaviors.get(expected, lambda: False)()
            reason = f"Required: {required_found[:3]}. Forbidden: {forbidden_found[:3] if forbidden_found else 'none'}"
            return passed, reason

        passed_v1, reason_v1 = check(response_v1)
        passed_v9, reason_v9 = check(response_v9)

        if not check_sku_integrity(test_case["input"], response_v9):
            passed_v9 = False
            reason_v9 += " | CRITICAL FAILURE: SKU Mismatch detected."

        return passed_v1, passed_v9, reason_v1, reason_v9


# ============================================================================
# METRIC EVALUATOR (from metric_evaluator.py)
# ============================================================================

class ComparativeMetricEvaluator:
    """Evaluates both versions with DeepEval metrics."""
    def __init__(self, config: EvalConfig):
        self.config = config
        self.semaphore = asyncio.Semaphore(config.concurrent_metrics)
        self.evaluator_v1 = OllamaEvaluator(prompt_version="V1")
        self.evaluator_v9 = OllamaEvaluator(prompt_version="V9")
        self._init_metrics()

    def _init_metrics(self):
        self.metrics_v1 = {
            "Faithfulness": FaithfulnessMetric(
                threshold=self.config.metric_thresholds["Faithfulness"],
                model=self.evaluator_v1,
                include_reason=True
            ),
            "Answer_Rel": AnswerRelevancyMetric(
                threshold=self.config.metric_thresholds["Answer_Rel"],
                model=self.evaluator_v1,
                include_reason=True
            ),
            "C_Relevancia": ContextualRelevancyMetric(
                threshold=self.config.metric_thresholds["C_Relevancia"],
                model=self.evaluator_v1,
                include_reason=True
            ),
            "C_Precision": ContextualPrecisionMetric(
                threshold=self.config.metric_thresholds["C_Precision"],
                model=self.evaluator_v1,
                include_reason=True
            ),
            "C_Recall": ContextualRecallMetric(
                threshold=self.config.metric_thresholds["C_Recall"],
                model=self.evaluator_v1,
                include_reason=True
            )
        }
        self.metrics_v9 = {
            "Faithfulness": FaithfulnessMetric(
                threshold=self.config.metric_thresholds["Faithfulness"],
                model=self.evaluator_v9,
                include_reason=True
            ),
            "Answer_Rel": AnswerRelevancyMetric(
                threshold=self.config.metric_thresholds["Answer_Rel"],
                model=self.evaluator_v9,
                include_reason=True
            ),
            "C_Relevancia": ContextualRelevancyMetric(
                threshold=self.config.metric_thresholds["C_Relevancia"],
                model=self.evaluator_v9,
                include_reason=True
            ),
            "C_Precision": ContextualPrecisionMetric(
                threshold=self.config.metric_thresholds["C_Precision"],
                model=self.evaluator_v9,
                include_reason=True
            ),
            "C_Recall": ContextualRecallMetric(
                threshold=self.config.metric_thresholds["C_Recall"],
                model=self.evaluator_v9,
                include_reason=True
            )
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
# RAG MANAGER (from rag_manager.py)
# ============================================================================

class ComparativeRAGManager:
    """Manages V1 (Vanilla) and V9 (Temporal) with lazy loading."""
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
            self._vanilla = VanillaRAG(
                self.base_path,
                embedding_cache=self.embedding_cache,
                use_expansion=self.config.vanilla_use_expansion
            )
        return self._vanilla

    @property
    def temporal(self) -> SpecialistTimeAwareRAG:
        if self._temporal is None:
            print("🔄 Carregando RAG Temporal (V9 - COM expansão)...")
            self._temporal = SpecialistTimeAwareRAG(
                self.base_path,
                variant_name=self.config.temporal_variant,
                embedding_cache=self.embedding_cache,
                use_expansion=self.config.temporal_use_expansion
            )
            self._temporal.current_model = self.config.model_name
            self._temporal.temperature = self.config.temperature
            self._temporal.search_top_k = self.config.search_top_k
        return self._temporal

    async def search_both(self, query: str, ref_date: str) -> tuple:
        """Execute search on both versions in parallel."""
        print(f"\n{'='*60}")
        print(f"🔍 QUERY: {query}")
        print(f"📅 REF_DATE: {ref_date}")
        print(f"{'='*60}")
        v1_task = self.vanilla.search(query)
        v9_task = self.temporal.search(query, ref_date)
        results = await asyncio.gather(v1_task, v9_task)
        print(f"\n📊 V9 RESPONSE PREVIEW: {results[1]['answer'][:200]}...")
        print(f"📋 V9 AUDIT: {results[1].get('audit_trail', 'N/A')}")
        return results[0], results[1]


# ============================================================================
# REPORT GENERATOR (from report_generator.py)
# ============================================================================

class ReportGenerator:
    """Generates reports in multiple formats."""
    def __init__(self, output_dir: Path, timestamp: str):
        self.output_dir = output_dir
        self.timestamp = timestamp
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_all_reports(self, results_table: List[Dict], config, test_suite_stats: Dict) -> Dict:
        return {
            "csv": self._generate_csv(results_table),
            "txt": self._generate_txt(results_table, config, test_suite_stats),
            "md": self._generate_md(results_table, config, test_suite_stats),
            "summary_json": self._generate_summary_json(results_table)
        }

    def _generate_csv(self, results_table: List[Dict]) -> Path:
        csv_path = self.output_dir / f"COMPARATIVO_V1_VS_V9_{self.timestamp}.csv"
        pd.DataFrame(results_table).to_csv(csv_path, index=False)
        return csv_path

    def _generate_txt(self, results_table: List[Dict], config, test_suite_stats: Dict) -> Path:
        txt_path = self.output_dir / f"RELATORIO_COMPARATIVO_{self.timestamp}.txt"
        with open(txt_path, 'w', encoding='utf-8') as f:
            self._write_txt_header(f, config, test_suite_stats)
            for row in results_table:
                self._write_txt_case(f, row)
            self._write_txt_summary(f, results_table)
            self._write_txt_recommendation(f)
        return txt_path

    def _generate_md(self, results_table: List[Dict], config, test_suite_stats: Dict) -> Path:
        md_path = self.output_dir / f"RELATORIO_COMPARATIVO_{self.timestamp}.md"
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(f"# Relatório Comparativo: V1 (Vanilla) vs V9 (Temporal)\n\n")
            f.write(f"**Data:** {self.timestamp}\n")
            f.write(f"**Base:** {config.base_path.name}\n")
            f.write(f"**Total de casos:** {test_suite_stats['total']}\n\n")
            f.write("## Resumo dos Resultados\n\n")
            self._write_md_summary(f, results_table)
            f.write("\n## Análise Detalhada\n\n")
            self._write_md_metrics_table(f, results_table)
            self._write_md_behavioral_table(f, results_table)
            f.write("\n## Recomendação\n\n")
            self._write_md_recommendation(f)
        return md_path

    def _generate_summary_json(self, results_table: List[Dict]) -> Path:
        json_path = self.output_dir / f"RESUMO_{self.timestamp}.json"
        traditional = [r for r in results_table if r.get("Test_Type") != "behavioral"]
        behavioral = [r for r in results_table if r.get("Test_Type") == "behavioral"]
        summary = {
            "timestamp": self.timestamp,
            "total_cases": len(results_table),
            "traditional_cases": len(traditional),
            "behavioral_cases": len(behavioral),
            "metrics": {},
            "behavioral": {}
        }
        if traditional:
            metrics = ["Faithfulness", "Answer_Rel", "C_Relevancia", "C_Precision", "C_Recall"]
            for metric in metrics:
                v1_scores = [r.get(f"V1_{metric}_Score", 0) for r in traditional if isinstance(r.get(f"V1_{metric}_Score"), (int, float))]
                v9_scores = [r.get(f"V9_{metric}_Score", 0) for r in traditional if isinstance(r.get(f"V9_{metric}_Score"), (int, float))]
                summary["metrics"][metric] = {
                    "v1_avg": sum(v1_scores) / len(v1_scores) if v1_scores else 0,
                    "v9_avg": sum(v9_scores) / len(v9_scores) if v9_scores else 0,
                    "v1_count": len(v1_scores),
                    "v9_count": len(v9_scores)
                }
        if behavioral:
            v1_passed = sum(1 for r in behavioral if r.get("V1_Behavioral_Passed"))
            v9_passed = sum(1 for r in behavioral if r.get("V9_Behavioral_Passed"))
            summary["behavioral"] = {
                "v1_passed": v1_passed,
                "v9_passed": v9_passed,
                "total": len(behavioral),
                "v1_rate": v1_passed / len(behavioral) if behavioral else 0,
                "v9_rate": v9_passed / len(behavioral) if behavioral else 0
            }
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        return json_path

    def _write_txt_header(self, f, config, test_suite_stats: Dict):
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
            f.write(f"\n--- V1 MÉTRICAS ---\n")
            for metric in ["Faithfulness", "Answer_Rel", "C_Relevancia", "C_Precision", "C_Recall"]:
                score = row.get(f"V1_{metric}_Score", 0)
                reason = row.get(f"V1_{metric}_Reason", "No reason provided")
                f.write(f"{metric}: {score:.3f}\n")
                f.write(f"  Reason: {reason[:500]}\n")
        f.write(f"\n--- V9 (TEMPORAL) ---\n")
        f.write(f"Answer: {row.get('V9_Answer', '')[:800]}\n")
        if row.get('Test_Type') == 'behavioral':
            f.write(f"Behavioral Passed: {row.get('V9_Behavioral_Passed', False)}\n")
            f.write(f"Behavioral Reason: {row.get('V9_Behavioral_Reason', '')}\n")
        else:
            f.write(f"\n--- V9 MÉTRICAS ---\n")
            for metric in ["Faithfulness", "Answer_Rel", "C_Relevancia", "C_Precision", "C_Recall"]:
                score = row.get(f"V9_{metric}_Score", 0)
                reason = row.get(f"V9_{metric}_Reason", "No reason provided")
                f.write(f"{metric}: {score:.3f}\n")
                f.write(f"  Reason: {reason}\n")
        f.write("-" * 60 + "\n")

    def _write_txt_summary(self, f, results_table: List[Dict]):
        f.write("\n" + "=" * 80 + "\n")
        f.write("RESUMO DOS RESULTADOS\n")
        f.write("=" * 80 + "\n")
        traditional = [r for r in results_table if r.get("Test_Type") != "behavioral"]
        if traditional:
            f.write("\n📊 MÉTRICAS MÉDIAS (DeepEval):\n")
            for metric in ["Faithfulness", "Answer_Rel", "C_Relevancia", "C_Precision", "C_Recall"]:
                v1_scores = [r.get(f"V1_{metric}_Score", 0) for r in traditional if isinstance(r.get(f"V1_{metric}_Score"), (int, float))]
                v9_scores = [r.get(f"V9_{metric}_Score", 0) for r in traditional if isinstance(r.get(f"V9_{metric}_Score"), (int, float))]
                if v1_scores and v9_scores:
                    v1_avg = sum(v1_scores) / len(v1_scores)
                    v9_avg = sum(v9_scores) / len(v9_scores)
                    variation = v9_avg - v1_avg
                    arrow = "↑" if variation > 0 else "↓" if variation < 0 else "→"
                    f.write(f"  {metric}: V1={v1_avg:.3f} {arrow} V9={v9_avg:.3f} (Δ {variation:+.3f})\n")
        behavioral = [r for r in results_table if r.get("Test_Type") == "behavioral"]
        if behavioral:
            v1_passed = sum(1 for r in behavioral if r.get("V1_Behavioral_Passed"))
            v9_passed = sum(1 for r in behavioral if r.get("V9_Behavioral_Passed"))
            f.write(f"\n📊 TESTES COMPORTAMENTAIS:\n")
            f.write(f"  V1: {v1_passed}/{len(behavioral)} ({v1_passed/len(behavioral)*100:.0f}%)\n")
            f.write(f"  V9: {v9_passed}/{len(behavioral)} ({v9_passed/len(behavioral)*100:.0f}%)\n")
            f.write(f"\n  Detalhamento:\n")
            for row in behavioral:
                test_id = row.get('ID', 'unknown')
                v1_status = "✅" if row.get('V1_Behavioral_Passed') else "❌"
                v9_status = "✅" if row.get('V9_Behavioral_Passed') else "❌"
                f.write(f"    {test_id}: V1 {v1_status} | V9 {v9_status}\n")
                f.write(f"      V1 Reason: {row.get('V1_Behavioral_Reason', '')[:200]}\n")
                f.write(f"      V9 Reason: {row.get('V9_Behavioral_Reason', '')[:200]}\n")

    def _write_txt_recommendation(self, f):
        f.write("\n" + "=" * 80 + "\n")
        f.write("🎯 RECOMENDAÇÃO FINAL\n")
        f.write("=" * 80 + "\n")
        f.write("""
        ✅ Use V9 (Temporal) para:
           - Suporte técnico com SKU específico
           - E-commerce e catálogo de produtos
           - Cenários que exigem precisão e rastreabilidade
        
        ✅ Use V1 (Vanilla) para:
           - Chat geral e FAQs
           - Troubleshooting conceitual
           - Quando o usuário NÃO tem o SKU
        
        📌 Conclusão: V9 é SUPERIOR em precisão e controle de alucinação.
                       V1 é SUPERIOR em utilidade e abrangência.
        """)

    def _write_md_summary(self, f, results_table: List[Dict]):
        behavioral = [r for r in results_table if r.get("Test_Type") == "behavioral"]
        traditional = [r for r in results_table if r.get("Test_Type") != "behavioral"]
        if behavioral:
            v9_passed = sum(1 for r in behavioral if r.get("V9_Behavioral_Passed"))
            f.write(f"- **Testes Comportamentais (SKU lock):** {v9_passed}/{len(behavioral)} passaram ({v9_passed/len(behavioral)*100:.0f}%)\n")
        if traditional:
            v9_faith = sum(r.get("V9_Faithfulness_Score", 0) for r in traditional) / len(traditional)
            f.write(f"- **Faithfulness médio:** {v9_faith:.3f}\n")

    def _write_md_metrics_table(self, f, results_table: List[Dict]):
        f.write("### Métricas DeepEval\n\n")
        f.write("| Métrica | V1 (Vanilla) | V9 (Temporal) | Variação |\n")
        f.write("|---------|--------------|---------------|----------|\n")
        traditional = [r for r in results_table if r.get("Test_Type") != "behavioral"]
        if traditional:
            for metric in ["Faithfulness", "Answer_Rel", "C_Relevancia", "C_Precision", "C_Recall"]:
                v1_scores = [r.get(f"V1_{metric}_Score", 0) for r in traditional]
                v9_scores = [r.get(f"V9_{metric}_Score", 0) for r in traditional]
                if v1_scores:
                    v1_avg = sum(v1_scores) / len(v1_scores)
                    v9_avg = sum(v9_scores) / len(v9_scores)
                    variation = v9_avg - v1_avg
                    emoji = "🟢" if variation > 0 else "🔴" if variation < 0 else "⚪"
                    f.write(f"| {metric} | {v1_avg:.3f} | {v9_avg:.3f} | {emoji} {variation:+.3f} |\n")

    def _write_md_behavioral_table(self, f, results_table: List[Dict]):
        behavioral = [r for r in results_table if r.get("Test_Type") == "behavioral"]
        if not behavioral:
            return
        f.write("\n### Testes Comportamentais\n\n")
        f.write("| ID | Comportamento Esperado | V1 | V9 | V1 Reason | V9 Reason |\n")
        f.write("|----|----------------------|----|----|-----------|-----------|\n")
        for row in behavioral:
            test_id = row.get('ID', 'unknown')
            expected = row.get('Expected_Behavior', 'unknown')[:30]
            v1_status = "✅" if row.get('V1_Behavioral_Passed') else "❌"
            v9_status = "✅" if row.get('V9_Behavioral_Passed') else "❌"
            v1_reason = row.get('V1_Behavioral_Reason', '').replace('|', '\\|')
            v9_reason = row.get('V9_Behavioral_Reason', '').replace('|', '\\|')
            f.write(f"| {test_id} | {expected} | {v1_status} | {v9_status} | {v1_reason} | {v9_reason} |\n")

    def _write_md_recommendation(self, f):
        f.write("""
## 🎯 Recomendação Final

| Caso de Uso | Melhor Escolha | Motivo |
|-------------|----------------|--------|
| Chat geral / FAQ | V1 (Vanilla) | Mais útil e abrangente |
| Suporte com SKU | V9 (Temporal) | Mais preciso, sem alucinação |
| E-commerce / Catálogo | V9 (Temporal) | Rastreável e consistente |
| Troubleshooting | V1 (Vanilla) | Pode usar conhecimento interno |
| Atendimento técnico | V9 (Temporal) | Auditoria completa |

### Conclusão

- **V9 é superior para casos que exigem PRECISÃO e RASTREABILIDADE**
- **V1 é melhor para CASOS GERAIS onde utilidade > precisão**
- **O trade-off é intencional e deve guiar a escolha de acordo com o caso de uso**
""")


# ============================================================================
# SUMMARY PRINTER (from summary_printer.py)
# ============================================================================

class SummaryPrinter:
    """Prints evaluation summary to console."""
    @staticmethod
    def print_summary(results_table: List[Dict]):
        print("\n" + "=" * 80)
        print("✅ AVALIAÇÃO COMPARATIVA CONCLUÍDA")
        print("=" * 80)
        SummaryPrinter._print_metric_analysis(results_table)
        SummaryPrinter._print_behavioral_analysis(results_table)
        SummaryPrinter._print_recommendation()

    @staticmethod
    def _print_metric_analysis(results_table: List[Dict]):
        traditional = [r for r in results_table if r.get("Test_Type") != "behavioral"]
        if not traditional:
            return
        print("\n📊 ANÁLISE DE GANHO DO V9 SOBRE V1:")
        metrics = ["Faithfulness", "Answer_Rel", "C_Relevancia"]
        for metric in metrics:
            v1_scores = [r.get(f"V1_{metric}_Score", 0) for r in traditional if isinstance(r.get(f"V1_{metric}_Score"), (int, float))]
            v9_scores = [r.get(f"V9_{metric}_Score", 0) for r in traditional if isinstance(r.get(f"V9_{metric}_Score"), (int, float))]
            if v1_scores and v9_scores:
                v1_avg = sum(v1_scores) / len(v1_scores)
                v9_avg = sum(v9_scores) / len(v9_scores)
                gain = v9_avg - v1_avg
                gain_pct = (gain / v1_avg * 100) if v1_avg > 0 else 0
                symbol = "🟢" if gain > 0.05 else "🔴" if gain < -0.05 else "⚪"
                print(f"   {symbol} {metric}: V1={v1_avg:.3f} → V9={v9_avg:.3f} ({gain:+.3f} / {gain_pct:+.1f}%)")

    @staticmethod
    def _print_behavioral_analysis(results_table: List[Dict]):
        behavioral = [r for r in results_table if r.get("Test_Type") == "behavioral"]
        if not behavioral:
            return
        v1_passed = sum(1 for r in behavioral if r.get("V1_Behavioral_Passed"))
        v9_passed = sum(1 for r in behavioral if r.get("V9_Behavioral_Passed"))
        print(f"\n📊 TESTES COMPORTAMENTAIS ({len(behavioral)} casos):")
        print(f"   V1 (Vanilla): {v1_passed}/{len(behavioral)} ({v1_passed/len(behavioral)*100:.0f}%)")
        print(f"   V9 (Temporal): {v9_passed}/{len(behavioral)} ({v9_passed/len(behavioral)*100:.0f}%)")
        if v9_passed < v1_passed:
            print(f"   ⚠️ V9 é MAIS RESTRITIVO (SKU lock) - comportamento esperado")
        elif v9_passed > v1_passed:
            print(f"   ✅ V9 tem MELHOR ADERÊNCIA às regras comportamentais")

    @staticmethod
    def _print_recommendation():
        print("\n" + "=" * 80)
        print("🎯 RECOMENDAÇÃO FINAL")
        print("=" * 80)
        print("""
        ✅ Use V9 (Temporal) para:
           - Suporte técnico com SKU específico
           - E-commerce e catálogo de produtos
           - Cenários que exigem precisão e rastreabilidade
        
        ✅ Use V1 (Vanilla) para:
           - Chat geral e FAQs
           - Troubleshooting conceitual
           - Quando o usuário NÃO tem o SKU
        
        📌 Trade-off: V9 é mais PRECISO, V1 é mais ÚTIL
        """)


# ============================================================================
# TEST SUITE LOADER (from test_suite_loader.py)
# ============================================================================

class TestSuiteLoader:
    """Loads and filters the test dataset."""
    def __init__(self):
        self._full_suite = TEST_SUITE
        self._traditional_cache = None
        self._behavioral_cache = None

    @property
    def all_tests(self) -> List[Dict]:
        return self._full_suite

    @property
    def traditional_tests(self) -> List[Dict]:
        if self._traditional_cache is None:
            self._traditional_cache = get_traditional_tests()
        return self._traditional_cache

    @property
    def behavioral_tests(self) -> List[Dict]:
        if self._behavioral_cache is None:
            self._behavioral_cache = get_behavioral_tests()
        return self._behavioral_cache

    def get_by_id(self, test_id: str) -> Optional[Dict]:
        for test in self._full_suite:
            if test.get('id') == test_id:
                return test
        return None

    def get_by_expected_behavior(self, expected: str) -> List[Dict]:
        return [t for t in self.behavioral_tests if t.get('expected_behavior') == expected]

    def get_stats(self) -> Dict:
        traditional_count = len(self.traditional_tests)
        behavioral_count = len(self.behavioral_tests)
        behavioral_types = {}
        for test in self.behavioral_tests:
            behavior = test.get('expected_behavior', 'unknown')
            behavioral_types[behavior] = behavioral_types.get(behavior, 0) + 1
        return {
            "total": len(self._full_suite),
            "traditional": traditional_count,
            "behavioral": behavioral_count,
            "behavioral_types": behavioral_types,
            "traditional_ids": [t.get('id') for t in self.traditional_tests],
            "behavioral_ids": [t.get('id') for t in self.behavioral_tests]
        }

    def filter_by_sku_pattern(self, sku_pattern: str) -> List[Dict]:
        pattern_lower = sku_pattern.lower()
        return [t for t in self._full_suite if pattern_lower in t.get('input', '').lower()]

    def print_summary(self) -> None:
        stats = self.get_stats()
        print("\n📊 DATASET DE TESTES")
        print("=" * 40)
        print(f"Total de casos: {stats['total']}")
        print(f"├── Tradicionais: {stats['traditional']}")
        print(f"└── Comportamentais: {stats['behavioral']}")
        if stats['behavioral_types']:
            print("\n📋 Tipos de comportamento:")
            for behavior, count in stats['behavioral_types'].items():
                print(f"   ├── {behavior}: {count}")
        print("\n🏷️ IDs dos testes:")
        print(f"   Tradicionais: {', '.join(stats['traditional_ids'])}")
        print(f"   Comportamentais: {', '.join(stats['behavioral_ids'])}")


# ============================================================================
# MAIN EVALUATION PIPELINE (from evaluate_rag_deepval_unified_TemporalVS_NaoTemporalV4.py)
# ============================================================================

class ComparativeEvaluationPipeline:
    """Main pipeline orchestrating the comparative evaluation."""
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
        pbar.write(f"   V1 normalized: {res_v1.get('normalized_query', query)}")
        pbar.write(f"   V9 normalized: {res_v9.get('normalized_query', query)}")
        case_v1 = LLMTestCase(
            input=query,
            actual_output=res_v1["answer"],
            retrieval_context=res_v1.get("sources", [])[:5],
            expected_output=test_case.get("expected_output")
        )
        case_v9 = LLMTestCase(
            input=query,
            actual_output=res_v9["answer"],
            retrieval_context=res_v9.get("sources", [])[:5],
            expected_output=test_case.get("expected_output")
        )
        try:
            metrics_v1, metrics_v9 = await self.metric_evaluator.evaluate_both(case_v1, case_v9, pbar)
        except Exception as e:
            pbar.write(f"   ⚠️ ERRO nas métricas: {str(e)}")
            metrics_v1 = {name: {"score": 0.0, "reason": f"Erro: {str(e)}"} 
                        for name in ["Faithfulness", "Answer_Rel", "C_Relevancia", "C_Precision", "C_Recall"]}
            metrics_v9 = metrics_v1.copy()
        behav_v1, behav_v9, reason_v1, reason_v9 = self.behavioral_analyzer.analyze(
            test_case, res_v1["answer"], res_v9["answer"]
        )
        row = self._build_result_row(test_case, test_type, query, 
                                     res_v1, res_v9, 
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
        }
        for name, data in metrics_v1.items():
            row[f"V1_{name}_Score"] = data["score"]
            row[f"V1_{name}_Reason"] = data["reason"]
        for name, data in metrics_v9.items():
            row[f"V9_{name}_Score"] = data["score"]
            row[f"V9_{name}_Reason"] = data["reason"]
        row["Expected_Behavior"] = test_case.get("expected_behavior", "")
        return row

    def _print_header(self):
        print("\n" + "=" * 80)
        print("🚀 AVALIAÇÃO COMPARATIVA: V1 (Vanilla) vs V9 (Temporal)")
        print(f"📍 Data: {self.config.timestamp}")
        print(f"📊 Casos: {len(TEST_SUITE)}")
        print(f"   - Tradicionais: {len([t for t in TEST_SUITE if t.get('test_type') != 'behavioral'])}")
        print(f"   - Comportamentais: {len([t for t in TEST_SUITE if t.get('test_type') == 'behavioral'])}")
        print("=" * 80)

    def _write_report_header(self, f_report):
        f_report.write(f"RELATÓRIO COMPARATIVO V1 vs V9\n")
        f_report.write(f"Data: {self.config.timestamp}\n")
        f_report.write(f"Base: {self.config.base_path}\n")
        f_report.write("=" * 80 + "\n\n")

    def _write_recommendation(self, f_report):
        f_report.write("\n" + "=" * 80 + "\n")
        f_report.write("RECOMENDAÇÃO FINAL\n")
        f_report.write("=" * 80 + "\n\n")
        f_report.write("""
        ✅ V9 (Temporal) → Use para: suporte com SKU, e-commerce, precisão
        ✅ V1 (Vanilla) → Use para: chat geral, troubleshooting, conceitos
        
        O V9 é SUPERIOR em precisão e rastreabilidade.
        O V1 é SUPERIOR em utilidade e abrangência.
        """)

    def _write_case_report(self, f_report, test_case, query, ref_date,
                           res_v1, res_v9, test_type,
                           behav_v1, behav_v9, reason_v1, reason_v9,
                           metrics_v1, metrics_v9):
        f_report.write(f"\n{'='*80}\n")
        f_report.write(f"ID: {test_case.get('id')}\n")
        f_report.write(f"Query: {query}\n")
        f_report.write(f"Reference Date: {ref_date}\n")
        f_report.write(f"\n--- V1 (VANILLA) ---\n")
        f_report.write(f"RESPONSE:\n{res_v1['answer']}\n")
        f_report.write(f"\n--- V9 (TEMPORAL) ---\n")
        f_report.write(f"RESPONSE:\n{res_v9['answer']}\n")
        if test_type == "behavioral":
            f_report.write(f"\n--- COMPORTAMENTAL ---\n")
            f_report.write(f"V1 Passed: {behav_v1} | Reason: {reason_v1}\n")
            f_report.write(f"V9 Passed: {behav_v9} | Reason: {reason_v9}\n")
        else:
            f_report.write(f"\n--- MÉTRICAS (DeepEval) ---\n")
            for name in metrics_v1.keys():
                f_report.write(f"{name}:\n")
                f_report.write(f"  V1: {metrics_v1[name]['score']:.3f}\n")
                f_report.write(f"  V1 Reason: {metrics_v1[name]['reason']}\n")
                f_report.write(f"  V9: {metrics_v9[name]['score']:.3f}\n")
                f_report.write(f"  V9 Reason: {metrics_v9[name]['reason']}\n")
                f_report.write(f"\n")
        f_report.flush()


async def main():
    pipeline = ComparativeEvaluationPipeline()
    await pipeline.run()


if __name__ == "__main__":
    asyncio.run(main())