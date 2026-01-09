# 2_detect_language.py

import sys
from pathlib import Path
import re
import pandas as pd
# Importa o módulo de detecção
from langdetect import detect_langs, DetectorFactory, detect
from tqdm import tqdm  # ← Biblioteca para barra de progresso
import random

# --- Configuração de Caminhos ---

# 1. Obtém o caminho absoluto da pasta do script atual.
caminho_script = Path(__file__).resolve().parent

# 2. Acessa a pasta raiz do projeto subindo dois níveis.
caminho_raiz_projeto = caminho_script.parent.parent

# 3. Adiciona o caminho da raiz ao caminho de busca do Python.
sys.path.append(str(caminho_raiz_projeto))

try:
    from config import DIRETORIO_DADOS_LIMPEZA_DATASETS
except ImportError as e:
    print(f"Erro ao importar módulos. Verifique 'config.py'. Erro: {e}")
    sys.exit(1)

# Garante que a detecção de idioma seja consistente
DetectorFactory.seed = 0

tamanho_minimo_caracteres = 6

def extract_first_sentence(text):
    """
    Extrai a primeira frase do texto, lidando com marcadores [USUARIO] e outros padrões.
    """
    if not text or pd.isna(text):
        return ""
    
    text = str(text).strip()
    if not text:
        return ""
    
    # Remove o marcador [USUARIO] do início se estiver sozinho
    text = re.sub(r'^\[USUARIO\]\s*', '', text)
    
    # Também trata padrões comuns de usuário sem marcadores
    user_patterns = [
        r'^USUARIO\s+\w+[\s,:;-]+',
        r'^USER\s+\w+[\s,:;-]+', 
        r'^@\w+[\s,:;-]+',
        r'^u/\w+[\s,:;-]+',
    ]
    
    for pattern in user_patterns:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    
    text = text.strip()
    
    if not text:
        return ""
    
    # Encontra a primeira frase significativa
    # Procura por frases que terminem com pontuação OU tenham comprimento mínimo
    patterns = [
        r'^([^.!?\n]{15,}[.!?])',  # 15+ chars terminando com pontuação
        r'^([^.!?\n]{20,})',       # 20+ chars sem pontuação
        r'^([^.!?\n]{10,}[.!?]|[^.!?\n]{15,})',  # Fallback mais flexível
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            sentence = match.group(1).strip()
            # Filtra frases que são apenas marcadores técnicos
            if (len(sentence) >= 10 and 
                not re.match(r'^\[(URL|EMAIL|CODIGO|BLOCO_CODIGO)\]', sentence) and
                not sentence.isdigit()):
                return sentence
    
    # Último fallback: primeiras palavras significativas
    words = text.split()
    meaningful_words = []
    for word in words:
        if len(word) >= 3 and not re.match(r'^\[?\w+\]?$', word):  # Filtra palavras curtas e marcadores
            meaningful_words.append(word)
        if len(meaningful_words) >= 5:  # Pega até 5 palavras significativas
            break
    
    result = ' '.join(meaningful_words[:5])
    return result if len(result) >= 10 else ""

def get_language_by_first_sentence(text, threshold=0.15):
    """
    Versão otimizada que ignora marcadores técnicos.
    """
    try:
        # Extrai a primeira frase limpa
        first_sentence = extract_first_sentence(text)
        
        # Critérios rigorosos para texto válido
        if (not first_sentence or 
            len(first_sentence.strip()) < tamanho_minimo_caracteres or
            first_sentence.isupper() or
            re.match(r'^[\d\s\W]+$', first_sentence) or
            re.match(r'^\[(URL|EMAIL|CODIGO|BLOCO_CODIGO)\]', first_sentence)):
            return 'other'
        
        # DEBUG: Mostra alguns exemplos do que está sendo analisado
        if random.random() < 0.001:  # Apenas 0.1% para não poluir o output
            print(f"DEBUG: Analisando -> '{first_sentence[:50]}...'")
        
        # Detecta o idioma
        langs = detect_langs(first_sentence)
        best = max(langs, key=lambda x: x.prob)
        best_lang, prob = best.lang, best.prob

        # Regras para misturas
        lang_codes = [l.lang for l in langs if l.prob > 0.25]
        
        if 'pt' in lang_codes and 'en' in lang_codes:
            pt_prob = next((l.prob for l in langs if l.lang == 'pt'), 0)
            en_prob = next((l.prob for l in langs if l.lang == 'en'), 0)
            
            if pt_prob > 0.3 and en_prob > 0.3:
                return 'pt-mixed' if pt_prob >= en_prob else 'en-mixed'

        # Threshold mais alto para confiança
        if best.lang in ['pt', 'en'] and prob >= threshold:
            return best.lang

        return 'other'

    except Exception as e:
        # DEBUG: Mostra erros ocasionalmente
        if random.random() < 0.001:
            print(f"DEBUG: Erro na detecção: {e}")
        return 'other'

# --- Processamento Principal (Detecção de Idioma) ---

def main_detection():
    print("--- 2. INICIANDO DETECÇÃO DE IDIOMA (PRIMEIRA FRASE) ---")

    # Caminhos
    caminho_entrada_limpa = DIRETORIO_DADOS_LIMPEZA_DATASETS / 'respostas_combinadas_limpo.csv'
    caminho_saida_detectada = DIRETORIO_DADOS_LIMPEZA_DATASETS / 'respostas_com_lingua_detectada.csv'

    # Carregar o arquivo CSV limpo
    try:
        print(f"Carregando dados limpos de: {caminho_entrada_limpa}")
        df = pd.read_csv(caminho_entrada_limpa, low_memory=False)
        print(f"Total de registros carregados: {len(df):,}")
    except FileNotFoundError:
        print(f"Erro: Arquivo intermediário de limpeza não encontrado. Execute '1_clean_data.py' primeiro. Caminho: {caminho_entrada_limpa}")
        return

    # Proteção: Verifica se a coluna limpa existe
    if 'Conteudo_Comentario_Limpo' not in df.columns:
        print("Erro: A coluna 'Conteudo_Comentario_Limpo' não foi encontrada. Verifique '1_clean_data.py'.")
        return

    # 1. Aplica a detecção de idioma baseada na primeira frase COM BARRA DE PROGRESSO
    print("Aplicando detecção de idioma na PRIMEIRA FRASE da coluna limpa...")
    
    # Usando tqdm para mostrar progresso
    tqdm.pandas(desc="Detectando idiomas", unit="registros")
    df['language'] = df['Conteudo_Comentario_Limpo'].astype(str).progress_apply(get_language_by_first_sentence)

    # 2. Extrai a primeira frase (também com barra de progresso)
    print("Extraindo primeiras frases para debug...")
    df['primeira_frase'] = df['Conteudo_Comentario_Limpo'].astype(str).progress_apply(extract_first_sentence)

    # 3. Salva o resultado 
    DIRETORIO_DADOS_LIMPEZA_DATASETS.mkdir(parents=True, exist_ok=True)
    df.to_csv(caminho_saida_detectada, index=False)

    print("-" * 50)
    print(f"✅ Detecção por primeira frase concluída. Arquivo salvo em: {caminho_saida_detectada}")
    print(f"Distribuição de idiomas: \n{df['language'].value_counts()}")
    
    # Mostra alguns exemplos para validação
    print("\n📝 Exemplos de primeiras frases por idioma:")
    for lang in df['language'].unique():
        samples = df[df['language'] == lang]['primeira_frase'].head(5)
        print(f"\n{lang.upper()}:")
        for i, sample in enumerate(samples):
            print(f"  {i+1}. {sample[:80]}{'...' if len(sample) > 80 else ''}")
    
    # Estatísticas adicionais
    total_registros = len(df)
    print(f"\n📊 Estatísticas:")
    print(f"Total de registros processados: {total_registros:,}")
    for lang, count in df['language'].value_counts().items():
        percentual = (count / total_registros) * 100
        print(f"  {lang}: {count:,} ({percentual:.1f}%)")
    
    print("-" * 50)

if __name__ == "__main__":
    main_detection()