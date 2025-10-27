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

# Agora a importação do módulo 'config' deve funcionar.
from config import DIRETORIO_DADOS_LINGUAGENS, DIRETORIO_DADOS_LABELSTUDIO

import pandas as pd
from langdetect import detect, DetectorFactory

# Garante que a detecção de idioma seja consistente
DetectorFactory.seed = 0

def get_language(text):
    """Detecta o idioma de um texto, retornando 'unknown' se falhar."""
    try:
        return detect(text)
    except:
        return 'unknown'

# Caminho do seu arquivo CSV
caminho_entrada = DIRETORIO_DADOS_LABELSTUDIO / 'dataset-respostas-com-label.csv'

# Carregar o arquivo CSV em um DataFrame
try:
    df = pd.read_csv(caminho_entrada)
except FileNotFoundError:
    print(f"Erro: O arquivo não foi encontrado no caminho especificado: {caminho_entrada}")
    exit()

# Adiciona uma nova coluna 'language' ao DataFrame
# Aplica a função de detecção de idioma à coluna 'Conteudo_Comentario'
df['language'] = df['Conteudo_Comentario'].astype(str).apply(get_language)

# Agrupa os dados por idioma e salva cada grupo em um novo arquivo CSV
for lang, group in df.groupby('language'):
    # CORREÇÃO: Usar um f-string (f'...') para interpolar a variável 'lang'
    # no nome do arquivo antes de combiná-lo com o caminho do diretório.
    output_filename = DIRETORIO_DADOS_LINGUAGENS / f'dataset_respostas_{lang}.csv'
    
    group.to_csv(output_filename, index=False)
    print(f"Dados do idioma '{lang}' salvos em '{output_filename}'")