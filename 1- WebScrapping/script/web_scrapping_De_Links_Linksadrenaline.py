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
from config import DIRETORIO_DADOS_WEBSCRAPPING
caminho_saida = DIRETORIO_DADOS_WEBSCRAPPING / 'links_discussoes_Adrenaline.csv'

import time
import csv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# --- Configurações iniciais ---
driver = webdriver.Chrome()
driver.maximize_window()
termo_de_busca = "g7 15 7588"
wait = WebDriverWait(driver, 30)

# Lista para armazenar todos os dados coletados
todos_os_links_Adrenaline = []
contagem_links = 0

# --- Passo 1: Realizar a busca inicial ---
try:
    print("Acessando a página de notebooks do fórum...")
    driver.get("https://forum.adrenaline.com.br/forums/notebooks.175/")

    print("Clicando no ícone de pesquisa...")
    search_icon = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a.p-navgroup-link--search")))
    search_icon.click()

    print(f"Inserindo o termo '{termo_de_busca}' e iniciando a pesquisa...")
    search_input = wait.until(EC.visibility_of_element_located((By.NAME, "keywords")))
    search_input.send_keys(termo_de_busca)
    
    # Submete a pesquisa pressionando Enter
    search_input.send_keys(Keys.ENTER)
    
    print("Pesquisa iniciada com sucesso! Aguardando a página de resultados...")

except Exception as e:
    print(f"Erro na fase de busca inicial: {e}")
    driver.quit()
    exit()

# --- Passo 2: Coletar links de todas as páginas de resultados ---
while True:
    try:
        # Tenta lidar com o pop-up de cookies se ele aparecer antes de cada iteração
        try:
            print("Verificando se o aviso de cookies está presente...")
            # Use um tempo de espera menor para não travar o script se o pop-up não estiver lá
            cookie_button = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a.js-noticeDismiss")))
            if cookie_button:
                # Usa JavaScript para clicar no botão, evitando intercepções
                driver.execute_script("arguments[0].click();", cookie_button)
                print("Aviso de cookies aceito. Continuar a navegação...")
                time.sleep(2) # Pequena pausa para o pop-up desaparecer
        except TimeoutException:
            print("Aviso de cookies não encontrado, prosseguindo.")
        except Exception as e:
            print(f"Ocorreu um erro ao tentar fechar o aviso de cookies: {e}")
            pass

        # Aguarda a lista de resultados carregar
        wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "li.block-row.block-row--separated.js-inlineModContainer")))
        
        # Encontra todos os elementos que contêm os resultados da busca na página atual
        resultados = driver.find_elements(By.CSS_SELECTOR, "li.block-row.block-row--separated.js-inlineModContainer")
        
        # Extrai os dados de cada resultado
        for resultado in resultados:
            try:
                titulo_elemento = resultado.find_element(By.CSS_SELECTOR, "h3.contentRow-title a")
                titulo = titulo_elemento.text.strip()
                link = titulo_elemento.get_attribute("href")
                todos_os_links_Adrenaline.append({"Título": titulo, "Link": link})
                contagem_links += 1
                print(f"Coletado ({contagem_links}): {titulo} -> {link}")
            except NoSuchElementException:
                print("Não foi possível extrair um link (elemento não encontrado), pulando...")
                continue
            except Exception as e:
                print(f"Não foi possível extrair um link. Erro: {e}")
                continue

        # Tenta encontrar o botão "Próxima"
        print("Procurando o botão 'Próxima' página...")
        try:
            proxima_pagina_link = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a.pageNav-jump.pageNav-jump--next")))
            
            print("Navegando para a próxima página...")
            # Usa JavaScript para forçar o clique no botão "Próxima"
            driver.execute_script("arguments[0].click();", proxima_pagina_link)
            time.sleep(3) # Pausa para a nova página carregar
        except (TimeoutException, NoSuchElementException):
            print("Não há mais páginas. Coleta concluída.")
            break # Sai do loop se o botão não for encontrado ou clicável

    except Exception as e:
        print(f"Coleta de links finalizada ou ocorreu um erro inesperado: {e}")
        break

# --- Passo 3: Salvar os dados em um arquivo CSV ---
print("\nSalvando os links coletados em um arquivo CSV...")
try:
    with open(caminho_saida, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=["Título", "Link"])
        writer.writeheader()
        writer.writerows(todos_os_links_Adrenaline)
    print(f"Dados salvos com sucesso em '{caminho_saida}'. Total de links: {len(todos_os_links_Adrenaline)}")
except Exception as e:
    print(f"Ocorreu um erro ao salvar o arquivo CSV: {e}")

# --- Passo 4: Encerrar o navegador ---
driver.quit()
print("Processo concluído. Navegador fechado.")