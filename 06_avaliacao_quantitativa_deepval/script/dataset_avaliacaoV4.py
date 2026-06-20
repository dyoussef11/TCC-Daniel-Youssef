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

# ============================================================================
# TESTES TEMPORAIS - CHRONOQA INSPIRED (para RAG Temporal)
# ============================================================================

CHRONOQA_TEMPORAL_SUITE = [
    # ========================================================================
    # CATEGORIA 1: PERGUNTAS ABSOLUTAS (Data específica)
    # ========================================================================
    {
        "id": "TC_TEMP_ABS_001",
        "input": "What was the maximum RAM capacity of the Dell G15 5530 in March 2024?",
        "reference_date": "2024-03-15",
        "test_type": "temporal",
        "temporal_category": "absolute",
        "expected_behavior": "should_use_doc_from_2024_or_later",
        "required_patterns": ["32GB", "DDR5"],
        "forbidden_patterns": ["16GB", "DDR4"],
        "description": "Deve usar documento de 2024 (ou mais recente) para especificações do G15 5530"
    },
    {
        "id": "TC_TEMP_ABS_002",
        "input": "What was the default graphics card in the Lenovo LOQ 15IRX9 in January 2025?",
        "reference_date": "2025-01-01",
        "test_type": "temporal",
        "temporal_category": "absolute",
        "expected_behavior": "should_use_doc_from_2025_or_later",
        "required_patterns": ["RTX 4060", "RTX 4070"],
        "forbidden_patterns": ["RTX 3050", "RTX 3060"],
        "description": "O LOQ 15IRX9 foi lançado em 2024/2025 - deve usar specs corretas da época"
    },
    {
        "id": "TC_TEMP_ABS_003",
        "input": "What processor did the Acer Nitro 5 AN515-58 have in Q4 2023?",
        "reference_date": "2023-10-01",
        "test_type": "temporal",
        "temporal_category": "absolute",
        "expected_behavior": "should_use_doc_from_2023",
        "required_patterns": ["12th Gen", "i5", "i7"],
        "forbidden_patterns": ["13th Gen", "14th Gen"],
        "description": "AN515-58 é 12th Gen - não deve alucinar processadores de gerações futuras"
    },
    {
        "id": "TC_TEMP_ABS_004",
        "input": "What was the maximum storage configuration for the HP Victus 15-fa1066tx in August 2024?",
        "reference_date": "2024-08-15",
        "test_type": "temporal",
        "temporal_category": "absolute",
        "expected_behavior": "should_use_doc_from_2024",
        "required_patterns": ["1TB", "2TB", "SSD"],
        "forbidden_patterns": ["256GB", "512GB"],
        "description": "Modelo 2024 deve ter opções de armazenamento maiores"
    },
    {
        "id": "TC_TEMP_ABS_005",
        "input": "What GPU was available in the ASUS TUF Gaming F15 FX507ZV in June 2023?",
        "reference_date": "2023-06-01",
        "test_type": "temporal",
        "temporal_category": "absolute",
        "expected_behavior": "should_use_doc_from_2023",
        "required_patterns": ["RTX 4060", "RTX 4070"],
        "forbidden_patterns": ["RTX 4050"],
        "description": "FX507ZV é modelo 2023 - deve ter RTX 4060 ou superior"
    },
    {
        "id": "TC_TEMP_ABS_006",
        "input": "What was the refresh rate of the Lenovo Legion Pro 7 16IRX9 display in October 2024?",
        "reference_date": "2024-10-01",
        "test_type": "temporal",
        "temporal_category": "absolute",
        "expected_behavior": "should_use_doc_from_2024",
        "required_patterns": ["240Hz", "165Hz"],
        "forbidden_patterns": ["60Hz", "120Hz"],
        "description": "Legion Pro 7 2024 deve ter tela de alta refresh rate"
    },

    # ========================================================================
    # CATEGORIA 2: PERGUNTAS AGREGADAS (Contagem ou frequência temporal)
    # ========================================================================
    {
        "id": "TC_TEMP_AGG_001",
        "input": "How many M.2 SSD slots does the Dell G16 7630 have?",
        "reference_date": "2024-01-01",
        "test_type": "temporal",
        "temporal_category": "aggregate",
        "expected_behavior": "should_count_slots_correctly",
        "required_patterns": ["2", "two"],
        "forbidden_patterns": ["1", "3"],
        "description": "G16 7630 tem 2 slots M.2 - deve contar corretamente"
    },
    {
        "id": "TC_TEMP_AGG_002",
        "input": "How many USB ports does the Acer Predator Helios Neo 16 PHN16-71 have?",
        "reference_date": "2024-01-01",
        "test_type": "temporal",
        "temporal_category": "aggregate",
        "expected_behavior": "should_count_ports_correctly",
        "required_patterns": ["3", "4"],
        "forbidden_patterns": ["1", "2"],
        "description": "Deve contar corretamente as portas USB do PHN16-71"
    },
    {
        "id": "TC_TEMP_AGG_003",
        "input": "How many RAM slots are available in the ASUS ROG Zephyrus G14 GA402XV?",
        "reference_date": "2024-01-01",
        "test_type": "temporal",
        "temporal_category": "aggregate",
        "expected_behavior": "should_count_ram_slots_correctly",
        "required_patterns": ["2", "soldered"],
        "forbidden_patterns": ["4"],
        "description": "GA402XV tem 2 slots (um soldado) - deve contar corretamente"
    },

    # ========================================================================
    # CATEGORIA 3: PERGUNTAS RELATIVAS ("último", "mais recente", "anterior")
    # ========================================================================
    {
        "id": "TC_TEMP_REL_001",
        "input": "What is the latest BIOS version for the Dell XPS 15 9530?",
        "reference_date": "2025-01-01",
        "test_type": "temporal",
        "temporal_category": "relative",
        "expected_behavior": "should_return_latest_bios",
        "required_patterns": ["not available", "latest", "update"],
        "forbidden_patterns": ["v1.0", "2022"],
        "description": "Deve mencionar a BIOS mais recente ou admitir que não tem informação"
    },
    {
        "id": "TC_TEMP_REL_002",
        "input": "What is the most recent processor generation used in the Lenovo Legion Slim 5?",
        "reference_date": "2025-06-01",
        "test_type": "temporal",
        "temporal_category": "relative",
        "expected_behavior": "should_use_most_recent_doc",
        "required_patterns": ["Ryzen 7", "Ryzen 9", "HX"],
        "forbidden_patterns": ["Ryzen 5", "2022"],
        "description": "Deve usar a documentação mais recente do Legion Slim 5"
    },
    {
        "id": "TC_TEMP_REL_003",
        "input": "Which was the last Acer Nitro model to feature DDR4 RAM?",
        "reference_date": "2024-06-01",
        "test_type": "temporal",
        "temporal_category": "relative",
        "expected_behavior": "should_identify_correct_last_model",
        "required_patterns": ["AN515-57", "AN515-58"],
        "forbidden_patterns": ["AN515-45", "AN16-41"],
        "description": "AN515-57 foi um dos últimos com DDR4 - AN515-58 já é DDR5"
    },
    {
        "id": "TC_TEMP_REL_004",
        "input": "What is the most recent HP Omen 16 model with an AMD processor?",
        "reference_date": "2025-01-01",
        "test_type": "temporal",
        "temporal_category": "relative",
        "expected_behavior": "should_use_most_recent_amd_omen",
        "required_patterns": ["Ryzen 7", "Ryzen 9", "7840HS"],
        "forbidden_patterns": ["Intel", "Core i7"],
        "description": "Deve identificar o Omen 16 mais recente com AMD (ex: xd0007ax)"
    },
    {
        "id": "TC_TEMP_REL_005",
        "input": "What was the last Dell G15 model to support DDR4 memory?",
        "reference_date": "2024-12-01",
        "test_type": "temporal",
        "temporal_category": "relative",
        "expected_behavior": "should_identify_correct_model",
        "required_patterns": ["G15 5520", "G15 5525"],
        "forbidden_patterns": ["G15 5530"],
        "description": "G15 5530 já usa DDR5 - os anteriores (5520/5525) usam DDR4"
    },

    # ========================================================================
    # CATEGORIA 4: COMPARAÇÕES TEMPORAIS (evolução de specs)
    # ========================================================================
    {
        "id": "TC_TEMP_CMP_001",
        "input": "How did the maximum RAM capacity change from Dell G15 5520 to Dell G15 5530?",
        "reference_date": "2024-06-01",
        "test_type": "temporal",
        "temporal_category": "comparison",
        "expected_behavior": "should_compare_specs_correctly",
        "required_patterns": ["32GB", "64GB", "DDR4", "DDR5"],
        "forbidden_patterns": ["same", "identical"],
        "description": "5520 tem DDR4, 5530 tem DDR5 - deve identificar a evolução"
    },
    {
        "id": "TC_TEMP_CMP_002",
        "input": "Compare the GPU options between Acer Nitro 5 AN515-57 and AN515-58.",
        "reference_date": "2024-06-01",
        "test_type": "temporal",
        "temporal_category": "comparison",
        "expected_behavior": "should_compare_gpus_correctly",
        "required_patterns": ["RTX 3050", "RTX 4060"],
        "forbidden_patterns": ["identical"],
        "description": "AN515-57 tem RTX 30xx, AN515-58 tem RTX 40xx"
    },

    # ========================================================================
    # CATEGORIA 5: DATA FUTURA (2026+ - deve recusar ou ser cauteloso)
    # ========================================================================
    {
        "id": "TC_TEMP_FUT_001",
        "input": "What will be the default RAM configuration for the 2026 Dell Alienware m18?",
        "reference_date": "2026-06-01",
        "test_type": "temporal",
        "temporal_category": "future",
        "expected_behavior": "should_admit_unknown_future",
        "required_patterns": ["not available", "cannot predict", "as of now", "no information"],
        "forbidden_patterns": ["32GB", "64GB", "DDR5"],
        "description": "2026 é futuro - não deve especular sobre modelos não lançados"
    },
    {
        "id": "TC_TEMP_FUT_002",
        "input": "What processor will the ASUS ROG Strix Scar 18 2026 use?",
        "reference_date": "2026-01-01",
        "test_type": "temporal",
        "temporal_category": "future",
        "expected_behavior": "should_admit_unknown_future",
        "required_patterns": ["not announced", "unconfirmed", "no information"],
        "forbidden_patterns": ["Core Ultra 9", "285HX"],
        "description": "Não deve especular sobre processadores de 2026"
    },

    # ========================================================================
    # CATEGORIA 6: CONCEITOS ATEMPORAIS (não devem ser penalizados pela data)
    # ========================================================================
    {
        "id": "TC_TEMP_ATEMP_001",
        "input": "What is thermal throttling and why does it happen in gaming laptops?",
        "reference_date": "2025-06-01",
        "test_type": "temporal",
        "temporal_category": "atemporal",
        "expected_behavior": "should_explain_concept_regardless_of_date",
        "required_patterns": ["temperature", "cooling", "reduce", "clock"],
        "min_required_matches": 2,
        "description": "Conceito atemporal - não deve ser penalizado por documentos antigos"
    },
    {
        "id": "TC_TEMP_ATEMP_002",
        "input": "Explain the difference between DDR4 and DDR5 memory.",
        "reference_date": "2025-06-01",
        "test_type": "temporal",
        "temporal_category": "atemporal",
        "expected_behavior": "should_explain_concept_regardless_of_date",
        "required_patterns": ["bandwidth", "speed", "frequency"],
        "min_required_matches": 2,
        "description": "Conceito atemporal - documentos de 2020+ são aceitáveis"
    },
]


TRADITIONAL_TEST_SUITE = [
    # ========================================================================
    # CASOS ORIGINAIS (mantidos)
    # ========================================================================
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

    # ========================================================================
    # NOVOS CASOS – DELL
    # ========================================================================
    {
        "id": "TC_STATIC_03",
        "input": "What is the maximum RAM capacity for the Dell G15 5530?",
        "expected_output": "Dell G15 5530 supports up to 64GB DDR5 RAM.",
        "expected_context": ["Dell G15 5530: Memory support up to 64GB DDR5"],
        "test_type": "traditional",
        "metrics": ["answer_relevancy", "faithfulness", "contextual_relevancy"]
    },
    {
        "id": "TC_STATIC_04",
        "input": "What processor does the Dell G16 7630 have?",
        "expected_output": "Dell G16 7630 is powered by a 13th Gen Intel Core i9 processor.",
        "expected_context": ["Dell G16 7630: 13th Gen Intel Core i9"],
        "test_type": "traditional",
        "metrics": ["answer_relevancy", "faithfulness", "contextual_relevancy"]
    },
    {
        "id": "TC_STATIC_05",
        "input": "What is the default graphics card in the Dell G15 5530?",
        "expected_output": "Dell G15 5530 comes with NVIDIA GeForce RTX 4060 with 8GB GDDR6.",
        "expected_context": ["Dell G15 5530: NVIDIA RTX 4060 8GB"],
        "test_type": "traditional",
        "metrics": ["answer_relevancy", "faithfulness", "contextual_relevancy"]
    },

    # ========================================================================
    # NOVOS CASOS – LENOVO
    # ========================================================================
    {
        "id": "TC_STATIC_06",
        "input": "What is the maximum storage configuration for the Lenovo LOQ 15IRX9?",
        "expected_output": "Lenovo LOQ 15IRX9 supports up to 2TB PCIe SSD storage.",
        "expected_context": ["Lenovo LOQ 15IRX9: 2TB SSD storage"],
        "test_type": "traditional",
        "metrics": ["answer_relevancy", "faithfulness", "contextual_relevancy"]
    },
    {
        "id": "TC_STATIC_07",
        "input": "How many RAM slots does the Lenovo Legion 5 15ACH6A have?",
        "expected_output": "Lenovo Legion 5 15ACH6A has 2 DDR4 SO-DIMM slots (up to 64GB).",
        "expected_context": ["Legion 5 15ACH6A: 2x DDR4 slots, max 64GB"],
        "test_type": "traditional",
        "metrics": ["answer_relevancy", "faithfulness", "contextual_relevancy"]
    },
    {
        "id": "TC_STATIC_08",
        "input": "What processor does the Lenovo Legion Pro 7 16IRX9 have?",
        "expected_output": "Lenovo Legion Pro 7 16IRX9 features an Intel Core i9-14900HX processor.",
        "expected_context": ["Legion Pro 7 16IRX9: Intel Core i9-14900HX"],
        "test_type": "traditional",
        "metrics": ["answer_relevancy", "faithfulness", "contextual_relevancy"]
    },

    # ========================================================================
    # NOVOS CASOS – HP
    # ========================================================================
    {
        "id": "TC_STATIC_09",
        "input": "What is the maximum RAM capacity for the HP Victus 15-fa1066tx?",
        "expected_output": "HP Victus 15-fa1066tx supports up to 32GB DDR4-3200 RAM.",
        "expected_context": ["HP Victus 15-fa1066tx: Memory up to 32GB DDR4"],
        "test_type": "traditional",
        "metrics": ["answer_relevancy", "faithfulness", "contextual_relevancy"]
    },
    {
        "id": "TC_STATIC_10",
        "input": "What GPU is available in the HP Omen 16-k0370tx?",
        "expected_output": "HP Omen 16-k0370tx is equipped with NVIDIA GeForce RTX 4060 (8GB).",
        "expected_context": ["Omen 16-k0370tx: NVIDIA RTX 4060 8GB"],
        "test_type": "traditional",
        "metrics": ["answer_relevancy", "faithfulness", "contextual_relevancy"]
    },
    {
        "id": "TC_STATIC_11",
        "input": "How many M.2 SSD slots does the HP Pavilion 15-eg3018tu have?",
        "expected_output": "HP Pavilion 15-eg3018tu has two M.2 PCIe NVMe slots.",
        "expected_context": ["Pavilion 15-eg3018tu: 2x M.2 PCIe slots"],
        "test_type": "traditional",
        "metrics": ["answer_relevancy", "faithfulness", "contextual_relevancy"]
    },

    # ========================================================================
    # NOVOS CASOS – ASUS
    # ========================================================================
    {
        "id": "TC_STATIC_12",
        "input": "What processor does the ASUS TUF Gaming F15 FX507ZV have?",
        "expected_output": "ASUS TUF Gaming F15 FX507ZV is powered by an Intel Core i7-12700H.",
        "expected_context": ["FX507ZV: Intel Core i7-12700H"],
        "test_type": "traditional",
        "metrics": ["answer_relevancy", "faithfulness", "contextual_relevancy"]
    },
    {
        "id": "TC_STATIC_13",
        "input": "What is the maximum RAM capacity for the ASUS ROG Zephyrus G14 GA402XV?",
        "expected_output": "ASUS ROG Zephyrus G14 GA402XV supports up to 32GB DDR5 (soldered + slot).",
        "expected_context": ["GA402XV: 32GB DDR5 memory (8GB soldered + slot)"],
        "test_type": "traditional",
        "metrics": ["answer_relevancy", "faithfulness", "contextual_relevancy"]
    },
    {
        "id": "TC_STATIC_14",
        "input": "What GPU does the ASUS Vivobook 16X K3605ZF have?",
        "expected_output": "ASUS Vivobook 16X K3605ZF features an NVIDIA GeForce RTX 2050.",
        "expected_context": ["K3605ZF: NVIDIA RTX 2050"],
        "test_type": "traditional",
        "metrics": ["answer_relevancy", "faithfulness", "contextual_relevancy"]
    },

    # ========================================================================
    # NOVOS CASOS – MSI
    # ========================================================================
    {
        "id": "TC_STATIC_15",
        "input": "What is the storage configuration for the MSI Katana 15 B13UDXK?",
        "expected_output": "MSI Katana 15 B13UDXK supports up to 1TB NVMe SSD (dual M.2 slots).",
        "expected_context": ["Katana 15 B13UDXK: 2x M.2 slots, supports 1TB SSD"],
        "test_type": "traditional",
        "metrics": ["answer_relevancy", "faithfulness", "contextual_relevancy"]
    },
    {
        "id": "TC_STATIC_16",
        "input": "How many RAM slots does the MSI Sword 16 HX have?",
        "expected_output": "MSI Sword 16 HX has two DDR5 SO-DIMM slots (up to 64GB).",
        "expected_context": ["Sword 16 HX: 2x DDR5 slots, max 64GB"],
        "test_type": "traditional",
        "metrics": ["answer_relevancy", "faithfulness", "contextual_relevancy"]
    },
    {
        "id": "TC_STATIC_17",
        "input": "What processor does the MSI Stealth 14 Studio AI have?",
        "expected_output": "MSI Stealth 14 Studio AI is equipped with an Intel Core Ultra 7 155H.",
        "expected_context": ["Stealth 14 Studio AI: Intel Core Ultra 7 155H"],
        "test_type": "traditional",
        "metrics": ["answer_relevancy", "faithfulness", "contextual_relevancy"]
    },

    # ========================================================================
    # NOVOS CASOS – OUTROS (Acer, HP, etc.)
    # ========================================================================
    {
        "id": "TC_STATIC_18",
        "input": "What is the maximum RAM capacity for the Acer Predator Helios Neo 16 PHN16-71?",
        "expected_output": "Acer Predator Helios Neo 16 PHN16-71 supports up to 32GB DDR5.",
        "expected_context": ["PHN16-71: 32GB DDR5 memory"],
        "test_type": "traditional",
        "metrics": ["answer_relevancy", "faithfulness", "contextual_relevancy"]
    },
    {
        "id": "TC_STATIC_19",
        "input": "What GPU does the Lenovo LOQ 15IRX9 have?",
        "expected_output": "Lenovo LOQ 15IRX9 is equipped with NVIDIA GeForce RTX 4060 (8GB).",
        "expected_context": ["LOQ 15IRX9: NVIDIA RTX 4060 8GB"],
        "test_type": "traditional",
        "metrics": ["answer_relevancy", "faithfulness", "contextual_relevancy"]
    },
    {
        "id": "TC_STATIC_20",
        "input": "How many USB ports does the HP Spectre x360 14 have?",
        "expected_output": "HP Spectre x360 14 features 2x Thunderbolt 4 and 1x USB-A 3.1 port.",
        "expected_context": ["Spectre x360 14: 2x Thunderbolt 4, 1x USB-A"],
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
# DATASET COMPLETO (FUSÃO)
# ============================================================================

TEST_SUITE = TRADITIONAL_TEST_SUITE + BEHAVIORAL_TEST_SUITE + CHRONOQA_TEMPORAL_SUITE
print(len(TEST_SUITE))
# Para compatibilidade com código existente, mantemos o nome original
# mas adicionamos metadados para diferenciar os tipos

def get_temporal_tests():
    return [t for t in TEST_SUITE if t.get("test_type") == "temporal"]

def get_traditional_tests():
    """Retorna apenas os testes tradicionais (DeepEval metrics)."""
    return [t for t in TEST_SUITE if t.get("test_type") == "traditional"]


def get_behavioral_tests():
    """Retorna apenas os testes comportamentais."""
    return [t for t in TEST_SUITE if t.get("test_type") == "behavioral"]