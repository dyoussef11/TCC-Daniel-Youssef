# evaluate_rag_deepeval_Apenas_TemporalV4_COMPATIVEL.py
"""
Avaliação do RAG Temporal com métricas DeepEval.
Compatível com a nova estrutura da base de conhecimento V6/V7.
"""

import asyncio
import sys
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from core.paths import VETORIZATION_DATA, VALIDACAO_SCRIPT, AVALIACAO_DATA 
sys.path.append(str(VALIDACAO_SCRIPT))

from RAG_Temporal_V8 import SpecialistTimeAwareRAG
from dataset_avaliacaoV3 import TEST_SUITE
from custom_evaluatorV2Backup import OllamaEvaluator

from deepeval.test_case import LLMTestCase, LLMTestCaseParams
from deepeval.metrics import (
    ContextualRelevancyMetric,
    ContextualPrecisionMetric,
    ContextualRecallMetric,
    FaithfulnessMetric,
    AnswerRelevancyMetric,
    GEval
)

# ============================================================================
# CONFIGURAÇÕES
# ============================================================================

# Use a base mais recente
CAMINHO_BASE = VETORIZATION_DATA / 'base_conhecimento_multilingueV6_OTIMIZADO.json'
# Fallback para V5 se V6 não existir
if not CAMINHO_BASE.exists():
    CAMINHO_BASE = VETORIZATION_DATA / 'base_conhecimento_multilingueV5.json'

# ============================================================================
# UTILITÁRIOS DE FORMATAÇÃO
# ============================================================================

def formatar_contexto_para_juiz(sources: List[str], metadata_list: List[Dict]) -> List[str]:
    """
    Formata o contexto de forma rica para o avaliador DeepEval.
    
    Estrutura compatível com os novos campos da base V6/V7:
    - title: Título do post
    - model: Nome canônico do modelo
    - fault: Diagnóstico técnico
    - severity: Gravidade (Low/Medium/High/Critical)
    - timeline: Período da discussão (YYYY-MM-DD to YYYY-MM-DD)
    - solutions: Lista de soluções
    """
    contexto_formatado = []
    
    for i, (txt, meta) in enumerate(zip(sources, metadata_list)):
        # Extrai campos com fallbacks seguros
        title = meta.get('title', 'Sem Título')
        model = meta.get('model', 'N/A')
        fault = meta.get('fault', 'N/A')
        severity = meta.get('severity', 'N/A')
        timeline = meta.get('timeline', 'N/A')
        intent = meta.get('intent', 'N/A')
        
        # Soluções (podem ser lista ou string)
        solutions = meta.get('solutions', [])
        if isinstance(solutions, list):
            solutions_str = " | ".join(solutions[:2]) if solutions else "N/A"
        else:
            solutions_str = str(solutions) if solutions else "N/A"
        
        # Constrói entrada rica para o avaliador
        entry = (
            f"SOURCE_{i} | "
            f"TITLE: {title} | "
            f"MODEL: {model} | "
            f"FAULT: {fault} | "
            f"SEVERITY: {severity} | "
            f"INTENT: {intent} | "
            f"TIMELINE: {timeline} | "
            f"SOLUTIONS: {solutions_str}\n"
            f"CONTENT: {txt}"
        )
        contexto_formatado.append(entry)
    
    return contexto_formatado


def formatar_fontes_para_relatorio(metadata_list: List[Dict]) -> List[str]:
    """
    Formata as fontes para exibição no relatório final.
    """
    fontes = []
    
    for meta in metadata_list:
        title = meta.get('title', 'Sem Título')
        model = meta.get('model', 'N/A')
        fault = meta.get('fault', 'N/A')
        severity = meta.get('severity', 'N/A')
        timeline = meta.get('timeline', 'N/A')
        
        # Ícone de severidade
        severity_icon = {
            'Critical': '🔴',
            'High': '🟠',
            'Medium': '🟡',
            'Low': '🟢'
        }.get(severity, '⚪')
        
        fonte = (
            f"  {severity_icon} {title}\n"
            f"     Modelo: {model} | Fault: {fault}\n"
            f"     Severidade: {severity} | Timeline: {timeline}"
        )
        fontes.append(fonte)
    
    return fontes


# ============================================================================
# PIPELINE DE AVALIAÇÃO
# ============================================================================

async def rodar_avaliacao_deepeval():
    """Executa avaliação completa com métricas DeepEval."""
    
    print("=" * 70)
    print("🧪 AVALIAÇÃO CIENTÍFICA RAG TEMPORAL")
    print("=" * 70)
    print(f"📁 Base: {CAMINHO_BASE}")
    print(f"📊 Casos de teste: {len(TEST_SUITE)}")
    
    # Inicializa componentes
    rag = SpecialistTimeAwareRAG(CAMINHO_BASE, variant_name="V8_HYBRID_AUDITOR")
    avaliador = OllamaEvaluator(model_name="qwen3:4b-instruct")
    
    # Métricas com justificativa
    metricas = {
        "Context_Relevancy": ContextualRelevancyMetric(
            threshold=0.7, model=avaliador, include_reason=True
        ),
        "Context_Precision": ContextualPrecisionMetric(
            threshold=0.7, model=avaliador, include_reason=True
        ),
        "Context_Recall": ContextualRecallMetric(
            threshold=0.7, model=avaliador, include_reason=True
        ),
        "Faithfulness": FaithfulnessMetric(
            threshold=0.8, model=avaliador, include_reason=True
        ),
        "Answer_Relevancy": AnswerRelevancyMetric(
            threshold=0.7, model=avaliador, include_reason=True
        ),
        "Zero_Trust_Compliance": GEval(
            name="Zero_Trust_Compliance",
            criteria="Verify if output rejects temporal anomalies and SKU mismatches based on provided sources. Check if FAULT and SEVERITY are correctly referenced.",
            evaluation_params=[
                LLMTestCaseParams.INPUT,
                LLMTestCaseParams.ACTUAL_OUTPUT,
                LLMTestCaseParams.RETRIEVAL_CONTEXT
            ],
            model=avaliador,
            threshold=0.8
        ),
        "Source_Attribution": GEval(
            name="Source_Attribution",
            criteria="Verify if the answer correctly attributes information to the sources, citing TITLE, MODEL, FAULT, and TIMELINE when appropriate.",
            evaluation_params=[
                LLMTestCaseParams.ACTUAL_OUTPUT,
                LLMTestCaseParams.RETRIEVAL_CONTEXT
            ],
            model=avaliador,
            threshold=0.8
        )
    }
    
    # Prepara arquivo de relatório
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    arquivo_relatorio = AVALIACAO_DATA / f"relatorio_V8_{timestamp}.txt"
    
    resultados = []
    
    with open(arquivo_relatorio, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("RELATÓRIO DE AVALIAÇÃO - RAG TEMPORAL V8\n")
        f.write(f"Data: {timestamp}\n")
        f.write(f"Base: {CAMINHO_BASE.name}\n")
        f.write("=" * 80 + "\n\n")
        
        for test_data in TEST_SUITE:
            test_id = test_data['id']
            query = test_data['input']
            ref_date = test_data.get('reference_date', '2026-03-26')
            
            print(f"\n▶ Avaliando: {test_id}")
            print(f"   Query: {query[:80]}...")
            
            # Executa busca
            res_rag = await rag.search(query, ref_date)
            
            # Extrai fontes e metadados
            sources = res_rag.get("sources", [])
            metadata_list = res_rag.get("retrieved_metadata", [])
            
            # Formata contexto para o avaliador
            contexto_formatado = formatar_contexto_para_juiz(sources, metadata_list)
            fontes_relatorio = formatar_fontes_para_relatorio(metadata_list)
            
            # Cria caso de teste
            test_case = LLMTestCase(
                input=query,
                actual_output=res_rag["answer"],
                expected_output=test_data.get("expected_output", ""),
                retrieval_context=contexto_formatado,
                expected_context=test_data.get("expected_context", [])
            )
            
            # Escreve no relatório
            f.write("=" * 80 + "\n")
            f.write(f"ID: {test_id}\n")
            f.write(f"Query: {query}\n")
            f.write(f"Reference Date: {ref_date}\n")
            f.write("\n📚 FONTES RECUPERADAS:\n")
            f.write("\n".join(fontes_relatorio) + "\n")
            f.write("\n" + "-" * 40 + "\n")
            f.write("🤖 RESPOSTA:\n")
            f.write(f"{res_rag['answer']}\n")
            f.write("-" * 40 + "\n\n")
            
            # Avalia métricas
            f.write("📊 MÉTRICAS:\n")
            
            caso_resultados = {"id": test_id, "query": query[:50]}
            
            for nome, metrica in metricas.items():
                try:
                    metrica.measure(test_case)
                    score = metrica.score
                    success = metrica.is_successful()
                    reason = getattr(metrica, 'reason', 'N/A')
                    
                    icon = "✅" if success else "❌"
                    f.write(f"{icon} {nome}: {score:.3f}\n")
                    f.write(f"   → {reason[:200]}\n\n")
                    
                    caso_resultados[nome] = score
                except Exception as e:
                    f.write(f"⚠️ {nome}: ERRO - {str(e)[:100]}\n\n")
                    caso_resultados[nome] = 0.0
            
            f.write("=" * 80 + "\n\n")
            f.flush()
            
            resultados.append(caso_resultados)
    
    # Sumário final
    print("\n" + "=" * 70)
    print("✅ AVALIAÇÃO CONCLUÍDA")
    print("=" * 70)
    print(f"📄 Relatório: {arquivo_relatorio}")
    
    # Calcula médias
    if resultados:
        print("\n📊 MÉDIAS GERAIS:")
        for nome in metricas.keys():
            media = sum(r.get(nome, 0) for r in resultados) / len(resultados)
            print(f"   {nome}: {media:.3f}")
    
    return resultados


# ============================================================================
# PONTO DE ENTRADA
# ============================================================================

if __name__ == "__main__":
    asyncio.run(rodar_avaliacao_deepeval())