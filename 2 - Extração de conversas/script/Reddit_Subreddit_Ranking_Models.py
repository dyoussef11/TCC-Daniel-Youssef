import sys
import json
import praw
from pathlib import Path
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- 1. CONFIGURAÇÕES E CAMINHOS ---
caminho_script = Path(__file__).resolve().parent
caminho_raiz_projeto = caminho_script.parent.parent 
sys.path.append(str(caminho_raiz_projeto))

try:
    from config import DIRETORIO_CSV_DATASET_FINAL, DIRETORIO_DADOS_EXTRACAO_QA
    from modelo_de_busca import ler_e_filtrar_modelos
except ImportError:
    DIRETORIO_CSV_DATASET_FINAL = caminho_script
    DIRETORIO_DADOS_EXTRACAO_QA = caminho_script / 'dados_saida' # Cria pasta local se não existir
    def ler_e_filtrar_modelos(caminho, marca, tipo): return []

CAMINHO_ENTRADA_CSV = DIRETORIO_CSV_DATASET_FINAL / 'dataset_laptops_UNICOS.csv'
ARQUIVO_SAIDA_JSON = DIRETORIO_DADOS_EXTRACAO_QA / 'fontes_detalhadas.json'
ARQUIVO_SAIDA_TXT = DIRETORIO_DADOS_EXTRACAO_QA / 'lista_para_busca.txt'

# --- 2. PARÂMETROS ---
SUBREDDIT_ALVO = "all" # Busca global para descobrir novas fontes
QTD_LIMITE_POSTS = None 

# --- 3. AUTENTICAÇÃO ---
try:
    reddit = praw.Reddit(
        client_id='qgrpjfyUUZNPAp0wCymcdQ',
        client_secret='WshvOFWLM2YV5Rq87GRP-xwCwQoXPA',
        user_agent='ResearchTopic_SourceFinder/1.2'
    )
    print(f"Autenticação: OK (Read-Only: {reddit.read_only})")
except Exception as e:
    print(f"Erro Auth: {e}")
    sys.exit()

# --- 4. FUNÇÕES ---

def contar_volume(modelo):
    """ Busca no r/all e retorna a lista de subreddits onde o modelo aparece. """
    termo = f'"{modelo}"'
    print(f"🔍 Varrendo r/all por: {termo} ...")
    
    try:
        resultados = reddit.subreddit(SUBREDDIT_ALVO).search(
            termo, sort="relevance", limit=QTD_LIMITE_POSTS
        )
        
        lista_subs = [post.subreddit.display_name for post in resultados]
        return modelo, lista_subs
        
    except Exception as e:
        print(f"Erro na busca de '{modelo}': {e}")
        return modelo, []

def salvar_fontes_futuras(dados_agregados, contador_global):
    """
    Salva os resultados em JSON e gera uma string pronta para uso no PRAW.
    """
    DIRETORIO_DADOS_EXTRACAO_QA.mkdir(parents=True, exist_ok=True)

    # 1. Salva o JSON detalhado (Modelo -> Subreddits)
    with open(ARQUIVO_SAIDA_JSON, 'w', encoding='utf-8') as f:
        json.dump(dados_agregados, f, indent=4, ensure_ascii=False)

    # 2. Gera a string de busca otimizada (apenas subs com mais de X menções relevantes)
    # Filtro: pegamos apenas subreddits que apareceram pelo menos 2 vezes no total para evitar lixo
    top_subreddits = [sub for sub, qtd in contador_global.most_common() if qtd >= 1]
    
    # PRAW aceita subreddits separados por "+"
    string_praw = "+".join(top_subreddits)
    
    with open(ARQUIVO_SAIDA_TXT, 'w', encoding='utf-8') as f:
        f.write("=== STRING FORMATADA PARA O SCRIPT DE EXTRACAO ===\n")
        f.write("Copie a linha abaixo e cole em SUBREDDITS_ALVO:\n\n")
        f.write(string_praw)
        f.write("\n\n=== RANKING GERAL DE FONTES DESCOBERTAS ===\n")
        for sub, qtd in contador_global.most_common():
            f.write(f"{sub}: {qtd} posts encontrados\n")

    print(f"\n✅ Resultados salvos em:\n -> {ARQUIVO_SAIDA_JSON}\n -> {ARQUIVO_SAIDA_TXT}")

# --- 5. MAIN ---
def main():
    print("\n=== DESCOBRIDOR DE FONTES (Mapear & Salvar) ===")
    
    opcao = input("1. Usar CSV | 2. Digitar Modelo Manualmente: ").strip()
    lista_modelos = []

    if opcao == '2':
        entrada = input("Digite o modelo (ex: Dell G7 15 7588): ").strip()
        if entrada: lista_modelos = [entrada]
    else:
        try:
            lista_modelos = ler_e_filtrar_modelos(CAMINHO_ENTRADA_CSV, None, 'Gamer')
        except:
            print("Erro ao ler CSV.")
            sys.exit()

    if not lista_modelos: sys.exit()

    # Estruturas para guardar os dados
    dados_para_json = [] 
    contador_global_subs = Counter()

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(contar_volume, modelo): modelo for modelo in lista_modelos}
        
        for future in as_completed(futures):
            modelo, lista_subs = future.result()
            
            if lista_subs:
                # Estatísticas deste modelo específico
                ranking_modelo = Counter(lista_subs).most_common()
                print(f" -> '{modelo}': encontrado em {len(ranking_modelo)} comunidades diferentes.")
                
                # Atualiza as estatísticas globais e o JSON
                contador_global_subs.update(lista_subs)
                dados_para_json.append({
                    "modelo": modelo,
                    "total_posts": len(lista_subs),
                    "top_fontes": dict(ranking_modelo)
                })
            else:
                print(f" -> '{modelo}': Nenhum resultado.")

    # Salva tudo no final
    if dados_para_json:
        salvar_fontes_futuras(dados_para_json, contador_global_subs)
    else:
        print("Nenhum dado encontrado para salvar.")

if __name__ == "__main__":
    main()