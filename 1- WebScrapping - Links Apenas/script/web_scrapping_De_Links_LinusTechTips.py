import sys
from pathlib import Path
import csv
import time
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# Obtém o caminho absoluto da pasta do script atual.
caminho_script = Path(__file__).resolve().parent

# Acessa a pasta raiz do projeto subindo dois níveis.
caminho_raiz_projeto = caminho_script.parent.parent

# Adiciona o caminho da raiz ao caminho de busca do Python.
sys.path.append(str(caminho_raiz_projeto))

# Agora a importação do módulo 'config' deve funcionar.
from config import DIRETORIO_DADOS_WEBSCRAPPING


# --- CONSTANTES DE CONFIGURAÇÃO E DADOS ---
SITE_URL = "https://linustechtips.com/search/"
# Termo de busca FIXO para este exemplo. Se precisar de loop, mova a atribuição.
TERMO_DE_BUSCA = '"g7 15 7588"' 
CAMPO_MODELO_BUSCADO_FIXO = TERMO_DE_BUSCA.replace('"', '') # Valor que será salvo no CSV

# --- DECLARAÇÕES DE HTML EM VARIÁVEIS (Seletores) ---
# Selenium (By.NAME)
SELETOR_CAMPO_BUSCA = "q" 

# Selenium (By.CSS_SELECTOR)
SELETOR_LINKS_RESULTADO = "ol.ipsStream a[data-linktype='link']"
SELETOR_BOTAO_PROXIMA_PAGINA = "li.pagination-next a"


caminho_saida = DIRETORIO_DADOS_WEBSCRAPPING / 'links_discussoes_LinusTechTips.csv'

# Use undetected-chromedriver instead of standard Selenium
driver = uc.Chrome()
driver.maximize_window()
driver.get(SITE_URL)
wait = WebDriverWait(driver, 20)

try:
    print("Aguardando o campo de busca...")
    # Usa a constante de seletor (By.NAME)
    barra_de_busca = wait.until(EC.presence_of_element_located((By.NAME, SELETOR_CAMPO_BUSCA)))
    time.sleep(3)

    # Usa ActionChains para interagir com o elemento
    actions = ActionChains(driver)
    # Usa a constante TERMO_DE_BUSCA
    actions.move_to_element(barra_de_busca).click().send_keys(TERMO_DE_BUSCA).send_keys(Keys.ENTER).perform()
    print(f"Texto '{TERMO_DE_BUSCA}' inserido no campo de busca e a tecla Enter pressionada.")

    print("Pesquisa realizada com sucesso!")
    time.sleep(5)

    all_results_data = []
    # --- INICIANDO EXTRAÇÃO DE DADOS ---
    print("\n--- INICIANDO COLETA DE TÍTULOS E LINKS ---")

    while True:
        try:
            # Usa a constante de seletor
            discussion_titles_elements = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, SELETOR_LINKS_RESULTADO)))
            
            # Se não encontrar resultados, o loop de paginação irá parar, mas verificamos explicitamente:
            if not discussion_titles_elements and driver.current_url.endswith("page=1"):
                print("Zero resultados encontrados na primeira página. Finalizando coleta.")
                break

            novos_links = 0
            print("Coletando títulos e links da página atual...")
            for element in discussion_titles_elements:
                link = element.get_attribute("href")
                title = element.text.strip()
                
                result_data = {
                    "Título da Discussão": title, 
                    "Link da Discussão": link,
                    "Modelo Buscado": CAMPO_MODELO_BUSCADO_FIXO # Adiciona a informação do modelo buscado
                }
                
                # Check for and prevent duplicate entries based on link
                if not any(d['Link da Discussão'] == link for d in all_results_data):
                    all_results_data.append(result_data)
                    novos_links += 1
            
            print(f"Novos links coletados: {novos_links}. Total de resultados coletados até agora: {len(all_results_data)}")

            # Tenta encontrar o botão "Próximo" para paginação
            # Usa a constante de seletor
            next_button = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.CSS_SELECTOR, SELETOR_BOTAO_PROXIMA_PAGINA)))
            
            # Clica via JS para maior robustez
            driver.execute_script("arguments[0].click();", next_button)
            print("Clicando no botão 'Próximo'...")
            time.sleep(3)  # Pause for the new page to load

        except TimeoutException as e:
            # Captura o Timeout se o botão 'Próximo' não aparecer (fim da paginação)
            print(f"Botão 'Próximo' não encontrado ou tempo de espera esgotado. Fim da paginação.")
            break
        except Exception as e:
            print(f"Ocorreu um erro durante a coleta/paginação. Finalizando. Detalhe do erro: {e}")
            break

    # --- SALVANDO DADOS EM CSV ---
    if all_results_data:
        with open(caminho_saida, 'w', newline='', encoding='utf-8') as file:
            fieldnames = ['Título da Discussão', 'Link da Discussão', 'Modelo Buscado']
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_results_data)

        print(f"\nDados salvos com sucesso em '{caminho_saida}'. Total de resultados: {len(all_results_data)}")
    else:
        print("\nNenhum resultado foi coletado para salvar.")
        
except Exception as e:
    print(f"Ocorreu um erro FATAL: {e}")
    import traceback
    traceback.print_exc()

finally:
    # Always close the browser
    print("Fechando o navegador...")
    driver.quit()