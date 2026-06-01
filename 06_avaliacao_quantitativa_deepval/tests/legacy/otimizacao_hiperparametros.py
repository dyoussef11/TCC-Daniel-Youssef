"""
otimizacao_hiperparametros_v2.py
Otimização de hiperparâmetros - REUTILIZANDO a mesma instância do RAG.
"""

import asyncio
import itertools
from datetime import datetime
from pathlib import Path
from typing import Dict, List
from dataclasses import dataclass, field

import pandas as pd
from tqdm import tqdm

from deepeval.test_case import LLMTestCase
from deepeval.metrics import (
    AnswerRelevancyMetric,
    FaithfulnessMetric,
    ContextualRelevancyMetric
)

from core.paths import VETORIZATION_DATA, AVALIACAO_DATA, VALIDACAO_SCRIPT
import sys
sys.path.append(str(VALIDACAO_SCRIPT))

from dataset_avaliacaoV3 import TEST_SUITE
from RAG_Temporal_V8_CPUMode_CacheReady import SpecialistTimeAwareRAG
from custom_evaluatorV2Backup import OllamaEvaluator
from evaluate_rag_deepeval_TemporalVSNãoTemporalV7_CacheReady import EmbeddingCache


@dataclass
class HyperparamGrid:
    models: List[str] = field(default_factory=lambda: ["phi3.5:latest", "qwen3:4b-instruct"])
    temperatures: List[float] = field(default_factory=lambda: [0.0, 0.3])
    top_k_values: List[int] = field(default_factory=lambda: [5, 10])
    similarity_thresholds: List[float] = field(default_factory=lambda: [1.0, 1.2])
    
    def __len__(self) -> int:
        """Retorna o número total de combinações."""
        return (len(self.models) * len(self.temperatures) * 
                len(self.top_k_values) * len(self.similarity_thresholds))
    
    def combinations(self) -> List[Dict]:
        combos = []
        for model, temp, top_k, threshold in itertools.product(
            self.models, self.temperatures, self.top_k_values, self.similarity_thresholds
        ):
            combos.append({
                "model": model,
                "temperature": temp,
                "top_k": top_k,
                "similarity_threshold": threshold
            })
        return combos


class ReusableRAGOptimizer:
    """
    Otimizador que REUTILIZA a mesma instância do RAG.
    Apenas os parâmetros de inferência são alterados entre combinações.
    """
    
    def __init__(self, base_path: Path, test_suite: List[Dict]):
        self.base_path = base_path
        self.test_suite = test_suite[:2]  # 2 casos para teste rápido
        self.results = []
        self.grid = HyperparamGrid()
        self.evaluator = OllamaEvaluator(model_name="qwen3:4b-instruct")
        
        # Cache compartilhado
        self.cache = EmbeddingCache(AVALIACAO_DATA / "cache", max_size=1000)
        
        # ⭐ CRIA O RAG UMA ÚNICA VEZ
        print("\n🔧 Criando instância única do RAG...")
        self.rag = SpecialistTimeAwareRAG(self.base_path, embedding_cache=self.cache)
        print("✅ RAG carregado uma única vez - será reutilizado!")
        
        total_combos = len(self.grid)  # ⭐ Agora funciona!
        print(f"\n⚡ Configuração:")
        print(f"   Cache: {self.cache.stats()['size']} embeddings")
        print(f"   Combinações: {total_combos}")
        print(f"   Queries por combinação: {len(self.test_suite)}")
        print(f"   Total execuções: {total_combos * len(self.test_suite)}")
    
    async def evaluate_combination(self, hyperparams: Dict, case: Dict) -> Dict:
        """Avalia uma combinação - REUTILIZANDO a mesma instância do RAG."""
        
        query = case["input"]
        ref_date = case.get("reference_date", "2026-03-12")
        expected = case.get("expected_output", "")
        
        # ⭐ ALTERA OS PARÂMETROS DINAMICAMENTE (sem recriar o RAG)
        self.rag.search_top_k = hyperparams["top_k"]
        self.rag.similarity_threshold = hyperparams["similarity_threshold"]
        self.rag.temperature = hyperparams["temperature"]
        self.rag.current_model = hyperparams["model"]
        
        # Gera resposta (embedding virá do cache!)
        result = await self.rag.search(query, ref_date)
        actual_output = result["answer"]
        retrieval_context = result.get("sources", [])[:5]
        
        # Cria caso de teste
        test_case = LLMTestCase(
            input=query,
            actual_output=actual_output,
            expected_output=expected,
            retrieval_context=retrieval_context
        )
        
        # Avalia métricas em paralelo
        answer_metric = AnswerRelevancyMetric(model=self.evaluator, include_reason=False, threshold=0.5)
        faith_metric = FaithfulnessMetric(model=self.evaluator, include_reason=False, threshold=0.7)
        context_metric = ContextualRelevancyMetric(model=self.evaluator, include_reason=False, threshold=0.5)
        
        tasks = [
            self._measure_metric(test_case, answer_metric),
            self._measure_metric(test_case, faith_metric),
            self._measure_metric(test_case, context_metric)
        ]
        scores = await asyncio.gather(*tasks)
        
        combined = scores[0] * 0.3 + scores[1] * 0.5 + scores[2] * 0.2
        
        return {
            **hyperparams,
            "query": query[:50],
            "answer_relevancy": scores[0],
            "faithfulness": scores[1],
            "contextual_relevancy": scores[2],
            "combined_score": combined
        }
    
    async def _measure_metric(self, test_case: LLMTestCase, metric) -> float:
        try:
            await asyncio.to_thread(metric.measure, test_case)
            return float(metric.score)
        except Exception as e:
            return 0.0
    
    async def run(self) -> pd.DataFrame:
        combos = self.grid.combinations()
        
        total_evals = len(combos) * len(self.test_suite)
        print(f"\n📊 Iniciando {total_evals} avaliações...")
        
        with tqdm(total=total_evals, desc="Testando combinações") as pbar:
            for hyperparams in combos:
                for case in self.test_suite:
                    try:
                        result = await self.evaluate_combination(hyperparams, case)
                        result["test_case_id"] = case.get("id", "unknown")
                        self.results.append(result)
                    except Exception as e:
                        print(f"\n❌ Erro: {e}")
                        import traceback
                        traceback.print_exc()
                    pbar.update(1)
        
        df = pd.DataFrame(self.results)
        if not df.empty:
            df = df.sort_values("combined_score", ascending=False)
        return df
    
    def print_results(self, df: pd.DataFrame):
        print("\n" + "=" * 70)
        print("📊 RESULTADOS DA OTIMIZAÇÃO (RAG REUTILIZADO)")
        print("=" * 70)
        
        if df.empty:
            print("Nenhum resultado obtido.")
            return
        
        # Resultados por combinação (média)
        grouped = df.groupby(["model", "temperature", "top_k", "similarity_threshold"]).agg({
            "answer_relevancy": "mean",
            "faithfulness": "mean",
            "contextual_relevancy": "mean",
            "combined_score": "mean"
        }).reset_index().sort_values("combined_score", ascending=False)
        
        print("\n🏆 MELHORES COMBINAÇÕES (média):")
        print("-" * 50)
        for i, row in grouped.head(5).iterrows():
            print(f"\n📌 #{i+1} (Score: {row['combined_score']:.3f})")
            print(f"   Modelo: {row['model']}")
            print(f"   Temperatura: {row['temperature']}")
            print(f"   Top-K: {row['top_k']:.0f}")
            print(f"   Threshold: {row['similarity_threshold']}")
            print(f"   📈 Answer Relevancy: {row['answer_relevancy']:.3f}")
            print(f"   📈 Faithfulness: {row['faithfulness']:.3f}")
            print(f"   📈 Contextual Relevancy: {row['contextual_relevancy']:.3f}")
        
        # Salva resultados
        output_path = AVALIACAO_DATA / f"hyperparam_optimized_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
        df.to_csv(output_path, index=False)
        grouped.to_csv(output_path.parent / f"hyperparam_summary_{datetime.now().strftime('%Y%m%d_%H%M')}.csv", index=False)
        
        print(f"\n💾 Resultados salvos em: {output_path}")
        print(f"💾 Sumário salvo em: {output_path.parent}/hyperparam_summary_*.csv")


async def quick_verify():
    """Verificação rápida se o RAG está funcionando."""
    print("\n" + "=" * 70)
    print("🔍 VERIFICAÇÃO RÁPIDA")
    print("=" * 70)
    
    base_path = VETORIZATION_DATA / 'base_conhecimento_multilingueV7.json'
    cache = EmbeddingCache(AVALIACAO_DATA / "cache", max_size=1000)
    
    print("\n🔧 Criando RAG...")
    rag = SpecialistTimeAwareRAG(base_path, embedding_cache=cache)
    
    query = "What is the maximum RAM capacity for the Acer Nitro 5 AN515-56?"
    print(f"\n📝 Testando query: {query[:80]}...")
    
    result = await rag.search(query)
    print(f"\n✅ Resposta recebida (primeiros 200 chars):")
    print(f"   {result['answer'][:200]}...")
    print(f"\n📊 Estatísticas do cache: {cache.stats()}")
    
    print("\n✅ Verificação concluída! Tudo funcionando.")


async def main():
    print("\n" + "=" * 70)
    print("🔧 OTIMIZAÇÃO - REUTILIZANDO A MESMA INSTÂNCIA DO RAG")
    print("=" * 70)
    
    base_path = VETORIZATION_DATA / 'base_conhecimento_multilingueV7.json'
    if not base_path.exists():
        print(f"❌ Base não encontrada: {base_path}")
        return
    
    print("\nEscolha uma opção:")
    print("1 - Verificação rápida (testar se o RAG funciona)")
    print("2 - Otimização completa (16 combinações x 2 queries)")
    
    choice = input("\nOpção (1/2): ").strip()
    
    if choice == "1":
        await quick_verify()
    else:
        optimizer = ReusableRAGOptimizer(base_path, TEST_SUITE)
        results = await optimizer.run()
        optimizer.print_results(results)


if __name__ == "__main__":
    asyncio.run(main())