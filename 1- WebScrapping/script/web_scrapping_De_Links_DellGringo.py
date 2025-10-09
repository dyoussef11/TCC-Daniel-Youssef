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
caminho_saida = DIRETORIO_DADOS_WEBSCRAPPING / 'links_ComunidadeDell_Gringa_7588.csv'


import csv
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys

driver = webdriver.Chrome()
driver.maximize_window()
site_url = "https://www.dell.com/community/en/categories/dell-community"
driver.get(site_url)
termo_de_busca = ' "g7" AND "15" AND "7588"'
wait = WebDriverWait(driver, 20)

try:
    # Fecha o pop-up de cookies se ele existir
    try:
        cookie_button = wait.until(EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler")))
        cookie_button.click()
        time.sleep(2)
    except:
        pass

    print("Aguardando o campo de busca...")
    barra_de_busca = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input.search-input__input")))
    
    # Usa ActionChains para interagir com o elemento
    actions = ActionChains(driver)
    actions.move_to_element(barra_de_busca).click().send_keys(termo_de_busca).perform()
    print(f"Texto '{termo_de_busca}' inserido no campo de busca usando ActionChains.")
    
    print("Aguardando o botão de busca...")
    botao_de_busca = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".search-input__submit-button-lg.search-input__submit-button__right")))
    botao_de_busca.click()
    
    print("Pesquisa realizada com sucesso!")
    time.sleep(3)

    # --- FILTRO DE TIPO DE CONVERSA ---
    print("Aguardando o dropdown de 'Tipo de conversa'...")
    tipo_de_conversa_dropdown = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".conversation-types-filter__dropdown .Select-control")))
    tipo_de_conversa_dropdown.click()
    
    print("Dropdown de 'Tipo de conversa' clicado.")
    
    print("Aguardando a opção 'Posts'...")
    publicacoes_option = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[contains(@class, 'Select-option') and contains(., 'Posts')]")))
    publicacoes_option.click()
    print("Opção 'Posts' selecionada.")
    time.sleep(2)
    
    all_discussion_links = []
    # --- INÍCIO DA EXTRAÇÃO DE LINKS ---
    print("\n--- INICIANDO COLETA DE LINKS ---")

    while True:
        # Extrai os links da página atual, filtrando por links com o atributo 'title'
        print("Coletando links da página atual...")
        discussion_elements = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "section.conversation-card .conversation-card__details a[title]")))
        
        for element in discussion_elements:
            link = element.get_attribute("href")
            if link:
                # Garante que o link não seja duplicado na lista
                if link not in all_discussion_links:
                    all_discussion_links.append(link)
        
        print(f"Total de links coletados até agora: {len(all_discussion_links)}")

        # Tenta encontrar o botão "Próximo"
        try:
            next_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "li.pagination-next:not(.pagination-disabled)")))
            print("Clicando no botão 'Próximo'...")
            next_button.click()
            time.sleep(3) # Pausa para a página carregar
        except:
            print("Botão 'Próximo' não encontrado ou desabilitado. Fim da paginação.")
            break

        # Salva os links em um arquivo CSV
        with open(caminho_saida, 'w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow(['Link da Discussão']) # Cabeçalho do CSV
            for link in all_discussion_links:
                writer.writerow([link])
        
        print(f"\nLinks salvos com sucesso em {caminho_saida}. Total de links: {len(all_discussion_links)}")
    
    
except Exception as e:
    print(f"Ocorreu um erro: {e}")
    import traceback
    traceback.print_exc()

print("Aguardando 30 segundos para visualização do resultado...")
time.sleep(30)
driver.quit()