"""core/metric_evaluator.py - Avaliação de métricas DeepEval"""

import asyncio
from typing import Dict, Tuple, Optional

from tqdm import tqdm
from deepeval.test_case import LLMTestCase
from deepeval.metrics import (
    ContextualPrecisionMetric,
    ContextualRelevancyMetric,
    ContextualRecallMetric,
    FaithfulnessMetric,
    AnswerRelevancyMetric
)

from custom_evaluatorV2Backup import OllamaEvaluator


class ComparativeMetricEvaluator:
    """Avalia ambas as versões com métricas DeepEval"""
    
    def __init__(self, config):
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
    
    # core/metric_evaluator.py - Otimização de concorrência
    async def evaluate_both(self, case_v1: LLMTestCase, case_v9: LLMTestCase, 
                        pbar: Optional[tqdm] = None) -> Tuple[Dict, Dict]:
        results_v1 = {}
        results_v9 = {}
        
        # Criamos uma lista de tarefas para execução paralela
        tasks = []
        metric_names = list(self.metrics_v1.keys())

        for name in metric_names:
            tasks.append(self._measure(self.metrics_v1[name], case_v1, pbar))
            tasks.append(self._measure(self.metrics_v9[name], case_v9, pbar))

        # Executa tudo respeitando o semáforo configurado em EvalConfig
        raw_results = await asyncio.gather(*tasks)

        # Reorganiza os resultados nos dicionários correspondentes
        for i, name in enumerate(metric_names):
            v1_idx = i * 2
            v9_idx = i * 2 + 1
            results_v1[name] = {"score": raw_results[v1_idx][0], "reason": raw_results[v1_idx][1]}
            results_v9[name] = {"score": raw_results[v9_idx][0], "reason": raw_results[v9_idx][1]}
        
        return results_v1, results_v9
    
    async def _measure(self, metric, test_case: LLMTestCase, 
                pbar=None) -> Tuple[float, str]:
        async with self.semaphore:
            # OTIMIZAÇÃO: Log explícito da métrica e versão
            metric_name = metric.__class__.__name__
            version = getattr(metric.model, 'prompt_version', 'Unknown')
            if pbar:
                pbar.write(f"   [RUNNING] {metric_name} for {version}...")
            try:
                await asyncio.to_thread(metric.measure, test_case)
                
                # Verificar se há erro no reason
                reason = self._extract_reason(metric)
                if "validation error" in reason.lower() or "field required" in reason.lower():
                    # Tentar recuperar com um fallback
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