import sys
from pathlib import Path
import csv
import pandas as pd
import time # Adicionado para pausas
import os # Necessário para criar diretórios

# Obtém o caminho absoluto da pasta do script atual.
caminho_script = Path(__file__).resolve().parent
caminho_raiz_projeto = caminho_script.parent.parent
sys.path.append(str(caminho_raiz_projeto))

# Agora a importação do módulo 'config' deve funcionar.
from config import DIRETORIO_DADOS_WEBSCRAPPING,DIRETORIO_DADOS_EXTRACAO_QA

import undetected_chromedriver as uc
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# --- VARIÁVEIS DE CONFIGURAÇÃO DE SAÍDA ---
caminho_entrada = DIRETORIO_DADOS_WEBSCRAPPING / 'links_discussoes_LinusTechTips.csv'
caminho_saida_perguntas = DIRETORIO_DADOS_EXTRACAO_QA / 'perguntas/posts_LinusTechTips_Perguntas.csv'
caminho_saida_respostas = DIRETORIO_DADOS_EXTRACAO_QA / 'respostas/comentarios_LinusTechTips_Respostas.csv'

# --- SELETORES DE PÁGINA (CONSTANTES) ---
SELETOR_TITULO_PAGINA = "h1.ipsType_pageTitle.ipsContained_container"
SELETOR_TODOS_POSTS_E_COMENTARIOS = "article.cPost"
SELETOR_CONTEUDO_POST_COMENTARIO = "div.cPost_contentWrap"

# Listas para armazenar dados de posts e comentários
posts_data = []
comments_data = []
driver = None

# --- FUNÇÃO DE SALVAMENTO REUSÁVEL ---
def salvar_dados_parciais(posts_data_list, comments_data_list, path_posts, path_comments):
    """Salva os dados de posts e comentários nos caminhos especificados."""
    if posts_data_list:
        df_posts = pd.DataFrame(posts_data_list)
        path_posts.parent.mkdir(parents=True, exist_ok=True)
        df_posts.to_csv(path_posts, index=False, encoding='utf-8')
        print(f"\n[SALVAMENTO PARCIAL] {len(posts_data_list)} posts salvos em '{path_posts.name}'.")
    
    if comments_data_list:
        df_comments = pd.DataFrame(comments_data_list)
        path_comments.parent.mkdir(parents=True, exist_ok=True)
        df_comments.to_csv(path_comments, index=False, encoding='utf-8')
        print(f"[SALVAMENTO PARCIAL] {len(comments_data_list)} comentários salvos em '{path_comments.name}'.")

# --- INÍCIO DO PROCESSO PRINCIPAL COM TRATAMENTO DE ERROS ---

try:
    # --- Configuração e Inicialização do WebDriver ---
    chrome_options = Options()
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--blink-settings=imagesEnabled=false")
    chrome_options.add_argument("--disable-gpu")
    
    # OBS: Você precisa ter a versão 141 do Chrome instalada ou usar None para a última
    # Usando None para maior compatibilidade, a menos que 141 seja estritamente necessário
    # Removi version_main=141 para deixar o uc.Chrome gerenciar a versão, o que é mais estável.
    driver = uc.Chrome(version_main=141,options=chrome_options)
    wait = WebDriverWait(driver, 15)

    # --- Leitura do Arquivo CSV ---
    try:
        df = pd.read_csv(caminho_entrada)
        links_para_processar = df['Link da Discussão']
        print(f"Total de {len(links_para_processar)} links carregados para extração.")
    except FileNotFoundError:
        print(f"Erro: O arquivo '{caminho_entrada}' não foi encontrado.")
        sys.exit() # Usa sys.exit() para sair do try principal

    # --- Loop sobre a coluna 'link' do DataFrame ---
    for index, link in enumerate(links_para_processar):
        # Use o índice como um ID único para cada post
        post_id = index
        print(f"Analisando link {index + 1}/{len(links_para_processar)} (ID: {post_id}): {link}")
        
        try:
            driver.get(link)

            # Espera o título da página carregar
            wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, SELETOR_TITULO_PAGINA)))

            # Pega o HTML da página
            page_source = driver.page_source
            soup = BeautifulSoup(page_source, 'html.parser')

            # Extrai o título do post (Pergunta)
            title_element = soup.find("h1", class_=SELETOR_TITULO_PAGINA.split('.')[-1]) 
            page_title = title_element.text.strip() if title_element else "Título não encontrado"

            # Encontra todos os elementos de post/comentário
            all_posts_and_comments = soup.find_all("article", class_=SELETOR_TODOS_POSTS_E_COMENTARIOS.split('.')[-1])

            # --- Extração de Dados do Post (Pergunta) ---
            if all_posts_and_comments:
                first_post_element = all_posts_and_comments[0]
                post_content_elem = first_post_element.find("div", class_=SELETOR_CONTEUDO_POST_COMENTARIO.split('.')[-1])
                post_content = "\n".join([p.text for p in post_content_elem.find_all("p")]) if post_content_elem else "Conteúdo não encontrado"

                posts_data.append({
                    "ID_Post": post_id,
                    "Titulo_Post": page_title,
                    "URL_Post": link,
                    "Conteudo_Post": post_content
                })
            
            # --- Extração de Dados dos Comentários ---
            if len(all_posts_and_comments) > 1:
                for comment_body in all_posts_and_comments[1:]:
                    try:
                        comment_text_elem = comment_body.find("div", class_=SELETOR_CONTEUDO_POST_COMENTARIO.split('.')[-1])
                        comment_text = "\n".join([p.text for p in comment_text_elem.find_all("p")]) if comment_text_elem else "Comentário não encontrado"
                        
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
        # Salva o progresso após a conclusão do segundo, quarto, sexto, etc. link
        if (index + 1) % 2 == 0:
            salvar_dados_parciais(posts_data, comments_data, caminho_saida_perguntas, caminho_saida_respostas)
            time.sleep(1) # Pausa breve para garantir a escrita no disco

    # --- SALVAMENTO FINAL APÓS O LOOP (Dados restantes) ---
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