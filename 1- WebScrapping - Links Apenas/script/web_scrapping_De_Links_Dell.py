import sys
from pathlib import Path
import csv
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# Obtém o caminho absoluto da pasta do script atual.
caminho_script = Path(__file__).resolve().parent
# Acessa a pasta raiz do projeto subindo dois níveis.
caminho_raiz_projeto = caminho_script.parent.parent
# Adiciona o caminho da raiz ao caminho de busca do Python.
sys.path.append(str(caminho_raiz_projeto))

# Agora a importação do módulo 'config' e 'modelo_de_busca' deve funcionar.
from config import DIRETORIO_DADOS_WEBSCRAPPING, DIRETORIO_CSV_DATASET_FINAL
from modelo_de_busca import ler_e_filtrar_modelos

DIRETORIO_DADOS_WEBSCRAPPING.mkdir(parents=True, exist_ok=True)
caminho_saida = DIRETORIO_DADOS_WEBSCRAPPING / 'links_discussoes_Dell_Brasil.csv'
caminho_entrada = DIRETORIO_CSV_DATASET_FINAL / 'dataset_laptops.csv'

# --- Configuração de Busca e Filtro de CSV ---
# Buscando apenas modelos da Dell.
MARCA_ALVO = 'DELL'

# Lê e filtra os modelos do CSV
modelos_a_buscar = ler_e_filtrar_modelos(caminho_entrada, MARCA_ALVO)

if not modelos_a_buscar:
    print(f"Não foram encontrados modelos para a marca '{MARCA_ALVO}' no arquivo CSV ou houve um erro na leitura. Saindo.")
    sys.exit()

# --- Configurações iniciais do Selenium ---
chrome_options = Options()
# chrome_options.add_argument("--headless")
chrome_options.add_argument("--window-size=1920,1080")
chrome_options.add_argument("--blink-settings=imagesEnabled=false")
chrome_options.add_argument("--disable-gpu")

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install())) # Modo Normal (sem headless)

# Usamos um wait mais longo, já que a busca por vários modelos levará tempo
wait = WebDriverWait(driver, 30)

site_url = "https://www.dell.com/community/pt/categories/comunidade-da-dell"

all_discussion_links = [] # Armazena tuplas de (titulo, link, modelo_buscado)
cookie_popup_fechado = False

# --- SELETORES EM VARIÁVEIS (Novo e Atualizado) ---
SELETOR_DIGITAR = "input[placeholder='O que você está procurando?']"
SELETOR_NEXT_BUTTON = 'li[title="Próximo"]'
SELETOR_BUSCA = ".search-input__submit-button-lg.search-input__submit-button__right"
SELETOR_COOKIE = "onetrust-accept-btn-handler"
# Tipo de Conversa
SELETOR_DROPDOWN_TIPO_CONVERSA = ".conversation-types-filter__dropdown .Select-control"
SELETOR_OPCAO_PUBLICACOES = "//div[contains(@class, 'Select-option') and contains(., 'Publicações')]"
# Categoria
SELETOR_CONTAINER_FILTRO_CATEGORIA = ".category-hierarchy-filter"
SELETOR_OPCAO_NOTEBOOKS_LAPTOPS = "//div[contains(@class, 'category-hierarchy-filter__option') and normalize-space(.)='Notebooks/Laptops']"
# Elementos de Discussão
SELETOR_ELEMENTOS_DISCUSSAO = "section.conversation-card .conversation-card__details a[title]"


# --- LOOP PRINCIPAL: Itera sobre cada modelo lido do CSV ---
for i, modelo_de_busca in enumerate(modelos_a_buscar):
    # Formata o termo para busca avançada
    termo_de_busca = f'"{modelo_de_busca}"'
    links_modelo_atual = 0 # Variável para contar links encontrados NESTE modelo
    
    print(f"\n{'='*70}")
    print(f"INICIANDO BUSCA {i+1}/{len(modelos_a_buscar)}: Modelo '{modelo_de_busca}' com termo: {termo_de_busca}")
    print(f"{'='*70}")

    driver.get(site_url)

    try:
        # Fecha o pop-up de cookies se ele existir (apenas na primeira iteração)
        if not cookie_popup_fechado:
            try:
                cookie_button = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.ID, SELETOR_COOKIE)))
                cookie_button.click()
                time.sleep(2)
                cookie_popup_fechado = True
            except:
                pass
        
        # =========================================================
        # INSERÇÃO E BUSCA (Lógica de Re-captura para Stale Element)
        # =========================================================
        print("Aguardando o campo de busca...")
        
        # 1. CAPTURA INICIAL E ATIVAÇÃO
        barra_de_busca = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, SELETOR_DIGITAR))
        )
        barra_de_busca.click()

        # 2. RE-CAPTURA DO ELEMENTO (Se for Stale após o clique)
        barra_de_busca_atualizada = driver.find_element(By.CSS_SELECTOR, SELETOR_DIGITAR)
        
        # 3. INSERÇÃO DE TEXTO
        barra_de_busca_atualizada.clear()
        barra_de_busca_atualizada.send_keys(termo_de_busca)
        
        print(f"Texto '{termo_de_busca}' inserido no campo de busca.")
        
        # 4. Clica no botão de busca
        print("Aguardando o botão de busca...")
        botao_de_busca = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, SELETOR_BUSCA)))
        botao_de_busca.click()
        
        print("Pesquisa realizada com sucesso! Aguardando resultados...")
        time.sleep(3)

        # --- FILTRO DE TIPO DE CONVERSA (PUBLICACÕES) ---
        print("Aguardando o dropdown de 'Tipo de conversa'...")
        tipo_de_conversa_dropdown = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, SELETOR_DROPDOWN_TIPO_CONVERSA))
        )
        tipo_de_conversa_dropdown.click()
        
        print("Dropdown de 'Tipo de conversa' clicado.")
        
        print("Aguardando a opção 'Publicações'...")
        publicacoes_option = wait.until(EC.element_to_be_clickable((By.XPATH, SELETOR_OPCAO_PUBLICACOES)))
        publicacoes_option.click()
        print("Opção 'Publicações' selecionada.")
        time.sleep(2)


        # --- FILTRO DE CATEGORIA (NOTEBOOKS/LAPTOPS) ---
        print("\n--- APLICANDO FILTRO DE CATEGORIA ---")
        
        # 1. Clica no contêiner do filtro (para abri-lo)
        print("Aguardando o contêiner do filtro de categoria...")
        filtro_categoria_container = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, SELETOR_CONTAINER_FILTRO_CATEGORIA)) 
        )
        filtro_categoria_container.click()
        print("Dropdown de Categoria clicado.")
        
        # 2. Clica na opção "Notebooks/Laptops"
        print("Aguardando a opção 'Notebooks/Laptops'...")
        
        time.sleep(2)
        laptops_option = wait.until(
            EC.element_to_be_clickable((By.XPATH, SELETOR_OPCAO_NOTEBOOKS_LAPTOPS))
        )
        laptops_option.click() # Clica no elemento
        
        # Clica via JavaScript para garantir o clique
        # driver.execute_script("arguments[0].click();", laptops_option) # Removi a duplicação do clique para evitar instabilidade.
        print("Opção 'Notebooks/Laptops' selecionada e filtro aplicado.")

        time.sleep(3) # Aumentei o tempo para garantir que os resultados com o filtro carreguem.
        
        # --- INÍCIO DA EXTRAÇÃO DE LINKS ---
        print("\n--- INICIANDO COLETA DE LINKS ---")
        
        pagina_atual = 1
        while True:
            # Extrai os links da página atual
            print(f"Coletando links da página {pagina_atual}...")
            
            # **NOVA LÓGICA DE DETECÇÃO DE ZERO RESULTADOS**
            try:
                # Tenta esperar que PELO MENOS um elemento de discussão esteja presente
                discussion_elements = wait.until(
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, SELETOR_ELEMENTOS_DISCUSSAO))
                )
            except TimeoutException:
                # Se o timeout ocorrer, significa que não há elementos de discussão visíveis.
                discussion_elements = []

            # Se nenhum elemento for encontrado, verifica o estado da busca
            if not discussion_elements:
                print(f"Nenhum elemento de discussão encontrado na página {pagina_atual}.")
                
                # Se for a primeira página e não houver links, pula para o próximo modelo.
                if pagina_atual == 1:
                    print(f"**ALERTA: Zero resultados para o modelo '{modelo_de_busca}'. Pulando para o próximo modelo.**")
                    # **PULA PARA O PRÓXIMO MODELO NO LOOP FOR**
                    break # Sai do loop while True de paginação
                else:
                    # Se não há links, mas não é a primeira página (significa que a paginação parou)
                    break 

            
            novos_links_coletados = 0
            for element in discussion_elements:
                link = element.get_attribute("href")
                title = element.get_attribute("title")
                
                if link and title:
                    item_data = (title, link, modelo_de_busca)
                    # Garante que o link não seja duplicado na lista global
                    if item_data not in all_discussion_links:
                        all_discussion_links.append(item_data)
                        novos_links_coletados += 1
                        links_modelo_atual += 1 # Contabiliza para o modelo atual
            
            print(f"Novos links coletados nesta página: {novos_links_coletados}. Total acumulado: {len(all_discussion_links)}. Total para o modelo atual: {links_modelo_atual}")

            # Tenta encontrar o botão "Próximo"
            try:
                # Diminui o timeout aqui, pois esperamos que o botão seja rápido (ou não exista)
                next_button = WebDriverWait(driver, 2).until(EC.element_to_be_clickable((By.CSS_SELECTOR, SELETOR_NEXT_BUTTON)))
                
                # Verifica se o botão está desabilitado (pode ter uma classe 'disabled' ou atributo)
                if 'disabled' in next_button.get_attribute('class'):
                     raise Exception("Botão 'Próximo' desabilitado.")

                print("Clicando no botão 'Próximo'...")
                driver.execute_script("arguments[0].click();", next_button)
                pagina_atual += 1
                time.sleep(3) # Pausa para a página carregar
            except Exception:
                print("Botão 'Próximo' não encontrado ou desabilitado. Fim da paginação para o modelo atual.")
                break # Sai do loop while True

    except Exception as e:
        print(f"Ocorreu um erro FATAL na busca pelo modelo '{modelo_de_busca}': {e}")
        import traceback
        traceback.print_exc()
        continue # Pula para o próximo modelo no loop FOR (se for um erro inesperado)
    

# --- FIM DO LOOP ---

# Salva TODOS os resultados acumulados em um único arquivo CSV
if all_discussion_links:
    print("\n--- SALVANDO TODOS OS RESULTADOS ACUMULADOS ---")
    with open(caminho_saida, 'w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow(['Título da Discussão', 'Link da Discussão', 'Modelo Buscado']) # Cabeçalho do CSV
        for title, url, modelo in all_discussion_links:
            writer.writerow([title, url, modelo])

    print(f"\nResultados salvos com sucesso em {caminho_saida}. Total de resultados: {len(all_discussion_links)}")
else:
    print("Nenhum resultado foi coletado para salvar.")

driver.quit()
print("Processo concluído. Navegador fechado.")