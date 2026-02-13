from pathlib import Path
from core.bootstrap import ensure_project_root_in_path

# Garante que a raiz do projeto está disponível
ROOT = ensure_project_root_in_path()


# ==========================================================
# PASTAS PRINCIPAIS DO PIPELINE
# ==========================================================

DATASET_GAMER = ROOT / "0 - Dataset dos notebooks gamer"
WEBSCRAPING = ROOT / "1- WebScrapping - Links Apenas"
EXTRACAO = ROOT / "2 - Extração de conversas"
PREPROCESSAMENTO = ROOT / "3 - Pre-processamento dados"
NER = ROOT / "4 - NER com resumo_das_conversas"
VETORIZATION = ROOT / "5 - Vetorizacao_das_conversas"
VALIDACAO = ROOT / "6 - Validação time-aware"


# ==========================================================
# SUBPASTAS IMPORTANTES
# ==========================================================

# --- DATASET GAMER ---
DATASET_CONFIG = DATASET_GAMER / "config"
DATASET_FINAL_CSV = DATASET_GAMER / "dataset_final_csv"
DATASET_KRUGGLE = DATASET_GAMER / "kruggle_coletados_csv"
DATASET_SCRIPTS = DATASET_GAMER / "script"

# DATASET_CONFIG,
# DATASET_FINAL_CSV,
# DATASET_KRUGGLE, 
# DATASET_SCRIPTS


# --- EXTRAÇÃO ---
EXTRACAO_CONFIG = EXTRACAO / "config"
EXTRACAO_DATA = EXTRACAO / "data"
EXTRACAO_SCRIPT = EXTRACAO / "script"
EXTRACAO_SRC = EXTRACAO / "src"
EXTRACAO_SRC_CORE = EXTRACAO_SRC / "core_extration"
EXTRACAO_SRC_EXTRACTORS = EXTRACAO_SRC / "extractors"




# EXTRACAO_CONFIG,
# EXTRACAO_DATA,
# EXTRACAO_SCRIPT,
# EXTRACAO_SRC
# EXTRACAO_SRC_CORE
# EXTRACAO_SRC_EXTRACTORS

# --- PREPROCESSAMENTO ---

PREPROCESSAMENTO_DATA= PREPROCESSAMENTO / "data" 
PREPROCESSAMENTO_SCRIPT= PREPROCESSAMENTO / "script"

# PREPROCESSAMENTO_DATA,
# PREPROCESSAMENTO_SCRIPT

# --- NER ---
NER_DATA = NER / "data"
NER_RULES = NER / "rules"
NER_SCRIPT = NER / "script"

# NER_DATA, 
# NER_RULES, 
# NER_SCRIPT 


# --- VETORIZATION ---
VETORIZATION_CONFIG = VETORIZATION / "config"
VETORIZATION_DATA = VETORIZATION / "data"
VETORIZATION_SCRIPT = VETORIZATION / "script"
VETORIZATION_UTILS = VETORIZATION / "utils"

# VETORIZATION_CONFIG, 
# VETORIZATION_DATA,
# VETORIZATION_SCRIPT, 
# VETORIZATION_UTILS 


# --- VALIDAÇÃO ---
VALIDACAO_CONFIG = VALIDACAO / "config"
VALIDACAO_DATA = VALIDACAO / "data"
VALIDACAO_SCRIPT = VALIDACAO / "script"
VALIDACAO_UTILS = VALIDACAO / "utils"

# VALIDACAO_CONFIG,
# VALIDACAO_DATA, 
# VALIDACAO_SCRIPT, 
# VALIDACAO_UTILS


# ==========================================================
# OUTRAS PASTAS GERAIS
# ==========================================================

DATA_DIR = ROOT / "data"
LOGS_DIR = ROOT / "logs"
SCRAPY_SITES = ROOT / "scrapy-sites"
