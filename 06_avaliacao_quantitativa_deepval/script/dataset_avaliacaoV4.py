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

    {
    "id": "TC_BEHAVIOR_SKU_WITH_INTERNAL_FALLBACK",
    "input": "What is the TGP of RTX 3060 in Acer Nitro AN515-45?",
    "reference_date": "2025-06-01",
    "test_type": "behavioral",
    "expected_behavior": "should_use_internal_fallback_honestly",
    "required_patterns": [
        "no external documentation", "not found", "based on general knowledge",
        "typically", "common configuration", "RTX 3060"
    ],
    "forbidden_patterns": [
        "cannot answer", "unavailable", "no information"   # não pode simplesmente negar
    ],
    "description": "SKU específico sem documento → deve usar internal knowledge como fallback, não apenas dizer 'não sei'"
    },
    {
        "id": "TC_BEHAVIOR_AUDIT_TAGS_PRESENT",
        "input": "Does the Dell G15 5520 support PCIe 4.0?",
        "reference_date": "2025-06-01",
        "test_type": "behavioral",
        "expected_behavior": "should_include_audit_with_tags",
        "required_patterns": [
            "AUDIT:", "\\[RAG:", "\\[INTERNAL:"
        ],
        "pattern_type": "regex",
        "description": "A resposta deve conter seção AUDIT com tags RAG e INTERNAL"
    },
    {
        "id": "TC_BEHAVIOR_COMPARISON_MIXED_SOURCES",
        "input": "Compare battery life of Lenovo Legion 5 15ACH6 vs HP Victus 16-e0055dx",
        "reference_date": "2025-06-01",
        "test_type": "behavioral",
        "expected_behavior": "should_compare_with_fallback",
        "required_patterns": [
            "Legion", "Victus", "based on", "general knowledge", "typical"
        ],
        "forbidden_patterns": [
            "cannot compare", "insufficient data"
        ],
        "description": "Deve comparar mesmo que um dos SKUs não esteja no RAG, usando internal knowledge"
    },
    {
        "id": "TC_BEHAVIOR_SERIES_NO_INTERNAL_SPECS",
        "input": "What is the maximum RAM for Dell G15 series?",
        "reference_date": "2025-06-01",
        "test_type": "behavioral",
        "expected_behavior": "should_ask_for_sku_and_avoid_internal_specs",
        "required_patterns": [
            "specific model", "SKU", "which model"
        ],
        "forbidden_patterns": [
            "16GB", "32GB", "DDR4", "DDR5", "supports up to"
        ],
        "description": "Query de série → não pode dar specs mesmo que conhecimento interno as conheça"
    },
    {
        "id": "TC_BEHAVIOR_RAG_PLUS_INTERNAL_ENRICHMENT",
        "input": "Why does my Acer Nitro 5 AN515-58 throttle? Explain thermal design.",
        "reference_date": "2025-06-01",
        "test_type": "behavioral",
        "expected_behavior": "should_combine_rag_and_internal",
        "required_patterns": [
            "thermal throttling", "cooling", "temperature"
        ],
        "min_required_matches": 2,
        "description": "Pode usar RAG (se houver documento sobre AN515-58) e complementar com conhecimento interno de design térmico"
    }
]


# ============================================================================
# TESTES ESPECÍFICOS DE TEMPORALIDADE
# ============================================================================

TEMPORAL_TEST_SUITE = [
    {
        "id": "TC_TEMPORAL_PREFER_RECENT_DOC",
        "input": "What is the maximum RAM capacity for Dell XPS 15 9500?",
        "reference_date": "2025-06-01",
        "test_type": "behavioral",
        "expected_behavior": "should_prefer_2024_document_over_2014",
        "required_patterns": ["32GB", "64GB", "DDR4", "DDR5"],
        # Se houver documento de 2024 falando 64GB e outro de 2014 falando 32GB,
        # o temporal deve preferir o mais recente. O vanilla pode dar 32GB.
        "description": "Exige que o RAG temporal use dados mais recentes se disponíveis."
    },
    {
        "id": "TC_TEMPORAL_BIOS_VERSION_RECENCY",
        "input": "Latest BIOS version for Acer Nitro 5 AN515-58?",
        "reference_date": "2025-06-01",
        "test_type": "behavioral",
        "expected_behavior": "should_not_use_outdated_bios",
        "forbidden_patterns": [r"v1\.\d+", "2.0", "2020"],
        "required_patterns": ["not available", "latest", "update"],
        "pattern_type": "regex",
        "description": "Não deve citar versões antigas de BIOS se existir documentação recente; se não houver, deve admitir."
    },
    {
        "id": "TC_TEMPORAL_NEW_HARDWARE_2025",
        "input": "Does the RTX 5060 laptop GPU support PCIe 5.0?",
        "reference_date": "2025-06-01",
        "test_type": "behavioral",
        "expected_behavior": "should_use_internal_knowledge_or_admit_unknown",
        "required_patterns": ["not available", "no information", "unconfirmed", "likely", "typically"],
        "forbidden_patterns": ["yes", "no"],
        "description": "Pergunta sobre hardware muito recente (2025). O RAG deve evitar afirmações categóricas se não houver documento."
    },
    {
        "id": "TC_TEMPORAL_OLD_CONCEPT_NO_PENALTY",
        "input": "Explain what CPU thermal throttling means.",
        "reference_date": "2025-06-01",
        "test_type": "behavioral",
        "expected_behavior": "should_answer_using_general_knowledge_regardless_of_date",
        "required_patterns": ["temperature", "reduce", "clock", "frequency"],
        "min_required_matches": 2,
        "description": "Conceito atemporal; o RAG temporal não deve penalizar documentos antigos a ponto de não conseguir responder."
    },
    {
        "id": "TC_TEMPORAL_COMPARE_OLD_VS_NEW",
        "input": "Compare battery life of Dell XPS 15 9500 (2020 model) vs Dell XPS 15 9530 (2023 model).",
        "reference_date": "2025-06-01",
        "test_type": "behavioral",
        "expected_behavior": "should_use_appropriate_dates_for_each",
        "required_patterns": ["2020", "2023", "battery", "hours"],
        "forbidden_patterns": ["same", "identical"],
        "description": "Deve usar documentos de épocas diferentes sem confundir as especificações."
    },
    {
        "id": "TC_TEMPORAL_FUTURE_DATE_2026",
        "input": "What is the default TDP of Intel Core Ultra 9 285H?",
        "reference_date": "2026-06-01",
        "test_type": "behavioral",
        "expected_behavior": "should_not_invent_specs_for_future",
        "required_patterns": ["not available", "no information", "cannot confirm", "as of now"],
        "forbidden_patterns": ["45W", "65W", "125W", "TDP"],
        "description": "Pergunta sobre CPU que pode não ter sido lançada até 2026; o RAG deve evitar especular."
    },
    {
        "id": "TC_TEMPORAL_OLDER_SKU_STILL_VALID",
        "input": "How to upgrade RAM on Lenovo Legion 5 15ACH6 (2021 model)?",
        "reference_date": "2025-06-01",
        "test_type": "behavioral",
        "expected_behavior": "should_use_old_doc_and_not_penalize_too_much",
        "required_patterns": ["SODIMM", "DDR4", "remove", "install", "upgrade"],
        "description": "SKU antigo mas pergunta de upgrade (informação ainda válida). O RAG temporal deve usar o documento antigo mesmo com penalidade leve."
    },
    {
        "id": "TC_TEMPORAL_CLEAN_NO_AUDIT_TAGS",
        "input": "What is the maximum supported storage for HP Victus 16-e0055dx?",
        "reference_date": "2025-06-01",
        "test_type": "behavioral",
        "expected_behavior": "should_output_clean_text_without_tags_or_audit_blocks",
        "forbidden_patterns": ["AUDIT:", "ANSWER:", "\\[RAG:", "\\[INTERNAL:", "\\[SOURCE"],
        "description": "A resposta final não pode conter blocos de auditoria ou tags de sistema – apenas texto limpo (para ambos RAGs)."
    }
]

# Adicionar ao BEHAVIORAL_TEST_SUITE existente
BEHAVIORAL_TEST_SUITE.extend(TEMPORAL_TEST_SUITE)

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