import sys
from pathlib import Path

# Obtém o caminho absoluto da pasta do script atual.
caminho_script = Path(__file__).resolve().parent

# Acessa a pasta raiz do projeto subindo dois níveis.
caminho_raiz_projeto = caminho_script.parent.parent

# Adiciona o caminho da raiz ao caminho de busca do Python.
sys.path.append(str(caminho_raiz_projeto))

# Agora a importação do módulo 'config' deve funcionar.
from config import DIRETORIO_DADOS_WEBSCRAPPING, DIRETORIO_DADOS_EXTRACAO_QA

import undetected_chromedriver as uc
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup
import pandas as pd
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# --- Variáveis de Saída e Criação de Diretórios (Melhoria de Robustez) ---
DIRETORIO_SAIDA_PERGUNTAS = DIRETORIO_DADOS_EXTRACAO_QA / 'perguntas'
DIRETORIO_SAIDA_RESPOSTAS = DIRETORIO_DADOS_EXTRACAO_QA / 'respostas'

# Garante que os diretórios existam
DIRETORIO_SAIDA_PERGUNTAS.mkdir(parents=True, exist_ok=True)
DIRETORIO_SAIDA_RESPOSTAS.mkdir(parents=True, exist_ok=True)

caminho_saida_perguntas = DIRETORIO_SAIDA_PERGUNTAS / 'posts_ClubeHardware_Perguntas.csv'
caminho_saida_respostas = DIRETORIO_SAIDA_RESPOSTAS / 'comentarios_ClubeHardware_Respostas.csv'

# --- DECLARAÇÕES DE HTML EM VARIÁVEIS (Facilidade de Manutenção) ---
# Selenium (CSS)
SELETOR_BOTAO_COOKIES = 'div[class="ipsDialog_content a.ipsButton_fullWidth"]'


SELETOR_POST_TITLE = 'h1[class="ipsType_pageTitle ipsContained_container"]'


SELETOR_DIALOGO_COOKIES = "div.c-cookies-dialog"

SELETOR_PUBLICIDADE = 'span[class="__lxG__splash-close"]'

# BeautifulSoup (Classes HTML)
CLASSE_POST_COMPLETO = 'article[class="cPost ipsBox ipsResponsive_pull  ipsComment  ipsComment_parent ipsClearfix ipsClear ipsColumns ipsColumns_noSpacing ipsColumns_collapsePhone"]'

CLASSE_CONTEUDO_WRAP = 'div[class="cPost_contentWrap"]'

# Listas globais
posts_data = []
comments_data = []
driver = None


def extrair_dados_topico(soup, post_id, link):
    """
    Extrai o título, o conteúdo do post original e os comentários
    de um objeto BeautifulSoup.
    """
    # --- Extração de Dados do Post (Pergunta) ---
    title_element = soup.find('span[class="ipsType_break ipsContained"]', class_=SELETOR_POST_TITLE.split('.')[-1].replace(' ', '.')) # Reutiliza o seletor
    page_title = title_element.text.strip() if title_element else "Título não encontrado"
    print(f'Titulo:{title_element}{page_title}')
    # O conteúdo do post original é o primeiro elemento 'cPost'
    first_post_element = soup.find("article", class_=CLASSE_POST_COMPLETO)
    
    post_content = "Conteúdo não encontrado"
    if first_post_element:
        content_wrap = first_post_element.find("div", class_=CLASSE_CONTEUDO_WRAP)
        post_content = content_wrap.text.strip() if content_wrap else "Conteúdo não encontrado"

    # Adiciona os dados do post à lista de posts
    posts_data.append({
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
            comment_text = comment_text_elem.text.strip() if comment_text_elem else "Comentário não encontrado"

            # Adiciona os dados do comentário à lista de comentários
            comments_data.append({
                "ID_Post": post_id,  # Link para o post original usando o ID artificial
                "Conteudo_Comentario": comment_text,
            })

        except Exception as e:
            print(f"Erro ao extrair dados de um comentário no link {link}: {e}")
            continue

# =================================================================
#               INÍCIO DO SCRIPT PRINCIPAL
# =================================================================
try:
    # --- Configuração do WebDriver ---
    chrome_options = Options()
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--blink-settings=imagesEnabled=false")
    chrome_options.add_argument("--disable-gpu")
    
    driver = uc.Chrome(version_main=141, options=chrome_options)
    driver = uc.Chrome()
    wait = WebDriverWait(driver, 5)

    # --- Leitura do Arquivo CSV ---
    caminho_entrada = DIRETORIO_DADOS_WEBSCRAPPING / 'links_discussoes_ClubeHardware.csv'
    
    try:
        df = pd.read_csv(caminho_entrada)
    except FileNotFoundError:
        print(f"Erro: O arquivo '{caminho_entrada}' não foi encontrado.")
        exit()

    # --- Loop sobre a coluna 'link' do DataFrame ---
    for index, link in enumerate(df['Link da Discussão']):
        # Use o índice como um ID único para cada post
        post_id = index
        print(f"\nAnalisando link {index + 1}/{len(df['Link da Discussão'])} (ID: {post_id}): {link}")
        
        try:
            driver.get(link)

            wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, SELETOR_POST_TITLE)))

            # Pega o HTML da página
            page_source = driver.page_source
            soup = BeautifulSoup(page_source, 'html.parser')

            # --- Chamada da função de extração ---
            extrair_dados_topico(soup, post_id, link)
            
        except TimeoutException:
            print(f"Erro: Tempo de espera esgotado para o link {link}.")
        except Exception as e:
            print(f"Ocorreu um erro inesperado no link {link}: {e}")

    # --- Salvamento dos Dados em arquivos CSV ---
    if posts_data:
        df_posts = pd.DataFrame(posts_data)
        df_posts.to_csv(caminho_saida_perguntas, index=False, encoding='utf-8')
        print(f"\nDados de posts salvos em '{caminho_saida_perguntas}'.")
    else:
        print("\nNenhum dado de post foi extraído.")

    if comments_data:
        df_comments = pd.DataFrame(comments_data)
        df_comments.to_csv(caminho_saida_respostas, index=False, encoding='utf-8')
        print(f"Dados de comentários salvos em '{caminho_saida_respostas}'.")
    else:
        print("Nenhum dado de comentário foi extraído.")

finally:
    if driver:
        driver.quit()

print("\nProcesso concluído!")