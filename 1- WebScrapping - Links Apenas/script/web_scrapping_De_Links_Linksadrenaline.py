import sys
from pathlib import Path
import csv
import time
import random # [MODIFICAÇÃO] Importar random para pausas anti-bloqueio
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options

# Obtém o caminho absoluto da pasta do script atual.
caminho_script = Path(__file__).resolve().parent

# Acessa a pasta raiz do projeto subindo dois níveis.
caminho_raiz_projeto = caminho_script.parent.parent

# Adiciona o caminho da raiz ao caminho de busca do Python.
sys.path.append(str(caminho_raiz_projeto))

# --- ADAPTAÇÕES PARA DEMONSTRAÇÃO DO CÓDIGO (Simulação de imports) ---
# Se for rodar localmente, COMENTE/REMOVA estas linhas e use seus imports reais
# Agora a importação do módulo 'config' e 'modelo_de_busca' deve funcionar.
from config import DIRETORIO_DADOS_WEBSCRAPPING, DIRETORIO_CSV_DATASET_FINAL
from modelo_de_busca import ler_e_filtrar_modelos

caminho_saida = DIRETORIO_DADOS_WEBSCRAPPING / 'links_discussoes_ClubeHardware.csv'
caminho_entrada = DIRETORIO_CSV_DATASET_FINAL / 'dataset_laptops.csv'

# --- Configuração de Busca e Filtro de CSV ---
# Se MARCA_ALVO for None ou '', todos os modelos do CSV serão usados.
MARCA_ALVO = None
TIPO_NOTEBOOK = 'Gamer'
ID_FORUM_NOTEBOOKS = "175" # ID do fórum 'Notebooks' no Adrenaline
SITE_URL = "https://forum.adrenaline.com.br/search/?type=post"

MARCA_ALVO = None
TIPO_NOTEBOOK = 'Gamer'
# Lê e filtra os modelos do CSV
modelos_a_buscar = ler_e_filtrar_modelos(caminho_entrada, MARCA_ALVO, TIPO_NOTEBOOK)

if not modelos_a_buscar:
    print(f"Não foram encontrados modelos para a marca '{MARCA_ALVO}' no arquivo CSV ou houve um erro na leitura. Saindo.")
    sys.exit()

# --- DECLARAÇÕES DE HTML EM VARIÁVEIS (Facilidade de Manutenção) ---

# --- Cookies e Navegação ---
SELETOR_BOTAO_COOKIES = "a.js-noticeDismiss" # Botão 'Aceitar' do pop-up
SELETOR_ICONE_BUSCA = "a.p-navgroup-link--search" # Ícone da lupa para abrir o campo de busca
SELETOR_CAMPO_BUSCA = "keywords" # Name do campo de input (Usado com By.NAME)
SELETOR_CAMPO_FILTRO_FORUM = "c[nodes][]" # Name do Select para filtrar fóruns (Usado com By.NAME)

# --- Resultados e Paginação ---
SELETOR_RESULTADOS_LISTA_AUSENTE = '//div[text()="Nenhum resultado encontrado."]' # AJUSTE: Usaremos este XPath
SELETOR_RESULTADOS_LISTA_PRESENTE = 'li[class="block-row block-row--separated js-inlineModContainer"]'
SELETOR_RESULTADO_LINK_TITULO = "h3.contentRow-title a" # Link dentro do contêiner do resultado
SELETOR_BOTAO_PROXIMA_PAGINA = "a.pageNav-jump.pageNav-jump--next" # Link para a próxima página

# --- Configurações iniciais do Selenium (OTIMIZAÇÃO DE VELOCIDADE/ANTI-BLOQUEIO) ---
chrome_options = Options()
# [MODIFICAÇÃO] Modo headless ativo para maior velocidade
chrome_options.add_argument("--headless") 
chrome_options.add_argument("--window-size=1920,1080")
chrome_options.add_argument("--blink-settings=imagesEnabled=false")
chrome_options.add_argument("--disable-gpu")
# [MODIFICAÇÃO] Adicionar um User-Agent para parecer um navegador normal
chrome_options.add_argument(f"user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.75 Safari/537.36")


# Inicializa o driver APENAS UMA VEZ.
try:
    driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=chrome_options)
except Exception as e:
    print(f"ERRO ao inicializar o Chrome Driver: {e}. Verifique sua instalação do Chrome e permissões.")
    sys.exit()

# [MODIFICAÇÃO] Diminuir o tempo de espera implícita, pois usaremos EC.element_to_be_clickable
wait = WebDriverWait(driver, 15) 

todos_os_links_Adrenaline = [] # Armazena {"Título": titulo, "Link": link, "Modelo Buscado": modelo}
contagem_links = 0
cookie_popup_fechado = False


# --- LOOP PRINCIPAL: Itera sobre cada modelo lido do CSV ---
for i, modelo_de_busca in enumerate(modelos_a_buscar):
    termo_de_busca = modelo_de_busca 
    
    # [MODIFICAÇÃO] PAUSA ESTRATÉGICA E ALEATÓRIA ENTRE MODELOS
    # Crucial para evitar rate limiting e simular um humano
    if i > 0:
        sleep_time = random.uniform(2, 3) 
        print(f"Pausando por {sleep_time:.2f} segundos antes da busca do próximo modelo.")
        time.sleep(sleep_time)

    print(f"\n{'='*70}")
    print(f"INICIANDO BUSCA {i+1}/{len(modelos_a_buscar)}: Modelo '{modelo_de_busca}'")
    print(f"{'='*70}")
    
    # --- Passo 1: Configurar Filtros e Realizar a busca ---
    try:
        print("Acessando a página de busca do fórum...")
        driver.get(SITE_URL) 

        # Lida com o pop-up de cookies uma única vez
        if not cookie_popup_fechado:
            try:
                # Usa a variável de seletor
                cookie_button = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.CSS_SELECTOR, SELETOR_BOTAO_COOKIES)))
                if cookie_button:
                    # Clicar via JS é mais rápido e confiável
                    driver.execute_script("arguments[0].click();", cookie_button)
                    print("Aviso de cookies aceito.")
                    cookie_popup_fechado = True
            except:
                pass 

        # 1. SELEÇÃO DO FÓRUM "NOTEBOOKS" (FILTRO)
        print("Buscando e selecionando o campo 'Notebooks' no filtro...")
        # Usa a variável de seletor (By.NAME)
        select_element = wait.until(
            EC.presence_of_element_located((By.NAME, SELETOR_CAMPO_FILTRO_FORUM))
        )
        forum_select = Select(select_element)
        forum_select.select_by_value(ID_FORUM_NOTEBOOKS)
        print(f"Filtro 'Notebooks' selecionado (value={ID_FORUM_NOTEBOOKS}).")
        
        # 2. INSERÇÃO DO TERMO DE BUSCA
        print(f"Inserindo o termo '{termo_de_busca}' e iniciando a pesquisa...")
        # Clica no ícone de pesquisa para expandir o campo de input
        # Usa a variável de seletor (By.CSS_SELECTOR)
        search_icon = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, SELETOR_ICONE_BUSCA)))
        search_icon.click()

        # Encontra o campo de input de busca (usa a variável de seletor - By.NAME)
        search_input = wait.until(EC.visibility_of_element_located((By.NAME, SELETOR_CAMPO_BUSCA)))
        
        # Limpa o campo antes de enviar a nova busca
        search_input.clear()
        search_input.send_keys(termo_de_busca)
        search_input.send_keys(Keys.ENTER)
        
        print("Pesquisa iniciada com sucesso! Aguardando a página de resultados...")

    except Exception as e:
        print(f"Erro na fase de busca inicial para '{modelo_de_busca}': {e}. Pulando para o próximo modelo.")
        continue # Pula para o próximo modelo

    # --- Passo 2: Coletar links de todas as páginas de resultados (LÓGICA CORRIGIDA) ---
    pagina_atual = 1
    while True:
        try:
            # Tenta aguardar a lista de resultados carregar. Tempo de espera: 8s.
            WebDriverWait(driver, 8).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, SELETOR_RESULTADOS_LISTA_PRESENTE)))
            
        except TimeoutException:
            # Se o timeout ocorrer, tenta encontrar a mensagem de "Nenhum resultado encontrado."
            print("Timeout atingido ao esperar por resultados. Verificando se há mensagem de ausência...")

            try:
                # Procura explicitamente pelo texto "Nenhum resultado encontrado." (By.XPATH)
                WebDriverWait(driver, 3).until(
                    EC.presence_of_element_located((By.XPATH, SELETOR_RESULTADOS_LISTA_AUSENTE)) 
                )
                print(f"Zero resultados encontrados para o modelo '{modelo_de_busca}'. Pulando para o próximo modelo.")
                # SE ENCONTRADO, QUEBRA O LOOP DE PAGINAÇÃO.
                break
            
            except TimeoutException:
                # Se nem a lista de resultados nem a mensagem de ausência foram encontradas
                print(f"Erro inesperado ou timeout grave no carregamento da página de resultados para o modelo '{modelo_de_busca}'.")
                break # Pula para o próximo modelo

        # Se a execução chegou aqui, 'SELETOR_RESULTADOS_LISTA_PRESENTE' foi encontrado (primeiro 'try')
        
        # Encontra todos os elementos que contêm os resultados da busca na página atual
        resultados = driver.find_elements(By.CSS_SELECTOR, SELETOR_RESULTADOS_LISTA_PRESENTE)
        
        # Esta checagem é um backup
        if not resultados:
            print(f"Lista de resultados vazia (cheque de backup). Pulando.")
            break

        novos_links_coletados = 0
        
        # Extrai os dados de cada resultado
        for resultado in resultados:
            try:
                # Usa a variável de seletor
                titulo_elemento = resultado.find_element(By.CSS_SELECTOR, SELETOR_RESULTADO_LINK_TITULO)
                titulo = titulo_elemento.text.strip()
                link = titulo_elemento.get_attribute("href")
                
                # Garante que o link não foi coletado antes
                if not any(item['Link'] == link for item in todos_os_links_Adrenaline):
                    todos_os_links_Adrenaline.append({
                        "Título": titulo, 
                        "Link": link, 
                        "Modelo Buscado": modelo_de_busca
                    })
                    contagem_links += 1
                    novos_links_coletados += 1
            except NoSuchElementException:
                continue 
            except Exception as e:
                print(f"Erro ao extrair link em resultado individual: {e}")
                continue
        
        print(f"Página {pagina_atual} processada. Novos links: {novos_links_coletados}. Total acumulado: {len(todos_os_links_Adrenaline)}")
        pagina_atual += 1

        # Tenta encontrar o botão "Próxima"
        print("Procurando o botão 'Próxima' página...")
        try:
            # [MODIFICAÇÃO] Aumenta o tempo de espera para o link da próxima página para 5s 
            proxima_pagina_link = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, SELETOR_BOTAO_PROXIMA_PAGINA))
            )
            
            print("Navegando para a próxima página...")
            driver.execute_script("arguments[0].click();", proxima_pagina_link)
            
            # [MODIFICAÇÃO] Pausa menor e aleatória na paginação (dentro de um modelo)
            time.sleep(random.uniform(1.5, 3)) 
        except (TimeoutException, NoSuchElementException):
            print("Não há mais páginas. Fim da coleta para o modelo atual.")
            break # Sai do loop se o botão não for encontrado ou clicável

        except Exception as e:
            # Captura outros erros que podem ocorrer após a coleta bem-sucedida de uma página
            print(f"Coleta de links finalizada ou ocorreu um erro inesperado na paginação: {e}")
            break

# Fim do loop 'for' (ele irá para o próximo modelo)

# --- Passo 3: Salvar os dados em um arquivo CSV ---
print("\nSalvando os links coletados em um arquivo CSV...")
try:
    if todos_os_links_Adrenaline:
        # Usa DICTWRITER pois a lista de dados já está formatada como dicionário
        with open(caminho_saida, "w", newline="", encoding="utf-8") as file:
            fieldnames = ['Título', 'Link', 'Modelo Buscado']
            writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction='ignore') # 'ignore' para ignorar chaves extras, se houver
            writer.writeheader()
            writer.writerows(todos_os_links_Adrenaline)
        print(f"Dados salvos com sucesso em '{caminho_saida}'. Total de links únicos: {len(todos_os_links_Adrenaline)}")
    else:
        print("Nenhum link foi coletado para salvar.")

except Exception as e:
    print(f"Ocorreu um erro ao salvar o arquivo CSV: {e}")

# --- Passo 4: Encerrar o navegador ---
driver.quit()
print("Processo concluído. Navegador fechado.")