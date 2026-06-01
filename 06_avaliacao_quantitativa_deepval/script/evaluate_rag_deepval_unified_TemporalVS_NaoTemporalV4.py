"""evaluate_rag_comparative.py - Orquestrador principal da avaliação comparativa"""

import asyncio
from pathlib import Path
from typing import Dict, List

import pandas as pd
from tqdm import tqdm

from core.paths import VALIDACAO_SCRIPT, AVALIACAO_SCRIPT
import sys
sys.path.append(str(VALIDACAO_SCRIPT))
sys.path.append(str(AVALIACAO_SCRIPT))

from dataset_avaliacaoV4 import TEST_SUITE
from deepeval.test_case import LLMTestCase

from eval_modules.eval_config import EvalConfig
from eval_modules.embedding_cache import EmbeddingCache
from eval_modules.rag_manager import ComparativeRAGManager
from eval_modules.metric_evaluator import ComparativeMetricEvaluator
from eval_modules.behavioral_analyzer import BehavioralTestAnalyzer
from eval_modules.summary_printer import SummaryPrinter


class ComparativeEvaluationPipeline:
    """Pipeline principal que orquestra a avaliação comparativa"""
    
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
        
        # Executa ambas as versões
        res_v1, res_v9 = await self.rag_manager.search_both(query, ref_date)
        
        # Log da expansão (diagnóstico)
        pbar.write(f"   V1 normalized: {res_v1.get('normalized_query', query)}")
        pbar.write(f"   V9 normalized: {res_v9.get('normalized_query', query)}")
        
        # Prepara casos DeepEval
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
        
        # Avalia comportamento
        behav_v1, behav_v9, reason_v1, reason_v9 = self.behavioral_analyzer.analyze(
            test_case, res_v1["answer"], res_v9["answer"]
        )
        
        # Monta resultado
        row = self._build_result_row(test_case, test_type, query, 
                                     res_v1, res_v9, 
                                     behav_v1, behav_v9, reason_v1, reason_v9,
                                     metrics_v1, metrics_v9)
        
        # Escreve no relatório
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
            row["Expected_Behavior"] = test_case.get("expected_behavior", "")
        
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
                f_report.write(f"  V1 Reason: {metrics_v1[name]['reason']}\n")  # ✅ ADICIONADO
                f_report.write(f"  V9: {metrics_v9[name]['score']:.3f}\n")
                f_report.write(f"  V9 Reason: {metrics_v9[name]['reason']}\n")  # ✅ ADICIONADO
                f_report.write(f"\n")
        
        f_report.flush()


async def main():
    pipeline = ComparativeEvaluationPipeline()
    await pipeline.run()


if __name__ == "__main__":
    asyncio.run(main())