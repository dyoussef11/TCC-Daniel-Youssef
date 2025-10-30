import sys
from pathlib import Path
import csv
import pandas as pd
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor
import time
from threading import Lock, Event # 💡 NOVO: Event para gerenciar BLOQUEIO
import random

# Obtém o caminho absoluto da pasta do script atual.
caminho_script = Path(__file__).resolve().parent
caminho_raiz_projeto = caminho_script.parent.parent
sys.path.append(str(caminho_raiz_projeto))

from config import DIRETORIO_DADOS_WEBSCRAPPING,DIRETORIO_DADOS_EXTRACAO_QA

# --- SELETORES HTML (CONSTANTES) ---
SELETOR_TITULO = 'h1'
SELETOR_CONTEUDO_POST = 'conversation-balloon__content__text'
SELETOR_COMENTARIOS_LISTA = 'comment-list__comment'
SELETOR_CONTEUDO_COMENTARIO = 'dell-comment-balloon__content'

# --- CONFIGURAÇÃO DE PARALELISMO E CHECKPOINT ---
MAX_WORKERS = 2
TEMPO_ESPERA_SEGUNDOS = 3600 # 60 minutos

# 💡 Caminho do arquivo de progresso (mantido global, pois é uma constante)
ARQUIVO_PROGRESSO = DIRETORIO_DADOS_WEBSCRAPPING / 'progresso_dell_community_ingles.txt'

HEADERS = {
'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
'Accept-Encoding': 'gzip, deflate, br',
'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7'
}

# Listas e Locks (mantidos globais, mas passados indiretamente ou usados com locks)
posts_data = []
comments_data = []
data_lock = Lock()
progress_lock = Lock()

# 🎯 NOVO: Classe para gerenciar o estado compartilhado sem 'global'
class StatusManager:
    def __init__(self, total_links):
        # Usamos uma Lock para proteger 'processados' e 'ignorados'
        self.lock = Lock()
        self.processados = 0
        self.ignorados = 0
        self.total_links = total_links
        # Event é um objeto thread-safe perfeito para flags booleanas
        self.bloqueio_detectado = Event() 

    def incrementar_processados(self):
        with self.lock:
            self.processados += 1
            if self.processados % 100 == 0 or self.processados == self.total_links:
                print(f"Progresso: {self.processados}/{self.total_links} links processados ({self.processados * 100 / self.total_links:.2f}%)")
    
    def incrementar_ignorados(self):
        with self.lock:
            self.ignorados += 1
            
    def set_bloqueio(self):
        self.bloqueio_detectado.set() # Define o estado como True
        
    def is_bloqueado(self):
        return self.bloqueio_detectado.is_set()


# --- FUNÇÕES DE CHECKPOINT (USAM CONSTANTES GLOBAIS, NÃO AS VARIÁVEIS DE ESTADO) ---
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


def extrair_dados_dell_community(url_id_tuple, status_manager: StatusManager):
    """
    Função de extração que recebe a URL e o objeto StatusManager.
    """
    
    # Verifica o estado do bloqueio de forma segura
    if status_manager.is_bloqueado():
        return
        
    url, post_id = url_id_tuple
    
    pausa = random.uniform(3.0, 7.0)
    time.sleep(pausa)
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        # Detecta o bloqueio 403 e sinaliza a interrupção
        if '403 Client Error: Forbidden' in str(e):
            print(f"\n\n🚨🚨 BLOQUEIO DETECTADO! IP PROIBIDO NO LINK [{post_id}]. 🚨🚨")
            status_manager.set_bloqueio() # Define o flag de bloqueio
            return
        
        print(f"[{post_id}] ❌ Erro ao acessar {url}: {e}")
        return

    # --- Extração do Conteúdo ---
    soup = BeautifulSoup(response.content, 'html.parser')
    
    # Extração de Post (Pergunta)
    titulo_elem = soup.find(SELETOR_TITULO)
    page_title = titulo_elem.string.strip() if titulo_elem and titulo_elem.string else "Título não encontrado"
    texto_postagem_elem = soup.find(class_=SELETOR_CONTEUDO_POST)
    post_content = texto_postagem_elem.text.strip() if texto_postagem_elem else "Conteúdo não encontrado"

    with data_lock:
        posts_data.append({"ID_Post": post_id, "Titulo_Post": page_title, "URL_Post": url, "Conteudo_Post": post_content})

    # Extração de Comentários
    all_comments = soup.find_all(class_=SELETOR_COMENTARIOS_LISTA)
    new_comments = []
    for comment in all_comments:
        comment_content_elem = comment.find(class_=SELETOR_CONTEUDO_COMENTARIO)
        comment_content = comment_content_elem.text.strip() if comment_content_elem else "Comentário não encontrado"
        if comment_content and comment_content != "Comentário não encontrado":
            new_comments.append({"ID_Post": post_id, "Conteudo_Comentario": comment_content})

    if new_comments:
        with data_lock:
            comments_data.extend(new_comments)
            
    # Salva o progresso
    salvar_progresso(url)
    
    # Atualiza o progresso e imprime
    status_manager.incrementar_processados()


# --- Código Principal para processar os links do CSV ---
def main():
    start_time = time.time()
    
    caminho_entrada = DIRETORIO_DADOS_WEBSCRAPPING /'links_discussoes_Dell_Ingles.csv'
    caminho_saida_perguntas = DIRETORIO_DADOS_EXTRACAO_QA /'perguntas/posts_DellCommunity_Ingles_Perguntas_BRANDO.csv'
    caminho_saida_respostas = DIRETORIO_DADOS_EXTRACAO_QA /'respostas/comentarios_DellCommunity_Ingles_Respostas_BRANDO.csv'
    nome_coluna_url = 'Link da Discussão'
    
    links_para_processar = []
    
    # 1. Carrega o progresso anterior (para retomar)
    urls_processadas_anteriormente = carregar_progresso()

    try:
        # 2. Carrega e filtra todos os links do CSV
        caminho_saida_perguntas.parent.mkdir(parents=True, exist_ok=True)
        caminho_saida_respostas.parent.mkdir(parents=True, exist_ok=True)
        
        links_totais_no_arquivo = 0
        with open(caminho_entrada, 'r', encoding='utf-8') as infile:
            reader = csv.DictReader(infile)
            if nome_coluna_url not in reader.fieldnames:
                print(f"Erro: O arquivo CSV de entrada deve ter uma coluna chamada '{nome_coluna_url}'.")
                return
            
            for index, row in enumerate(reader):
                url = row[nome_coluna_url].strip()
                links_totais_no_arquivo += 1
                
                # Filtra links já processados (usa o checkpoint)
                if url in urls_processadas_anteriormente:
                    continue # Não precisa de StatusManager aqui, pois é um contador local
                
                if url:
                    links_para_processar.append((url, index))
        
        total_a_processar = len(links_para_processar)
        
        # 🎯 NOVO: Cria a instância do gerenciador de estado
        status_manager = StatusManager(total_a_processar)
        links_ignorados = links_totais_no_arquivo - total_a_processar 
        
        print(f"Links a processar nesta sessão: {total_a_processar}. Links ignorados (já processados): {links_ignorados}.")

        if total_a_processar == 0:
            print("Todos os links já foram processados. Saindo.")
            return

        # 3. Execução Paralela Branda
        print(f"Iniciando extração paralela branda com {MAX_WORKERS} workers...")
        
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            # Submete as tarefas, passando a instância do gerenciador de estado junto com o link
            futures = [executor.submit(extrair_dados_dell_community, link, status_manager) for link in links_para_processar]
            
            # Loop de monitoramento para verificar o flag de BLOQUEIO
            while any(f.running() or not f.done() for f in futures) and not status_manager.is_bloqueado():
                time.sleep(5) # Monitora o status das threads a cada 5 segundos

    except FileNotFoundError:
        print(f"Erro: O arquivo '{caminho_entrada}' não foi encontrado.")
        return
    except Exception as e:
        print(f"Ocorreu um erro durante a execução: {e}")
        return

    # --- 4. AÇÃO DE ESPERA OU SALVAMENTO FINAL ---
    if status_manager.is_bloqueado():
        print(f"\n=======================================================")
        print(f"⚠️ BLOQUEIO CRÍTICO DETECTADO! PARANDO O PROCESSAMENTO. ⚠️")
        print(f"Aguardando {TEMPO_ESPERA_SEGUNDOS / 60:.0f} minutos para a reativação do IP...")
        print(f"O script continuará do último link salvo após a reinicialização.")
        print(f"=======================================================")
        
        # Salva os dados coletados até o momento do bloqueio
        salvar_dados_finais(caminho_saida_perguntas, caminho_saida_respostas)
        
    else:
        # Se não houver bloqueio, salva os dados finais e calcula a duração
        salvar_dados_finais(caminho_saida_perguntas, caminho_saida_respostas)
        end_time = time.time()
        total_duration = end_time - start_time
        print(f"\nProcesso concluído! Duração total da sessão: {total_duration:.2f} segundos.")
        print(f"Taxa: {len(posts_data) / total_duration:.2f} links/segundo.")


def salvar_dados_finais(caminho_saida_perguntas, caminho_saida_respostas):
    """Função auxiliar para salvar os dados em um local centralizado."""
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

if __name__ == "__main__":
    main()