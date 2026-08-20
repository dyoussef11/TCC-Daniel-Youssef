
from pathlib import Path

try:
    from core.paths import PREPROCESSAMENTO_DATA, NER_DATA
    DIR_ENTRADA = PREPROCESSAMENTO_DATA / 'Dados_Final_Threshold_V13'
    # DIR_SAIDA_FINAL = NER_DATA / 'Base_Conhecimento_ResumidaV7_VERIFICADA'
    DIR_SAIDA_FINAL = NER_DATA / 'Base_Conhecimento_ResumidaV8_VERIFICADA'
    DIR_SAIDA_FINAL.mkdir(parents=True,exist_ok=True)
    # DIR_CHECKPOINTS = NER_DATA / "checkpoints_ia_v15_verificado"
    DIR_CHECKPOINTS = NER_DATA / "checkpoints_ia_v16_verificado"
    DIR_CHECKPOINTS.mkdir(parents=True,exist_ok=True)
except ImportError:
    DIR_ENTRADA = Path("./data/Dados_Final_ThresholdV6")
    DIR_SAIDA_FINAL = Path("./data/Base_Conhecimento_ResumidaV5_VERIFICADA")
    DIR_CHECKPOINTS = Path("./checkpoints_ia_v13_verificado")

# Parâmetros de Hardware
MAX_CONCURRENT = 1
MAX_TEMP = 80
COOLDOWN_TEMP = 72
# Adicione estas configurações de Chunking
CHUNK_SIZE = 2500   # Caracteres por bloco (aprox. 600 tokens)
MAX_CHUNKS_PER_POST = 8 # Limite de segurança para não processar eternamente um post

KEYWORDS_SOLUCAO = [
    # Confirmação de Sucesso
    "fixed", "solved", "solution", "worked", "working now", "resolved", 
    "issue gone", "no more crashes", "stable now", "fix found",
    
    # Ações de Software/Firmware
    "driver", "update", "bios", "firmware", "registry", "clean install", 
    "ddu", "undervolt", "overclock", "reinstalled", "downgrade",
    
    # Ações de Hardware
    "replaced", "repasted", "thermal paste", "new ram", "swapped", 
    "plugged", "disassembled", "cleaned", "heatsink", "fan replacement",
    
    # Termos de Recomendação
    "try this", "suggest", "recommended", "workaround", "tutorial", "guide"
]


PROMPT_LLAMA_EXTRACTION = """<|begin_of_text|><|start_header_id|>system<|end_header_id|>

You are a diagnostic extraction system. You only respond with function calls in the exact format specified. Do not output any other text or explanation.<|eot_id|><|start_header_id|>user<|end_header_id|>

Call the function 'extract_technical_analysis' with the accurately filled parameters based on the forum post below.

CANONICAL MODEL: {modelo_nome}
POST DATE: {post_date}

TITLE: {titulo}
CONTENT: {corpo}
COMMENTS: {comentarios}

Here is the function definition in JSON format that you must invoke:
[
    {{
        "name": "extract_technical_analysis",
        "description": "Extract technical problem and solutions from a hardware forum post",
        "parameters": {{
            "type": "dict",
            "required": ["summary", "intent", "detected_fault", "suggested_solution", "technical_severity", "discussion_timeline"],
            "properties": {{
                "summary": {{
                    "type": "string",
                    "description": "{modelo_nome}, [problem description] - [key symptoms] - [affected components]"
                }},
                "intent": {{
                    "type": "string",
                    "enum": ["Technical Specifications", "Troubleshooting", "Upgrade Advice", "Compatibility", "Warranty", "Performance"]
                }},
                "detected_fault": {{
                    "type": "string",
                    "description": "Specific technical fault or 'None'"
                }},
                "suggested_solution": {{
                    "type": "array",
                    "items": {{"type": "string"}},
                    "description": "Concise, actionable solution steps. Each step as a separate string in an array.",
                    "maxItems": 4
                }},
                "technical_severity": {{
                    "type": "string",
                    "enum": ["Low", "Medium", "High", "Critical"]
                }},
                "discussion_timeline": {{
                    "type": "string",
                    "description": "{post_date} to {post_date}"
                }}
            }}
        }}
    }}
]

CRITICAL RULES:
- You MUST respond ONLY by calling the 'extract_technical_analysis' function.
- The suggested_solution MUST be an array of strings. Example: ["Step one", "Step two", "Step three"]
- The function call format MUST be exactly: [extract_technical_analysis(summary="...", intent="...", detected_fault="...", suggested_solution=["step1", "step2"], technical_severity="...", discussion_timeline="...")]
- Do not include any other text, apology, or note.<|eot_id|><|start_header_id|>assistant<|end_header_id|>
[extract_technical_analysis(summary="{modelo_nome},"""