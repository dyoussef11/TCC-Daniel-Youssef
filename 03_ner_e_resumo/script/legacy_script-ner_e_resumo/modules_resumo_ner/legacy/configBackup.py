
from pathlib import Path

try:
    from core.paths import PREPROCESSAMENTO_DATA, NER_DATA
    DIR_ENTRADA = PREPROCESSAMENTO_DATA / 'Dados_Final_Threshold_V12'
    DIR_SAIDA_FINAL = NER_DATA / 'Base_Conhecimento_ResumidaV7_VERIFICADA'
    DIR_CHECKPOINTS = NER_DATA / "checkpoints_ia_v15_verificado"
except ImportError:
    DIR_ENTRADA = Path("./data/Dados_Final_ThresholdV6")
    DIR_SAIDA_FINAL = Path("./data/Base_Conhecimento_ResumidaV5_VERIFICADA")
    DIR_CHECKPOINTS = Path("./checkpoints_ia_v13_verificado")

# Parâmetros de Hardware
MAX_CONCURRENT = 1
MAX_TEMP = 82
COOLDOWN_TEMP = 72

PROMPT_LLAMA_EXTRACTION = """[INST] You are a hardware diagnostic extraction system. Extract technical problem and solutions from this forum post.

CANONICAL MODEL: {modelo_nome}
POST DATE: {post_date}

TITLE: {titulo}
CONTENT: {corpo}
COMMENTS: {comentarios}

Return ONLY valid JSON with these exact fields:
{{
  "summary": "{modelo_nome}, [problem description] - [key symptoms] - [affected components]",
  "intent": "Technical Specifications|Troubleshooting|Upgrade Advice|Compatibility|Warranty|Performance",
  "detected_fault": "specific technical fault or 'None'",
  "suggested_solution": ["solution step 1", "solution step 2", "solution step 3"],
  "technical_severity": "Low|Medium|High|Critical",
  "discussion_timeline": "{post_date} to {post_date}"
}}

CRITICAL FORMAT FOR "suggested_solution":
- MUST be an ARRAY of strings, NOT a single string
- Each solution step should be a concise, actionable instruction
- Order by: software fixes first, then hardware fixes, then replacement
- Maximum 4 solution steps

EXAMPLES OF CORRECT "suggested_solution":
✓ ["Update NVIDIA drivers to latest version", "Clean install drivers using DDU", "If issue persists, RMA the GPU"]
✓ ["Clean fans and heatsink with compressed air", "Repaste CPU with PTM7950", "Undervolt CPU by -50mV", "Limit turbo boost to 3.5GHz"]
✓ ["Replace display cable (inexpensive fix)", "If flickering continues, replace LCD panel"]

EXAMPLES OF INCORRECT "suggested_solution" (DO NOT DO THIS):
✗ "Clean fans and repaste CPU"  <- NOT AN ARRAY!
✗ ["Check and clean fans, apply new thermal paste"]  <- TOO MANY ACTIONS IN ONE STRING!

CRITICAL FORMAT FOR "summary":
You MUST follow this exact structure:
"{modelo_nome}, [problem description] - [key symptoms] - [affected components]"

EXAMPLE COMPLETE OUTPUT:
{{
  "summary": "Acer Predator Helios Neo 16 RTX 4050, CPU reaches 100°C during Cinebench R23 - thermal throttling despite 40W undervolt - cooling system, CPU",
  "intent": "Troubleshooting",
  "detected_fault": "Thermal throttling due to inadequate cooling",
  "suggested_solution": ["Clean cooling fans and heatsink", "Repaste CPU and GPU with PTM7950", "Undervolt CPU by -50mV using ThrottleStop", "Use cooling pad during intensive tasks"],
  "technical_severity": "Medium",
  "discussion_timeline": "2025-08-18 to 2025-08-18"
}}

Be concise. Extract only solutions mentioned in the post or comments. [/INST]"""