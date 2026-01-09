
import sys
from pathlib import Path
import pandas as pd
import time
import traceback 
import random
from bs4 import BeautifulSoup
# --- IMPORTAÇÃO CRUCIAL PARA PARALELISMO ---
# import multiprocessing as mp # Não necessário para esta versão single-process

# [IMPORTAÇÕES NECESSÁRIAS PARA SELENIUM/UNDETECTED]
import undetected_chromedriver as uc
from selenium.webdriver.chrome.options import Options 
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, NoSuchElementException


# --- CONFIGURAÇÃO DE CAMINHOS E IMPORTAÇÃO DO MÓDULO CONFIG ---
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
caminho_entrada = DIRETORIO_DADOS_WEBSCRAPPING / 'links_discussoes_Acer.csv'
# Manter caminhos separados para salvamento parcial
caminho_saida_perguntas = DIRETORIO_DADOS_EXTRACAO_QA / 'perguntas/posts_Acer_Perguntas.csv'
caminho_saida_respostas = DIRETORIO_DADOS_EXTRACAO_QA / 'respostas/comentarios_Acer_Respostas.csv'
# Caminho para o CSV ÚNICO (Pergunta e Resposta juntas)
caminho_saida_unidos = DIRETORIO_DADOS_EXTRACAO_QA / 'perguntas_respostas/perguntas_respostas_Acer.csv' 

# Listas para armazenar dados de posts e comentários
posts_data = []
comments_data = []
driver = None

# --- VARIÁVEIS DE CONFIGURAÇÃO DE EXTRAÇÃO ---
TITLE_ELEMENT_SELECTOR = "h1"
DATE_TITLE_SELECTOR = "time"
# Seletor genérico para o bloco de conteúdo (texto) de Posts e Comentários/Respostas.
# Usamos a classe 'userContent' que parece ser mais estável.
CONTENT_BLOCK_SELECTOR = {"name": "div", "class_": "userContent"}
# Seletor para os blocos de comentários/respostas após o post principal
COMMENT_BLOCK_SELECTOR = {"name": "div", "class_": "userContent"}
# Seletor para identificar a tag de Resposta Aceita (opcional, para redundância)
ACCEPTED_TAG_SELECTOR = "span.css-bdxm8w-Tags-styles-success-Metas-styles-alignVerticallyInMetaItem"


# --- FUNÇÃO DE SALVAMENTO REUSÁVEL ---
def salvar_dados_parciais(posts_data_list, comments_data_list, path_posts, path_comments):
    """Salva os dados de posts e comentários nos caminhos especificados."""
    if posts_data_list:
        df_posts = pd.DataFrame(posts_data_list)
        path_posts.parent.mkdir(parents=True, exist_ok=True)
        # Usa 'w' (write) para sobrescrever o arquivo com todos os dados acumulados
        df_posts.to_csv(path_posts, index=False, encoding='utf-8')
        print(f"\n[SALVAMENTO PARCIAL] {len(df_posts)} posts salvos em '{path_posts.name}'.")
    
    if comments_data_list:
        df_comments = pd.DataFrame(comments_data_list)
        path_comments.parent.mkdir(parents=True, exist_ok=True)
        # Usa 'w' (write) para sobrescrever o arquivo com todos os dados acumulados
        df_comments.to_csv(path_comments, index=False, encoding='utf-8')
        print(f"[SALVAMENTO PARCIAL] {len(df_comments)} comentários salvos em '{path_comments.name}'.")


# --- INÍCIO DO PROCESSO PRINCIPAL COM TRATAMENTO DE ERROS ---

try:
    # --- Configuração e Inicialização do WebDriver ---
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--blink-settings=imagesEnabled=false")
    chrome_options.add_argument("--disable-gpu")
    
    # OBS: O 'version_main' precisa ser ajustado para sua versão do Chrome
    driver = uc.Chrome(version_main=141, options=chrome_options) 
    wait = WebDriverWait(driver, 15) # Aumentado o timeout para robustez

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
        post_id = index
        print(f"\n--- Analisando link {index + 1}/{len(links_para_processar)} (ID: {post_id}): {link} ---")
        
        try:
            driver.get(link)

            # Espera um elemento importante carregar, como o h1 ou a primeira data
            wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, TITLE_ELEMENT_SELECTOR)))

            # Pega o HTML da página
            page_source = driver.page_source
            soup = BeautifulSoup(page_source, 'html.parser')
            
            # --- 1. EXTRAÇÃO DE METADADOS GERAIS ---
            title_element = soup.find(TITLE_ELEMENT_SELECTOR)
            page_title = title_element.text.strip() if title_element else "Título não encontrado"
            print(f'{page_title}')
            
            # Extrai todos os atributos 'datetime' da página em ordem
            all_time_elements = soup.find_all(DATE_TITLE_SELECTOR)
            all_datetimes = [time_elem.get('datetime') for time_elem in all_time_elements if time_elem.get('datetime')]
            print(f'{all_datetimes}')

            
            # --- 2. EXTRAÇÃO DO POST PRINCIPAL (PERGUNTA) ---
            # O conteúdo da pergunta é o primeiro div com a classe 'userContent' dentro do bloco principal
            main_column = soup.find('div', class_='userContent')
            # print(f'{main_column}')
            # post_content_element = main_column.find('span', class_='userContent') if main_column else None
            post_content_element = main_column.find('p') if main_column else None
            
            
            if post_content_element:
                post_datetime = all_datetimes[0] if len(all_datetimes) > 0 else "Data não encontrada"
                post_content = post_content_element.text.strip()
                print(f'{post_content}')
                
                posts_data.append({
                    "ID_Post": post_id,
                    "Titulo_Post": page_title,
                    "URL_Post": link,
                    "Data_Postagem": post_datetime,
                    "Conteudo_Post": post_content,
                })
            else:
                print(f"[ALERTA] Conteúdo do post principal não encontrado para o link {link}. Pulando a extração do post.")
                continue

            
            # --- 3. EXTRAÇÃO DOS COMENTÁRIOS (RESPOSTAS) ---
            # Todos os comentários/respostas estão em blocos com a classe 'comment separated'
            all_comments_blocks = soup.find_all(COMMENT_BLOCK_SELECTOR["name"], class_=COMMENT_BLOCK_SELECTOR["class_"])
            
            print(f'Total de comentários/respostas encontrados: {len(all_comments_blocks)}')

            # Itera sobre os blocos de comentário, a partir da segunda data (índice 1)
            for comment_index, comment_block in enumerate(all_comments_blocks):
                
                comment_datetime = all_datetimes[comment_index + 1] if len(all_datetimes) > (comment_index + 1) else "Data não encontrada"
                
                # O texto do comentário está dentro do div.userContent do bloco de comentário
                content_element = comment_block.find('div', class_='userContent')
                comment_text = content_element.text.strip() if content_element else "Conteúdo do Comentário não encontrado"
                
                # Verifica se a resposta foi aceita. O tag 'Accepted Answer' aparece no HTML dentro do bloco
                # de resposta aceita, que está dentro de um div com a classe 'comment separated'.
                # A forma mais robusta é procurar pelo texto ou pela tag de status visível.
                
                status_element = comment_block.find('span', class_=lambda x: x and 'Tags-styles-success' in x)
                is_accepted = status_element and status_element.text.strip() == "Accepted Answer"
                
                # Adiciona o comentário/resposta
                comments_data.append({
                    "ID_Post": post_id,
                    "ID_Comentario": f"{post_id}-{comment_index + 1}", 
                    "Data_Comentario": comment_datetime,
                    "Conteudo_Comentario": comment_text,
                    "Status_Resposta": "Accepted Answer" if is_accepted else "Not voted for answered"
                })
        
        except TimeoutException:
            print(f"Erro: Tempo de espera esgotado para o link {link}.")
            # Se der erro, salva o estado atual antes de continuar
            salvar_dados_parciais(posts_data, comments_data, caminho_saida_perguntas, caminho_saida_respostas)
            
        except NoSuchElementException:
            print(f"Erro: Elemento essencial não encontrado no link {link}. Página não carregada corretamente.")
            salvar_dados_parciais(posts_data, comments_data, caminho_saida_perguntas, caminho_saida_respostas)
            
        except Exception as e:
            print(f"Ocorreu um erro inesperado no link {link}: {e}")
            # traceback.print_exc()
            salvar_dados_parciais(posts_data, comments_data, caminho_saida_perguntas, caminho_saida_respostas)
        
        # --- SALVAMENTO PARCIAL (A CADA 2 LINKS PROCESSADOS) ---
        if (index + 1) % 2 == 0:
            salvar_dados_parciais(posts_data, comments_data, caminho_saida_perguntas, caminho_saida_respostas)
            time.sleep(random.uniform(1, 2)) 

    # --- SALVAMENTO FINAL E COMBINAÇÃO ---
    print("\n[PROCESSO COMPLETO] Salvando dados finais e combinando para CSV único...")
    # Garante que todos os dados foram salvos nos arquivos separados
    salvar_dados_parciais(posts_data, comments_data, caminho_saida_perguntas, caminho_saida_respostas)

    # Combinação dos DataFrames para o CSV único
    if posts_data and comments_data:
        df_posts = pd.DataFrame(posts_data)
        df_comments = pd.DataFrame(comments_data)

        # Renomeia e seleciona colunas para o merge
        df_comments_clean = df_comments[['ID_Post', 'Data_Comentario', 'Conteudo_Comentario', 'Status_Resposta']].rename(
            columns={
                'Data_Comentario': 'Resposta_Data', 
                'Conteudo_Comentario': 'Resposta_Conteudo',
                'Status_Resposta': 'Resposta_Status'
            }
        )
        
        # Combina Post e Comentários (Left Merge)
        df_combinado = pd.merge(
            df_posts, 
            df_comments_clean, 
            on='ID_Post', 
            how='left'
        )

        # Salva o CSV combinado
        caminho_saida_unidos.parent.mkdir(parents=True, exist_ok=True)
        df_combinado.to_csv(caminho_saida_unidos, index=False, encoding='utf-8')
        print(f"[SALVAMENTO ÚNICO CONCLUÍDO] Dados combinados salvos em '{caminho_saida_unidos.name}'.")
    else:
        print("[ALERTA] Não há dados suficientes de posts ou comentários para criar o arquivo combinado.")


# --- TRATAMENTO DE INTERRUPÇÃO E ENCERRAMENTO ---
except KeyboardInterrupt:
    print("\n\n[INTERRUPÇÃO DETECTADA - Ctrl+C] Salvando dados acumulados antes de finalizar...")
    salvar_dados_parciais(posts_data, comments_data, caminho_saida_perguntas, caminho_saida_respostas)

except Exception as e:
    print(f"\n\n[ERRO CRÍTICO] Ocorreu um erro inesperado: {e}. Salvando dados acumulados...")
    # traceback.print_exc()
    salvar_dados_parciais(posts_data, comments_data, caminho_saida_perguntas, caminho_saida_respostas)

finally:
    if driver:
        driver.quit()
        print("\nNavegador encerrado.")



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
caminho_entrada = DIRETORIO_DADOS_WEBSCRAPPING / 'links_discussoes_Acer.csv'
caminho_saida_perguntas = DIRETORIO_DADOS_EXTRACAO_QA / 'perguntas/posts_Acer_Perguntas.csv'
caminho_saida_respostas = DIRETORIO_DADOS_EXTRACAO_QA / 'respostas/comentarios_Acer_Respostas.csv'


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