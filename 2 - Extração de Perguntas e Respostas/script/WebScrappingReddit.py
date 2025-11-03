import sys
from pathlib import Path
import csv
import pandas as pd
import time
import praw
import os
from concurrent.futures import ThreadPoolExecutor, as_completed 

# --- CONFIGURAÇÃO INICIAL E IMPORTS ---
caminho_script = Path(__file__).resolve().parent
# Presume-se que a estrutura do projeto seja:
# /seu_projeto
#   /nome_do_script.py (caminho_script)
#   /config.py
#   /modelo_de_busca.py
caminho_raiz_projeto = caminho_script.parent.parent 
sys.path.append(str(caminho_raiz_projeto))

try:
    # Ajuste o caminho de importação se 'config.py' estiver em outro lugar
    from config import DIRETORIO_DADOS_WEBSCRAPPING, DIRETORIO_DADOS_EXTRACAO_QA, DIRETORIO_CSV_DATASET_FINAL
    from modelo_de_busca import ler_e_filtrar_modelos
except ImportError as e:
    print(f"Erro de importação de configuração ou módulo: {e}. Verifique se 'config.py' e 'modelo_de_busca.py' estão acessíveis.")
    sys.exit()

# --- VARIÁVEIS DE CONFIGURAÇÃO ---
MARCA_ALVO = None
TIPO_NOTEBOOK = 'Gamer'
caminho_entrada = DIRETORIO_CSV_DATASET_FINAL / 'dataset_laptops_UNICOS.csv'
# Definindo os caminhos de saída
caminho_saida_perguntas = DIRETORIO_DADOS_EXTRACAO_QA / 'perguntas/reddit_posts_Perguntas.csv'
caminho_saida_respostas = DIRETORIO_DADOS_EXTRACAO_QA / 'respostas/reddit_comments_Respostas.csv'

# Variável que rastreará o próximo ID artificial a ser usado
global_post_counter = 1 


def carregar_ultimo_id(caminho_posts):
    """Lê o último ID_Post_Artificial salvo para continuar a contagem."""
    if not caminho_posts.exists() or caminho_posts.stat().st_size == 0:
        return 1
    
    try:
        # Lê o CSV e encontra o valor máximo na coluna 'ID_Post_Artificial'
        df = pd.read_csv(caminho_posts, encoding='utf-8')
        if 'ID_Post_Artificial' in df.columns and not df['ID_Post_Artificial'].empty:
            ultimo_id = df['ID_Post_Artificial'].max()
            return int(ultimo_id) + 1
        else:
            return 1
    except Exception as e:
        print(f"Aviso: Erro ao carregar último ID do CSV ({e}). Iniciando contagem do 1.")
        return 1


def salvar_dados_csv(submissions_data_com_id, caminho_posts, caminho_comments):
    """Salva dados de posts e comentários (Perguntas e Respostas) usando ID artificial (ID_Post_Artificial)."""
    if not submissions_data_com_id:
        print("\nAviso: Lista de posts vazia. Nada para salvar.")
        return False

    print(f"\n[SALVAMENTO AUTOMÁTICO] Iniciando salvamento de {len(submissions_data_com_id)} posts acumulados...")

    caminho_posts.parent.mkdir(parents=True, exist_ok=True)
    caminho_comments.parent.mkdir(parents=True, exist_ok=True)

    total_posts_salvos = 0
    total_comments_salvos = 0

    # --- A. Salva as Perguntas (Posts) ---
    try:
        header_posts = ['ID_Post_Artificial', 'ID_Post_Reddit_Original', 'Modelo_Buscado', 'Titulo_Post', 'URL_Post', 'Conteudo_Post', 'Score_Post']
        arquivo_existe = caminho_posts.exists()

        with open(caminho_posts, 'a', newline='', encoding='utf-8') as posts_file:
            posts_writer = csv.writer(posts_file)

            # Escreve cabeçalho só se o arquivo não existir ou estiver vazio
            if not arquivo_existe or caminho_posts.stat().st_size == 0:
                posts_writer.writerow(header_posts)

            # submission_tuple é (id_artificial, submission_obj, modelo_buscado)
            for id_artificial, submission, modelo_buscado in submissions_data_com_id:
                posts_writer.writerow([
                    id_artificial, submission.id, modelo_buscado, submission.title, submission.url, submission.selftext, submission.score
                ])
                total_posts_salvos += 1
    except Exception as e:
        print(f"ERRO ao salvar posts: {e}")
        return False

    # --- B. Salva os Comentários ---
    try:
        # Usamos o ID_Post_Artificial para correlação
        header_comments = ['ID_Post_Artificial', 'Conteudo_Comentario', 'Score_Comentario', 'ID_Comentario_Reddit_Original']
        arquivo_existe = caminho_comments.exists()

        with open(caminho_comments, 'a', newline='', encoding='utf-8') as comments_file:
            comments_writer = csv.writer(comments_file)

            if not arquivo_existe or caminho_comments.stat().st_size == 0:
                comments_writer.writerow(header_comments)

            for id_artificial, submission, _ in submissions_data_com_id:
                try:
                    submission.comments.replace_more(limit=2)
                except Exception as e:
                    print(f"Aviso: Erro ao carregar comentários do post {submission.id}: {e}. Pulando comentários deste post.")
                    continue

                for comment in submission.comments.list():
                    # Ignorando objetos 'MoreComments'
                    if isinstance(comment, praw.models.MoreComments):
                        continue
                        
                    comment_id_original = getattr(comment, 'id', 'N/A')

                    if comment.author is not None and hasattr(comment, 'body'):
                        comments_writer.writerow([id_artificial, comment.body, comment.score, comment_id_original])
                        total_comments_salvos += 1
                    else:
                        # Para comentários removidos/deletados
                        comments_writer.writerow([id_artificial, "[Comentário removido/deletado]", "", comment_id_original])
    except Exception as e:
        print(f"ERRO ao salvar comentários: {e}")
        return False

    print(f"[SALVAMENTO CONCLUÍDO] +{total_posts_salvos} posts | +{total_comments_salvos} comentários adicionados.")
    return True


# --- 2. LEITURA E AUTENTICAÇÃO ---
try:
    modelos_a_buscar = ler_e_filtrar_modelos(caminho_entrada, MARCA_ALVO, TIPO_NOTEBOOK)
    if not modelos_a_buscar:
        print("Não foram encontrados modelos para busca. Saindo.")
        sys.exit()
    print(f"Total de {len(modelos_a_buscar)} modelos carregados para busca no Reddit.")
except Exception:
    print("Erro: A leitura dos modelos falhou. Verifique o caminho de entrada e 'modelo_de_busca.py'.")
    sys.exit()

# AUTENTICAÇÃO PRAW
try:
    reddit = praw.Reddit(
        client_id='qgrpjfyUUZNPAp0wCymcdQ',
        client_secret='WshvOFWLM2YV5Rq87GRP-xwCwQoXPA',
        user_agent='ResearchTopic by VividLibrary67'
    )
    print(f"Autenticação PRAW bem-sucedida. Modo somente leitura: {reddit.read_only}")
except Exception as e:
    print(f"Erro de autenticação PRAW: {e}")
    sys.exit()

# Inicializa/Retoma o contador global
global_post_counter = carregar_ultimo_id(caminho_saida_perguntas)
print(f"Contador de ID Artificial inicializado/retomado em: {global_post_counter}")

# Lista para acumular os dados com o ID artificial: (id_artificial, submission_obj, modelo_buscado)
all_submissions_data_com_id = []


# --- 3. FUNÇÃO PARA EXECUTAR BUSCA INDIVIDUAL ---
def buscar_modelo(modelo):
    """Executa a busca de posts para um modelo específico."""
    termo = f'"{modelo}"'
    try:
        print(f"\n🔍 Buscando no Reddit pelo termo: {termo}...")
        # Limite reduzido para o exemplo
        submissions = list(reddit.subreddit('laptops').search(termo, sort="relevance", limit=10)) 
        print(f"  -> {len(submissions)} posts encontrados para '{modelo}'.")
        time.sleep(1.5)  # pausa leve
        # Retorna apenas o objeto PRAW e o modelo buscado. O ID artificial é adicionado depois.
        return [(sub, modelo) for sub in submissions]
    except Exception as e:
        print(f"  -> ERRO ao buscar '{modelo}': {e}")
        return []


# --- 4. EXECUÇÃO PRINCIPAL (PARALELIZADA) ---
try:
    print("\n--- Iniciando busca paralelizada com até 3 threads ---")
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(buscar_modelo, modelo) for modelo in modelos_a_buscar]

        for i, future in enumerate(as_completed(futures), start=1):
            resultados_modelo = future.result() # Lista de (submission, modelo_buscado)
            
            # ATRIBUIÇÃO DO ID ARTIFICIAL
            for submission, modelo_buscado in resultados_modelo:
                all_submissions_data_com_id.append((global_post_counter, submission, modelo_buscado))
                global_post_counter += 1 # Incrementa o contador global para o próximo post

            print(f"[{i}/{len(modelos_a_buscar)}] Modelos processados. Total acumulado: {len(all_submissions_data_com_id)} posts.")

            # Salvamento parcial a cada 2 modelos processados
            if i % 2 == 0:
                print(f"\n--- SALVAMENTO PARCIAL (após {i} modelos) ---")
                salvar_dados_csv(all_submissions_data_com_id, caminho_saida_perguntas, caminho_saida_respostas)
                all_submissions_data_com_id.clear() # Limpa a lista após salvar
                time.sleep(3)

    # --- FIM DO LOOP: SALVAMENTO FINAL ---
    print("\n\n[PROCESSO CONCLUÍDO] Salvando dados finais...")
    salvar_dados_csv(all_submissions_data_com_id, caminho_saida_perguntas, caminho_saida_respostas)

except KeyboardInterrupt:
    print("\n\n[INTERRUPÇÃO DETECTADA - Ctrl+C] Salvando dados acumulados...")
    salvar_dados_csv(all_submissions_data_com_id, caminho_saida_perguntas, caminho_saida_respostas)

except Exception as e:
    print(f"\n\n[ERRO CRÍTICO NO PROCESSO] Salvando dados acumulados. Erro: {e}")
    salvar_dados_csv(all_submissions_data_com_id, caminho_saida_perguntas, caminho_saida_respostas)

finally:
    print("\nProcesso encerrado.")