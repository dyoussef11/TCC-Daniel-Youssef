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
PASTA_UNIFICACAO = DIRETORIO_DADOS_LINKS / "3 - Unificação dos CSV"
PASTA_CLASSIFICACAO = DIRETORIO_DADOS_LINKS / "4 - Classificação de Perguntas"
PASTA_SEPARACAO_PROBLEMAS = DIRETORIO_DADOS_LINKS / "5 - Separação das respostas - Problemas"
PASTA_LABELSTUDIO = DIRETORIO_DADOS_LINKS / "6 - Dataset - Respostas - LabelStudio"
PASTA_LINGUAGENS = DIRETORIO_DADOS_LINKS / "6.1 - Dataset - Respostas - Linguagens"
PASTA_SEPARACAO_TESTE = DIRETORIO_DADOS_LINKS / "6.3 - Dataset - Separação para teste"
PASTA_LIMPEZA_RESPOSTAS = DIRETORIO_DADOS_LINKS / "6.2 - Dataset - Respostas - Limpeza"
PASTA_BALANCEAMENTO = DIRETORIO_DADOS_LINKS / "7- Balaceamento do dataset do treino"
PASTA_BAG_OF_WORDS = DIRETORIO_DADOS_LINKS / "8 - Bag of Words - com dataset Desbalanceado"

# --- Mapeamento de Caminhos (DADOS) ---
# Caminhos para as pastas que contêm os arquivos de dados
DIRETORIO_DADOS_WEBSCRAPPING = PASTA_WEBSCRAPPING / "data"
DIRETORIO_DADOS_EXTRACAO_QA = PASTA_EXTRACAO_QA / "data"
DIRETORIO_DADOS_UNIFICACAO = PASTA_UNIFICACAO / "data"
DIRETORIO_DADOS_CLASSIFICACAO = PASTA_CLASSIFICACAO / "data"
DIRETORIO_DADOS_SEPARACAO_PROBLEMAS = PASTA_SEPARACAO_PROBLEMAS / "data"
DIRETORIO_DADOS_LABELSTUDIO = PASTA_LABELSTUDIO / "data"
DIRETORIO_DADOS_LINGUAGENS = PASTA_LINGUAGENS / "data"
DIRETORIO_DADOS_LIMPEZA = PASTA_LIMPEZA_RESPOSTAS / "data"
DIRETORIO_DADOS_SEPARACAO_TESTE = PASTA_SEPARACAO_TESTE / "data"
DIRETORIO_DADOS_BALANCEAMENTO = PASTA_BALANCEAMENTO / "data"
DIRETORIO_DADOS_BAG_OF_WORDS = PASTA_BAG_OF_WORDS / "data"
DIRETORIO_IMAGENS_MODELO_BAG_OF_WORDS = PASTA_BAG_OF_WORDS / "image"

# --- Mapeamento de Caminhos (SCRIPTS) ---
# Caminhos para as pastas que contêm os scripts
DIRETORIO_SCRIPTS_WEBSCRAPPING = PASTA_WEBSCRAPPING / "script"
DIRETORIO_SCRIPTS_EXTRACAO_QA = PASTA_EXTRACAO_QA / "script"
DIRETORIO_SCRIPTS_UNIFICACAO = PASTA_UNIFICACAO / "script"
DIRETORIO_SCRIPTS_CLASSIFICACAO = PASTA_CLASSIFICACAO / "script"
DIRETORIO_SCRIPTS_SEPARACAO_PROBLEMAS = PASTA_SEPARACAO_PROBLEMAS / "script"
DIRETORIO_SCRIPTS_LABELSTUDIO = PASTA_LABELSTUDIO / "script"
DIRETORIO_SCRIPTS_LINGUAGENS = PASTA_LINGUAGENS / "script"
DIRETORIO_SCRIPTS_LIMPEZAS = PASTA_LIMPEZA_RESPOSTAS / "script"
DIRETORIO_SCRIPTS_SEPARACAO_TESTE = PASTA_SEPARACAO_TESTE / "script"
DIRETORIO_SCRIPTS_BALANCEAMENTO = PASTA_BALANCEAMENTO / "script"
DIRETORIO_SCRIPTS_BAG_OF_WORDS = PASTA_BAG_OF_WORDS / "script"  

# --- Mapeamento de Caminhos (CSV) ---
# Caminhos para as pastas que contêm os CSVs
DIRETORIO_CSV_DATASET_FINAL = PASTA_MODELOS_NOTEBOOKS_GAMER / "dataset_final_csv"
DIRETORIO_CSV_DATASET_COLETADOS = PASTA_MODELOS_NOTEBOOKS_GAMER / "kruggle_coletados_csv"
