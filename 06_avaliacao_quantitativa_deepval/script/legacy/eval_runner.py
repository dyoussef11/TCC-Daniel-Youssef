import asyncio
import pandas as pd
from tqdm import tqdm
from deepeval.test_case import LLMTestCase
from deepeval.metrics import (
    FaithfulnessMetric, 
    AnswerRelevancyMetric,
    ContextualPrecisionMetric,
    ContextualRecallMetric,
    ContextualRelevancyMetric
)

from core.paths import VALIDACAO_SCRIPT, AVALIACAO_SCRIPT
import sys
sys.path.append(str(VALIDACAO_SCRIPT))
sys.path.append(str(AVALIACAO_SCRIPT))

# Seus imports originais
from RAG_BaseLine import VanillaRAG
from RAG_Temporal_V9 import SpecialistTimeAwareRAG
from eval_core import EvalConfig, EmbeddingCache, BehavioralAnalyzer
from custom_evaluatorV2Backup import OllamaEvaluator
from dataset_avaliacaoV4 import TEST_SUITE 

class MiniPipeline:
    def __init__(self):
        self.config = EvalConfig()
        self.cache = EmbeddingCache(self.config.cache_dir)
        self.analyzer = BehavioralAnalyzer()
        
        # Inicialização das RAGs
        self.v1 = VanillaRAG(self.config.base_path, embedding_cache=self.cache)
        self.v9 = SpecialistTimeAwareRAG(self.config.base_path, embedding_cache=self.cache)
        
        # Avaliador Local (Ollama)
        # Note: se o config não tiver 'evaluator_model', use o nome do modelo diretamente aqui
        model_name = getattr(self.config, 'evaluator_model', 'qwen3:4b-instruct')
        self.evaluator = OllamaEvaluator(model_name=model_name)
        
        # Inicialização das Métricas (Criamos uma vez no init para reutilizar)
        self._init_metrics()

    def _init_metrics(self):
        """Prepara todas as métricas com o avaliador local"""
        common_params = {"model": self.evaluator, "include_reason": True}
        
        self.metrics = {
            "Faithfulness": FaithfulnessMetric(threshold=0.7, **common_params),
            "Answer_Rel": AnswerRelevancyMetric(threshold=0.7, **common_params),
            "C_Precision": ContextualPrecisionMetric(threshold=0.7, **common_params),
            "C_Recall": ContextualRecallMetric(threshold=0.7, **common_params),
            "C_Relevancy": ContextualRelevancyMetric(threshold=0.7, **common_params)
        }

    async def run(self):
        results = []
        for case in tqdm(TEST_SUITE, desc="Comparando RAGs"):
            query = case["input"]
            ref_dt = case.get("reference_date", "2026-03-23")
            expected = case.get("expected_output", "")
            
            # 1. Busca Paralela
            res_v1, res_v9 = await asyncio.gather(
                self.v1.search(query, ref_date=ref_dt), 
                self.v9.search(query, ref_date=ref_dt)
            )

            # 2. Análise Comportamental
            pass_v1, pass_v9 = self.analyzer.analyze(case, res_v1["answer"], res_v9["answer"])

            # 3. Execução das Métricas DeepEval (Focado na V9)
            test_case_v9 = LLMTestCase(
                input=query,
                actual_output=res_v9["answer"],
                retrieval_context=res_v9.get("sources", []),
                expected_output=expected,
            )
            
            row = {
                "ID": case["id"],
                "Query": query,
                "V1_Pass": pass_v1,
                "V9_Pass": pass_v9,
                "V1_Answer": res_v1["answer"][:150] + "...",
                "V9_Answer": res_v9["answer"][:150] + "..."
            }

            # Loop para medir e salvar cada métrica de interesse
            for name, metric in self.metrics.items():
                try:
                    metric.measure(test_case_v9)
                    row[f"V9_{name}_Score"] = metric.score
                    row[f"V9_{name}_Reason"] = getattr(metric, 'reason', '')
                except Exception as e:
                    print(f"⚠️ Erro na métrica {name} para o caso {case['id']}: {e}")
                    row[f"V9_{name}_Score"] = 0.0

            results.append(row)
            
            # Salvamento incremental (segurança)
            if len(results) % 1 == 0:
                pd.DataFrame(results).to_csv(self.config.output_dir / f"TEMP_RESULTADO.csv", index=False)

        # 4. Salvamento Final
        output_path = self.config.output_dir / f"RESULTADO_COMPLETO_{self.config.timestamp}.csv"
        pd.DataFrame(results).to_csv(output_path, index=False)
        print(f"\n✅ Avaliação Finalizada! Relatório em: {output_path}")

if __name__ == "__main__":
    pipeline = MiniPipeline()
    asyncio.run(pipeline.run())