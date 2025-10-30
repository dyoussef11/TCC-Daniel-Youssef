import sys
from pathlib import Path
import csv
import pandas as pd
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor
import time
from threading import Lock
import random # 💡 NOVO: Para pausas aleatórias
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

# --- SELETORES HTML (CONSTANTES) ---
# Seletores para extração de dados da Dell Community
SELETOR_TITULO = 'h1'
SELETOR_CONTEUDO_POST = 'conversation-balloon__content__text'
SELETOR_COMENTARIOS_LISTA = 'comment-list__comment'
SELETOR_CONTEUDO_COMENTARIO = 'dell-comment-balloon__content'


# --- CONFIGURAÇÃO DE CHECKPOINT ---
ARQUIVO_PROGRESSO = DIRETORIO_DADOS_WEBSCRAPPING / 'progresso_dell_community.txt'
MAX_WORKERS = 5 # Mantido em 5 workers.

# 💡 HEADERS para simular um navegador
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
    'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
    'Accept-Encoding': 'gzip, deflate, br',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7'
}

# Listas para armazenar dados de posts e comentários
posts_data = []
comments_data = []

# Variáveis globais para rastreamento de progresso
LINKS_PROCESSADOS = 0
TOTAL_LINKS = 0
LINKS_IGNORADOS = 0 

# Para garantir que a escrita nas listas e no arquivo de progresso seja segura (thread-safe)
data_lock = Lock()
progress_lock = Lock()


def carregar_progresso():
    """Tenta carregar os links já processados do arquivo de progresso."""
    urls_processadas = set()
    if ARQUIVO_PROGRESSO.exists():
        with open(ARQUIVO_PROGRESSO, 'r', encoding='utf-8') as f:
            for line in f:
                urls_processadas.add(line.strip())
        print(f"Progresso encontrado. {len(urls_processadas)} links já foram processados.")
    return urls_processadas

def salvar_progresso(url):
    """Salva um URL no arquivo de progresso de forma segura."""
    with progress_lock:
        with open(ARQUIVO_PROGRESSO, 'a', encoding='utf-8') as f:
            f.write(url + '\n')


def extrair_dados_dell_community(url, post_id):
    global LINKS_PROCESSADOS, LINKS_IGNORADOS
    
    # 🎯 ALTERADO: Pausa aleatória aumentada para 1.0s a 3.0s
    pausa = random.uniform(1.0, 3.0) 
    time.sleep(pausa)
    
    try:
        # Inclui o cabeçalho User-Agent
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status() 
    except requests.exceptions.RequestException as e:
        # Erro 403 ou qualquer outro erro de rede
        print(f"[{post_id}] ❌ Erro ao acessar {url}: {e}")
        return

    soup = BeautifulSoup(response.content, 'html.parser')

    # --- Extração e Escrita Segura (Posts) ---
    titulo_elem = soup.find(SELETOR_TITULO)
    page_title = titulo_elem.string.strip() if titulo_elem and titulo_elem.string else "Título não encontrado"

    texto_postagem_elem = soup.find(class_=SELETOR_CONTEUDO_POST)
    post_content = texto_postagem_elem.text.strip() if texto_postagem_elem else "Conteúdo não encontrado"

    with data_lock:
        posts_data.append({
            "ID_Post": post_id,
            "Titulo_Post": page_title,
            "URL_Post": url,
            "Conteudo_Post": post_content
        })

    # --- Extração e Escrita Segura (Comentários) ---
    all_comments = soup.find_all(class_=SELETOR_COMENTARIOS_LISTA)
    new_comments = []
    for comment in all_comments:
        comment_content_elem = comment.find(class_=SELETOR_CONTEUDO_COMENTARIO)
        comment_content = comment_content_elem.text.strip() if comment_content_elem else "Comentário não encontrado"
        
        if comment_content and comment_content != "Comentário não encontrado":
            new_comments.append({
                "ID_Post": post_id,
                "Conteudo_Comentario": comment_content
            })
            
    if new_comments:
        with data_lock:
            comments_data.extend(new_comments)
            
    # Salva o progresso imediatamente após a extração bem-sucedida
    salvar_progresso(url)
    
    # Atualiza o progresso e imprime
    with data_lock:
        LINKS_PROCESSADOS += 1
        # Imprime o progresso a cada 100 links
        if LINKS_PROCESSADOS % 100 == 0 or LINKS_PROCESSADOS == TOTAL_LINKS:
            print(f"Progresso: {LINKS_PROCESSADOS}/{TOTAL_LINKS} links processados ({LINKS_PROCESSADOS * 100 / TOTAL_LINKS:.2f}%)")


# --- Código Principal para processar os links do CSV ---
def main():
    global TOTAL_LINKS, LINKS_PROCESSADOS, LINKS_IGNORADOS
    
    start_time = time.time()
    
    caminho_entrada = DIRETORIO_DADOS_WEBSCRAPPING /'links_discussoes_Dell_Brasil.csv'
    caminho_saida_perguntas = DIRETORIO_DADOS_EXTRACAO_QA / 'perguntas/posts_DellCommunity_Brasil_Perguntas.csv'
    caminho_saida_respostas = DIRETORIO_DADOS_EXTRACAO_QA / 'respostas/comentarios_DellCommunity_Brasil_Respostas.csv'
    nome_coluna_url= 'Link da Discussão'
    
    links_para_processar = []
    
    # 1. Carrega o progresso anterior
    urls_processadas_anteriormente = carregar_progresso()

    try:
        # 2. Carrega e filtra todos os links do CSV
        with open(caminho_entrada, 'r', encoding='utf-8') as infile:
            reader = csv.DictReader(infile)
            if nome_coluna_url not in reader.fieldnames:
                print(f"Erro: O arquivo CSV de entrada deve ter uma coluna chamada '{nome_coluna_url}'.")
                return
            
            for index, row in enumerate(reader):
                url = row[nome_coluna_url].strip()
                
                # Filtra links já processados
                if url in urls_processadas_anteriormente:
                    LINKS_IGNORADOS += 1
                    continue
                
                if url:
                    links_para_processar.append((url, index)) # Salva (URL, ID)
        
        TOTAL_LINKS = len(links_para_processar)
        print(f"Links a processar nesta sessão: {TOTAL_LINKS}. Links ignorados (já processados): {LINKS_IGNORADOS}.")

        if TOTAL_LINKS == 0:
            print("Todos os links já foram processados. Saindo.")
            return

        # 3. Execução Paralela com ThreadPoolExecutor
        print(f"Iniciando extração paralela com {MAX_WORKERS} workers...")
        
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            executor.map(lambda p: extrair_dados_dell_community(p[0], p[1]), links_para_processar)

    except FileNotFoundError:
        print(f"Erro: O arquivo '{caminho_entrada}' não foi encontrado.")
        return
    except Exception as e:
        print(f"Ocorreu um erro durante a execução paralela: {e}")
        return

    # 4. Salvamento dos Dados Finais em arquivos CSV
    print("\n--- Salvamento dos Dados Finais em arquivos CSV ---")
    
    caminho_saida_perguntas.parent.mkdir(parents=True, exist_ok=True)
    caminho_saida_respostas.parent.mkdir(parents=True, exist_ok=True)
    
    if posts_data:
        df_posts = pd.DataFrame(posts_data)
        df_posts.to_csv(caminho_saida_perguntas, index=False, encoding='utf-8')
        print(f"Dados de posts salvos em '{caminho_saida_perguntas}'. Total: {len(df_posts)}")
    else:
        print("Nenhum dado de post foi extraído.")

    if comments_data:
        df_comments = pd.DataFrame(comments_data)
        df_comments.to_csv(caminho_saida_respostas, index=False, encoding='utf-8')
        print(f"Dados de comentários salvos em '{caminho_saida_respostas}'. Total: {len(df_comments)}")
    else:
        print("Nenhum dado de comentário foi extraído.")

    end_time = time.time()
    total_duration = end_time - start_time
    print(f"\nProcesso concluído! Duração total da sessão: {total_duration:.2f} segundos.")
    print(f"Taxa: {LINKS_PROCESSADOS / total_duration:.2f} links/segundo.")


if __name__ == "__main__":
    main()