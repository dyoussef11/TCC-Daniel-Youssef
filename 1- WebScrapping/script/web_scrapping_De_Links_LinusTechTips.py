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
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys

caminho_saida = DIRETORIO_DADOS_WEBSCRAPPING / 'links_discussoes_LinusTechTips.csv'

# Use undetected-chromedriver instead of standard Selenium
driver = uc.Chrome()
driver.maximize_window()
site_url = "https://linustechtips.com/search/"
driver.get(site_url)
termo_de_busca = '"g7 15 7588"'
wait = WebDriverWait(driver, 20)

try:
    print("Aguardando o campo de busca...")
    # The search bar on LTT has the name "q"
    barra_de_busca = wait.until(EC.presence_of_element_located((By.NAME, "q")))
    time.sleep(3)

    # Use ActionChains to interact with the element
    actions = ActionChains(driver)
    actions.move_to_element(barra_de_busca).click().send_keys(termo_de_busca).send_keys(Keys.ENTER).perform()
    print(f"Texto '{termo_de_busca}' inserido no campo de busca e a tecla Enter pressionada.")

    print("Pesquisa realizada com sucesso!")
    # A small pause for the results page to load
    time.sleep(5)

    all_results_data = []
    # --- STARTING DATA EXTRACTION ---
    print("\n--- INICIANDO COLETA DE TÍTULOS E LINKS ---")

    while True:
        try:
            # Correct selector for the links
            discussion_titles_elements = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "ol.ipsStream a[data-linktype='link']")))
            
            print("Coletando títulos e links da página atual...")
            for element in discussion_titles_elements:
                link = element.get_attribute("href")
                title = element.text.strip()
                
                result_data = {"title": title, "link": link}
                
                # Check for and prevent duplicate entries
                if result_data not in all_results_data:
                    all_results_data.append(result_data)
            
            print(f"Total de resultados coletados até agora: {len(all_results_data)}")

            # Try to find the "Next" button for pagination
            # The selector is for the <a> tag inside the li.pagination-next
            next_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "li.pagination-next a")))
            next_button.click()
            print("Clicando no botão 'Próximo'...")
            time.sleep(3)  # Pause for the new page to load

        except Exception as e:
            # This 'except' block handles the end of pagination and other errors
            print(f"Botão 'Próximo' não encontrado ou desabilitado. Fim da paginação. Detalhe do erro: {e}")
            break

    # --- SAVING DATA TO CSV ---
    
    with open(caminho_saida, 'w', newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, fieldnames=['title', 'link'])
        writer.writeheader()
        writer.writerows(all_results_data)

    print(f"\nDados salvos com sucesso em '{caminho_saida}'. Total de resultados: {len(all_results_data)}")
    
except Exception as e:
    print(f"Ocorreu um erro: {e}")
    import traceback
    traceback.print_exc()

finally:
    # Always close the browser
    print("Fechando o navegador...")
    driver.quit()