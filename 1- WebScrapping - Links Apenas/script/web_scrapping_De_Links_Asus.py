import sys
from pathlib import Path
import csv
import time
import pandas as pd
import random # Importar para pausas anti-bloqueio
import traceback # Importar para melhor rastreamento de erro

# --- Configurações de Caminho e Módulos (Mantida) ---
caminho_script = Path(__file__).resolve().parent
caminho_raiz_projeto = caminho_script.parent.parent
sys.path.append(str(caminho_raiz_projeto))

from config import DIRETORIO_DADOS_WEBSCRAPPING, DIRETORIO_DADOS_EXTRACAO_QA

import undetected_chromedriver as uc
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# --- Variáveis de Saída e Criação de Diretórios ---
DIRETORIO_SAIDA_PERGUNTAS = DIRETORIO_DADOS_EXTRACAO_QA / 'perguntas'
DIRETORIO_SAIDA_RESPOSTAS = DIRETORIO_DADOS_EXTRACAO_QA / 'respostas'

# Garante que os diretórios existam
DIRETORIO_SAIDA_PERGUNTAS.mkdir(parents=True, exist_ok=True)
DIRETORIO_SAIDA_RESPOSTAS.mkdir(parents=True, exist_ok=True)

caminho_saida_perguntas = DIRETORIO_SAIDA_PERGUNTAS / 'posts_ClubeHardware_Perguntas.csv'
caminho_saida_respostas = DIRETORIO_SAIDA_RESPOSTAS / 'comentarios_ClubeHardware_Respostas.csv'

# NOVO: Caminho para o arquivo de rastreamento de progresso
caminho_links_concluidos = DIRETORIO_DADOS_EXTRACAO_QA / 'links_concluidos_ClubeHardware.txt'


# --- DECLARAÇÕES DE HTML EM VARIÁVEIS ---
SELETOR_BOTAO_COOKIES = "div.ipsDialog_content a.ipsButton_fullWidth"
SELETOR_POST_TITLE = "h1.ipsType_pageTitle.ipsContained_container"
SELETOR_DIALOGO_COOKIES = "div.c-cookies-dialog"
CLASSE_POST_COMPLETO = "cPost ipsBox ipsResponsive_pull ipsComment ipsComment_parent ipsClearfix ipsClear ipsColumns ipsColumns_noSpacing ipsColumns_collapsePhone"
CLASSE_CONTEUDO_WRAP = "cPost_contentWrap"

# Listas globais
posts_data = [] # Usada para armazenar dados do link atual antes de salvar
comments_data = [] # Usada para armazenar dados do link atual antes de salvar
driver = None


# --- FUNÇÕES DE CHECKPOINTING E PROGRESSO (NOVAS) ---

def carregar_links_concluidos(path: Path) -> set:
    """Carrega IDs de links já processados para retomar o progresso."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            # Converte linhas para int (IDs) e retorna um set
            return {int(line.strip()) for line in f if line.strip().isdigit()}
    except FileNotFoundError:
        return set()

def marcar_link_concluido(path: Path, post_id: int):
    """Adiciona o ID de um post (índice) à lista de concluídos."""
    with open(path, 'a', encoding='utf-8') as f:
        f.write(str(post_id) + '\n')

def salvar_dados_incrementais(path: Path, data: list, fieldnames: list, type_name: str):
    """Salva a lista de dados no arquivo CSV, anexando os dados."""
    
    if not data:
        print(f"Nenhum dado de {type_name} para salvar.")
        return

    # Verifica se o arquivo existe ou está vazio para decidir se deve escrever o cabeçalho
    escrever_cabecalho = not path.exists() or path.stat().st_size == 0

    try:
        # Usa 'a' (append) para anexar os novos dados
        with open(path, 'a', newline='', encoding='utf-8') as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            
            if escrever_cabecalho:
                writer.writeheader()
                
            writer.writerows(data)
            
        print(f"Dados de {type_name} (ID: {data[0]['ID_Post']}) APENDADOS ao arquivo de saída.")
    except Exception as e:
        print(f"ERRO ao salvar dados incrementais de {type_name}: {e}")
        # traceback.print_exc()

# --- FUNÇÃO DE EXTRAÇÃO MODIFICADA PARA RECEBER LISTAS LOCAIS ---
def extrair_dados_topico(soup, post_id, link, posts_list, comments_list):
    """
    Extrai o título, o conteúdo do post original e os comentários
    de um objeto BeautifulSoup.
    """
    # --- Extração de Dados do Post (Pergunta) ---
    title_element = soup.find("h1", class_=SELETOR_POST_TITLE.split('.')[-1].replace(' ', '.'))
    page_title = title_element.text.strip() if title_element else "Título não encontrado"

    first_post_element = soup.find("article", class_=CLASSE_POST_COMPLETO)
    
    post_content = "Conteúdo não encontrado"
    if first_post_element:
        content_wrap = first_post_element.find("div", class_=CLASSE_CONTEUDO_WRAP)
        # O post original é o primeiro elemento 'cPost', obtém seu conteúdo
        # Certifique-se de pegar o corpo principal e não citações internas
        if content_wrap:
             # Remoção mais robusta de quebras de linha e múltiplos espaços
            post_content = content_wrap.text.strip().replace('\n', ' ').replace('\r', '').replace('  ', ' ')
        else:
             post_content = "Conteúdo não encontrado"

    # Adiciona os dados do post à lista LOCAL de posts
    posts_list.append({
        "ID_Post": post_id,
        "Titulo_Post": page_title,
        "URL_Post": link,
        "Conteudo_Post": post_content
    })

    # --- Extração de Dados dos Comentários ---
    # Encontra todos os posts (inclui a pergunta original)
    comment_bodies = soup.find_all("article", class_=CLASSE_POST_COMPLETO)

    # Itera a partir do segundo elemento (índice 1) para pegar apenas os comentários/respostas
    for comment_body in comment_bodies[1:]:
        try:
            comment_text_elem = comment_body.find("div", class_=CLASSE_CONTEUDO_WRAP)
            
            comment_text = "Comentário não encontrado"
            if comment_text_elem:
                # Remoção mais robusta de quebras de linha e múltiplos espaços
                comment_text = comment_text_elem.text.strip().replace('\n', ' ').replace('\r', '').replace('  ', ' ')

            # Adiciona os dados do comentário à lista LOCAL de comentários
            comments_list.append({
                "ID_Post": post_id, 
                "Conteudo_Comentario": comment_text,
            })

        except Exception as e:
            print(f"Erro ao extrair dados de um comentário no link {link}: {e}")
            continue

# =================================================================
#               INÍCIO DO SCRIPT PRINCIPAL
# =================================================================
try:
    # --- Configuração do WebDriver ---
    chrome_options = Options()
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--blink-settings=imagesEnabled=false")
    chrome_options.add_argument("--disable-gpu")
    
    driver = uc.Chrome(service=ChromeService(ChromeDriverManager().install()), options=chrome_options)
    wait = WebDriverWait(driver, 15)

    # --- Leitura do Arquivo CSV ---
    caminho_entrada = DIRETORIO_DADOS_WEBSCRAPPING / 'links_discussoes_ClubeHardware.csv'
    
    try:
        df = pd.read_csv(caminho_entrada)
        # Filtra links duplicados e garante que a coluna 'link' seja a referência
        df = df.drop_duplicates(subset=['link']).reset_index(drop=True) 
    except FileNotFoundError:
        print(f"Erro: O arquivo '{caminho_entrada}' não foi encontrado.")
        exit()

    # --- Lógica de Retomada ---
    links_concluidos = carregar_links_concluidos(caminho_links_concluidos)
    print(f"Progresso carregado. {len(links_concluidos)} links já foram processados.")

    # --- Loop sobre a coluna 'link' do DataFrame ---
    for index, link in df['link'].items(): # Usar .items() para obter (index, value)
        post_id = index
        
        # Pula se o ID já estiver na lista de concluídos
        if post_id in links_concluidos:
            print(f"Link {index + 1}/{len(df['link'])} (ID: {post_id}): JÁ CONCLUÍDO. Pulando.")
            continue
            
        print(f"\nAnalisando link {index + 1}/{len(df['link'])} (ID: {post_id}): {link}")

        # Listas para armazenar dados apenas do link atual
        current_post_data = []
        current_comments_data = []
        
        try:
            driver.get(link)
            time.sleep(random.uniform(1, 2)) # Pausa anti-bloqueio entre páginas

            # --- Lidar com o pop-up de cookies ---
            try:
                accept_button = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.CSS_SELECTOR, SELETOR_BOTAO_COOKIES)))
                print("Pop-up de cookies detectado. Clicando em 'Aceitar'...")
                accept_button.click()
                WebDriverWait(driver, 5).until(EC.invisibility_of_element_located((By.CSS_SELECTOR, SELETOR_DIALOGO_COOKIES)))
            except TimeoutException:
                pass 
            
            # Espera o título da página carregar (usando wait padrão de 15s)
            wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, SELETOR_POST_TITLE)))

            # Pega o HTML da página
            page_source = driver.page_source
            soup = BeautifulSoup(page_source, 'html.parser')

            # --- Chamada da função de extração (usa listas locais) ---
            extrair_dados_topico(soup, post_id, link, current_post_data, current_comments_data)

            # --- PONTO CRUCIAL DE SALVAMENTO DE CHECKPOINT ---
            # 1. Salva os dados do post
            salvar_dados_incrementais(
                caminho_saida_perguntas, 
                current_post_data, 
                ['ID_Post', 'Titulo_Post', 'URL_Post', 'Conteudo_Post'],
                "Perguntas"
            )

            # 2. Salva os dados dos comentários
            salvar_dados_incrementais(
                caminho_saida_respostas, 
                current_comments_data, 
                ['ID_Post', 'Conteudo_Comentario'],
                "Respostas"
            )

            # 3. Marca o link como concluído
            marcar_link_concluido(caminho_links_concluidos, post_id)
            print(f"Link (ID: {post_id}) marcado como CONCLUÍDO. Progresso salvo.")
            
        except TimeoutException:
            print(f"Erro: Tempo de espera esgotado para o link {link}. Continuando para o próximo.")
        except Exception as e:
            print(f"Ocorreu um erro inesperado no link {link}: {e}")
            traceback.print_exc()
            # Não marca como concluído, permitindo a retomada.
            continue
            
except KeyboardInterrupt:
    print("\n[INTERRUPÇÃO DETECTADA] Encerrando o processo de forma segura...")
except Exception as e:
    print(f"\n[ERRO FATAL] Ocorreu um erro inesperado: {e}")
    traceback.print_exc()

finally:
    if driver:
        driver.quit()

print("\nProcesso concluído! O progresso foi salvo.")