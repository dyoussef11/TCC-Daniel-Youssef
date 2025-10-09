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
caminho_saida = DIRETORIO_DADOS_WEBSCRAPPING / 'links_discussoes_ClubeHardware.csv'

import csv
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- Passo 1: Configurar e Abrir o Navegador ---
driver = webdriver.Chrome()
driver.maximize_window()
termo_de_busca = "g7 15 7588"

# --- Passo 2: Acessar o Site e Fazer a Busca ---
site_url = "https://www.clubedohardware.com.br/search/"
driver.get(site_url)
wait = WebDriverWait(driver, 20)

print(f"Página acessada: {site_url}. Aguardando o carregamento...")

try:
    # --- A: Tratar o Pop-up de Anúncio ---
    try:
        print("Verificando se há um pop-up de anúncio...")
        close_ad_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "span.__lxG__splash-close")))
        close_ad_btn.click()
        print("Pop-up de anúncio fechado.")
        time.sleep(2)
    except:
        print("Nenhum pop-up de anúncio encontrado ou ele já foi fechado.")
        pass
    
    # --- B: Clicar na opção "Contenham todas as palavras" ---
    # Encontra o label associado ao input de rádio e clica nele.
    print("Selecionando a opção 'Contenham todas as palavras'...")
    radio_button_label = wait.until(EC.element_to_be_clickable((By.ID, "elField_andOr_full_label_and")))
    radio_button_label.click()
    print("Opção selecionada.")

    # --- C: Achar o campo de busca e preencher com o texto ---
    print("Aguardando o campo de busca...")

    # Espera até que o campo de busca esteja visível e clicável
    barra_de_busca = wait.until(EC.element_to_be_clickable((By.NAME, "q")))

    # Clica no campo para dar o foco, depois limpa e digita
    barra_de_busca.click()
    barra_de_busca.clear()
    barra_de_busca.send_keys(termo_de_busca)

    print(f"Texto '{termo_de_busca}' inserido no campo de busca.")
    # --- D: Pressionar Enter para iniciar a busca ---
    barra_de_busca.send_keys(Keys.ENTER)
    print("Tecla ENTER pressionada. Pesquisa iniciada com sucesso!")

    # --- INÍCIO DA EXTRAÇÃO DE LINKS ---
    print("\n--- INICIANDO COLETA DE LINKS ---")
    all_results = [] # Armazena tuplas de (titulo, link)

    while True:
        print("Coletando links e títulos da página atual...")
        
        try:
            # Use a more specific CSS selector for the search result links
            # This selector targets the <a> tag inside a div with class 'ipsType_break'
            discussion_links = wait.until(
    EC.presence_of_all_elements_located((By.CSS_SELECTOR, "a[data-linktype='link'][data-searchable]"))
)

            for link_element in discussion_links:
                title = link_element.text.strip()
                url = link_element.get_attribute("href")
                
                # Check if the title is not empty and it's not a duplicate
                if title and (title, url) not in all_results:
                    all_results.append((title, url))
            
            print(f"Total de resultados coletados até agora: {len(all_results)}")
            time.sleep(40)
            # Tenta encontrar o botão "Próximo"
            next_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "li.ipsPagination_next a")))
            print("Clicando no botão 'Próximo'...")
            next_button.click()
            time.sleep(3) # Pausa para a página carregar
        
        except Exception as e:
            print(f"Botão 'Próximo' não encontrado ou desabilitado. Fim da paginação. Erro: {e}")
            break

    # Salva os resultados em um arquivo CSV
    print("\n--- SALVANDO RESULTADOS ---")
    with open(caminho_saida, 'w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow(['Título da Discussão', 'Link da Discussão']) # Cabeçalho do CSV
        for title, url in all_results:
            writer.writerow([title, url])

    print(f"\nResultados salvos com sucesso em {caminho_saida}. Total de resultados: {len(all_results)}")
        
        
except Exception as e:
    print(f"Ocorreu um erro durante a busca: {e}")

# --- Passo 3: Esperar e Encerrar o Navegador ---
# print("Aguardando 60 segundos para visualização do resultado...")
# time.sleep(60)
print("Fechando o navegador.")
driver.quit()