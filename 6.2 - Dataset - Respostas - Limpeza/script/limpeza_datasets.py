import pandas as pd
import re
import nltk
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer, RSLPStemmer
from nltk.tokenize import word_tokenize
import sys
from pathlib import Path

# --- Configurações de Caminhos ---
# Esta lógica assume que o script está em um subdiretório do projeto.
caminho_script = Path(__file__).resolve().parent
caminho_raiz_projeto = caminho_script.parent.parent
sys.path.append(str(caminho_raiz_projeto))

# Tentar importar as variáveis de configuração
try:
    from config import DIRETORIO_DADOS_LIMPEZA, DIRETORIO_DADOS_LINGUAGENS
except ImportError:
    print("ERRO: Módulo 'config' não encontrado. Defina caminhos de fallback.")
    # Fallback para execução, se 'config.py' falhar
    DIRETORIO_DADOS_LIMPEZA = Path('./dados_limpos_saida')
    DIRETORIO_DADOS_LINGUAGENS = Path('.') 

# Certifica-se que o diretório de saída exista
DIRETORIO_DADOS_LIMPEZA.mkdir(parents=True, exist_ok=True)


caminhos_arquivos_entrada = [
    DIRETORIO_DADOS_LINGUAGENS / 'dataset_respostas_en.csv',
    DIRETORIO_DADOS_LINGUAGENS / 'dataset_respostas_pt.csv'
]

caminho_saida = DIRETORIO_DADOS_LIMPEZA


# --- 1. Baixar recursos do NLTK (Execute apenas uma vez no seu ambiente) ---
# Tenta baixar os recursos. Se falhar, as etapas de remoção de stopwords/stemming não funcionarão.
try:
    print("Tentando baixar recursos do NLTK...")
    nltk.download('stopwords', quiet=True)
    nltk.download('rslp', quiet=True)
    nltk.download('wordnet', quiet=True)
    nltk.download('punkt', quiet=True)
except Exception as e:
    print(f"Aviso: Não foi possível baixar todos os recursos do NLTK. Stemming/Stopwords podem falhar. Erro: {e}")

# --- 2. Inicializar Stemmers/Lemmatizers e Stopwords ---
lemmatizer = WordNetLemmatizer()
stemmer_pt = RSLPStemmer()

try:
    stopwords_en = set(stopwords.words('english'))
    stopwords_pt = set(stopwords.words('portuguese'))
except LookupError:
    # Fallback caso stopwords não tenham sido baixadas
    stopwords_en = set()
    stopwords_pt = set()
    print("Aviso: Stopwords não carregadas. A remoção de stopwords será ignorada.")


# --- 3. Dicionário de Gírias (Exemplo para Português) ---
girias_map = {
    'mt': 'muito',
    'pra': 'para',
    'vc': 'você',
    'dmais': 'demais',
    'fds': 'fim de semana'
}

# --- 4. Função Principal de Pré-Processamento ---
def preprocess_text(text, language):
    """
    Realiza Limpeza, Normalização, Padronização (Gírias),
    Remoção de Stopwords e Lematização/Stemming.
    """
    text = str(text)

    # 1. Padronização de Gírias
    tokens = text.lower().split()
    tokens_padronizados = [girias_map.get(token, token) for token in tokens]
    text = ' '.join(tokens_padronizados)

    # 2. Normalização Básica (Minúsculas, Remoção de URLs, Formatos de Citação)
    text = text.lower()
    text = re.sub(r'http\S+|www\S+|https\S+', '', text, flags=re.MULTILINE)
    text = re.sub(r'[\r\n\t]+', ' ', text)
    text = re.sub(r'svr-artur disse: \s*t', ' ', text) 

    # 3. Limpeza (Pontuação, Números, Caracteres Especiais)
    text = re.sub(r'[^a-záéíóúçãõâêîôû\s]', ' ', text)
    
    # 4. Normalização de Espaços
    text = re.sub(r'\s+', ' ', text).strip()
    
    if not text:
        return ""

    # 5. Tokenização (com fallback)
    try:
        tokens = word_tokenize(text, language='portuguese' if language == 'pt' else 'english')
    except LookupError:
        tokens = text.split()
    
    # 6. Remoção de Stopwords e Redução (Stemming/Lematização)
    if language == 'pt':
        stop_words = stopwords_pt
        processed_tokens = [stemmer_pt.stem(word) for word in tokens if word not in stop_words and len(word) > 1]
    elif language == 'en':
        stop_words = stopwords_en
        processed_tokens = [lemmatizer.lemmatize(word) for word in tokens if word not in stop_words and len(word) > 1]
    else:
        processed_tokens = [word for word in tokens if len(word) > 1] # Fallback para tokens sem stopword
    
    # 7. Reconstruir o texto
    return ' '.join(processed_tokens)

print("Funções de pré-processamento carregadas com sucesso.")

# --- 5. Lógica de Processamento e Saída ---

def processar_datasets_e_salvar():
    """
    Carrega os datasets por idioma, aplica a limpeza/normalização/lematização e salva.
    """
    for arquivo_path in caminhos_arquivos_entrada:
        try:
            print(f"\nIniciando processamento de: {arquivo_path.name}")
            
            # Carregar o DataFrame
            df = pd.read_csv(arquivo_path)
            
            # Determinar a linguagem
            # O nome do arquivo é 'dataset_respostas_XX.csv', onde XX é 'en' ou 'pt'
            language_code = arquivo_path.stem.split('_')[-1]
            
            # Aplicar o pré-processamento na coluna 'Conteudo_Comentario'
            df['Conteudo_Processado'] = df['Conteudo_Comentario'].apply(
                lambda x: preprocess_text(x, language=language_code)
            )

            # !!! MODIFICAÇÃO CHAVE AQUI !!!
            # Seleciona apenas as colunas 'Conteudo_Processado' e 'sentiment'
            df_saida = df[['Conteudo_Processado', 'sentiment']] 
            
            # Criar o nome do arquivo de saída e o caminho completo
            nome_saida = f"{arquivo_path.stem}_limpo.csv"
            caminho_final_saida = caminho_saida / nome_saida
            
            # Salvar o Resultado Final (usando o df_saida filtrado)
            df_saida.to_csv(caminho_final_saida, index=False)
            
            print(f"SUCESSO: Processamento de '{language_code.upper()}' concluído.")
            print(f"Arquivo salvo em: {caminho_final_saida}")
            
            # Amostra para verificação
            print("\n--- Amostra do Conteúdo Processado ---")
            # Usar df_saida para a amostra para refletir o arquivo salvo
            print(df_saida.head())

        except FileNotFoundError:
            print(f"ERRO: Arquivo de entrada não encontrado: {arquivo_path.name}. Verifique o DIRETIO_DADOS_LINGUAGENS.")
        except Exception as e:
            print(f"ERRO INESPERADO durante o processamento de {arquivo_path.name}: {e}")

# Executa a função principal para iniciar o pipeline
if __name__ == "__main__":
    processar_datasets_e_salvar()