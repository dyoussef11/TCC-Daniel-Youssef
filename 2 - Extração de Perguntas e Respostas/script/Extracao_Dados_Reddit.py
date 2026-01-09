import sys
import json
import time
import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter # <--- NOVO: Import necessário para contagem
import praw

# --- 1. CONFIGURAÇÕES E CAMINHOS ---
caminho_script = Path(__file__).resolve().parent
caminho_raiz_projeto = caminho_script.parent.parent 
sys.path.append(str(caminho_raiz_projeto))

try:
    from config import DIRETORIO_CSV_DATASET_FINAL, DIRETORIO_DADOS_EXTRACAO_QA
    from modelo_de_busca import ler_e_filtrar_modelos
except ImportError:
    print("Aviso: Módulos de configuração não encontrados. Usando caminhos locais.")
    DIRETORIO_CSV_DATASET_FINAL = caminho_script / 'dados_entrada'
    DIRETORIO_DADOS_EXTRACAO_QA = caminho_script / 'dados_saida'
    def ler_e_filtrar_modelos(caminho, marca, tipo): return []

CAMINHO_ENTRADA_CSV = DIRETORIO_CSV_DATASET_FINAL / 'dataset_laptops_UNICOS.csv'
CAMINHO_SAIDA_JSON = DIRETORIO_DADOS_EXTRACAO_QA / 'reddit_dados_estruturados_modelo.json'

# --- 2. PARÂMETROS DE BUSCA ---
QTD_LIMITE_POSTS = 100 # Aumentei um pouco para o ranking ficar mais interessante
SUBREDDITS_ALVO = "all"

# --- 3. AUTENTICAÇÃO PRAW ---
try:
    reddit = praw.Reddit(
        client_id='qgrpjfyUUZNPAp0wCymcdQ',
        client_secret='WshvOFWLM2YV5Rq87GRP-xwCwQoXPA',
        user_agent='ResearchTopic_TCC_Script/1.2' # Atualizei versão
    )
    print(f"Autenticação PRAW: OK (Read-Only: {reddit.read_only})")
except Exception as e:
    print(f"Erro Crítico de Autenticação: {e}")
    sys.exit()

# --- 4. FUNÇÕES UTILITÁRIAS ---

def unix_to_iso(timestamp):
    if not timestamp: return None
    return datetime.datetime.fromtimestamp(timestamp).isoformat()

def carregar_json_existente(caminho):
    if caminho.exists() and caminho.stat().st_size > 0:
        try:
            with open(caminho, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            return []
    return []

# --- NOVA FUNÇÃO DE RANKING ---
def exibir_ranking_subreddits(resultados_brutos, modelo):
    """
    Recebe uma lista de tuplas (submission, modelo) e imprime
    quais subreddits tiveram mais hits.
    """
    if not resultados_brutos:
        return

    # Extrai o nome do subreddit de cada objeto submission
    # .display_name pega o nome "bonito" (ex: "GamingLaptops")
    lista_subs = [post.subreddit.display_name for post, _ in resultados_brutos]
    
    ranking = Counter(lista_subs).most_common()

    print(f"\n📊 RANKING DE FONTES PARA: '{modelo}'")
    print(f"{'Subreddit':<25} | {'Posts':<5}")
    print("-" * 35)
    
    for sub, qtd in ranking:
        print(f"r/{sub:<23} | {qtd:<5}")
    print("-" * 35 + "\n")

def processar_submission(submission):
    """
    Constrói o dicionário do post e seus comentários.
    """
    autor_post = "[Usuário Deletado]"
    try:
        if submission.author:
            autor_post = submission.author.name
    except:
        pass

    # -- Camada 3: Comentários --
    lista_comentarios = []
    try:
        submission.comments.replace_more(limit=1) 
        for comment in submission.comments.list():
            autor_comentario = "[Deletado]"
            if hasattr(comment, 'author') and comment.author:
                autor_comentario = comment.author.name
                
            if hasattr(comment, 'body'):
                lista_comentarios.append({
                    "id_comentario": comment.id,
                    "autor_comentario": autor_comentario,
                    "conteudo": comment.body,
                    "score": comment.score,
                    "data_publicacao": unix_to_iso(comment.created_utc)
                })
    except Exception as e:
        print(f" [!] Erro ao ler comentários: {e}")

    # -- Camada 2: O Post --
    return {
        "id_post": submission.id,
        "subreddit": submission.subreddit.display_name, # <--- NOVO: Guardar no JSON também é útil
        "autor_post": autor_post,
        "titulo": submission.title,
        "url_original": submission.url,
        "conteudo_texto": submission.selftext,
        "score": submission.score,
        "proporcao_upvote": submission.upvote_ratio,
        "data_publicacao": unix_to_iso(submission.created_utc),
        "total_comentarios": submission.num_comments,
        "comentarios": lista_comentarios 
    }

def salvar_dados_json(buffer_dados, caminho_arquivo):
    if not buffer_dados: return

    print(f"\n[IO] Salvando {len(buffer_dados)} posts no JSON...")
    caminho_arquivo.parent.mkdir(parents=True, exist_ok=True)
    
    dados_existentes = carregar_json_existente(caminho_arquivo)
    
    novos_mapa = {}
    for sub, modelo in buffer_dados:
        if modelo not in novos_mapa: novos_mapa[modelo] = []
        novos_mapa[modelo].append(processar_submission(sub))

    data_atual = datetime.datetime.now().isoformat()

    for modelo, posts_estruturados in novos_mapa.items():
        encontrado = False
        for entry in dados_existentes:
            if entry.get("meta_data", {}).get("termo_pesquisado") == modelo:
                entry["posts"].extend(posts_estruturados)
                encontrado = True
                break
        
        if not encontrado:
            dados_existentes.append({
                "meta_data": {
                    "fonte": "Reddit",
                    "subreddits": SUBREDDITS_ALVO,
                    "data_extracao": data_atual,
                    "termo_pesquisado": modelo
                },
                "posts": posts_estruturados
            })

    try:
        with open(caminho_arquivo, 'w', encoding='utf-8') as f:
            json.dump(dados_existentes, f, ensure_ascii=False, indent=4)
        print(" -> JSON atualizado.")
    except Exception as e:
        print(f" [X] Erro IO: {e}")

# --- 5. BUSCA ---
def buscar_modelo(modelo):
    termo = f'"{modelo}"'
    try:
        print(f"🔍 Pesquisando: {termo}...")
        referencia = reddit.subreddit(SUBREDDITS_ALVO).search(
            termo, sort="relevance", limit=QTD_LIMITE_POSTS
        )
        res = list(referencia)
        print(f"   -> {len(res)} posts encontrados.")
        return [(sub, modelo) for sub in res]
    except Exception as e:
        print(f"   -> Erro busca: {e}")
        return []

# --- 6. MAIN ---
def main():
    print("\n=== EXTRATOR REDDIT COM RANKING ===")
    opcao = input("1. CSV | 2. Manual: ").strip()
    lista = []

    if opcao == '2':
        entrada = input("Hardware (ex: Dell G7 15 7588): ").strip()
        if entrada: lista = [entrada]
    else:
        try:
            lista = ler_e_filtrar_modelos(CAMINHO_ENTRADA_CSV, None, 'Gamer')
        except:
            print("Erro CSV.")
            sys.exit()

    if not lista: sys.exit()

    buffer = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(buscar_modelo, m) for m in lista]
        
        for i, f in enumerate(as_completed(futures), 1):
            resultado_thread = f.result() # Pega o resultado dessa thread específica
            
            # --- NOVO: Lógica de Ranking ---
            if resultado_thread:
                # O resultado é uma lista de tuplas [(post, 'modelo'), (post, 'modelo')...]
                # Pegamos o nome do modelo do primeiro item
                modelo_atual = resultado_thread[0][1]
                exibir_ranking_subreddits(resultado_thread, modelo_atual)
            
            buffer.extend(resultado_thread)
            
            # Salva periodicamente a cada 2 modelos processados
            if i % 2 == 0:
                salvar_dados_json(buffer, CAMINHO_SAIDA_JSON)
                buffer.clear()

    salvar_dados_json(buffer, CAMINHO_SAIDA_JSON)
    print("\nConcluído.")

if __name__ == "__main__":
    main()