# 2_detect_language.py (ou o nome do seu script)

import sys
from pathlib import Path
import re
import pandas as pd
# Importa o módulo de detecção
from langdetect import detect, DetectorFactory

# --- Configuração de Caminhos ---

# 1. Obtém o caminho absoluto da pasta do script atual.
caminho_script = Path(__file__).resolve().parent

# 2. Acessa a pasta raiz do projeto subindo dois níveis.
# Exemplo: 'C:\...\Notebook-Forum-Sentimento'
caminho_raiz_projeto = caminho_script.parent.parent

# 3. Adiciona o caminho da raiz ao caminho de busca do Python.
sys.path.append(str(caminho_raiz_projeto))

# Tenta importar as variáveis de configuração e as funções de utilidade
try:
    from config import DIRETORIO_DADOS_LIMPEZA_DATASETS
    # Se você moveu get_language_corrected para utils.py, descomente a linha abaixo:
    # from utils import get_language_corrected 
except ImportError as e:
    print(f"Erro ao importar módulos. Verifique 'config.py' e 'utils.py'. Erro: {e}")
    sys.exit(1)

# Garante que a detecção de idioma seja consistente
DetectorFactory.seed = 0

def get_language_corrected(text, min_length=20):
    """Detecta o idioma e consolida em 'pt', 'en' ou 'other'."""
    # O valor 'text' agora é garantido como string (inclusive 'nan' se for nulo)
    if len(text) < min_length:
        return 'other'
        
    try:
        lang = detect(text)
        
        if lang not in ['pt', 'en']:
            return 'other'
            
        return lang
    except:
        return 'other'

# --- Processamento Principal (Detecção de Idioma) ---

def main_detection():
    print("--- 2. INICIANDO DETECÇÃO DE IDIOMA ---")

    # Caminhos
    caminho_entrada_limpa = DIRETORIO_DADOS_LIMPEZA_DATASETS / 'respostas_somente_limpas.csv'
    # Salvando o resultado da detecção (pronto para separação)
    caminho_saida_detectada = DIRETORIO_DADOS_LIMPEZA_DATASETS / 'respostas_com_lingua_detectada.csv'

    # Carregar o arquivo CSV limpo
    try:
        print(f"Carregando dados limpos de: {caminho_entrada_limpa}")
        df = pd.read_csv(caminho_entrada_limpa)
    except FileNotFoundError:
        print(f"Erro: Arquivo intermediário de limpeza não encontrado. Execute '1_clean_data.py' primeiro. Caminho: {caminho_entrada_limpa}")
        return

    # Proteção: Verifica se a coluna limpa existe
    if 'Conteudo_Comentario_Limpo' not in df.columns:
        print("Erro: A coluna 'Conteudo_Comentario_Limpo' não foi encontrada. Verifique '1_clean_data.py'.")
        return

    # 1. Aplica a detecção de idioma
    print("Aplicando detecção de idioma na coluna limpa e gerando 'language'...")
    # CORREÇÃO AQUI: Garante que todos os valores (incluindo NaN) sejam strings antes de aplicar a função
    df['language'] = df['Conteudo_Comentario_Limpo'].astype(str).apply(get_language_corrected)

    # 2. Salva o resultado 
    DIRETORIO_DADOS_LIMPEZA_DATASETS.mkdir(parents=True, exist_ok=True)
    df.to_csv(caminho_saida_detectada, index=False)

    print("-" * 50)
    print(f"✅ Detecção concluída. Arquivo pronto para separação salvo em: {caminho_saida_detectada}")
    print(f"Distribuição de idiomas: \n{df['language'].value_counts()}")
    print("-" * 50)

if __name__ == "__main__":
    main_detection()