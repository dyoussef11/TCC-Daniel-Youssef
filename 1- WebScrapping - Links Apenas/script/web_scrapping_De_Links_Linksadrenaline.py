import sys
from pathlib import Path
import csv
import time
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
# Exemplo: 'C:\...\Buscar_Web\1- WebScrapping\script'
caminho_script = Path(__file__).resolve().parent

# Acessa a pasta raiz do projeto subindo dois níveis.
# Exemplo: 'C:\...\Buscar_Web'
caminho_raiz_projeto = caminho_script.parent.parent

# Adiciona o caminho da raiz ao caminho de busca do Python.
sys.path.append(str(caminho_raiz_projeto))

# Agora a importação do módulo 'config' e 'modelo_de_busca' deve funcionar.
from config import DIRETORIO_DADOS_WEBSCRAPPING, DIRETORIO_CSV_MODELOS_NOTEBOOKS
from modelo_de_busca import ler_e_filtrar_modelos

caminho_saida = DIRETORIO_DADOS_WEBSCRAPPING / 'links_discussoes_Adrenaline.csv'
caminho_entrada = DIRETORIO_CSV_MODELOS_NOTEBOOKS / 'modelos_de_busca.csv'

# --- Configuração de Busca e Filtro de CSV ---
# Se MARCA_ALVO for None ou '', todos os modelos do CSV serão usados.
# Para testar apenas a Dell: MARCA_ALVO = 'Dell'
MARCA_ALVO = None 

# Lê e filtra os modelos do CSV
modelos_a_buscar = ler_e_filtrar_modelos(caminho_entrada, MARCA_ALVO)

if not modelos_a_buscar:
    print(f"Não foram encontrados modelos para a marca '{MARCA_ALVO}' no arquivo CSV ou houve um erro na leitura. Saindo.")
    sys.exit()

# --- Configurações iniciais do Selenium (INTEGRANDO HEADLESS) ---
chrome_options = Options()
# Adiciona os argumentos para execução em modo headless e otimizações
chrome_options.add_argument("--headless")
chrome_options.add_argument("--window-size=1920,1080")
chrome_options.add_argument("--blink-settings=imagesEnabled=false")
chrome_options.add_argument("--disable-gpu")

# Inicializa o driver usando Service e Options
driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=chrome_options)
driver = webdriver.Chrome()
wait = WebDriverWait(driver, 30)

todos_os_links_Adrenaline = [] # Armazena {"Título": titulo, "Link": link, "Modelo Buscado": modelo}
contagem_links = 0
cookie_popup_fechado = False

site_url = "https://forum.adrenaline.com.br/search/?type=post"

# --- LOOP PRINCIPAL: Itera sobre cada modelo lido do CSV ---
for i, modelo_de_busca in enumerate(modelos_a_buscar):
    # Formata o termo de busca: o nome do modelo (o Adrenaline não suporta operadores AND/OR complexos no input inicial)
    termo_de_busca = modelo_de_busca 
    
    print(f"\n{'='*70}")
    print(f"INICIANDO BUSCA {i+1}/{len(modelos_a_buscar)}: Modelo '{modelo_de_busca}'")
    print(f"{'='*70}")
    
    # --- Passo 1: Realizar a busca ---
    try:
        print("Acessando a página do fórum e iniciando nova busca...")
        driver.get(site_url) # Volta para a página de notebooks para iniciar nova busca

        # Lida com o pop-up de cookies uma única vez
        if not cookie_popup_fechado:
             try:
                 cookie_button = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a.js-noticeDismiss")))
                 if cookie_button:
                     driver.execute_script("arguments[0].click();", cookie_button)
                     print("Aviso de cookies aceito.")
                     time.sleep(2)
                 cookie_popup_fechado = True
             except:
                 pass # Não encontrou o pop-up, assume que já está fechado

        # 1. SELEÇÃO DO FÓRUM "NOTEBOOKS" (FILTRO)
        print("Buscando e selecionando o campo 'Notebooks' no filtro...")
        select_element = wait.until(
            EC.presence_of_element_located((By.NAME, "c[nodes][]"))
        )
        forum_select = Select(select_element)
        forum_select.select_by_value("175")
        print("Filtro 'Notebooks' selecionado (value=175).")
        
        print("Pesquisa iniciada com sucesso! Aguardando a página de resultados...")
        time.sleep(3)
        
        print("Clicando no ícone de pesquisa...")
        search_icon = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a.p-navgroup-link--search")))
        search_icon.click()

        print(f"Inserindo o termo '{termo_de_busca}' e iniciando a pesquisa...")
        search_input = wait.until(EC.visibility_of_element_located((By.NAME, "keywords")))
        
        # Limpa o campo antes de enviar a nova busca
        search_input.clear()
        search_input.send_keys(termo_de_busca)
        search_input.send_keys(Keys.ENTER)

        

    except Exception as e:
        print(f"Erro na fase de busca inicial para '{modelo_de_busca}': {e}. Pulando para o próximo modelo.")
        continue # Pula para o próximo modelo

    # --- Passo 2: Coletar links de todas as páginas de resultados ---
    while True:
        try:
            # Aguarda a lista de resultados carregar
            wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "li.block-row.block-row--separated.js-inlineModContainer")))
            
            # Encontra todos os elementos que contêm os resultados da busca na página atual
            resultados = driver.find_elements(By.CSS_SELECTOR, "li.block-row.block-row--separated.js-inlineModContainer")
            
            novos_links_coletados = 0
            # Extrai os dados de cada resultado
            for resultado in resultados:
                try:
                    titulo_elemento = resultado.find_element(By.CSS_SELECTOR, "h3.contentRow-title a")
                    titulo = titulo_elemento.text.strip()
                    link = titulo_elemento.get_attribute("href")
                    
                    # Cria um identificador único baseado no link
                    item_identificador = link # Link como chave de unicidade
                    
                    # Garante que o link não foi coletado antes
                    if not any(item['Link'] == link for item in todos_os_links_Adrenaline):
                        todos_os_links_Adrenaline.append({
                            "Título": titulo, 
                            "Link": link, 
                            "Modelo Buscado": modelo_de_busca
                        })
                        contagem_links += 1
                        novos_links_coletados += 1
                        # print(f"Coletado ({contagem_links}): {titulo} -> {link}")
                except NoSuchElementException:
                    continue # Não foi possível extrair um link (elemento não encontrado)
                except Exception as e:
                    print(f"Erro ao extrair link em resultado individual: {e}")
                    continue
            
            print(f"Página processada. Novos links: {novos_links_coletados}. Total acumulado: {len(todos_os_links_Adrenaline)}")

            # Tenta encontrar o botão "Próxima"
            print("Procurando o botão 'Próxima' página...")
            try:
                # O EC deve usar o seletor do link dentro do pageNav-jump--next, se for o caso
                proxima_pagina_link = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a.pageNav-jump.pageNav-jump--next")))
                
                print("Navegando para a próxima página...")
                driver.execute_script("arguments[0].click();", proxima_pagina_link)
                time.sleep(3) # Pausa para a nova página carregar
            except (TimeoutException, NoSuchElementException):
                print("Não há mais páginas. Fim da coleta para o modelo atual.")
                break # Sai do loop se o botão não for encontrado ou clicável

        except Exception as e:
            print(f"Coleta de links finalizada ou ocorreu um erro inesperado: {e}")
            break

# --- Passo 3: Salvar os dados em um arquivo CSV ---
print("\nSalvando os links coletados em um arquivo CSV...")
try:
    if todos_os_links_Adrenaline:
        with open(caminho_saida, "w", newline="", encoding="utf-8") as file:
            fieldnames = ["Título", "Link", "Modelo Buscado"]
            writer = csv.DictWriter(file, fieldnames=fieldnames)
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
