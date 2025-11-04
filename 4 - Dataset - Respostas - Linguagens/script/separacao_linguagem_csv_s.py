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

# Tenta importar as variáveis de configuração (DIRETORIO_DADOS_...)
try:
    from config import DIRETORIO_DADOS_LINGUAGENS, DIRETORIO_DADOS_UNIFICACAO
except ImportError:
    # --- FALLBACK: Define os caminhos se 'config.py' não for encontrado ou não tiver as variáveis ---
    print("Aviso: Falha ao importar variáveis de 'config.py'. Usando paths de fallback baseados na estrutura de pastas.")
    
    # Baseado na estrutura comum de projetos (passo 4 para saída, passo 3 para entrada)
    # Ajuste o '3 - Unificação...' se o seu diretório for outro
    DIRETORIO_DADOS_UNIFICACAO = caminho_raiz_projeto / '3 - Unificação dos CSV por tipo' / 'data'
    DIRETORIO_DADOS_LINGUAGENS = caminho_raiz_projeto / '4 - Dataset - Respostas - Linguagens' / 'data'

# Garante que a detecção de idioma seja consistente
DetectorFactory.seed = 0

# --- Funções de Pré-processamento e Detecção (Mantidas) ---

def clean_text_robust(text):
    """Limpa o texto de forma agressiva para remover ruído que confunde o detector."""
    if pd.isna(text) or text is None:
        return ""

    text = str(text)

    # 1. Remover URLs e menções
    text = re.sub(r'http\S+|www\S+|https\S+', '', text, flags=re.MULTILINE)
    text = re.sub(r'@\w+', '', text)

    # 2. Remover quebras de linha/abas e caracteres especiais de formatação (ex: &#x200B;)
    text = text.replace('\r', ' ').replace('\n', ' ').replace('\t', ' ')
    text = re.sub(r'&#x\w+;', ' ', text)

    # 3. Remover caracteres não-alfanuméricos/ruído (mantendo letras, números e pontuação básica)
    # Mantém letras (incluindo acentuadas), números e pontuação comum (.,?!).
    text = re.sub(r'[^a-zA-Z0-9\sÁÉÍÓÚÀÈÌÒÙÃÕÂÊÎÔÛÇáéíóúàèìòùãõâêîôûç.,?!]', ' ', text)

    # 4. Remover múltiplos espaços em branco
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text

def get_language_corrected(text, min_length=20):
    """
    Detecta o idioma e consolida em 'pt', 'en' ou 'other'.
    Textos muito curtos ou que falham na detecção são classificados como 'other'.
    """
    # 1. Se o texto for muito curto após a limpeza, é considerado ruído ou não confiável.
    if len(text) < min_length:
        return 'other'
        
    try:
        # 2. Tenta detectar o idioma
        lang = detect(text)
        
        # 3. Consolida idiomas que não são pt ou en
        if lang not in ['pt', 'en']:
            return 'other'
            
        return lang
    except:
        # 4. Caso a detecção falhe por insuficiência de caracteres no texto limpo
        return 'other'

# --- Processamento Principal ---

# Caminho do seu arquivo CSV de entrada
caminho_entrada = DIRETORIO_DADOS_UNIFICACAO / 'respostas_combinadas_final.csv'

# Carregar o arquivo CSV em um DataFrame
try:
    # Lê o CSV e garante que a coluna de interesse seja tratada como string
    df = pd.read_csv(caminho_entrada, dtype={'Conteudo_Comentario': 'object'})
except FileNotFoundError:
    print(f"Erro: O arquivo não foi encontrado no caminho especificado: {caminho_entrada}")
    exit()

# ====================================================================================
# ✨ NOVO PASSO: Remoção de Linhas Duplicadas
# ====================================================================================
initial_rows = len(df)
# Remove duplicatas baseadas na coluna 'Conteudo_Comentario', mantendo a primeira ocorrência
df.drop_duplicates(subset=['Conteudo_Comentario'], inplace=True)
dropped_rows = initial_rows - len(df)
print(f"Desduplicação concluída: {dropped_rows} linhas duplicadas foram removidas. Total de linhas: {len(df)}")
# ====================================================================================

# 1. Aplica a limpeza robusta para criar uma nova coluna.
# CORREÇÃO: Passamos a REFERÊNCIA da função (clean_text_robust), SEM parênteses.
# O método .apply() irá chamar a função para cada linha.
df['Conteudo_Comentario_Limpo'] = df['Conteudo_Comentario'].astype(str).apply(clean_text_robust)

# 2. Aplica a detecção de idioma na coluna limpa.
# Passamos a REFERÊNCIA da função (get_language_corrected).
df['language'] = df['Conteudo_Comentario_Limpo'].apply(get_language_corrected)

# 3. Agrupa os dados por idioma ('pt', 'en', 'other') e salva cada grupo em um novo arquivo CSV
print(f"\nIniciando a separação do dataset em {df['language'].nunique()} categorias de idioma (pt, en, other/ruído)...")

for lang, group in df.groupby('language'):
    # Cria o diretório de dados se ele não existir
    DIRETORIO_DADOS_LINGUAGENS.mkdir(parents=True, exist_ok=True)
    
    output_filename = DIRETORIO_DADOS_LINGUAGENS / f'dataset_respostas_{lang}.csv'
    
    # Salva o DataFrame do grupo, removendo a coluna temporária 'Conteudo_Comentario_Limpo' antes de salvar
    group.drop(columns=['Conteudo_Comentario_Limpo']).to_csv(output_filename, index=False)
    print(f"Dados da categoria '{lang}' salvos em '{output_filename}'")