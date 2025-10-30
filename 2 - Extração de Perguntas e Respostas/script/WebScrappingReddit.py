import sys
from pathlib import Path
import csv
import pandas as pd # Adicionado para melhor manuseio de CSV, embora não estivesse no original, será útil.
import time # Adicionado para pausas (melhor prática)

# Obtém o caminho absoluto da pasta do script atual.
caminho_script = Path(__file__).resolve().parent

# Acessa a pasta raiz do projeto subindo dois níveis.
caminho_raiz_projeto = caminho_script.parent.parent

# Adiciona o caminho da raiz ao caminho de busca do Python.
sys.path.append(str(caminho_raiz_projeto))

# Agora a importação do módulo 'config' deve funcionar.
# 💡 NOVO: Importa DIRETORIO_CSV_DATASET_FINAL e a função auxiliar para leitura
from config import DIRETORIO_DADOS_WEBSCRAPPING,DIRETORIO_DADOS_EXTRACAO_QA, DIRETORIO_CSV_DATASET_FINAL,DIRETORIO_SCRIPTS_WEBSCRAPPING
from DIRETORIO_SCRIPTS_WEBSCRAPPING.modelo_de_busca import ler_e_filtrar_modelos # Assumindo que esta função existe para ler o CSV

import praw

# --- Configuração de Caminhos e Busca ---
MARCA_ALVO = 'DELL'
caminho_entrada = DIRETORIO_CSV_DATASET_FINAL / 'dataset_laptops.csv'
caminho_saida_perguntas = DIRETORIO_DADOS_EXTRACAO_QA / 'perguntas/reddit_posts_Perguntas.csv'
caminho_saida_respostas = DIRETORIO_DADOS_EXTRACAO_QA /'respostas/reddit_comments_Respostas.csv'

# --- 1. Leitura e Filtro dos Modelos do CSV ---
try:
    modelos_a_buscar = ler_e_filtrar_modelos(caminho_entrada, MARCA_ALVO)
    if not modelos_a_buscar:
        print(f"Não foram encontrados modelos para a marca '{MARCA_ALVO}' no arquivo CSV ou houve um erro na leitura. Saindo.")
        sys.exit()
    print(f"Total de {len(modelos_a_buscar)} modelos '{MARCA_ALVO}' carregados para busca no Reddit.")
except ImportError:
    print("Erro: Certifique-se de que a função 'ler_e_filtrar_modelos' está disponível (em 'modelo_de_busca.py').")
    sys.exit()


# --- Autenticação com as credenciais ---
reddit = praw.Reddit(client_id='qgrpjfyUUZNPAp0wCymcdQ',client_secret='WshvOFWLM2YV5Rq87GRP-xwCwQoXPA',user_agent='ResearchTopic by VividLibrary67')

print(f"Modo somente leitura: {reddit.read_only}")

# Lista para armazenar todos os posts encontrados (armazenando a tupla: (submission, modelo_buscado))
all_submissions_data = []

# --- 2. Loop de Busca: Itera sobre cada modelo ---
for i, modelo_de_busca in enumerate(modelos_a_buscar):
    # Formata o termo de busca para ser mais específico (e.g., "Inspiron 3520")
    termo_de_pesquisa = f'"{modelo_de_busca}"'
    
    print(f"\n[{i+1}/{len(modelos_a_buscar)}] Buscando no Reddit pelo termo: {termo_de_pesquisa}...")
    
    try:
        # 💡 Realiza a busca no subreddit 'all'
        submissions_encontradas = list(reddit.subreddit('all').search(termo_de_pesquisa, sort="relevance", limit=None))
        
        print(f"  -> {len(submissions_encontradas)} posts encontrados para '{modelo_de_busca}'.")

        # Armazena cada post encontrado junto com o modelo que gerou a busca
        for submission in submissions_encontradas:
            all_submissions_data.append((submission, modelo_de_busca))
            
        # Pausa para evitar limites de taxa (Rate Limit) do Reddit/PRAW
        time.sleep(2)
        
    except Exception as e:
        print(f"  -> ERRO ao buscar por '{modelo_de_busca}': {e}. Tentando continuar.")
        time.sleep(10) # Pausa maior após erro
        continue

print(f"\nNúmero TOTAL de posts acumulados: {len(all_submissions_data)}")

# --- 3. Salva as Perguntas (Posts) em um CSV separado ---
print(f"\nSalvando posts em '{caminho_saida_perguntas}'...")
with open(caminho_saida_perguntas, 'w', newline='', encoding='utf-8') as posts_file:
    posts_writer = csv.writer(posts_file)
    posts_writer.writerow(['ID_Post', 'Modelo_Buscado', 'Titulo_Post', 'URL_Post', 'Conteudo_Post', 'Score_Post'])
    
    for submission, modelo_buscado in all_submissions_data:
        posts_writer.writerow([
            submission.id,
            modelo_buscado, # 💡 NOVO: Modelo que gerou a busca
            submission.title,
            submission.url,
            submission.selftext,
            submission.score
        ])

# --- 4. Salva os Comentários em outro CSV separado ---
print(f"Salvando comentários em '{caminho_saida_respostas}'...")
with open(caminho_saida_respostas, 'w', newline='', encoding='utf-8') as comments_file:
    comments_writer = csv.writer(comments_file)
    comments_writer.writerow(['ID_Post', 'Conteudo_Comentario', 'Score_Comentario'])
    
    for submission, _ in all_submissions_data:
        try:
            # Carrega todos os comentários, incluindo os aninhados
            submission.comments.replace_more(limit=None)
        except Exception as e:
            print(f"Aviso: Erro ao carregar comentários do post {submission.id}: {e}")
            continue

        for comment in submission.comments.list():
            # Verifica se o comentário não é uma instância de 'MoreComments' (que já foi substituída)
            if comment.author is not None:
                # 💡 NOVO: Verifica se o corpo existe para evitar erros
                comment_body = comment.body if hasattr(comment, 'body') else "[Corpo não encontrado]"
                comment_data = [
                    submission.id, # ID do post pai para referência
                    comment_body,
                    comment.score
                ]
            else:
                # Lida com comentários removidos/deletados
                comment_data = [
                    submission.id,
                    "[Comentário removido/deletado]",
                    ""
                ]
            
            comments_writer.writerow(comment_data)

print("\nProcesso concluído! Os dados foram separados em dois arquivos CSV.")