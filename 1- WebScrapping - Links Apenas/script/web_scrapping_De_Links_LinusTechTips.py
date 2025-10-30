import sys
from pathlib import Path
import csv
import time
import random # [MODIFICAÇÃO] Importar random para pausas aleatórias
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.chrome.options import Options
import traceback # Importar para melhor rastreamento de erro
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager

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
# Termo de busca FIXO para este exemplo.
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
# [MODIFICAÇÃO] Adicionar options para configurar o driver (como headless)
chrome_options = Options()
# [MODIFICAÇÃO] Ativar modo headless para maior velocidade
chrome_options.add_argument("--headless") 
chrome_options.add_argument("--window-size=1920,1080")
chrome_options.add_argument("--blink-settings=imagesEnabled=false")
chrome_options.add_argument("--disable-gpu")
# [MODIFICAÇÃO] Adicionar User-Agent para simular um navegador normal
chrome_options.add_argument(f"user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.75 Safari/537.36")


# Inicializa o driver APENAS UMA VEZ.
driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=chrome_options)
# [MODIFICAÇÃO] Reduzir o tempo de espera padrão de 30s para 15s (mais ágil no headless)
wait = WebDriverWait(driver, 15)
# [MODIFICAÇÃO] Remoção de driver.maximize_window() para otimização de performance.
driver.get(SITE_URL)
# [MODIFICAÇÃO] Reduzir o tempo de espera de 20s para 15s (ainda robusto, mas mais rápido)
wait = WebDriverWait(driver, 15)

try:
    print("Aguardando o campo de busca...")
    # Usa a constante de seletor (By.NAME)
    barra_de_busca = wait.until(EC.presence_of_element_located((By.NAME, SELETOR_CAMPO_BUSCA)))
    # [MODIFICAÇÃO] Remover time.sleep(3). O wait já garantiu a presença do elemento.

    # Usa ActionChains para interagir com o elemento
    actions = ActionChains(driver)
    # Usa a constante TERMO_DE_BUSCA
    actions.move_to_element(barra_de_busca).click().send_keys(TERMO_DE_BUSCA).send_keys(Keys.ENTER).perform()
    print(f"Texto '{TERMO_DE_BUSCA}' inserido no campo de busca e a tecla Enter pressionada.")

    print("Pesquisa realizada com sucesso!")
    # [MODIFICAÇÃO] Remover time.sleep(5). O próximo wait (presence_of_all_elements_located) cuidará da espera.

    all_results_data = []
    # --- INICIANDO EXTRAÇÃO DE DADOS ---
    print("\n--- INICIANDO COLETA DE TÍTULOS E LINKS ---")

    while True:
        try:
            # Usa a constante de seletor. Timeout de 10s para a lista de resultados.
            discussion_titles_elements = WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, SELETOR_LINKS_RESULTADO))
            )
            
            # Se não encontrar resultados, o loop de paginação irá parar, mas verificamos explicitamente:
            if not discussion_titles_elements and ('page=1' in driver.current_url or 'search/?type=post' in driver.current_url):
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
            
            # [MODIFICAÇÃO] Usar pausa aleatória na paginação (Anti-Bloqueio/Simulação Humana)
            sleep_time = random.uniform(2, 4) 
            time.sleep(sleep_time)
            print(f"Pausa de {sleep_time:.2f} segundos para carregamento.") 

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
    traceback.print_exc()

finally:
    # Always close the browser
    print("Fechando o navegador...")
    driver.quit()