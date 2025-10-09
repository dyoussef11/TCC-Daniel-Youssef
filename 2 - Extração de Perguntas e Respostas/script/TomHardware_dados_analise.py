import sys
from pathlib import Path

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

# Listas para armazenar dados de posts e comentários
posts_data = []
comments_data = []
driver = None

try:
    # --- Configuração do WebDriver ---
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--blink-settings=imagesEnabled=false")
    chrome_options.add_argument("--disable-gpu")
    
    driver = uc.Chrome(service=ChromeService(ChromeDriverManager().install()), options=chrome_options)
    wait = WebDriverWait(driver, 15)

    # --- Leitura do Arquivo CSV ---
    caminho_entrada = DIRETORIO_DADOS_WEBSCRAPPING/'links_discussoes_Tom_Hardware.csv'
    try:
        df = pd.read_csv(caminho_entrada)
    except FileNotFoundError:
        print(f"Erro: O arquivo '{caminho_entrada}' não foi encontrado.")
        exit()

    # --- Loop sobre a coluna 'link' do DataFrame ---
    for index, link in enumerate(df['link']):
        # Use o índice como um ID único para cada post
        post_id = index
        print(f"Analisando link {index + 1}/{len(df['link'])} (ID: {post_id}): {link}")
        
        try:
            driver.get(link)

            # Espera o título da página carregar
            wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "h1.p-title-value")))

            # Pega o HTML da página
            page_source = driver.page_source
            soup = BeautifulSoup(page_source, 'html.parser')

            # --- Extração de Dados do Post (Pergunta) ---
            title_element = soup.find("h1", class_="p-title-value")
            page_title = title_element.text.strip() if title_element else "Título não encontrado"
            
            # O conteúdo do post original é o primeiro elemento 'message-inner'
            all_messages = soup.find_all("div", class_="message-inner")
            
            if all_messages:
                first_message_content = all_messages[0].find("div", class_="bbWrapper")
                post_content = first_message_content.text.strip() if first_message_content else "Conteúdo não encontrado"
                
                # Adiciona os dados do post à lista de posts
                posts_data.append({
                    "ID_Post": post_id,
                    "Titulo_Post": page_title,
                    "URL_Post": link,
                    "Conteudo_Post": post_content
                })
            
            # --- Extração de Dados dos Comentários ---
            # Itera sobre os comentários, pulando o primeiro elemento que é o post principal
            if len(all_messages) > 1:
                for comment_body in all_messages[1:]:
                    try:
                        comment_text_elem = comment_body.find("div", class_="bbWrapper")
                        comment_text = comment_text_elem.text.strip() if comment_text_elem else "Comentário não encontrado"
                        
                        # Adiciona os dados do comentário à lista de comentários
                        comments_data.append({
                            "ID_Post": post_id,  # Link para o post original usando o ID artificial
                            "Conteudo_Comentario": comment_text,
                        })
                    
                    except Exception as e:
                        print(f"Erro ao extrair dados de um comentário no link {link}: {e}")
                        continue
        
        except TimeoutException:
            print(f"Erro: Tempo de espera esgotado para o link {link}.")
        except Exception as e:
            print(f"Ocorreu um erro inesperado no link {link}: {e}")

    # --- Salvamento dos Dados em arquivos CSV ---
    if posts_data:
        df_posts = pd.DataFrame(posts_data)
        caminho_saida_perguntas = DIRETORIO_DADOS_EXTRACAO_QA /'perguntas/posts_TomHardware_Perguntas.csv'
        df_posts.to_csv(caminho_saida_perguntas, index=False, encoding='utf-8')
        print(f"\nDados de posts salvos em '{caminho_saida_perguntas}'.")
    else:
        print("\nNenhum dado de post foi extraído.")

    if comments_data:
        df_comments = pd.DataFrame(comments_data)
        caminho_saida_respostas = DIRETORIO_DADOS_EXTRACAO_QA / 'respostas/comentarios_TomHardware_Respostas.csv'
        df_comments.to_csv(caminho_saida_respostas, index=False, encoding='utf-8')
        print(f"Dados de comentários salvos em '{caminho_saida_respostas}'.")
    else:
        print("Nenhum dado de comentário foi extraído.")

finally:
    # Garante que o navegador será fechado, independentemente de erros
    if driver:
        driver.quit()

print("\nProcesso concluído!")