import sys
from pathlib import Path

# Obtém o caminho absoluto da pasta do script atual.
# Exemplo: 'C:\...\Buscar_Web\1- WebScrapping\script'
caminho_script = Path(__file__).resolve().parent

# Acessa a pasta raiz do projeto subindo dois níveis.
# Exemplo: 'C:\...\Buscar_Web'
caminho_raiz_projeto = caminho_script.parent.parent

# Adiciona o caminho da raiz ao caminho de busca do Python.
sys.path.append(str(caminho_raiz_projeto))

# Pasta base do projeto (o diretório onde este arquivo está)
DIRETORIO_DADOS_LINKS = Path(__file__).resolve().parent

# --- Estrutura principal do projeto ---
# Pastas de nível superior que contêm 'data' e 'script'
# Mantenha os nomes das pastas em inglês para evitar problemas
PASTA_MODELOS_NOTEBOOKS_GAMER = DIRETORIO_DADOS_LINKS / "0 - Dataset dos notebooks gamer"
PASTA_WEBSCRAPPING = DIRETORIO_DADOS_LINKS / "1- WebScrapping - Links Apenas"
PASTA_EXTRACAO_QA = DIRETORIO_DADOS_LINKS / "2 - Extração de Perguntas e Respostas"
PASTA_UNIFICACAO = DIRETORIO_DADOS_LINKS / "3 - Unificação dos CSV por tipo"
PASTA_LIMPEZA_DATASETS = DIRETORIO_DADOS_LINKS / "3.1 - Limpeza dos CSV unificados por tipo"
PASTA_SUMARIZACAO_DE_TEXTOS = DIRETORIO_DADOS_LINKS / "3.2 - Sumarizacao Texto"
PASTA_MODELO_ZERO_SHOT = DIRETORIO_DADOS_LINKS / "4 - Dataset - ZeroShot - Rotulo Classificacao"

# --- Mapeamento de Caminhos (DADOS) ---
# Caminhos para as pastas que contêm os arquivos de dados
DIRETORIO_DADOS_WEBSCRAPPING = PASTA_WEBSCRAPPING / "data"
DIRETORIO_DADOS_EXTRACAO_QA = PASTA_EXTRACAO_QA / "data"
DIRETORIO_DADOS_UNIFICACAO = PASTA_UNIFICACAO / "data"
DIRETORIO_DADOS_LIMPEZA_DATASETS = PASTA_LIMPEZA_DATASETS / "data"
DIRETORIO_DADOS_MODELO_ZERO_SHOT = PASTA_MODELO_ZERO_SHOT / "data"
DIRETORIO_DADOS_SUMARIZACAO_DE_TEXTOS = PASTA_SUMARIZACAO_DE_TEXTOS / "data"

# --- Mapeamento de Caminhos (SCRIPTS) ---
# Caminhos para as pastas que contêm os scripts
DIRETORIO_SCRIPTS_WEBSCRAPPING = PASTA_WEBSCRAPPING / "script"
DIRETORIO_SCRIPT_MODELO_BUSCA= DIRETORIO_SCRIPTS_WEBSCRAPPING / "modelo_de_busca"
DIRETORIO_SCRIPTS_EXTRACAO_QA = PASTA_EXTRACAO_QA / "script"
DIRETORIO_SCRIPTS_UNIFICACAO = PASTA_UNIFICACAO / "script"
DIRETORIO_SCRIPTS_LIMPEZA_DATASETS = PASTA_LIMPEZA_DATASETS / "script"
DIRETORIO_SCRIPTS_MODELO_ZERO_SHOT = PASTA_MODELO_ZERO_SHOT / "script"
DIRETORIO_SCRIPTS_SUMARIZACAO_DE_TEXTOS = PASTA_SUMARIZACAO_DE_TEXTOS / "script"

# --- Mapeamento de Caminhos (CSV) ---
# Caminhos para as pastas que contêm os CSVs
DIRETORIO_CSV_DATASET_FINAL = PASTA_MODELOS_NOTEBOOKS_GAMER / "dataset_final_csv"
DIRETORIO_CSV_DATASET_COLETADOS = PASTA_MODELOS_NOTEBOOKS_GAMER / "kruggle_coletados_csv"

# --- Mapeamento de Caminhos (UTILS) ---
DIRETORIO_UTILS_WEBSCRAPPING = PASTA_WEBSCRAPPING / "utils"
DIRETORIO_UTILS_EXTRACAO_QA = PASTA_EXTRACAO_QA / "utils"
DIRETORIO_UTILS_UNIFICACAO = PASTA_UNIFICACAO / "utils"
DIRETORIO_UTILS_LIMPEZA_DATASETS = PASTA_LIMPEZA_DATASETS / "utils"
DIRETORIO_UTILS_SUMARIZACAO_DE_TEXTOS = PASTA_SUMARIZACAO_DE_TEXTOS / "utils"
DIRETORIO_UTILS_MODELO_ZERO_SHOT = PASTA_MODELO_ZERO_SHOT / "utils"

# --- Adicionar todos os diretórios utils ao sys.path ---
utils_dirs = [
    DIRETORIO_UTILS_WEBSCRAPPING,
    DIRETORIO_UTILS_EXTRACAO_QA,
    DIRETORIO_UTILS_UNIFICACAO,
    DIRETORIO_UTILS_LIMPEZA_DATASETS,
    DIRETORIO_UTILS_SUMARIZACAO_DE_TEXTOS,
    DIRETORIO_UTILS_MODELO_ZERO_SHOT
]

for utils_dir in utils_dirs:
    if utils_dir.exists():
        sys.path.append(str(utils_dir))