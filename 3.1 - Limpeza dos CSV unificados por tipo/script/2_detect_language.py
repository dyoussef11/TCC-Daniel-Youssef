# 2_detect_language.py (ou o nome do seu script)

import sys
from pathlib import Path
import re
import pandas as pd
# Importa o módulo de detecção
from langdetect import detect_langs, DetectorFactory

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

def get_language_corrected(text, min_length=20, threshold=0.6):
    """
    Detecta o idioma predominante em um texto, considerando mistura pt/en.
    Retorna 'pt', 'en' ou 'other'.
    """
    if not isinstance(text, str):
        return 'other'

    # Remove números, URLs e menções que atrapalham o detector
    clean = re.sub(r'@\S+|http\S+|www\S+|\d+', ' ', text)
    clean = re.sub(r'[^a-zA-ZÀ-ÿ ]', ' ', clean)
    clean = re.sub(r'\s+', ' ', clean).strip()

    if len(clean) < min_length:
        return 'other'

    try:
        langs = detect_langs(clean)
        if not langs:
            return 'other'

        # Exemplo de saída: [pt:0.71, en:0.28]
        best = max(langs, key=lambda x: x.prob)
        best_lang, prob = best.lang, best.prob

        # --- Regras refinadas ---
        # 1. Se há mistura pt/en, escolher o mais forte, mas permitir dualidade
        lang_codes = [l.lang for l in langs if l.prob > 0.2]
        if 'pt' in lang_codes and 'en' in lang_codes:
            # português e inglês misturados — pode marcar como 'pt' se o texto for majoritariamente português
            if best.lang == 'pt' or prob >= 0.5:
                return 'pt-mixed'
            else:
                return 'en-mixed'

        # 2. Se o idioma dominante é confiável
        if best.lang in ['pt', 'en'] and prob >= threshold:
            return best.lang

        return 'other'

    except Exception:
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