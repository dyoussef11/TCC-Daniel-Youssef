import sys
from pathlib import Path
import csv
import pandas as pd
from bs4 import BeautifulSoup
import time
from threading import Lock, Event 
import random
import traceback 

# [IMPORTAÇÕES NECESSÁRIAS PARA SELENIUM/UNDETECTED]
import undetected_chromedriver as uc
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, WebDriverException, NoSuchElementException

# Obtém o caminho absoluto da pasta do script atual.
caminho_script = Path(__file__).resolve().parent
# Acessa a pasta raiz do projeto subindo dois níveis.
caminho_raiz_projeto = caminho_script.parent.parent
# Adiciona o caminho da raiz ao caminho de busca do Python.
sys.path.append(str(caminho_raiz_projeto))

# Assumindo que 'config' e os diretórios estão configurados
from config import DIRETORIO_DADOS_WEBSCRAPPING, DIRETORIO_DADOS_EXTRACAO_QA

# --- SELETORES HTML (CONSTANTES) ---
SELETOR_TITULO = 'h1'
SELETOR_CONTEUDO_POST = 'conversation-balloon__content__text'
SELETOR_COMENTARIOS_LISTA = 'comment-list__comment'
SELETOR_CONTEUDO_COMENTARIO = 'dell-comment-balloon__content'
# Para esperar o conteúdo carregar no Selenium
SELETOR_ESPERA_CONTEUDO = (By.CLASS_NAME, 'conversation-balloon__content__text') 


# --- CONFIGURAÇÃO DE ARQUIVOS E CHECKPOINT ---
ARQUIVO_PROGRESSO = DIRETORIO_DADOS_WEBSCRAPPING / 'progresso_dell_community.txt'
caminho_entrada = DIRETORIO_DADOS_WEBSCRAPPING /'links_discussoes_Dell_Brasil.csv'
caminho_saida_perguntas = DIRETORIO_DADOS_EXTRACAO_QA / 'perguntas/posts_DellCommunity_Brasil_Perguntas.csv'
caminho_saida_respostas = DIRETORIO_DADOS_EXTRACAO_QA / 'respostas/comentarios_DellCommunity_Brasil_Respostas.csv'

# Lista de listas para armazenar dados de posts e comentários
posts_data = []
comments_data = []

# Variáveis globais de status
LINKS_PROCESSADOS = 0
LINKS_IGNORADOS = 0 

# Para garantir que a escrita no arquivo de progresso seja segura
progress_lock = Lock()

# Variáveis do WebDriver (serão inicializadas em main)
driver = None
wait_selenium = None
NOME_COLUNA_URL= 'Link da Discussão'

# --- FUNÇÕES DE CHECKPOINT ---
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

# --- FUNÇÃO DE EXTRAÇÃO (MODIFICADA PARA USAR SELENIUM) ---
def extrair_dados_dell_community(url, post_id):
    """Extrai os dados de uma única URL usando Selenium e BeautifulSoup."""
    global LINKS_PROCESSADOS, driver, wait_selenium
    
    # Pausa aleatória ANTES de iniciar a navegação
    pausa_nav = random.uniform(1, 2) 
    time.sleep(pausa_nav)
    
    try:
        # 1. Navegar para a URL
        driver.get(url)
        
        # 2. Esperar que o conteúdo principal (o corpo do post) esteja visível
        # Timeout aqui captura erros de carregamento e URLs inacessíveis
        wait_selenium.until(EC.visibility_of_element_located(SELETOR_ESPERA_CONTEUDO))
        
        # 3. Extrair o HTML e processar com BeautifulSoup
        soup = BeautifulSoup(driver.page_source, 'html.parser')

    except (TimeoutException, WebDriverException, NoSuchElementException) as e:
        print(f"[{post_id}] ❌ Erro de Selenium (Timeout/Nav/Elemento): {url}. Erro: {e}")
        # Retorna sem salvar progresso para re-tentar na próxima execução
        return

    # --- Extração (Posts) ---
    titulo_elem = soup.find(SELETOR_TITULO)
    page_title = titulo_elem.string.strip() if titulo_elem and titulo_elem.string else "Título não encontrado"

    texto_postagem_elem = soup.find(class_=SELETOR_CONTEUDO_POST)
    post_content = texto_postagem_elem.text.strip() if texto_postagem_elem else "Conteúdo não encontrado"

    # Escrita na lista global (Seguro em modo sequencial)
    posts_data.append({
        "ID_Post": post_id,
        "Titulo_Post": page_title,
        "URL_Post": url,
        "Conteudo_Post": post_content.replace('\n', ' ').replace('\r', '').strip()
    })

    # --- Extração (Comentários) ---
    all_comments = soup.find_all(class_=SELETOR_COMENTARIOS_LISTA)
    new_comments = []
    for comment in all_comments:
        comment_content_elem = comment.find(class_=SELETOR_CONTEUDO_COMENTARIO)
        comment_content = comment_content_elem.text.strip() if comment_content_elem else "Comentário não encontrado"
        
        if comment_content and comment_content != "Comentário não encontrado":
            new_comments.append({
                "ID_Post": post_id,
                "Conteudo_Comentario": comment_content.replace('\n', ' ').replace('\r', '').strip()
            })
            
    if new_comments:
        comments_data.extend(new_comments)
            
    # Salva o progresso IMEDIATAMENTE após a extração bem-sucedida
    salvar_progresso(url)
    
    # Atualiza o progresso global
    LINKS_PROCESSADOS += 1
    return True # Sinaliza sucesso


# --- Código Principal ---
def main():
    global LINKS_PROCESSADOS, LINKS_IGNORADOS, driver, wait_selenium
    start_time = time.time()
    
    links_para_processar = []
    
    # 1. Carrega o progresso anterior
    urls_processadas_anteriormente = carregar_progresso()

    # --- Inicialização do WebDriver ---
    print("\n--- INICIALIZANDO UNDETECTED CHROMEDRIVER ---")
    chrome_options = ChromeOptions()
    # Mantido o modo não headless para evitar detecção
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--no-sandbox")
    
    try:
        # Inicializa o driver
        driver = uc.Chrome(version_main=141, options=chrome_options)
        wait_selenium = WebDriverWait(driver, 10) # Timeout de espera para elementos
    except Exception as e:
        print(f"Erro ao inicializar o ChromeDriver: {e}")
        return

    try:
        # 2. Carrega e filtra todos os links do CSV
        with open(caminho_entrada, 'r', encoding='utf-8') as infile:
            reader = csv.DictReader(infile)
            if NOME_COLUNA_URL not in reader.fieldnames:
                print(f"Erro: O arquivo CSV de entrada deve ter uma coluna chamada '{NOME_COLUNA_URL}'.")
                return
            
            for index, row in enumerate(reader):
                url = row[NOME_COLUNA_URL].strip()
                
                # Filtra links já processados (Checkpointing)
                if url in urls_processadas_anteriormente:
                    LINKS_IGNORADOS += 1
                    continue
                
                if url:
                    # Adiciona (URL, ID do Post)
                    links_para_processar.append((url, index)) 
        
        TOTAL_LINKS = len(links_para_processar)
        print(f"Links a processar nesta sessão: {TOTAL_LINKS}. Links ignorados (já processados): {LINKS_IGNORADOS}.")

        if TOTAL_LINKS == 0:
            print("Todos os links já foram processados. Saindo.")
            return

        # 3. Execução SEQUENCIAL em Lotes de N (usando 5, conforme seu último código)
        BATCH_SIZE = 5 # Definido como 5 para consistência com o último código fornecido
        print(f"Iniciando extração SEQUENCIAL em lotes de {BATCH_SIZE}...")
        
        
        for batch_index in range(0, TOTAL_LINKS, BATCH_SIZE):
            
            # --- INICIA CRONÔMETRO DO LOTE ---
            start_batch_time = time.time()
            
            batch = links_para_processar[batch_index:batch_index + BATCH_SIZE]
            
            print(f"\n--- Processando Lote {batch_index // BATCH_SIZE + 1} (Links {batch_index + 1} a {batch_index + len(batch)}) ---")
            
            success_count_in_batch = 0
            
            for url, post_id in batch:
                # O try/except interno é CRUCIAL para não quebrar o lote/processo
                try:
                    if extrair_dados_dell_community(url, post_id):
                        success_count_in_batch += 1
                except Exception as e:
                    # Captura erros inesperados de Python
                    print(f"[ERRO CRÍTICO NÃO TRATADO NO LINK] Falha ao processar {url} (ID: {post_id}). Erro: {e}")
                    traceback.print_exc()
            
            # --- PARA CRONÔMETRO DO LOTE ---
            end_batch_time = time.time()
            batch_duration = end_batch_time - start_batch_time
            
            # --- CÁLCULO E IMPRESSÃO DA TAXA DO LOTE ---
            if success_count_in_batch > 0 and batch_duration > 0:
                batch_rate = success_count_in_batch / batch_duration
                print(f"LOTE CONCLUÍDO: Duração: {batch_duration:.2f}s | Sucesso: {success_count_in_batch}/{len(batch)} links | Taxa: {batch_rate:.2f} links/s")
            else:
                 print(f"LOTE CONCLUÍDO: Duração: {batch_duration:.2f}s | (0 links coletados com sucesso)")
            
            # Imprime o progresso acumulado após cada lote
            total_disponivel = TOTAL_LINKS + LINKS_IGNORADOS
            total_processado_atual = LINKS_PROCESSADOS + LINKS_IGNORADOS
            percentual = (total_processado_atual) * 100 / total_disponivel
            print(f"Checkpoint Geral: Total processado nesta sessão: {LINKS_PROCESSADOS}. Acumulado total: {total_processado_atual}. Percentual total: {percentual:.2f}%.")
            print("----------------------------------------------------------------------")
                 
    except FileNotFoundError:
        print(f"Erro: O arquivo '{caminho_entrada}' não foi encontrado.")
        
    except Exception as e:
        # Exceção de nível superior (e.g., erro de loop, erro de leitura de arquivo)
        print(f"Ocorreu um erro durante a execução principal: {e}")
        traceback.print_exc()

    finally:
        # Garante o fechamento do navegador, mesmo em caso de erro ou interrupção (Ctrl+C)
        if driver:
            driver.quit()

    # 4. Salvamento dos Dados Finais em arquivos CSV
    print("\n--- Salvamento dos Dados Finais em arquivos CSV ---")
    
    # Garante que os diretórios existam
    DIRETORIO_DADOS_EXTRACAO_QA.mkdir(parents=True, exist_ok=True)
    caminho_saida_perguntas.parent.mkdir(parents=True, exist_ok=True)
    caminho_saida_respostas.parent.mkdir(parents=True, exist_ok=True)
    
    if posts_data:
        df_posts = pd.DataFrame(posts_data)
        # SALVAMENTO ROBUSTO: Anexa os dados coletados na sessão
        df_posts.to_csv(caminho_saida_perguntas, index=False, encoding='utf-8', mode='a', header=not caminho_saida_perguntas.exists())
        print(f"Dados de posts salvos em '{caminho_saida_perguntas}'. Total: {len(df_posts)} (Novos).")
    else:
        print("Nenhum dado de post foi extraído.")

    if comments_data:
        df_comments = pd.DataFrame(comments_data)
        # SALVAMENTO ROBUSTO: Anexa os dados coletados na sessão
        df_comments.to_csv(caminho_saida_respostas, index=False, encoding='utf-8', mode='a', header=not caminho_saida_respostas.exists())
        print(f"Dados de comentários salvos em '{caminho_saida_respostas}'. Total: {len(df_comments)} (Novos).")
    else:
        print("Nenhum dado de comentário foi extraído.")

    end_time = time.time()
    total_duration = end_time - start_time
    taxa = LINKS_PROCESSADOS / total_duration if total_duration > 0 and LINKS_PROCESSADOS > 0 else 0 
    
    print(f"\nProcesso concluído! Duração total da sessão: {total_duration:.2f} segundos.")
    print(f"Taxa total da sessão: {taxa:.2f} links/segundo.")


if __name__ == "__main__":
    main()