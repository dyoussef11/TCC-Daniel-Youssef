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

import csv
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys

caminho_saida = DIRETORIO_DADOS_WEBSCRAPPING / 'links_discussoes_Tom_Guide.csv'
driver = webdriver.Chrome()
driver.maximize_window()
site_url = "https://forums.tomsguide.com/search/"
driver.get(site_url)
termo_de_busca = "g7 15 7588"
wait = WebDriverWait(driver, 20)

print("Aguardando o campo de busca...")
barra_de_busca = wait.until(EC.presence_of_element_located((By.NAME, "keywords")))

# Use ActionChains to interact with the element and press ENTER
actions = ActionChains(driver)
actions.move_to_element(barra_de_busca).click().send_keys(termo_de_busca).send_keys(Keys.ENTER).perform()
print(f"Texto '{termo_de_busca}' inserido no campo de busca e a tecla Enter pressionada.")

print("Pesquisa realizada com sucesso!")
time.sleep(3) # A small pause to ensure the page has loaded

all_results = []
# --- INÍCIO DA EXTRAÇÃO DE DADOS ---
print("\n--- INICIANDO COLETA DE TÍTULOS E LINKS ---")

while True:
    try:
        # Correctly target the 'h3' element that contains the link and title
        discussion_titles = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "h3.contentRow-title a")))
        
        print("Coletando títulos e links da página atual...")
        for element in discussion_titles:
            link = element.get_attribute("href")
            title = element.text.strip()
            
            # Use a dictionary to store both pieces of data
            result_data = {"title": title, "link": link}
            
            # Ensure the link isn't duplicated
            if result_data not in all_results:
                all_results.append(result_data)
        
        print(f"Total de resultados coletados até agora: {len(all_results)}")

        # Try to find the "Next" button for pagination
        next_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "li.pagination-next a")))
        next_button.click()
        print("Clicando no botão 'Próximo'...")
        time.sleep(3) # Pause for the new page to load

    except:
        print("Botão 'Próximo' não encontrado ou desabilitado. Fim da paginação.")
        break

# Salva os links e títulos em um arquivo CSV

with open(caminho_saida, 'w', newline='', encoding='utf-8') as file:
    writer = csv.DictWriter(file, fieldnames=['title', 'link'])
    writer.writeheader() # Write the headers
    writer.writerows(all_results)
    
print(f"\nDados salvos com sucesso em '{caminho_saida}'. Total de resultados: {len(all_results)}")

driver.quit()