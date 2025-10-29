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
from config import DIRETORIO_DADOS_WEBSCRAPPING,DIRETORIO_DADOS_EXTRACAO_QA


import requests
from bs4 import BeautifulSoup
import csv
import pandas as pd
from urllib.parse import urlparse

# Listas para armazenar dados de posts e comentários
posts_data = []
comments_data = []

def extrair_dados_dell_community(url, post_id):
    """
    Extrai informações de uma página da Dell Community
    e popula as listas de posts e comentários.
    """
    try:
        response = requests.get(url, timeout=10)
        # Lança um erro para códigos de status HTTP ruins (ex: 404 Not Found)
        response.raise_for_status() 
    except requests.exceptions.RequestException as e:
        print(f"Erro ao acessar {url}: {e}")
        return

    soup = BeautifulSoup(response.content, 'html.parser')

    # --- Extração da Pergunta (Post Original) ---
    titulo_elem = soup.h1
    page_title = titulo_elem.string.strip() if titulo_elem else "Título não encontrado"

    texto_postagem_elem = soup.find(class_='conversation-balloon__content__text')
    post_content = texto_postagem_elem.text.strip() if texto_postagem_elem else "Conteúdo não encontrado"

    posts_data.append({
        "ID_Post": post_id,
        "Titulo_Post": page_title,
        "URL_Post": url,
        "Conteudo_Post": post_content
    })

    # --- Extração das Respostas (Comentários) ---
    # Encontra todos os elementos que representam uma resposta
    all_comments = soup.find_all(class_='comment-list__comment')

    for comment in all_comments:
        comment_content_elem = comment.find(class_="dell-comment-balloon__content")
        comment_content = comment_content_elem.text.strip() if comment_content_elem else "Comentário não encontrado"
        
        # Adiciona o comentário à lista, garantindo que não seja vazio
        if comment_content and comment_content != "Comentário não encontrado":
            comments_data.append({
                "ID_Post": post_id,
                "Conteudo_Comentario": comment_content
            })

# --- Código Principal para processar os links do CSV ---
caminho_entrada = DIRETORIO_DADOS_WEBSCRAPPING /'links_discussoes_Dell_Brasil.csv'
caminho_saida_perguntas = DIRETORIO_DADOS_EXTRACAO_QA / 'perguntas/posts_DellCommunity_Brasil_Perguntas.csv'
caminho_saida_respostas = DIRETORIO_DADOS_EXTRACAO_QA / 'respostas/comentarios_DellCommunity_Brasil_Respostas.csv'

try:
    with open(caminho_entrada, 'r', encoding='utf-8') as infile:
        reader = csv.DictReader(infile)
        if 'URL' not in reader.fieldnames:
            print("Erro: O arquivo CSV de entrada deve ter uma coluna chamada 'URL'.")
        else:
            for index, row in enumerate(reader):
                url = row['URL'].strip()
                if url:
                    print(f"Processando link {index + 1}: {url}")
                    extrair_dados_dell_community(url, index)

except FileNotFoundError:
    print(f"Erro: O arquivo '{caminho_entrada}' não foi encontrado.")

# --- Salvamento dos Dados em arquivos CSV ---
if posts_data:
    df_posts = pd.DataFrame(posts_data)
    df_posts.to_csv(caminho_saida_perguntas, index=False, encoding='utf-8')
    print(f"\nDados de posts salvos em '{caminho_saida_perguntas}'.")
else:
    print("\nNenhum dado de post foi extraído.")

if comments_data:
    df_comments = pd.DataFrame(comments_data)
    df_comments.to_csv(caminho_saida_respostas, index=False, encoding='utf-8')
    print(f"Dados de comentários salvos em '{caminho_saida_respostas}'.")
else:
    print("Nenhum dado de comentário foi extraído.")

print("\nProcesso concluído!")