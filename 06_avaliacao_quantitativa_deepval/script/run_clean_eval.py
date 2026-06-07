import asyncio
import json
import pandas as pd
from pathlib import Path
from datetime import datetime

from deepeval.test_case import LLMTestCase
from deepeval import evaluate
from deepeval.metrics import FaithfulnessMetric, AnswerRelevancyMetric

# Importações dos seus módulos existentes
from custom_evaluatorV2Backup import create_evaluator
from dataset_avaliacaoV4 import TEST_SUITE
from core.paths import VALIDACAO_SCRIPT, AVALIACAO_SCRIPT
import sys
sys.path.append(str(VALIDACAO_SCRIPT))
sys.path.append(str(AVALIACAO_SCRIPT))
from RAG_BaseLine import VanillaRAG
from RAG_Temporal_V9_3 import SpecialistTimeAwareRAG

# ============================================================================
# 1. ESTÁGIO DE GERAÇÃO: Coleta de respostas em paralelo
# ============================================================================
async def generate_rag_responses(test_suite: list, base_path: Path) -> list:
    """Roda as queries no RAG V1 e V9 isolando a etapa de inferência."""
    print("🔄 Inicializando motores de busca RAG...")
    v1_rag = VanillaRAG(base_path, use_expansion=False)
    v9_rag = SpecialistTimeAwareRAG(base_path, variant_name="V9_HYBRID_MIXED_AUDITOR", use_expansion=True)
    
    generated_dataset = []
    
    print(f"🏃 Rodando inferência para {len(test_suite)} casos...")
    for case in test_suite:
        query = case["input"]
        ref_date = case.get("reference_date", "2026-03-12")
        
        # Chamadas concorrentes por caso de teste
        v1_task = asyncio.to_thread(v1_rag.search, query)
        v9_task = asyncio.to_thread(v9_rag.search, query, ref_date)
        res_v1, res_v9 = await asyncio.gather(v1_task, v9_task)
        
        generated_dataset.append({
            "meta": case,
            "v1_output": res_v1["answer"],
            "v1_context": res_v1.get("sources", [])[:3],
            "v9_output": res_v9["answer"],
            "v9_context": res_v9.get("sources", [])[:3]
        })
    return generated_dataset

# ============================================================================
# 2. ESTÁGIO DE VALIDAÇÃO COMPORTAMENTAL (Rápido e Sem Custo de LLM)
# ============================================================================
def evaluate_behavioral_rules(output: str, meta: dict) -> dict:
    """Aplica o filtro rápido de padrões proibidos e obrigatórios."""
    if meta.get("test_type") != "behavioral":
        return {"passed": True, "reason": "N/A (Traditional)"}
        
    output_lower = output.lower()
    forbidden = meta.get("forbidden_patterns", [])
    required = meta.get("required_patterns", [])
    
    forbidden_found = [p for p in forbidden if p.lower() in output_lower]
    required_found = [p for p in required if p.lower() in output_lower]
    
    passed = len(forbidden_found) == 0 and len(required_found) >= meta.get("min_required_matches", 1)
    
    reason = f"Faltou: {[p for p in required if p.lower() not in output_lower]}." if not passed else "OK"
    if forbidden_found:
        reason += f" Encontrou Proibido: {forbidden_found}"
        
    return {"passed": passed, "reason": reason}

# ============================================================================
# 3. PIPELINE PRINCIPAL DE EXECUÇÃO
# ============================================================================
async def main():
    base_path = Path("./base_conhecimento_multilingueV9.json")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    
    # Passo 1: Obter saídas dos modelos (Gargalo de IO de rede/Ollama)
    raw_data = await generate_rag_responses(TEST_SUITE, base_path)
    
    # Passo 2: Inicializar Métricas Oficiais do DeepEval com seus avaliadores customizados
    evaluator_v1 = create_evaluator(version="V1", model_name="qwen3:4b-instruct")
    evaluator_v9 = create_evaluator(version="V9", model_name="qwen3:4b-instruct")
    
    metrics_v1 = [
        FaithfulnessMetric(threshold=0.8, model=evaluator_v1),
        AnswerRelevancyMetric(threshold=0.8, model=evaluator_v1)
    ]
    metrics_v9 = [
        FaithfulnessMetric(threshold=0.9, model=evaluator_v9),
        AnswerRelevancyMetric(threshold=0.8, model=evaluator_v9)
    ]
    
    # Passo 3: Preparar os TestCases estruturados para o DeepEval Engine
    test_cases_v1 = []
    test_cases_v9 = []
    results_summary = []
    
    for item in raw_data:
        meta = item["meta"]
        
        # Validadores comportamentais locais via heurística de string (Custo zero de LLM)
        behav_v1 = evaluate_behavioral_rules(item["v1_output"], meta)
        behav_v9 = evaluate_behavioral_rules(item["v9_output"], meta)
        
        # Criando payloads para a engine do DeepEval
        tc_v1 = LLMTestCase(input=meta["input"], actual_output=item["v1_output"], retrieval_context=item["v1_context"], expected_output=meta.get("expected_output", "N/A"))
        tc_v9 = LLMTestCase(input=meta["input"], actual_output=item["v9_output"], retrieval_context=item["v9_context"], expected_output=meta.get("expected_output", "N/A"))
        
        test_cases_v1.append(tc_v1)
        test_cases_v9.append(tc_v9)
        
        results_summary.append({
            "ID": meta["id"],
            "Query": meta["input"],
            "Type": meta.get("test_type"),
            "V1_Behavioral_Pass": behav_v1["passed"],
            "V1_Behavioral_Reason": behav_v1["reason"],
            "V9_Behavioral_Pass": behav_v9["passed"],
            "V9_Behavioral_Reason": behav_v9["reason"],
        })

    # Passo 4: O Pulo do Gato para Escala — Execução em Lote Assíncrona Nativa do DeepEval
    print("📊 Executando avaliação em lote via DeepEval Engine (V1)...")
    # O DeepEval gerencia a concorrência internamente de forma otimizada
    eval_v1_results = evaluate(test_cases_v1, metrics_v1, print_results=False)
    
    print("📊 Executando avaliação em lote via DeepEval Engine (V9)...")
    eval_v9_results = evaluate(test_cases_v9, metrics_v9, print_results=False)
    
    # Passo 5: Consolidação dos resultados em um DataFrame limpo
    for i, res in enumerate(eval_v1_results):
        # Mapeia dinamicamente os scores retornados pelo DeepEval
        for metric_result in res.metrics_results:
            results_summary[i][f"V1_{metric_result.name}_Score"] = metric_result.score

    for i, res in enumerate(eval_v9_results):
        for metric_result in res.metrics_results:
            results_summary[i][f"V9_{metric_result.name}_Score"] = metric_result.score

    # Salva os resultados agregados de forma limpa
    df = pd.DataFrame(results_summary)
    output_path = Path("./resultados") / f"Clean_Report_{timestamp}.csv"
    output_path.parent.mkdir(exist_ok=True)
    df.to_csv(output_path, index=False)
    print(f"🎯 Avaliação concluída com sucesso! Relatório gerado em: {output_path}")

if __name__ == "__main__":
    asyncio.run(main())