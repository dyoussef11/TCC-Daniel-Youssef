import sys
from pathlib import Path
import csv
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
import undetected_chromedriver as uc
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException
from selenium.webdriver.common.keys import Keys
import traceback
# --- Configuração de Caminhos e Módulos (Mantida) ---
# Obtém o caminho absoluto da pasta do script atual.
caminho_script = Path(__file__).resolve().parent

# Acessa a pasta raiz do projeto subindo dois níveis.
caminho_raiz_projeto = caminho_script.parent.parent

# Adiciona o caminho da raiz ao caminho de busca do Python.
sys.path.append(str(caminho_raiz_projeto))

# Agora a importação do módulo 'config' e 'modelo_de_busca' deve funcionar.
# Assumindo que essas importações são essenciais para o setup.

from config import DIRETORIO_DADOS_WEBSCRAPPING, DIRETORIO_CSV_DATASET_FINAL
from modelo_de_busca import ler_e_filtrar_modelos




caminho_saida = DIRETORIO_DADOS_WEBSCRAPPING / 'links_discussoes_Lenovo_Brasil.csv'
caminho_entrada = DIRETORIO_CSV_DATASET_FINAL / 'dataset_laptops.csv'
# Garante que os diretórios de saída existam
caminho_saida.parent.mkdir(parents=True, exist_ok=True)
caminho_entrada.parent.mkdir(parents=True, exist_ok=True)

# --- Configuração de Busca ---
MARCA_ALVO = 'LENOVO'

# Lê e filtra os modelos do CSV
modelos_a_buscar = ler_e_filtrar_modelos(caminho_entrada, MARCA_ALVO)

if not modelos_a_buscar:
    print(f"Não foram encontrados modelos para a marca '{MARCA_ALVO}' no arquivo CSV ou houve um erro na leitura. Saindo.")

# --- Configurações iniciais do Selenium (CORRIGIDAS) ---
chrome_options = Options()
# Adiciona os argumentos para execução em modo headless e otimizações
chrome_options.add_argument("--headless") # Modo Headless ativado
chrome_options.add_argument("--window-size=1920,1080")
chrome_options.add_argument("--blink-settings=imagesEnabled=false")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--no-sandbox") # Essencial para alguns ambientes headless

# Inicializa o driver corretamente com as opções headless
service = ChromeService(ChromeDriverManager().install())
driver = uc.Chrome(service=ChromeService(ChromeDriverManager().install()), options=chrome_options)
driver = uc.Chrome()
wait = WebDriverWait(driver, 30)

site_url = "https://forums.lenovo.com/t5/Comunidade-Lenovo/ct-p/community_pt?language=pt"



SELETOR_INPUT = 'input[id="searchInput"]'
 # Campo de texto da busca

SELETOR_BUSCA = 'button[class*="SearchBar-styles-left"]' # Botão de busca


SELETOR_COOKIE_LENOVO = 'button[id="_evidon-banner-acceptbutton"]'


SELETOR_LINKS_DISCUSSAO = 'a[class*="link-warpper"]'

#link_30


SELETOR_PROXIMA_PAGINA = '//a[@aria-label="Next Page"]' # NOVO: Seletor para os links individuais # NOVO: Seletor para os links individuais
all_discussion_links = []

all_discussion_links = []

# Função para salvar os links no CSV (mantida)
def salvar_links_csv(caminho, links):
    """Salva a lista de links no arquivo CSV."""
    with open(caminho, 'w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow(['Título da Discussão', 'Link da Discussão', 'Modelo Buscado'])
        for title, url, modelo in links:
            writer.writerow([title, url, modelo])
    print(f"\nLinks salvos com sucesso em {caminho}. Total de links: {len(links)}")


# --- LOOP PRINCIPAL: Itera sobre cada modelo lido do CSV ---
for i, modelo_de_busca in enumerate(modelos_a_buscar):
    termo_de_busca = f'{modelo_de_busca}'
    
    print(f"\n{'='*70}")
    print(f"INICIANDO BUSCA {i+1}/{len(modelos_a_buscar)}: Modelo '{modelo_de_busca}'")
    print(f"{'='*70}")

    driver.get(site_url)
    
    try:
        # 1. Fecha o pop-up de cookies se ele existir
        print("Verificando e fechando o pop-up de cookies...")
        try:
            cookie_button = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, SELETOR_COOKIE_LENOVO)))
            time.sleep(2) 
            cookie_button.click()
            print("Pop-up de cookies fechado.")
            
        except (TimeoutException, NoSuchElementException):
            print("Pop-up de cookies não encontrado ou já fechado.")
            pass
        
        # 2. Insere o termo de busca no campo de texto
        print("Aguardando e inserindo termo de busca...")
        barra_de_busca = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, SELETOR_INPUT)))
        barra_de_busca.clear()
        barra_de_busca.send_keys(termo_de_busca)
        barra_de_busca.send_keys(Keys.ENTER)
        time.sleep(1) 
        
        # --- INÍCIO DA EXTRAÇÃO DE LINKS ---
        print("\n--- INICIANDO COLETA DE LINKS ---")

        pagina_atual = 1
        while True:
            print(f"Coletando links da página {pagina_atual}...")
            
            # Tenta encontrar todos os links <a>
            try:
                # O seletor é CSS, então a busca deve ser By.CSS_SELECTOR, não By.CLASS_NAME
                discussion_elements = wait.until(
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, SELETOR_LINKS_DISCUSSAO))
                )
            except TimeoutException:
                print("Nenhum resultado encontrado nesta página (Timeout).")
                break 
            
            novos_links_coletados = 0
            for element in discussion_elements:
                
                link = element.get_attribute("href")
                title = element.text.strip().replace('\n', ' ') 
                
                if link and title:
                    item_data = (title, link, modelo_de_busca)
                    if item_data not in all_discussion_links:
                        all_discussion_links.append(item_data)
                        novos_links_coletados += 1
            
            print(f"Links coletados na Pág {pagina_atual}: {novos_links_coletados}. Total geral: {len(all_discussion_links)}")
            
            # Tenta salvar os links incrementalmente
            salvar_links_csv(caminho_saida, all_discussion_links)

            # Tenta encontrar o botão "Próximo" para a paginação
            try:
                # 1. Tenta encontrar o botão via XPATH
                next_button = WebDriverWait(driver, 2).until(
                    EC.element_to_be_clickable((By.XPATH, SELETOR_PROXIMA_PAGINA))
                )
                print("Clicando no botão 'Próximo' (tentativa normal)...")
                next_button.click()
                
                # Se o clique normal funcionar:
                pagina_atual += 1
                time.sleep(3)
            
            except ElementClickInterceptedException:
                # 2. SE O ERRO ElementClickInterceptedException OCORRER AQUI, FORÇA O JS
                print("Botão interceptado! Tentando clicar via JavaScript...")
                # O elemento 'next_button' já foi localizado no 'wait.until' acima
                driver.execute_script("arguments[0].click();", next_button)
                pagina_atual += 1
                time.sleep(3)
                
            except (TimeoutException, NoSuchElementException):
                # 3. Se não for encontrado, é o fim.
                print("Botão 'Próximo' não encontrado ou desabilitado. Fim da paginação.")
                break


    except Exception as e:
        print(f"Ocorreu um erro no loop principal para o modelo '{modelo_de_busca}': {e}")
        traceback.print_exc()

# --- FINALIZAÇÃO ---
print("\nProcesso de web scraping concluído.")
print("Aguardando 5 segundos antes de fechar o driver.")
time.sleep(5)
driver.quit()