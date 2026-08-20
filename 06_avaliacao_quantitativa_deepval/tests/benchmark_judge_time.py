#!/usr/bin/env python3
"""
Benchmark do tempo de julgamento (juiz) com 1 pergunta específica.
Mede o tempo que cada métrica leva para avaliar uma resposta sobre o Acer Nitro 5 AN515-58.
"""

import asyncio
import time
import sys
from pathlib import Path
from typing import List, Dict, Any

# Adiciona caminhos
from core.paths import VALIDACAO_SCRIPT, AVALIACAO_SCRIPT, VETORIZATION_DATA, AVALIACAO_DATA
for path in [VALIDACAO_SCRIPT, AVALIACAO_SCRIPT]:
    if str(path) not in sys.path:
        sys.path.append(str(path))

from RAG_BaseLineV2 import VanillaRAG
from RAG_Temporal_V9_3 import SpecialistTimeAwareRAG
from custom_evaluatorV4 import OllamaEvaluator
from deepeval import evaluate
from deepeval.test_case import LLMTestCase
from deepeval.metrics import (
    FaithfulnessMetric,
    AnswerRelevancyMetric,
    ContextualRelevancyMetric,
    ContextualPrecisionMetric,
    ContextualRecallMetric,
    GEval
)
from deepeval.evaluate import AsyncConfig
from deepeval.test_case import SingleTurnParams
from deepeval.metrics.g_eval import Rubric

# Importar funções de criação de métricas do script principal
# (para evitar duplicação, copiamos as funções aqui)
def create_native_metrics(evaluator: OllamaEvaluator) -> List[Any]:
    return [
        FaithfulnessMetric(threshold=0.80, model=evaluator, include_reason=True, verbose_mode=True),
        AnswerRelevancyMetric(threshold=0.85, model=evaluator, include_reason=True, verbose_mode=True),
        ContextualRelevancyMetric(threshold=0.8, model=evaluator, include_reason=True, verbose_mode=True),
        ContextualPrecisionMetric(threshold=0.8, model=evaluator, include_reason=True, verbose_mode=True),
        ContextualRecallMetric(threshold=0.8, model=evaluator, include_reason=True, verbose_mode=True)
    ]

def create_unified_behavioral_geval(evaluator: OllamaEvaluator) -> GEval:
    criteria = (
        "Evaluate compliance with mixed operational guardrails (SKU presence, series queries, missing data, and output cleanliness)."
    )
    rubric = [
        Rubric(
            score_range=(0, 3),
            expected_outcome=(
                "Critical Violation: Provided specific hardware specs for a generic SERIES query, OR "
                "failed to state that external documentation was missing for an unknown SKU, OR "
                "polluted the text output with forbidden system tags/headers like [RAG], [INTERNAL], 'AUDIT:', or 'ANSWER:'."
            )
        ),
        Rubric(
            score_range=(4, 6),
            expected_outcome=(
                "Partial Compliance: Kept the output clean without tags, but violated one of the routing logic rules "
                "(e.g., provided partial specs for a line series instead of demanding the SKU)."
            )
        ),
        Rubric(
            score_range=(7, 10),
            expected_outcome=(
                "Full Compliance: Perfect execution. Detected query type accurately, triggered the required disclaimer "
                "for missing SKUs, correctly refused specs for series queries, and delivered a completely clean, natural response paragraph."
            )
        )
    ]
    return GEval(
        name="Mixed Guardrails (Unified)",
        model=evaluator,
        criteria=criteria,
        rubric=rubric,
        evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT, SingleTurnParams.RETRIEVAL_CONTEXT],
        evaluation_steps=[
            "Determine query type (SKU, series, comparison, general).",
            "Check compliance with the specific operational rule for that type.",
            "Verify no forbidden raw tags or system processing blocks pollute the text output."
        ],
        threshold=0.8,
        verbose_mode=True
    )

def create_temporal_geval(evaluator: OllamaEvaluator) -> GEval:
    criteria = (
        "Evaluate response compliance with temporal reasoning rules and specification accuracy across generations."
    )
    rubric = [
        Rubric(
            score_range=(0, 3),
            expected_outcome=(
                "Temporal Failure: Invented specifications for future dates (2026+), hallucinated hardware versions, "
                "or completely mixed up historical specs (e.g., stating a DDR4 model uses DDR5 based on outdated/incorrect documentation)."
            )
        ),
        Rubric(
            score_range=(4, 6),
            expected_outcome=(
                "Minor Temporal Inconsistency: Preferred older documents over newer ones when both were present in context, "
                "but did not boldly invent non-existent versions or future hardware."
            )
        ),
        Rubric(
            score_range=(7, 10),
            expected_outcome=(
                "Chronological Excellence: Correctly respected the reference date, handled future-dated queries with strict "
                "caution ('not available'/'unconfirmed'), and accurately separated component generations (DDR4 vs DDR5)."
            )
        )
    ]
    return GEval(
        name="Temporal Consistency",
        model=evaluator,
        criteria=criteria,
        rubric=rubric,
        evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT, SingleTurnParams.RETRIEVAL_CONTEXT],
        evaluation_steps=[
            "Check if the response uses the appropriate document recency based on the reference date.",
            "Verify that future-dated queries are handled with caution (no speculation).",
            "Ensure that comparisons respect chronological evolution of specifications.",
            "Penalize hallucinated versions or specs that contradict the temporal context."
        ],
        threshold=0.8,
        verbose_mode=True
    )

def create_strict_temporal_reranking_geval(evaluator: OllamaEvaluator) -> GEval:
    criteria = (
        "Analyze if the engine suffered from temporal obsolescence by favoring outdated context documents over the chronological requested timeline."
    )
    rubric = [
        Rubric(
            score_range=(0, 4),
            expected_outcome=(
                "Obsolete Output: The response fell victim to a lack of temporal awareness. It incorporated features, "
                "components, or BIOS versions that were already replaced or obsolete by the time of the reference date, "
                "meaning it favored older documentation present in the context (typical vanilla vector search error)."
            )
        ),
        Rubric(
            score_range=(5, 10),
            expected_outcome=(
                "Dynamic Recency Alignment: The response shows absolute chronological alignment. It successfully "
                "deprioritized obsolete data and strictly used current/newer specifications relevant to the anchor year."
            )
        )
    ]
    return GEval(
        name="Temporal Reranking Enforcement",
        model=evaluator,
        criteria=criteria,
        rubric=rubric,
        evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT, SingleTurnParams.RETRIEVAL_CONTEXT],
        evaluation_steps=[
            "Identify the reference date or chronological anchor in the user input.",
            "Check if the actual output used specifications that are accurate only for past contexts.",
            "Determine if the system failed to deprioritize obsolete technical documentation."
        ],
        threshold=0.8,
        verbose_mode=True
    )

def create_intelligent_fallback_geval(evaluator: OllamaEvaluator) -> GEval:
    criteria = (
        "Evaluate the response's defensive fallback triggering and resistance to context-driven hallucinations."
    )
    rubric = [
        Rubric(
            score_range=(0, 3),
            expected_outcome=(
                "Hallucinated Mapping: The response hallucinated or forcefully mapped specs from a completely different "
                "product line just because it appeared in the retrieval context, OR gave precise hardware specs for an unknown SKU/Series."
            )
        ),
        Rubric(
            score_range=(4, 6),
            expected_outcome=(
                "Insufficient Disclaimer: Attempted a generic fallback response but forgot to explicitly state the mandatory "
                "disclaimer that no current official documentation was found for that specific SKU."
            )
        ),
        Rubric(
            score_range=(7, 10),
            expected_outcome=(
                "Smart Defense: Perfect fallback activation. For missing/unknown data, it openly admitted the lack of "
                "external documentation first, and then provided safe, generic architectural constraints using clean internal knowledge."
            )
        )
    ]
    return GEval(
        name="Smart Fallback Triggering",
        model=evaluator,
        criteria=criteria,
        rubric=rubric,
        evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT, SingleTurnParams.RETRIEVAL_CONTEXT],
        evaluation_steps=[
            "Identify if the query is a Series query, an unknown SKU, or a future-dated product.",
            "Verify if the response successfully triggered a fallback/disclaimer or a request for clarification.",
            "Penalize with 0.0 if the response boldly states specifications that belong to a generic or different model."
        ],
        threshold=0.8,
        verbose_mode=True
    )

# ============================================================================
# CONFIGURAÇÃO
# ============================================================================

BASE_PATH = VETORIZATION_DATA /'base_vetorizada' / 'base_conhecimento_multilingueV9.json'
JUIZ_MODELO = "qwen3:4b-instruct"  # Modelo que atuará como juiz
GERADOR_MODELO = "phi3.5:latest"    # Modelo que gera a resposta (pode ser qualquer um)
PERGUNTA = "Quais são as especificações técnicas do notebook Acer Nitro 5 AN515-58?"
REF_DATE = "2026-06-23"

# Número de repetições para média
NUM_REPS = 3

# ============================================================================
# FUNÇÃO PARA GERAR UMA RESPOSTA (usando um gerador)
# ============================================================================

async def gerar_resposta(pergunta: str, modelo_gerador: str) -> LLMTestCase:
    """Gera uma resposta usando o VanillaRAG (ou Temporal) com o modelo especificado."""
    # Usaremos o VanillaRAG para simplicidade, mas você pode usar o Temporal
    from RAG_BaseLineV2 import VanillaRAG
    rag = VanillaRAG(BASE_PATH, use_expansion=False)
    # Configurar o modelo gerador
    rag.current_model = modelo_gerador
    rag.temperature = 0.0
    rag.search_top_k = 5

    resultado = await rag.search(pergunta)
    resposta = resultado["answer"]
    fontes = resultado.get("sources", [])[:5]

    # Cria um LLMTestCase
    tc = LLMTestCase(
        input=pergunta,
        actual_output=resposta,
        retrieval_context=fontes,
        expected_output="",  # Não temos expected_output
        metadata={"id": "teste_acer", "test_type": "traditional"}
    )
    await rag.close()
    return tc

# ============================================================================
# FUNÇÃO PARA AVALIAR COM UM JUIZ E CRONOMETRAR
# ============================================================================

async def avaliar_com_juiz(tc: LLMTestCase, juiz_modelo: str) -> Dict[str, float]:
    """Avalia o caso de teste com o modelo juiz e retorna tempos por métrica."""
    evaluator = OllamaEvaluator(model_name=juiz_modelo, prompt_version="V1")

    # Conjunto de métricas (tradicionais + G-Evals)
    metrics_trad = create_native_metrics(evaluator)
    metrics_geval = [
        create_unified_behavioral_geval(evaluator),
        create_temporal_geval(evaluator),
        create_strict_temporal_reranking_geval(evaluator),
        create_intelligent_fallback_geval(evaluator)
    ]
    todas_metricas = metrics_trad + metrics_geval

    tempos = {}

    for metric in todas_metricas:
        nome = metric.__class__.__name__
        # Para G-Eval, o nome pode ser sobrescrito; pegamos o atributo name se existir
        if hasattr(metric, 'name'):
            nome = metric.name
        print(f"⏳ Avaliando com {nome}...")
        inicio = time.time()
        try:
            # Avalia apenas com essa métrica
            resultado = evaluate([tc], [metric], async_config=AsyncConfig(max_concurrent=1))
            elapsed = time.time() - inicio
            tempos[nome] = elapsed
            print(f"   ✅ {nome} concluído em {elapsed:.2f}s")
        except Exception as e:
            print(f"   ❌ Erro em {nome}: {e}")
            tempos[nome] = None

    return tempos

# ============================================================================
# MAIN
# ============================================================================

async def main():
    print(f"🚀 Benchmark do tempo de julgamento")
    print(f"Juiz: {JUIZ_MODELO}")
    print(f"Gerador: {GERADOR_MODELO}")
    print(f"Pergunta: '{PERGUNTA}'")
    print(f"Repetições: {NUM_REPS}\n")

    # Gerar a resposta uma única vez (reutilizamos para todas as repetições de avaliação)
    print("Gerando resposta...")
    tc = await gerar_resposta(PERGUNTA, GERADOR_MODELO)
    print(f"Resposta gerada (primeiros 200 caracteres):\n{tc.actual_output[:200]}...\n")

    # Executa avaliações repetidas para ter média
    todos_tempos = []
    for rep in range(1, NUM_REPS + 1):
        print(f"\n--- Repetição {rep} ---")
        tempos = await avaliar_com_juiz(tc, JUIZ_MODELO)
        todos_tempos.append(tempos)

    # Calcula médias
    metricas = set()
    for t in todos_tempos:
        metricas.update(t.keys())

    print("\n" + "=" * 80)
    print("📊 RELATÓRIO DE TEMPO DE JULGAMENTO")
    print("=" * 80)
    print(f"{'Métrica':<40} | {'Média (s)':>12} | {'Mínimo':>12} | {'Máximo':>12}")
    print("-" * 80)

    for metrica in sorted(metricas):
        tempos_validos = [t[metrica] for t in todos_tempos if metrica in t and t[metrica] is not None]
        if not tempos_validos:
            print(f"{metrica:<40} | {'FALHA':^12}")
            continue
        media = sum(tempos_validos) / len(tempos_validos)
        minimo = min(tempos_validos)
        maximo = max(tempos_validos)
        print(f"{metrica:<40} | {media:>12.2f} | {minimo:>12.2f} | {maximo:>12.2f}")

    # Sugestão de timeout (média + 3*desvio + 60s)
    # Mas aqui não calculamos desvio, usamos máximo + 60s para segurança
    print("\n💡 Sugestão de timeout (para o juiz) baseado no máximo + 60s:")
    for metrica in sorted(metricas):
        tempos_validos = [t[metrica] for t in todos_tempos if metrica in t and t[metrica] is not None]
        if tempos_validos:
            maximo = max(tempos_validos)
            sugerido = maximo + 60
            print(f"  {metrica}: {sugerido:.0f}s")

if __name__ == "__main__":
    asyncio.run(main())