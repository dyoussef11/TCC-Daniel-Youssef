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


import praw
import csv

# --- Autenticação com as credenciais ---
# Use variáveis de ambiente ou um arquivo de configuração para credenciais em produção.
reddit = praw.Reddit(client_id='qgrpjfyUUZNPAp0wCymcdQ',
                     client_secret='WshvOFWLM2YV5Rq87GRP-xwCwQoXPA',
                     user_agent='ResearchTopic by VividLibrary67')

print(f"Modo somente leitura: {reddit.read_only}")

# --- Definições ---
termo_de_pesquisa = '"g7 15 7588"'
caminho_saida_perguntas = DIRETORIO_DADOS_EXTRACAO_QA / 'perguntas/reddit_posts_Perguntas.csv'
caminho_saida_respostas = DIRETORIO_DADOS_EXTRACAO_QA /'respostas/reddit_comments_Respostas.csv'

# Lista para armazenar todos os posts encontrados
all_submissions = []
print(f"Buscando posts com o termo '{termo_de_pesquisa}'...")

# Realiza a busca. PRAW busca todos os posts possíveis
for submission in reddit.subreddit('all').search(termo_de_pesquisa, sort="relevance"):
    all_submissions.append(submission)

print(f"Número total de posts encontrados: {len(all_submissions)}")

# --- Salva as Perguntas (Posts) em um CSV separado ---
print(f"\nSalvando posts em '{caminho_saida_perguntas}'...")
with open(caminho_saida_perguntas, 'w', newline='', encoding='utf-8') as posts_file:
    posts_writer = csv.writer(posts_file)
    posts_writer.writerow(['ID_Post', 'Titulo_Post', 'URL_Post', 'Conteudo_Post', 'Score_Post'])
    
    for submission in all_submissions:
        posts_writer.writerow([
            submission.id,
            submission.title,
            submission.url,
            submission.selftext,
            submission.score
        ])

# --- Salva os Comentários em outro CSV separado ---
print(f"Salvando comentários em '{caminho_saida_respostas}'...")
with open(caminho_saida_respostas, 'w', newline='', encoding='utf-8') as comments_file:
    comments_writer = csv.writer(comments_file)
    comments_writer.writerow(['ID_Post', 'Conteudo_Comentario', 'Score_Comentario'])
    
    for submission in all_submissions:
        # Carrega todos os comentários, incluindo os aninhados
        submission.comments.replace_more(limit=None)
        
        for comment in submission.comments.list():
            if comment.author is not None:
                comment_data = [
                
                    submission.id,  # ID do post pai para referência
                    comment.body,
                    comment.score
                ]
            else:
                comment_data = [
                    submission.id,
                    "[Removido]",
                    "[Comentário removido]",
                    ""
                ]
            
            comments_writer.writerow(comment_data)

print("\nProcesso concluído! Os dados foram separados em dois arquivos CSV.")