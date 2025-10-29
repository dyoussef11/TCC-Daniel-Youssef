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
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException # Importação útil

# Obtém o caminho absoluto da pasta do script atual.
# Exemplo: 'C:\...\Buscar_Web\1- WebScrapping\script'
caminho_script = Path(__file__).resolve().parent

# Acessa a pasta raiz do projeto subindo dois níveis.
# Exemplo: 'C:\...\Buscar_Web'
caminho_raiz_projeto = caminho_script.parent.parent

# Adiciona o caminho da raiz ao caminho de busca do Python.
sys.path.append(str(caminho_raiz_projeto))

# Agora a importação do módulo 'config' deve funcionar.
from config import DIRETORIO_DADOS_WEBSCRAPPING, DIRETORIO_CSV_DATASET_FINAL
from modelo_de_busca import ler_e_filtrar_modelos

caminho_saida = DIRETORIO_DADOS_WEBSCRAPPING / 'links_discussoes_Dell_Ingles.csv'
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
# Mantendo o headless, mas pode comentar para debug
# chrome_options.add_argument("--headless") 
chrome_options.add_argument("--window-size=1920,1080")
chrome_options.add_argument("--blink-settings=imagesEnabled=false")
chrome_options.add_argument("--disable-gpu")

# CORREÇÃO: Inicialização única do driver
driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=chrome_options)
wait = WebDriverWait(driver, 20) # Usamos o wait mais longo

site_url = "https://www.dell.com/community/en/categories/dell-community"
all_discussion_links = [] # Armazena tuplas de (titulo, link, modelo_buscado)

# --- SELETORES EM VARIÁVEIS ---
SELETOR_COOKIE = "onetrust-accept-btn-handler"
SELETOR_DIGITAR_BUSCA = "input[placeholder='What are you looking for?']"
SELETOR_BOTAO_BUSCA = ".search-input__submit-button-lg.search-input__submit-button__right"
# Tipo de Conversa (Conversation Type)
SELETOR_DROPDOWN_TIPO_CONVERSA = ".conversation-types-filter__dropdown .Select-control"
SELETOR_OPCAO_POSTS = "//div[contains(@class, 'Select-option') and contains(., 'Posts')]"
# Categoria (Category)
SELETOR_CONTAINER_FILTRO_CATEGORIA = ".category-hierarchy-filter"
SELETOR_OPCAO_LAPTOPS = "//div[contains(@class, 'category-hierarchy-filter__option flex center-y') and contains(., 'Laptops')]"
# Elementos da Discussão e Paginação
SELETOR_ELEMENTOS_DISCUSSAO = "section.conversation-card .conversation-card__details a[title]"
SELETOR_NEXT_BUTTON = 'li[title="Next"]'

# --- LOOP PRINCIPAL: Itera sobre cada modelo lido do CSV ---
for i, modelo_de_busca in enumerate(modelos_a_buscar):
    # Formata o termo para busca avançada
    termo_de_busca = f'"{modelo_de_busca}"'
    
    print(f"\n{'='*70}")
    print(f"INICIANDO BUSCA {i+1}/{len(modelos_a_buscar)}: Modelo '{modelo_de_busca}' com termo: {termo_de_busca}")
    print(f"{'='*70}")

    driver.get(site_url)     

    try:
        # Fecha o pop-up de cookies se ele existir
        try:
            # Usa a variável SELETOR_COOKIE
            cookie_button = wait.until(EC.element_to_be_clickable((By.ID, SELETOR_COOKIE)))
            cookie_button.click()
            time.sleep(2)
        except:
            pass

        # =========================================================
        # BLOCO DE BUSCA
        # =========================================================
        print("Aguardando o campo de busca...")
        
        # 1. CAPTURA INICIAL E ATIVAÇÃO (Usando a variável)
        barra_de_busca = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, SELETOR_DIGITAR_BUSCA))
        )
        barra_de_busca.click()

        # 2. RE-CAPTURA DO ELEMENTO (Resolve o Stale Element)
        barra_de_busca_atualizada = driver.find_element(By.CSS_SELECTOR, SELETOR_DIGITAR_BUSCA)
        
        # 3. INSERÇÃO DE TEXTO
        barra_de_busca_atualizada.clear()
        barra_de_busca_atualizada.send_keys(termo_de_busca)
        
        print(f"Texto '{termo_de_busca}' inserido no campo de busca.")
        
        print("Aguardando o botão de busca...")
        # Clica no botão de busca (Usando a variável)
        botao_de_busca = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, SELETOR_BOTAO_BUSCA)))
        botao_de_busca.click()
        
        print("Pesquisa realizada com sucesso!")
        time.sleep(3)

        # --- FILTRO DE TIPO DE CONVERSA (POSTS) ---
        print("Aguardando o dropdown de 'Conversation Type'...")
        # Usa a variável
        tipo_de_conversa_dropdown = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, SELETOR_DROPDOWN_TIPO_CONVERSA)))
        tipo_de_conversa_dropdown.click()
        
        print("Dropdown de 'Conversation Type' clicado.")
        
        print("Aguardando a opção 'Posts'...")
        # Usa a variável
        publicacoes_option = wait.until(EC.element_to_be_clickable((By.XPATH, SELETOR_OPCAO_POSTS)))
        publicacoes_option.click()
        print("Opção 'Posts' selecionada.")
        time.sleep(2)


        # --- FILTRO DE CATEGORIA (LAPTOPS) ---
        print("\n--- APLICANDO FILTRO DE CATEGORIA ---")
        print("Aguardando o dropdown de 'Category'...")
        
        # 1. Clica no contêiner do filtro (Usando a variável)
        filtro_categoria_container = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, SELETOR_CONTAINER_FILTRO_CATEGORIA))
        )
        filtro_categoria_container.click()
        print("Dropdown de 'Category' clicado.")
        time.sleep(1) # Pausa curta para o menu abrir

        # 2. Clica na opção "Laptops" (Usando a variável)
        print("Aguardando a opção 'Laptops'...")
        laptops_option = wait.until(
            EC.element_to_be_clickable((By.XPATH, SELETOR_OPCAO_LAPTOPS))
        )
        laptops_option.click()
        print("Opção 'Laptops' selecionada e filtro aplicado.")


        time.sleep(2)
        
        # --- INÍCIO DA EXTRAÇÃO DE LINKS ---
        print("\n--- INICIANDO COLETA DE LINKS ---")

        while True:
            # Extrai os links da página atual (Usando a variável)
            print("Coletando links da página atual...")
            discussion_elements = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, SELETOR_ELEMENTOS_DISCUSSAO)))
            
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
            
            print(f"Novos links coletados: {novos_links_coletados}. Total de links acumulados: {len(all_discussion_links)}")

            # Tenta encontrar o botão "Próximo" (Usando a variável)
            try:
                next_button = WebDriverWait(driver, 2).until(EC.element_to_be_clickable((By.CSS_SELECTOR, SELETOR_NEXT_BUTTON)))
                print("Clicando no botão 'Next'...")
                # Uso de JavaScript para clique mais robusto
                driver.execute_script("arguments[0].click();", next_button)
                time.sleep(3) # Pausa para a página carregar
            except:
                print("Botão 'Next' não encontrado ou desabilitado. Fim da paginação.")
                break
        
    except Exception as e:
        print(f"Ocorreu um erro FATAL na busca pelo modelo '{modelo_de_busca}': {e}")
        import traceback
        traceback.print_exc()
        continue # Pula para o próximo modelo

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

print("Processo concluído. Navegador fechado.")
# Não é mais necessário esperar 30s aqui, pois o salvamento está no fim.
driver.quit()