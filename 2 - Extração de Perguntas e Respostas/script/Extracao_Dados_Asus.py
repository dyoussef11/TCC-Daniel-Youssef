import sys
from pathlib import Path
import csv
import pandas as pd
import requests
from bs4 import BeautifulSoup
import time
import random
import traceback 
import os
import tempfile
# --- IMPORTAÇÃO CRUCIAL PARA PARALELISMO ---
import multiprocessing as mp 



# [IMPORTAÇÕES NECESSÁRIAS PARA SELENIUM/UNDETECTED]
import undetected_chromedriver as uc
from selenium.webdriver.chrome.options import Options 
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

# Agora a importação do módulo 'config' deve funcionar.
from config import DIRETORIO_DADOS_WEBSCRAPPING,DIRETORIO_DADOS_EXTRACAO_QA



# Listas para armazenar dados de posts e comentários
posts_data = []
comments_data = []
driver = None

# --- VARIÁVEIS DE CONFIGURAÇÃO DE SAÍDA ---
caminho_entrada = DIRETORIO_DADOS_WEBSCRAPPING / 'links_discussoes_Asus.csv'
caminho_saida_perguntas = DIRETORIO_DADOS_EXTRACAO_QA / 'perguntas/posts_Asus_Perguntas.csv'
caminho_saida_respostas = DIRETORIO_DADOS_EXTRACAO_QA / 'respostas/comentarios_Asus_Respostas.csv'


# --- FUNÇÃO DE SALVAMENTO REUSÁVEL ---
def salvar_dados_parciais(posts_data_list, comments_data_list, path_posts, path_comments):
    """Salva os dados de posts e comentários nos caminhos especificados."""
    if posts_data_list:
        df_posts = pd.DataFrame(posts_data_list)
        path_posts.parent.mkdir(parents=True, exist_ok=True)
        # Usa 'w' (write) para sobrescrever o arquivo com todos os dados acumulados
        df_posts.to_csv(path_posts, index=False, encoding='utf-8')
        print(f"\n[SALVAMENTO PARCIAL] {len(posts_data_list)} posts salvos em '{path_posts.name}'.")
    
    if comments_data_list:
        df_comments = pd.DataFrame(comments_data_list)
        path_comments.parent.mkdir(parents=True, exist_ok=True)
        # Usa 'w' (write) para sobrescrever o arquivo com todos os dados acumulados
        df_comments.to_csv(path_comments, index=False, encoding='utf-8')
        print(f"[SALVAMENTO PARCIAL] {len(comments_data_list)} comentários salvos em '{path_comments.name}'.")


# --- INÍCIO DO PROCESSO PRINCIPAL COM TRATAMENTO DE ERROS ---

try:
    # --- Configuração e Inicialização do WebDriver ---
    chrome_options = Options()
    # Mantendo --headless ativo no Tom's Guide, se for a sua preferência
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--blink-settings=imagesEnabled=false")
    chrome_options.add_argument("--disable-gpu")
    
    # Inicializa o driver (revertido para uc.Chrome() sem version_main para estabilidade)
    driver = uc.Chrome(version_main=141,options=chrome_options)
    wait = WebDriverWait(driver, 15)

    # --- Leitura do Arquivo CSV ---
    try:
        df = pd.read_csv(caminho_entrada)
        links_para_processar = df['Link da Discussão']
        print(f"Total de {len(links_para_processar)} links carregados para extração.")
    except FileNotFoundError:
        print(f"Erro: O arquivo '{caminho_entrada}' não foi encontrado.")
        sys.exit() 

    # --- Loop sobre a coluna 'link' do DataFrame ---
    for index, link in enumerate(links_para_processar):
        # Usa o índice como um ID único para cada post
        post_id = index
        print(f"Analisando link {index + 1}/{len(links_para_processar)} (ID: {post_id}): {link}")
        
        try:
            driver.get(link)

            # Espera o título da página carregar (Seletor específico do Tom's Guide)
            wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "h1.p-title-value")))

            # Pega o HTML da página
            page_source = driver.page_source
            soup = BeautifulSoup(page_source, 'html.parser')

            # --- Extração de Dados do Post (Pergunta) ---
            title_element = soup.find("h1", class_="p-title-value")
            page_title = title_element.text.strip() if title_element else "Título não encontrado"
            
            # Encontra todos os elementos de post/comentário (message-inner)
            all_messages = soup.find_all("div", class_="message-inner")
            
            if all_messages:
                # Post Principal
                first_message_content = all_messages[0].find("div", class_="bbWrapper")
                post_content = first_message_content.text.strip() if first_message_content else "Conteúdo não encontrado"
                
                posts_data.append({
                    "ID_Post": post_id,
                    "Titulo_Post": page_title,
                    "URL_Post": link,
                    "Conteudo_Post": post_content
                })
            
            # --- Extração de Dados dos Comentários ---
            # Itera sobre os comentários (todos após o primeiro post)
            if len(all_messages) > 1:
                for comment_body in all_messages[1:]:
                    try:
                        comment_text_elem = comment_body.find("div", class_="bbWrapper")
                        comment_text = comment_text_elem.text.strip() if comment_text_elem else "Comentário não encontrado"
                        
                        comments_data.append({
                            "ID_Post": post_id, 
                            "Conteudo_Comentario": comment_text,
                        })
                    except Exception as e:
                        print(f"Erro ao extrair dados de um comentário no link {link}: {e}")
                        continue
            
        except TimeoutException:
            print(f"Erro: Tempo de espera esgotado para o link {link}.")
        except Exception as e:
            print(f"Ocorreu um erro inesperado no link {link}: {e}")
        
        # --- SALVAMENTO PARCIAL (A CADA 2 LINKS PROCESSADOS) ---
        if (index + 1) % 2 == 0:
            salvar_dados_parciais(posts_data, comments_data, caminho_saida_perguntas, caminho_saida_respostas)
            time.sleep(1) 

    # --- SALVAMENTO FINAL APÓS O LOOP ---
    print("\n[PROCESSO COMPLETO] Salvando dados finais...")
    salvar_dados_parciais(posts_data, comments_data, caminho_saida_perguntas, caminho_saida_respostas)


# --- TRATAMENTO DE INTERRUPÇÃO E ENCERRAMENTO ---

except KeyboardInterrupt:
    print("\n\n[INTERRUPÇÃO DETECTADA - Ctrl+C] Salvando dados acumulados antes de finalizar...")
    salvar_dados_parciais(posts_data, comments_data, caminho_saida_perguntas, caminho_saida_respostas)

except Exception as e:
    print(f"\n\n[ERRO CRÍTICO] Ocorreu um erro inesperado: {e}. Salvando dados acumulados...")
    salvar_dados_parciais(posts_data, comments_data, caminho_saida_perguntas, caminho_saida_respostas)

finally:
    if driver:
        driver.quit()
        print("\nNavegador encerrado.")

print("\nProcesso de extração concluído!")