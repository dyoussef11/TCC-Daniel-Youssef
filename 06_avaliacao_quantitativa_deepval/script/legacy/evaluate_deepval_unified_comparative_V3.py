
#!/usr/bin/env python3
"""
UNIFIED EVALUATION SCRIPT: V1 (Vanilla) vs V9 (Temporal)
All internal classes and functions consolidated into a single file.
Preserves original functionality, imports, and execution logic with enhanced stability.
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
from tqdm.asyncio import tqdm

# External imports required by the original modules
from deepeval.test_case import LLMTestCase
from deepeval.metrics import (
    ContextualPrecisionMetric,
    ContextualRelevancyMetric,
    ContextualRecallMetric,
    FaithfulnessMetric,
    AnswerRelevancyMetric,
)

# Import custom external modules
from core.paths import VALIDACAO_SCRIPT, AVALIACAO_SCRIPT, VETORIZATION_DATA, AVALIACAO_DATA
from dataset_avaliacaoV4 import TEST_SUITE, get_traditional_tests, get_behavioral_tests

# Configure dynamic imports safely
for path in [VALIDACAO_SCRIPT, AVALIACAO_SCRIPT]:
    if str(path) not in sys.path:
        sys.path.append(str(path))

from RAG_BaseLine import VanillaRAG
from RAG_Temporal_V9_3 import SpecialistTimeAwareRAG
from custom_evaluatorV2Backup import OllamaEvaluator


# ============================================================================
# HELPER FUNCTIONS
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


def detect_query_type(query: str) -> Dict[str, Any]:
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


def calculate_improvement(v1_score: float, v9_score: float) -> Dict[str, Any]:
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
    hours, remainder = divmod(int(seconds), 3600)
    minutes, secs = divmod(remainder, 60)
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
        if any(pattern in sku_lower for pattern in patterns):
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
# EVAL CONFIG
# ============================================================================

@dataclass
class EvalConfig:
    """Centralized configuration for comparative evaluation."""
    base_path: Path = VETORIZATION_DATA / 'base_conhecimento_multilingueV9.json'
    evaluator_model: str = "qwen3.5:9b"
    cache_dir: Path = AVALIACAO_DATA / "cache"
    embedding_cache_size: int = 1000
    vanilla_use_expansion: bool = False
    temporal_use_expansion: bool = True
    temporal_variant: str = "V9_HYBRID_MIXED_AUDITOR"
    model_name: str = "mistral:7b-instruct"
    temperature: float = 0.0
    top_p: float = 0.9
    search_top_k: int = 20
    concurrent_tasks: int = 2          # Limita requisições ao Ollama simultaneamente
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
# EMBEDDING CACHE
# ============================================================================

class EmbeddingCache:
    """LRU cache for query embeddings using a robust structure."""
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
            except Exception:
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
            self._get_path(oldest_key).unlink(missing_ok=True)
        self._cache[key] = embedding.copy()
        try:
            with open(self._get_path(key), 'wb') as f:
                pickle.dump(embedding, f)
        except IOError:
            pass

    def stats(self) -> Dict[str, Any]:
        return {
            "size": len(self._cache),
            "max_size": self.max_size,
            "directory": str(self.cache_dir)
        }


# ============================================================================
# BEHAVIORAL ANALYZER
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
# METRIC EVALUATOR
# ============================================================================

class ComparativeMetricEvaluator:
    """Evaluates both versions with DeepEval metrics using thread safety."""
    def __init__(self, config: EvalConfig):
        self.config = config
        self.semaphore = asyncio.Semaphore(config.concurrent_metrics)
        self.evaluator_v1 = OllamaEvaluator(prompt_version="V1")
        self.evaluator_v9 = OllamaEvaluator(prompt_version="V9")
        self._init_metrics()

    def _init_metrics(self):
        self.metrics_v1 = {
            "Faithfulness": FaithfulnessMetric(threshold=self.config.metric_thresholds["Faithfulness"], model=self.evaluator_v1, include_reason=True),
            "Answer_Rel": AnswerRelevancyMetric(threshold=self.config.metric_thresholds["Answer_Rel"], model=self.evaluator_v1, include_reason=True),
            "C_Relevancia": ContextualRelevancyMetric(threshold=self.config.metric_thresholds["C_Relevancia"], model=self.evaluator_v1, include_reason=True),
            "C_Precision": ContextualPrecisionMetric(threshold=self.config.metric_thresholds["C_Precision"], model=self.evaluator_v1, include_reason=True),
            "C_Recall": ContextualRecallMetric(threshold=self.config.metric_thresholds["C_Recall"], model=self.evaluator_v1, include_reason=True)
        }
        self.metrics_v9 = {
            "Faithfulness": FaithfulnessMetric(threshold=self.config.metric_thresholds["Faithfulness"], model=self.evaluator_v9, include_reason=True),
            "Answer_Rel": AnswerRelevancyMetric(threshold=self.config.metric_thresholds["Answer_Rel"], model=self.evaluator_v9, include_reason=True),
            "C_Relevancia": ContextualRelevancyMetric(threshold=self.config.metric_thresholds["C_Relevancia"], model=self.evaluator_v9, include_reason=True),
            "C_Precision": ContextualPrecisionMetric(threshold=self.config.metric_thresholds["C_Precision"], model=self.evaluator_v9, include_reason=True),
            "C_Recall": ContextualRecallMetric(threshold=self.config.metric_thresholds["C_Recall"], model=self.evaluator_v9, include_reason=True)
        }

    async def evaluate_both(self, case_v1: LLMTestCase, case_v9: LLMTestCase, pbar: Optional[Any] = None) -> Tuple[Dict, Dict]:
        results_v1, results_v9 = {}, {}
        metric_names = list(self.metrics_v1.keys())
        
        tasks = []
        for name in metric_names:
            tasks.append(self._measure(self.metrics_v1[name], case_v1, pbar))
            tasks.append(self._measure(self.metrics_v9[name], case_v9, pbar))
            
        raw_results = await asyncio.gather(*tasks)
        
        for i, name in enumerate(metric_names):
            results_v1[name] = {"score": raw_results[i * 2][0], "reason": raw_results[i * 2][1]}
            results_v9[name] = {"score": raw_results[i * 2 + 1][0], "reason": raw_results[i * 2 + 1][1]}
            
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
        if getattr(metric, 'reason', None):
            return str(metric.reason).replace('\n', ' ')
        if getattr(metric, 'verdicts', None):
            reasons = [str(getattr(v, 'reason', ''))[:200] for v in metric.verdicts[:3] if getattr(v, 'reason', None)]
            return " | ".join(reasons) if reasons else "No reason"
        return "No reason available"


# ============================================================================
# RAG MANAGER
# ============================================================================

class ComparativeRAGManager:
    """Manages V1 (Vanilla) and V9 (Temporal) with thread-safe lazy loading."""
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

    async def search_both(self, query: str, ref_date: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Execute search on both versions in parallel."""
        v1_task = asyncio.create_task(asyncio.to_thread(self.vanilla.search, query))
        v9_task = asyncio.create_task(asyncio.to_thread(self.temporal.search, query, ref_date))
        
        # Resolve calls with compatibility wrapper if engines are not native async
        results = await asyncio.gather(v1_task, v9_task)
        return results[0], results[1]


# ============================================================================
# REPORT GENERATOR
# ============================================================================

class ReportGenerator:
    """Generates reports in multiple formats safely using proper I/O wrappers."""
    def __init__(self, output_dir: Path, timestamp: str):
        self.output_dir = output_dir
        self.timestamp = timestamp
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_all_reports(self, results_table: List[Dict], config, test_suite_stats: Dict) -> Dict[str, Path]:
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
            for m in metrics:
                v1_scores = [r[f"V1_{m}_Score"] for r in traditional if isinstance(r.get(f"V1_{m}_Score"), (int, float))]
                v9_scores = [r[f"V9_{m}_Score"] for r in traditional if isinstance(r.get(f"V9_{m}_Score"), (int, float))]
                summary["metrics"][m] = {
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
        f.write(f"{'='*80}\nRELATÓRIO COMPARATIVO: V1 (Vanilla) vs V9 (Temporal)\n{'='*80}\n")
        f.write(f"Data: {self.timestamp}\nBase: {config.base_path}\nAvaliador: {config.evaluator_model}\n")
        f.write(f"Modelo LLM: {config.model_name}\nTemperature: {config.temperature}\n{'-'*80}\n")
        f.write(f"Total de casos: {test_suite_stats['total']}\n├── Tradicionais: {test_suite_stats['traditional']}\n")
        f.write(f"└── Comportamentais: {test_suite_stats['behavioral']}\n{'='*80}\n\n")

    def _write_txt_case(self, f, row: Dict):
        f.write(f"\n{'='*60}\nID: {row.get('ID', 'unknown')}\nTest Type: {row.get('Test_Type', 'traditional')}\nQuery: {row.get('Query', '')}\n")
        f.write(f"\n--- V1 (VANILLA) ---\nAnswer: {row.get('V1_Answer', '')[:800]}\n")
        if row.get('Test_Type') == 'behavioral':
            f.write(f"Behavioral Passed: {row.get('V1_Behavioral_Passed', False)}\nBehavioral Reason: {row.get('V1_Behavioral_Reason', '')}\n")
        else:
            f.write(f"\n--- V1 MÉTRICAS ---\n")
            for m in ["Faithfulness", "Answer_Rel", "C_Relevancia", "C_Precision", "C_Recall"]:
                f.write(f"{m}: {row.get(f'V1_{m}_Score', 0):.3f}\n  Reason: {row.get(f'V1_{m}_Reason', '')[:500]}\n")
                
        f.write(f"\n--- V9 (TEMPORAL) ---\nAnswer: {row.get('V9_Answer', '')[:800]}\n")
        if row.get('Test_Type') == 'behavioral':
            f.write(f"Behavioral Passed: {row.get('V9_Behavioral_Passed', False)}\nBehavioral Reason: {row.get('V9_Behavioral_Reason', '')}\n")
        else:
            f.write(f"\n--- V9 MÉTRICAS ---\n")
            for m in ["Faithfulness", "Answer_Rel", "C_Relevancia", "C_Precision", "C_Recall"]:
                f.write(f"{m}: {row.get(f'V9_{m}_Score', 0):.3f}\n  Reason: {row.get(f'V9_{m}_Reason', '')}\n")
        f.write("-" * 60 + "\n")

    def _write_txt_summary(self, f, results_table: List[Dict]):
        f.write(f"\n{'='*80}\nRESUMO DOS RESULTADOS\n{'='*80}\n")
        traditional = [r for r in results_table if r.get("Test_Type") != "behavioral"]
        if traditional:
            f.write("\n📊 MÉTRICAS MÉDIAS (DeepEval):\n")
            for m in ["Faithfulness", "Answer_Rel", "C_Relevancia", "C_Precision", "C_Recall"]:
                v1_s = [r[f"V1_{m}_Score"] for r in traditional if isinstance(r.get(f"V1_{m}_Score"), (int, float))]
                v9_s = [r[f"V9_{m}_Score"] for r in traditional if isinstance(r.get(f"V9_{m}_Score"), (int, float))]
                if v1_s and v9_s:
                    v1_avg, v9_avg = sum(v1_s) / len(v1_s), sum(v9_s) / len(v9_s)
                    var = v9_avg - v1_avg
                    arrow = "↑" if var > 0 else "↓" if var < 0 else "→"
                    f.write(f"  {m}: V1={v1_avg:.3f} {arrow} V9={v9_avg:.3f} (Δ {var:+.3f})\n")
                    
        behavioral = [r for r in results_table if r.get("Test_Type") == "behavioral"]
        if behavioral:
            v1_p = sum(1 for r in behavioral if r.get("V1_Behavioral_Passed"))
            v9_p = sum(1 for r in behavioral if r.get("V9_Behavioral_Passed"))
            f.write(f"\n📊 TESTES COMPORTAMENTAIS:\n  V1: {v1_p}/{len(behavioral)} ({v1_p/len(behavioral)*100:.0f}%)\n  V9: {v9_p}/{len(behavioral)} ({v9_p/len(behavioral)*100:.0f}%)\n")

    def _write_txt_recommendation(self, f):
        f.write(f"\n{'='*80}\n🎯 RECOMENDAÇÃO FINAL\n{'='*80}\n" +
                "\n✅ Use V9 (Temporal) para suporte específico com SKU, e-commerce e catálogo.\n" +
                "✅ Use V1 (Vanilla) para chat geral e troubleshooting sem SKU do produto.\n")

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
        f.write("### Métricas DeepEval\n\n| Métrica | V1 (Vanilla) | V9 (Temporal) | Variação |\n|---|---|---|---|\n")
        traditional = [r for r in results_table if r.get("Test_Type") != "behavioral"]
        if traditional:
            for m in ["Faithfulness", "Answer_Rel", "C_Relevancia", "C_Precision", "C_Recall"]:
                v1_avg = np.mean([r[f"V1_{m}_Score"] for r in traditional])
                v9_avg = np.mean([r[f"V9_{m}_Score"] for r in traditional])
                var = v9_avg - v1_avg
                emoji = "🟢" if var > 0 else "🔴" if var < 0 else "⚪"
                f.write(f"| {m} | {v1_avg:.3f} | {v9_avg:.3f} | {emoji} {var:+.3f} |\n")

    def _write_md_behavioral_table(self, f, results_table: List[Dict]):
        behavioral = [r for r in results_table if r.get("Test_Type") == "behavioral"]
        if not behavioral: return
        f.write("\n### Testes Comportamentais\n\n| ID | Comportamento Esperado | V1 | V9 | V1 Reason | V9 Reason |\n|---|---|---|---|---|---|\n")
        for row in behavioral:
            f.write(f"| {row.get('ID')} | {row.get('Expected_Behavior', '')[:30]} | "
                    f"{'✅' if row.get('V1_Behavioral_Passed') else '❌'} | {'✅' if row.get('V9_Behavioral_Passed') else '❌'} | "
                    f"{row.get('V1_Behavioral_Reason', '').replace('|', '\\|')} | {row.get('V9_Behavioral_Reason', '').replace('|', '\\|')} |\n")

    def _write_md_recommendation(self, f):
        f.write("\n### Conclusão\n- **V9 é superior para casos que exigem PRECISÃO e RASTREABILIDADE**\n- **V1 é melhor para CASOS GERAIS onde utilidade > precisão**\n")


# ============================================================================
# SUMMARY PRINTER
# ============================================================================

class SummaryPrinter:
    """Prints evaluation summary to console cleanly."""
    @staticmethod
    def print_summary(results_table: List[Dict]):
        print(f"\n{'='*80}\n✅ AVALIAÇÃO COMPARATIVA CONCLUÍDA\n{'='*80}")
        SummaryPrinter._print_metric_analysis(results_table)
        SummaryPrinter._print_behavioral_analysis(results_table)
        
    @staticmethod
    def _print_metric_analysis(results_table: List[Dict]):
        traditional = [r for r in results_table if r.get("Test_Type") != "behavioral"]
        if not traditional: return
        print("\n📊 ANÁLISE DE GANHO DO V9 SOBRE V1:")
        for metric in ["Faithfulness", "Answer_Rel", "C_Relevancia"]:
            v1_scores = [r[f"V1_{metric}_Score"] for r in traditional if isinstance(r.get(f"V1_{metric}_Score"), (int, float))]
            v9_scores = [r[f"V9_{metric}_Score"] for r in traditional if isinstance(r.get(f"V9_{metric}_Score"), (int, float))]
            if v1_scores and v9_scores:
                v1_avg, v9_avg = np.mean(v1_scores), np.mean(v9_scores)
                gain = v9_avg - v1_avg
                gain_pct = (gain / v1_avg * 100) if v1_avg > 0 else 0
                symbol = "🟢" if gain > 0.05 else "🔴" if gain < -0.05 else "⚪"
                print(f"   {symbol} {metric}: V1={v1_avg:.3f} → V9={v9_avg:.3f} ({gain:+.3f} / {gain_pct:+.1f}%)")

    @staticmethod
    def _print_behavioral_analysis(results_table: List[Dict]):
        behavioral = [r for r in results_table if r.get("Test_Type") == "behavioral"]
        if not behavioral: return
        v1_passed = sum(1 for r in behavioral if r.get("V1_Behavioral_Passed"))
        v9_passed = sum(1 for r in behavioral if r.get("V9_Behavioral_Passed"))
        print(f"\n📊 TESTES COMPORTAMENTAIS ({len(behavioral)} casos):")
        print(f"   V1 (Vanilla): {v1_passed}/{len(behavioral)} ({v1_passed/len(behavioral)*100:.0f}%)")
        print(f"   V9 (Temporal): {v9_passed}/{len(behavioral)} ({v9_passed/len(behavioral)*100:.0f}%)")


# ============================================================================
# MAIN EVALUATION PIPELINE
# ============================================================================

class ComparativeEvaluationPipeline:
    """Orchestrates the entire comparative execution pipeline asynchronously."""
    def __init__(self):
        self.config = EvalConfig()
        self.embedding_cache = EmbeddingCache(self.config.cache_dir, self.config.embedding_cache_size)
        self.rag_manager = ComparativeRAGManager(self.config.base_path, self.config, self.embedding_cache)
        self.metric_evaluator = ComparativeMetricEvaluator(self.config)
        self.behavioral_analyzer = BehavioralTestAnalyzer()
        self.csv_path = self.config.output_dir / f"COMPARATIVO_V1_VS_V9_{self.config.timestamp}.csv"
        self.txt_path = self.config.output_dir / f"RELATORIO_COMPARATIVO_{self.config.timestamp}.txt"
        self.semaphore = asyncio.Semaphore(self.config.concurrent_tasks)

    async def run(self):
        self._print_header()
        results_table = []

        with open(self.txt_path, 'w', encoding='utf-8') as f_report:
            f_report.write(f"RELATÓRIO COMPARATIVO V1 vs V9\nData: {self.config.timestamp}\nBase: {self.config.base_path}\n{'='*80}\n\n")
            
            # Executa tasks controladas por pool assíncrono para velocidade máxima
            tasks = [self._process_bounded_case(tc, f_report) for tc in TEST_SUITE]
            
            # Exibe barra de progresso reativa assíncrona
            for future in tqdm.as_completed(tasks, desc="Avaliando Casos"):
                row = await future
                results_table.append(row)
                # Escrita incremental segura do dataframe
                pd.DataFrame(results_table).to_csv(self.csv_path, index=False)

            f_report.write(f"\n{'='*80}\nRECOMENDAÇÃO FINAL\n{'='*80}\n\nO V9 é SUPERIOR em precisão; V1 em escopo.\n")
            
        SummaryPrinter.print_summary(results_table)
        print(f"\n📁 CSV: {self.csv_path}\n📁 Relatório: {self.txt_path}")

    async def _process_bounded_case(self, test_case: Dict, f_report) -> Dict:
        """Adiciona controle de concorrência à execução do pipeline individual."""
        async with self.semaphore:
            return await self._process_case(test_case, f_report)

    async def _process_case(self, test_case: Dict, f_report) -> Dict:
        query = test_case["input"]
        ref_date = test_case.get("reference_date", "2026-03-12")
        test_type = test_case.get("test_type", "traditional")
        
        # Executa barramento de busca paralelo
        res_v1, res_v9 = await self.rag_manager.search_both(query, ref_date)
        
        case_v1 = LLMTestCase(input=query, actual_output=res_v1["answer"], retrieval_context=res_v1.get("sources", [])[:5], expected_output=test_case.get("expected_output"))
        case_v9 = LLMTestCase(input=query, actual_output=res_v9["answer"], retrieval_context=res_v9.get("sources", [])[:5], expected_output=test_case.get("expected_output"))
        
        try:
            metrics_v1, metrics_v9 = await self.metric_evaluator.evaluate_both(case_v1, case_v9)
        except Exception:
            metrics_v1 = {name: {"score": 0.0, "reason": "Erro no runtime do avaliador"} 
                          for name in ["Faithfulness", "Answer_Rel", "C_Relevancia", "C_Precision", "C_Recall"]}
            metrics_v9 = metrics_v1.copy()
            
        behav_v1, behav_v9, reason_v1, reason_v9 = self.behavioral_analyzer.analyze(test_case, res_v1["answer"], res_v9["answer"])
        
        row = {
            "ID": test_case.get("id", "unknown"), "Test_Type": test_type, "Query": query,
            "V1_Answer": res_v1["answer"], "V1_Behavioral_Passed": behav_v1, "V1_Behavioral_Reason": reason_v1,
            "V9_Answer": res_v9["answer"], "V9_Behavioral_Passed": behav_v9, "V9_Behavioral_Reason": reason_v9,
            "Expected_Behavior": test_case.get("expected_behavior", "")
        }
        
        for name in metrics_v1:
            row[f"V1_{name}_Score"] = metrics_v1[name]["score"]
            row[f"V1_{name}_Reason"] = metrics_v1[name]["reason"]
            row[f"V9_{name}_Score"] = metrics_v9[name]["score"]
            row[f"V9_{name}_Reason"] = metrics_v9[name]["reason"]
            
        self._write_case_report(f_report, test_case, query, ref_date, res_v1, res_v9, test_type, behav_v1, behav_v9, reason_v1, reason_v9, metrics_v1, metrics_v9)
        return row

    def _write_case_report(self, f_report, test_case, query, ref_date, res_v1, res_v9, test_type, behav_v1, behav_v9, reason_v1, reason_v9, metrics_v1, metrics_v9):
        report_data = (
            f"\n{'='*80}\nID: {test_case.get('id')}\nQuery: {query}\nReference Date: {ref_date}\n"
            f"\n--- V1 (VANILLA) ---\nRESPONSE:\n{res_v1['answer']}\n"
            f"\n--- V9 (TEMPORAL) ---\nRESPONSE:\n{res_v9['answer']}\n"
        )
        if test_type == "behavioral":
            report_data += f"\n--- COMPORTAMENTAL ---\nV1 Passed: {behav_v1} | Reason: {reason_v1}\nV9 Passed: {behav_v9} | Reason: {reason_v9}\n"
        else:
            report_data += f"\n--- MÉTRICAS (DeepEval) ---\n"
            for n in metrics_v1:
                report_data += f"{n}:\n  V1: {metrics_v1[n]['score']:.3f} | V1 Reason: {metrics_v1[n]['reason']}\n  V9: {metrics_v9[n]['score']:.3f} | V9 Reason: {metrics_v9[n]['reason']}\n"
        f_report.write(report_data)
        f_report.flush()

    def _print_header(self):
        print(f"\n{'='*80}\n🚀 AVALIAÇÃO COMPARATIVA: V1 (Vanilla) vs V9 (Temporal)\n📍 Data: {self.config.timestamp}\n📊 Casos: {len(TEST_SUITE)}\n{'='*80}")


async def main():
    pipeline = ComparativeEvaluationPipeline()
    await pipeline.run()


if __name__ == "__main__":
    asyncio.run(main())

