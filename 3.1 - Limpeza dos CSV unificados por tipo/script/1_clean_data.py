# 1_clean_data.py

import sys
from pathlib import Path
import pandas as pd
# Importa o módulo de detecção, mas não será usado neste script (mantido por consistência de cabeçalho)
from langdetect import detect, DetectorFactory 
import re 

# --- Configuração de Caminhos ---

# 1. Obtém o caminho absoluto da pasta do script atual.
caminho_script = Path(__file__).resolve().parent

# 2. Acessa a pasta raiz do projeto subindo dois níveis.
caminho_raiz_projeto = caminho_script.parent.parent

# 3. Adiciona o caminho da raiz ao caminho de busca do Python.
sys.path.append(str(caminho_raiz_projeto))

# Tenta importar as variáveis de configuração e as funções de limpeza
try:
    from config import DIRETORIO_DADOS_UNIFICACAO, DIRETORIO_DADOS_LIMPEZA_DATASETS
    # from utils import clean_text
except ImportError as e:
    print(f"Erro ao importar módulos. Verifique 'config.py' e 'utils.py'. Erro: {e}")
    sys.exit(1)

def clean_text(text):
    """
    Realiza a limpeza padronizada do texto, removendo ruídos de fórum/web.
    """
    if pd.isna(text):
        return text

    text = str(text)

    # 1. REMOÇÃO DE ENTIDADES (Mentions, URLs, Zero-Width Space)
    text = re.sub(r'@\S+|http\S+|www\S+|&#x200B;', ' ', text)

    # 2. REMOÇÃO DE CABEÇALHOS DE CITAÇÃO
    text = re.sub(r'Em\s+\d{2}/\d{2}/\d{4}\s+às\s+\d{2}:\d{2}.+?disse:\s*', ' ', text, flags=re.IGNORECASE)

    # 3. CONSOLIDAÇÃO DE RUÍDO DE FORMATAÇÃO
    text = re.sub(r'[\r\n\t\xa0]+', ' ', text)
    text = re.sub(r'\s+\s*', ' ', text)

    # 4. NORMALIZAÇÃO DE CAIXA
    text = text.lower()

    # 5. REMOÇÃO DO RUÍDO NUMÉRICO ISOLADO
    text = re.sub(r'\s\d+\s*$', '', text)

    # 6. CONSOLIDAÇÃO DE ESPAÇOS E FINALIZAÇÃO
    text = re.sub(r'\s+', ' ', text).strip()

    return text


# --- Processamento Principal (Apenas Limpeza) ---

def main_cleaning():
    print("--- 1. INICIANDO LIMPEZA DE DADOS (PRIMEIRA ETAPA) ---")

    # Caminhos
    caminho_entrada = DIRETORIO_DADOS_UNIFICACAO / 'respostas_combinadas_final.csv'
    # Salvando o resultado da limpeza em um novo arquivo intermediário
    caminho_saida_limpeza = DIRETORIO_DADOS_LIMPEZA_DATASETS / 'respostas_somente_limpas.csv'

    # Carregar o arquivo CSV
    try:
        print(f"Carregando dados brutos de: {caminho_entrada}")
        # É crucial carregar apenas as colunas necessárias para economizar memória, se o dataset for grande.
        df = pd.read_csv(caminho_entrada, dtype={'Conteudo_Comentario': 'object'})
    except FileNotFoundError:
        print(f"Erro: Arquivo não encontrado: {caminho_entrada}")
        return

    # 1. Aplica a limpeza (função importada de utils.py)
    print("Aplicando limpeza e gerando coluna 'Conteudo_Comentario_Limpo'...")
    df['Conteudo_Comentario_Limpo'] = df['Conteudo_Comentario'].astype(str).apply(clean_text)

    # 2. Seleciona as colunas a serem salvas
    # Incluímos Conteudo_Comentario_Limpo e as colunas originais que são importantes (ex: IDs, data, etc.)
    colunas_salvas = [col for col in df.columns if col not in ['Conteudo_Comentario_Limpo']] + ['Conteudo_Comentario_Limpo']
    df_final = df[colunas_salvas]

    # 3. Salva o resultado
    DIRETORIO_DADOS_LIMPEZA_DATASETS.mkdir(parents=True, exist_ok=True)
    df_final.to_csv(caminho_saida_limpeza, index=False)

    print("-" * 50)
    print(f"✅ Limpeza de dados concluída. Arquivo salvo em: {caminho_saida_limpeza}")
    print(f"Total de registros: {len(df_final)}")
    print("-" * 50)

if __name__ == "__main__":
    main_cleaning()