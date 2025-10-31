import sys
from pathlib import Path
import csv
import pandas as pd
import time
import praw
import os
from concurrent.futures import ThreadPoolExecutor, as_completed  # <<< Adicionado para paralelização

# --- CONFIGURAÇÃO INICIAL E IMPORTS ---
caminho_script = Path(__file__).resolve().parent
caminho_raiz_projeto = caminho_script.parent.parent
sys.path.append(str(caminho_raiz_projeto))

try:
    from config import DIRETORIO_DADOS_WEBSCRAPPING, DIRETORIO_DADOS_EXTRACAO_QA, DIRETORIO_CSV_DATASET_FINAL
    from modelo_de_busca import ler_e_filtrar_modelos
except ImportError as e:
    print(f"Erro de importação de configuração ou módulo: {e}. Verifique se 'config.py' e 'modelo_de_busca.py' estão acessíveis.")
    sys.exit()

# --- VARIÁVEIS DE CONFIGURAÇÃO ---
MARCA_ALVO = None
TIPO_NOTEBOOK = 'Gamer'
caminho_entrada = DIRETORIO_CSV_DATASET_FINAL / 'dataset_laptops_UNICOS.csv'
caminho_saida_perguntas = DIRETORIO_DADOS_EXTRACAO_QA / 'perguntas/reddit_posts_Perguntas.csv'
caminho_saida_respostas = DIRETORIO_DADOS_EXTRACAO_QA / 'respostas/reddit_comments_Respostas.csv'


def salvar_dados_csv(submissions_data, caminho_posts, caminho_comments):
    """Salva dados de posts e comentários (Perguntas e Respostas) de forma incremental (append)."""
    if not submissions_data:
        print("\nAviso: Lista de posts vazia. Nada para salvar.")
        return False

    print(f"\n[SALVAMENTO AUTOMÁTICO] Iniciando salvamento de {len(submissions_data)} posts acumulados...")

    caminho_posts.parent.mkdir(parents=True, exist_ok=True)
    caminho_comments.parent.mkdir(parents=True, exist_ok=True)

    total_posts_salvos = 0
    total_comments_salvos = 0

    # --- A. Salva as Perguntas (Posts) ---
    try:
        header_posts = ['ID_Post', 'Modelo_Buscado', 'Titulo_Post', 'URL_Post', 'Conteudo_Post', 'Score_Post']
        arquivo_existe = caminho_posts.exists()

        with open(caminho_posts, 'a', newline='', encoding='utf-8') as posts_file:
            posts_writer = csv.writer(posts_file)

            # Escreve cabeçalho só se o arquivo não existir ou estiver vazio
            if not arquivo_existe or caminho_posts.stat().st_size == 0:
                posts_writer.writerow(header_posts)

            for submission, modelo_buscado in submissions_data:
                posts_writer.writerow([
                    submission.id, modelo_buscado, submission.title, submission.url, submission.selftext, submission.score
                ])
                total_posts_salvos += 1
    except Exception as e:
        print(f"ERRO ao salvar posts: {e}")
        return False

    # --- B. Salva os Comentários ---
    try:
        header_comments = ['ID_Post', 'Conteudo_Comentario', 'Score_Comentario']
        arquivo_existe = caminho_comments.exists()

        with open(caminho_comments, 'a', newline='', encoding='utf-8') as comments_file:
            comments_writer = csv.writer(comments_file)

            if not arquivo_existe or caminho_comments.stat().st_size == 0:
                comments_writer.writerow(header_comments)

            for submission, _ in submissions_data:
                try:
                    submission.comments.replace_more(limit=2)
                except Exception as e:
                    print(f"Aviso: Erro ao carregar comentários do post {submission.id}: {e}. Pulando comentários deste post.")
                    continue

                for comment in submission.comments.list():
                    if comment.author is not None and hasattr(comment, 'body'):
                        comments_writer.writerow([submission.id, comment.body, comment.score])
                        total_comments_salvos += 1
                    else:
                        comments_writer.writerow([submission.id, "[Comentário removido/deletado]", ""])
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

# Autenticação PRAW
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

all_submissions_data = []


# --- 3. FUNÇÃO PARA EXECUTAR BUSCA INDIVIDUAL ---
def buscar_modelo(modelo):
    """Executa a busca de posts para um modelo específico."""
    termo = f'"{modelo}"'
    try:
        print(f"\n🔍 Buscando no Reddit pelo termo: {termo}...")
        submissions = list(reddit.subreddit('laptops').search(termo, sort="relevance", limit=10))
        print(f"  -> {len(submissions)} posts encontrados para '{modelo}'.")
        time.sleep(1.5)  # pausa leve para não saturar a API
        return [(sub, modelo) for sub in submissions]
    except Exception as e:
        print(f"  -> ERRO ao buscar '{modelo}': {e}")
        return []


# --- 4. EXECUÇÃO PRINCIPAL (PARALELIZADA) ---
try:
    print("\n--- Iniciando busca paralelizada com até 3 threads ---")
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(buscar_modelo, modelo) for modelo in modelos_a_buscar]

        for i, future in enumerate(as_completed(futures), start=1):
            resultado = future.result()
            all_submissions_data.extend(resultado)

            print(f"[{i}/{len(modelos_a_buscar)}] Modelos processados. Total acumulado: {len(all_submissions_data)} posts.")

            # Salvamento parcial a cada 2 modelos processados
            if i % 2 == 0:
                print(f"\n--- SALVAMENTO PARCIAL (após {i} modelos) ---")
                salvar_dados_csv(all_submissions_data, caminho_saida_perguntas, caminho_saida_respostas)
                all_submissions_data.clear()
                time.sleep(3)

    # --- FIM DO LOOP: SALVAMENTO FINAL ---
    print("\n\n[PROCESSO CONCLUÍDO] Salvando dados finais...")
    salvar_dados_csv(all_submissions_data, caminho_saida_perguntas, caminho_saida_respostas)

except KeyboardInterrupt:
    print("\n\n[INTERRUPÇÃO DETECTADA - Ctrl+C] Salvando dados acumulados...")
    salvar_dados_csv(all_submissions_data, caminho_saida_perguntas, caminho_saida_respostas)

except Exception as e:
    print(f"\n\n[ERRO CRÍTICO NO PROCESSO] Salvando dados acumulados. Erro: {e}")
    salvar_dados_csv(all_submissions_data, caminho_saida_perguntas, caminho_saida_respostas)

finally:
    print("\nProcesso encerrado.")
