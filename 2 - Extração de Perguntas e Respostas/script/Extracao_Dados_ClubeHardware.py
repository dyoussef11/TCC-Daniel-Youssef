import sys
from pathlib import Path
import undetected_chromedriver as uc
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup
import pandas as pd
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# --- Configuração de Caminhos (Mantido) ---
# Obtém o caminho absoluto da pasta do script atual.
caminho_script = Path(__file__).resolve().parent

# Acessa a pasta raiz do projeto subindo dois níveis.
caminho_raiz_projeto = caminho_script.parent.parent

# Adiciona o caminho da raiz ao caminho de busca do Python.
sys.path.append(str(caminho_raiz_projeto))

# Agora a importação do módulo 'config' deve funcionar.
# ATENÇÃO: É necessário que o módulo 'config' exista e contenha as variáveis
# DIRETORIO_DADOS_WEBSCRAPPING e DIRETORIO_DADOS_EXTRACAO_QA
from config import DIRETORIO_DADOS_WEBSCRAPPING, DIRETORIO_DADOS_EXTRACAO_QA

# --- Variáveis de Saída e Criação de Diretórios (AJUSTADO para um único CSV de Q&A) ---
# Cria um diretório de saída unificado para o resultado final

caminho_saida_qa = DIRETORIO_DADOS_EXTRACAO_QA / 'perguntas_e_respostas/perguntas_respostas_ClubeHardware.csv' # Caminho de saída único

# --- DECLARAÇÕES DE HTML EM VARIÁVEIS (AJUSTADO) ---
SELETOR_POST_TITLE = 'h1[class="ipsType_pageTitle ipsContained_container"]'

# CLASSE_POST_COMPLETO deve ser o seletor para TODOS os posts/comentários
# O seletor 'article[class*="cPost"]' é mais robusto para posts em fóruns IP.
CLASSE_POST_COMPLETO = 'article[class*="cPost"]' 

# Usa o atributo data-role
CLASSE_CONTEUDO_WRAP = 'div[data-role="commentContent"]' 

# Usa a tag <time> que contém o atributo datetime
CLASSE_DATA_TEMPO = 'time' 

CLASSE_RESPOSTA_ACEITA = 'cPost ipsBox ipsResponsive_pull ipsComment ipsComment_accepted'

# --- Lista global ÚNICA para os dados de Pergunta/Resposta ---
qa_data = [] # Esta lista armazenará todos os pares Q&A
driver = None


def extrair_dados_topico(soup, post_id, link):
    """
    Extrai o título, o conteúdo do post original e itera sobre as respostas,
    combinando-os em um único registro Q&A para cada resposta.
    """
    
    # 1. Extração de Dados da Pergunta (Post Principal)
    
    # Extrai o Título
    title_element = soup.find('h1', class_='ipsType_pageTitle') 
    page_title = title_element.text.strip() if title_element else "Título não encontrado"
    print(f'page_title: {page_title}')
    
    # Encontra TODOS os posts/comentários
    all_posts = soup.select(CLASSE_POST_COMPLETO)
    
    if not all_posts:
        print(f"Aviso: Post original (pergunta) não encontrado no link {link}. Ignorando o link.")
        return

    # O primeiro post (índice 0) é a Pergunta
    first_post_element = all_posts[0]
    
    # Extrai Conteúdo da Pergunta usando o seletor data-role
    # Não precisa de [0] aqui, pois 'first_post_element' é um único objeto Tag
    post_content_elem = first_post_element.find('div', attrs={'data-role': 'commentContent'})
    post_content = post_content_elem.text.strip() if post_content_elem else "Conteúdo da Pergunta não encontrado"

    # Extrai Data da Pergunta usando o seletor 'time'
    data_postagem_elem = first_post_element.find(CLASSE_DATA_TEMPO)
    data_postagem = data_postagem_elem.get('datetime', '') if data_postagem_elem else ""

    print(f'Conteúdo da Pergunta: {post_content[:50]}...') # Print truncado para legibilidade
    
    # 2. Extração de Dados das Respostas (Comentários)
    
    # Itera sobre os posts a partir do segundo (índice 1)
    comment_bodies = all_posts
    
    if len(comment_bodies) <= 1:
        print(f"Aviso: Nenhuma resposta encontrada para o post ID {post_id}.")
        return
        
    for comment_body in comment_bodies[1:]:
        try:
            # Extrai Conteúdo da Resposta (usando o seletor data-role)
            comment_text_elem = comment_body.find('div', attrs={'data-role': 'commentContent'})
            comment_text = comment_text_elem.text.strip() if comment_text_elem else "Conteúdo da Resposta não encontrado"

            # Extrai Data da Resposta (usando o seletor 'time')
            data_resposta_elem = comment_body.find(CLASSE_DATA_TEMPO)
            data_resposta = data_resposta_elem.get('datetime', '') if data_resposta_elem else ""
            print(f'data_resposta:{data_resposta}')
            
            # Verifica se é a Resposta Aceita
            # Verifica se a classe de aceitação está presente em qualquer lugar do atributo 'class'
            is_accepted = 1 if CLASSE_RESPOSTA_ACEITA in comment_body.get('class', []) else 0
            print(f'is_accepted:{is_accepted}')
            # 3. Combinação em um único registro de Q&A
            qa_data.append({
                "ID_Post": post_id,
                "Titulo_Post": page_title,
                "URL_Post": link,
                "Data_Postagem": data_postagem,
                "Conteudo_Post": post_content,
                "Data_Resposta": data_resposta,
                "Resposta_Conteudo": comment_text,
                "Resposta_Aceita": is_accepted
            })

        except Exception as e:
            print(f"Erro ao extrair dados de uma resposta no link {link}: {e}")
            continue

# =================================================================
#               INÍCIO DO SCRIPT PRINCIPAL (MANTIDO)
# =================================================================
try:
    # --- Configuração do WebDriver ---
    chrome_options = Options()
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--blink-settings=imagesEnabled=false")
    chrome_options.add_argument("--disable-gpu")
    
    # Usando apenas uma instância do uc.Chrome
    # ATENÇÃO: Verifique se a versão 141 está correta para sua instalação
    driver = uc.Chrome(version_main=141,options=chrome_options)
    wait = WebDriverWait(driver, 10) # Aumentado para 10s para maior robustez

    # --- Leitura do Arquivo CSV ---
    caminho_entrada = DIRETORIO_DADOS_WEBSCRAPPING / 'links_discussoes_ClubeHardware.csv'
    
    try:
        df = pd.read_csv(caminho_entrada)
    except FileNotFoundError:
        print(f"Erro: O arquivo '{caminho_entrada}' não foi encontrado.")
        exit()

    # --- Loop sobre a coluna 'link' do DataFrame ---
    for index, link in enumerate(df['Link da Discussão']):
        post_id = index
        print(f"\nAnalisando link {index + 1}/{len(df['Link da Discussão'])} (ID: {post_id}): {link}")
        
        try:
            driver.get(link)

            # Espera até que o título do post esteja visível
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

    # --- Salvamento dos Dados em arquivo CSV ÚNICO ---
    if qa_data:
        df_qa = pd.DataFrame(qa_data)
        
        # Define a ordem das colunas conforme o solicitado
        colunas_ordenadas = [
            "ID_Post",
            "Titulo_Post",
            "URL_Post",
            "Data_Postagem",
            "Conteudo_Post",
            "Data_Resposta",
            "Resposta_Conteudo",
            "Resposta_Aceita"
        ]
        
        df_qa = df_qa.reindex(columns=colunas_ordenadas)
        df_qa.to_csv(caminho_saida_qa, index=False, encoding='utf-8')
        print(f"\nDados de Pergunta/Resposta salvos em '{caminho_saida_qa}'.")
    else:
        print("\nNenhum dado de Pergunta/Resposta foi extraído.")


finally:
    if driver:
        driver.quit()

print("\nProcesso concluído! 🎉")