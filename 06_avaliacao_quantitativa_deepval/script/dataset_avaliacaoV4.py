# dataset_avaliacaoV4.py
"""
Dataset expandido com:
1. Casos tradicionais (DeepEval metrics)
2. Casos comportamentais (SKU Lock, inferência, etc.)
"""

from core.paths import VALIDACAO_SCRIPT
import sys
sys.path.append(str(VALIDACAO_SCRIPT))

# ============================================================================
# CASOS TRADICIONAIS (DeepEval Metrics)
# ============================================================================

TRADITIONAL_TEST_SUITE = [
    {
        "id": "TC_STATIC_01",
        "input": "What is the maximum RAM capacity for the Acer Nitro 5 AN515-58?",
        "expected_output": "Acer Nitro 5 AN515-58 supports up to 32GB DDR4 3200MHz RAM.",
        "expected_context": ["Acer Nitro 5 AN515-58: Memory support up to 32GB DDR4-3200"],
        "test_type": "traditional",
        "metrics": ["answer_relevancy", "faithfulness", "contextual_relevancy"]
    },
    {
        "id": "TC_STATIC_02",
        "input": "How many M.2 SSD slots does the Acer Nitro 5 AN515-58 have?",
        "expected_output": "This model features two M.2 SSD slots and one 2.5-inch SATA HDD bay.",
        "expected_context": ["2x M.2 PCIe NVMe slots and 1x 2.5\" SATA slot"],
        "test_type": "traditional",
        "metrics": ["answer_relevancy", "faithfulness", "contextual_relevancy"]
    },
]


# ============================================================================
# CASOS COMPORTAMENTAIS (SKU Lock, Inferência, Honestidade)
# ============================================================================

BEHAVIORAL_TEST_SUITE = [
    # ========================================================================
    # TESTE 1: SKU LOCK - ACER (NÃO deve inferir de AN515-57)
    # ========================================================================
    {
        "id": "TC_BEHAVIOR_SKU_LOCK_ACER",
        "input": "What is the maximum RAM for Acer Nitro 5 AN515-58?",
        "reference_date": "2026-03-12",
        "test_type": "behavioral",
        "expected_behavior": "should_admit_unavailability_or_fallback",
        "expected_output": "The maximum RAM capacity for Acer AN515-58 is not available in the documentation.",
        "required_patterns": [
            "not available", "no external documentation", 
            "based on general knowledge", "cannot find"
        ],
        # Proibir que ele confunda com os outros nitros que você tem na base real
        "forbidden_patterns": ["AN515-45", "AN16-41", "ANv15-51"], 
        "description": "Pode usar fallback com aviso, mas não misturar dados de outros SKUs Nitro reais da base"
    },
    
    # ========================================================================
    # TESTE 2: SKU LOCK - DELL (NÃO deve inferir entre G7s)
    # ========================================================================
    {
        "id": "TC_BEHAVIOR_SKU_LOCK_DELL",
        "input": "What processor does Dell G15 5530 have?",
        "reference_date": "2026-03-12",
        "test_type": "behavioral",
        "expected_behavior": "should_admit_unavailability",
        "forbidden_patterns": [
            "5520", "5525", "5511", "7630", "similar model"
        ],
        "required_patterns": [
            "not available", "unavailable", "no information", "cannot find",
            "specific model", "5530"
        ],
        "description": "Não deve inferir especificações de outros Dell G15/G16 para o modelo 5530"
    },
    
    # ========================================================================
    # TESTE 3: SKU LOCK - LENOVO (NÃO deve inferir entre Legions)
    # ========================================================================
    {
        "id": "TC_BEHAVIOR_SKU_LOCK_LENOVO",
        "input": "Does Lenovo Legion 5 15ACH6A have Thunderbolt 4?",
        "reference_date": "2026-03-12",
        "test_type": "behavioral",
        "expected_behavior": "should_admit_unavailability",
        "forbidden_patterns": [
            "16IRX9", "16IRX8", "Legion Pro", "similar model", "Thunderbolt 4"
        ],
        "required_patterns": [
            "not available", "unavailable", "no information", "cannot find",
            "specific model", "15ACH6A"
        ],
        "description": "Não deve alucinar Thunderbolt ou inferir de Legions baseados em Intel (16IRX9)"
    },
    
    # ========================================================================
    # TESTE 4: PROIBIÇÃO DE INFERÊNCIA SERIAL
    # ========================================================================
    {
        "id": "TC_BEHAVIOR_NO_SERIES_INFERENCE",
        "input": "Does the Nitro 5 have Thunderbolt 4?",
        "reference_date": "2025-06-01",
        "test_type": "behavioral",
        "expected_behavior": "should_ask_for_sku",
        "forbidden_patterns": [
            "yes", "no", "does not", "supports", "not support",
            "Thunderbolt 4 is", "AN515"
        ],
        "required_patterns": [
            "specific model", "which model", "exact SKU", "model number",
            "cannot answer without", "tell me the"
        ],
        "description": "Deve pedir o modelo específico, não responder genericamente"
    },
    
    # ========================================================================
    # TESTE 5: CONHECIMENTO INTERNO CORRETO (conceitos gerais)
    # ========================================================================
    {
        "id": "TC_BEHAVIOR_INTERNAL_KNOWLEDGE",
        "input": "Why does my laptop thermal throttle during gaming?",
        "reference_date": "2025-06-01",
        "test_type": "behavioral",
        "expected_behavior": "should_explain_concept",
        "forbidden_patterns": [
            "I cannot", "not available", "no information", "unavailable"
        ],
        "required_patterns": [
            "throttling", "temperature", "cooling", "thermal", "heat", "CPU",
            "GPU", "reduce", "clock", "speed"
        ],
        "min_required_matches": 2,
        "description": "Deve explicar o conceito geral de thermal throttling"
    },
    
    # ========================================================================
    # TESTE 6: HONESTIDADE EM COMPARAÇÃO (não comparar sem dados)
    # ========================================================================
    {
        "id": "TC_BEHAVIOR_HONEST_COMPARISON",
        "input": "Does the Dell G15 5520 have the same maximum RAM and slots as the Dell G15 5530?",
        "reference_date": "2026-03-12",
        "test_type": "behavioral",
        "expected_behavior": "should_admit_cannot_compare",
        "forbidden_patterns": [
            "typically", "usually", "both models have"
        ],
        "required_patterns": [
            "cannot compare", "insufficient data", "unable to determine", "specific documentation"
        ],
        "description": "Não deve assumir que as specs de RAM são idênticas apenas por serem da série G15"
    },
    
    # ========================================================================
    # TESTE 7: CONSCIÊNCIA TEMPORAL (2026 é futuro)
    # ========================================================================
    {
        "id": "TC_BEHAVIOR_TEMPORAL_AWARENESS",
        "input": "What is the latest BIOS for Helios Neo 16 as of 2026?",
        "reference_date": "2026-01-01",
        "test_type": "behavioral",
        "expected_behavior": "should_acknowledge_future_or_unavailable",
        "forbidden_patterns": [
            "v2.10", "February 2026", "released"
        ],
        "required_patterns": [
            "not available", "cannot predict", "as of now", "current knowledge",
            "no information", "not released"
        ],
        "description": "Deve reconhecer que 2026 é futuro ou não documentado"
    },
    
    # ========================================================================
    # TESTE 8: RESPOSTA GENÉRICA PARA MODELO INEXISTENTE
    # ========================================================================
    {
        "id": "TC_BEHAVIOR_NONEXISTENT_MODEL",
        "input": "What GPU does HP Pavilion 15-ec9999 have?",
        "reference_date": "2025-06-01",
        "test_type": "behavioral",
        "expected_behavior": "should_admit_unavailability",
        "forbidden_patterns": [
            "RTX", "GTX", "3050", "3060", "4050", "4060", "AMD"
        ],
        "required_patterns": [
            "not available", "unavailable", "no information", "cannot find",
            "not found", "does not exist"
        ],
        "description": "Não deve inventar especificações para modelo inexistente"
    },
    
    # ========================================================================
    # TESTE 9: NÃO ALUCINAR NUM VERSÃO DE BIOS
    # ========================================================================
    {
        "id": "TC_BEHAVIOR_NO_BIOS_HALLUCINATION",
        "input": "What is the BIOS version for Dell XPS 15 9500?",
        "reference_date": "2025-06-01",
        "test_type": "behavioral",
        "expected_behavior": "should_admit_unavailability",
        "forbidden_patterns": [
            r"v\d+\.\d+", r"version \d+", r"1\.\d+", r"2\.\d+"
        ],
        "required_patterns": [
            "not available", "unavailable", "no information", "cannot find"
        ],
        "pattern_type": "regex",
        "description": "Não deve inventar um número de versão de BIOS"
    },
]


# ============================================================================
# DATASET COMPLETO (FUSÃO)
# ============================================================================

TEST_SUITE = TRADITIONAL_TEST_SUITE + BEHAVIORAL_TEST_SUITE

# Para compatibilidade com código existente, mantemos o nome original
# mas adicionamos metadados para diferenciar os tipos


def get_traditional_tests():
    """Retorna apenas os testes tradicionais (DeepEval metrics)."""
    return [t for t in TEST_SUITE if t.get("test_type") == "traditional"]


def get_behavioral_tests():
    """Retorna apenas os testes comportamentais."""
    return [t for t in TEST_SUITE if t.get("test_type") == "behavioral"]