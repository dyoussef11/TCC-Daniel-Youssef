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
    Limpeza robusta para textos de fórum, voltada para modelos zero-shot.
    Remove ruídos, normaliza e mantém semântica útil.
    """
    if pd.isna(text):
        return text

    text = str(text)

    # 1. Remoção de menções, URLs, caracteres invisíveis e formatação de texto
    text = re.sub(r'@\S+|http\S+|www\S+|&#x200B;', ' ', text)
    text = re.sub(r'[\x00-\x1F\x7F-\x9F]', ' ', text)  # remove caracteres de controle
    
    # NOVO: Remoção de caracteres de formatação Markdown/Fórum (*, _, ~)
    text = re.sub(r'[*_~]', ' ', text)

    # 2. Remoção de cabeçalhos de citação
    text = re.sub(r'Em\s+\d{2}/\d{2}/\d{4}\s+às\s+\d{2}:\d{2}.+?disse:\s*', ' ', text, flags=re.IGNORECASE)

    # 3. Normalização e pontuação
    text = re.sub(r'[…]+', '.', text)
    text = re.sub(r'([!?]){2,}', r'\1', text)
    
    # Sua adição: Remove múltiplos espaços após pontuação (ex: 'a.  b' -> 'a.b')
    text = re.sub(r'([.,!?])\s+', r'\1', text) 
    
    # Mantém a separação correta (ex: 'a.b' -> 'a. b')
    text = re.sub(r'([.,!?])([A-Za-z])', r'\1 \2', text)

    # NOVO: Remoção de aspas (aspas duplas/simples) e emoticons simples
    text = re.sub(r'["\']', '', text) # Remove aspas duplas e simples
    # Regex para emoticons textuais comuns
    text = re.sub(r'[:;=X][-oO*^]?[)D(P/|\\$S@]', ' ', text)

    # 4. Consolidação de espaços e remoção de formatação
    text = re.sub(r'[\r\n\t\xa0]+', ' ', text)
    text = re.sub(r'\s+', ' ', text)

    # 5. Normalização de caixa
    text = text.lower()

    # 6. Remoção de ruído numérico e frases irrelevantes
    irrelevantes = [r'\bobrigad[ao]\b', r'\bespero ter ajudado\b', r'\bboa sorte\b', r'\bvaleu\b', r'\benfim\b']
    text = re.sub('|'.join(irrelevantes), '', text)
    text = re.sub(r'\s\d+\s*$', '', text) # Limpeza de score/números no final
    
    # 7. Normalização de valores monetários
    text = re.sub(r'r\$\s?([\d,.]+)', r'\1 reais', text)
    text = re.sub(r'(\d+)k', r'\1 mil', text)

    # 8. Finalização
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