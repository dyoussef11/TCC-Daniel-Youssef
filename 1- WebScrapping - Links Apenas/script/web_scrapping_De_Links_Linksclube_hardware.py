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
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# Obtém o caminho absoluto da pasta do script atual.
# Exemplo: 'C:\...\Buscar_Web\1- WebScrapping\script'
caminho_script = Path(__file__).resolve().parent

# Acessa a pasta raiz do projeto subindo dois níveis.
# Exemplo: 'C:\...\Buscar_Web'
caminho_raiz_projeto = caminho_script.parent.parent

# Adiciona o caminho da raiz ao caminho de busca do Python.
sys.path.append(str(caminho_raiz_projeto))

# Agora a importação do módulo 'config' e 'modelo_de_busca' deve funcionar.
from config import DIRETORIO_DADOS_WEBSCRAPPING, DIRETORIO_CSV_MODELOS_NOTEBOOKS
from modelo_de_busca import ler_e_filtrar_modelos

caminho_saida = DIRETORIO_DADOS_WEBSCRAPPING / 'links_discussoes_ClubeHardware.csv'
caminho_entrada = DIRETORIO_CSV_MODELOS_NOTEBOOKS / 'modelos_de_busca.csv'

# --- Configuração de Busca ---
# Se MARCA_ALVO for None ou '', todos os modelos do CSV serão usados.
MARCA_ALVO = None

# Lê e filtra os modelos do CSV
modelos_a_buscar = ler_e_filtrar_modelos(caminho_entrada, MARCA_ALVO)

if not modelos_a_buscar:
    print(f"Não foram encontrados modelos para a marca '{MARCA_ALVO}' no arquivo CSV ou houve um erro na leitura. Saindo.")
    sys.exit()

# --- Configurações iniciais do Selenium (INTEGRANDO HEADLESS) ---
chrome_options = Options()
# Adiciona os argumentos para execução em modo headless e otimizações
chrome_options.add_argument("--headless")
chrome_options.add_argument("--window-size=1920,1080")
chrome_options.add_argument("--blink-settings=imagesEnabled=false")
chrome_options.add_argument("--disable-gpu")

# Inicializa o driver usando Service e Options (MODO HEADLESS - CORRIGIDO)
driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=chrome_options)
# Aumenta o tempo de espera
driver = webdriver.Chrome()
wait = WebDriverWait(driver, 30)

site_url = "https://www.clubedohardware.com.br/search/"

all_results = [] # Armazena tuplas de (titulo, link, modelo) de forma acumulativa
cookie_popup_fechado = False # Flag para fechar o pop-up apenas uma vez

# --- INÍCIO DO LOOP PRINCIPAL SOBRE OS MODELOS ---
for i, modelo_de_busca in enumerate(modelos_a_buscar):
    # Formata o termo para pesquisa exata
    termo_de_busca = f'"{modelo_de_busca}"'
    
    print(f"\n{'='*60}")
    print(f"INICIANDO BUSCA {i+1}/{len(modelos_a_buscar)}: Modelo '{modelo_de_busca}' com termo: {termo_de_busca}")
    print(f"{'='*60}")
    
    # 1. Navegar para a página de busca (necessário a cada novo termo)
    driver.get(site_url)
    print(f"Página acessada: {site_url}. Aguardando o carregamento...")

    try:
        # --- A: Tratar o Pop-up de Anúncio (Apenas na primeira iteração) ---
        if not cookie_popup_fechado:
            try:
                print("Verificando se há um pop-up de anúncio...")
                # Reduz o tempo de espera para o pop-up para não atrasar se ele não estiver lá
                close_ad_btn = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "span.__lxG__splash-close")))
                close_ad_btn.click()
                print("Pop-up de anúncio fechado.")
                time.sleep(1)
                cookie_popup_fechado = True
            except:
                print("Nenhum pop-up de anúncio encontrado ou ele já foi fechado.")
                cookie_popup_fechado = True
                pass
        
        # --- B: Clicar na opção "Contenham todas as palavras" (CORREÇÃO FINAL: Usando ID do LABEL) ---
        
        LABEL_ID = "elField_andOr_full_label_and"
        
        print("Selecionando a opção 'Contenham todas as palavras'...")
        
        # Tenta encontrar o LABEL e clica (o LABEL é a área clicável visível)
        radio_label = wait.until(EC.element_to_be_clickable((By.ID, LABEL_ID)))
        
        # Clica no LABEL usando JavaScript para evitar problemas de cobertura/tamanho
        driver.execute_script("arguments[0].click();", radio_label)
        print("Opção selecionada via JavaScript no LABEL.")


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

        # --- INÍCIO DA EXTRAÇÃO DE LINKS PARA O MODELO ATUAL ---
        print("\n--- INICIANDO COLETA DE LINKS ---")

        while True:
            print("Coletando links e títulos da página atual...")
            
            try:
                # Espera que os links de resultado estejam presentes
                discussion_links = wait.until(
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, "a[data-linktype='link'][data-searchable]"))
                )

                novos_links = 0
                for link_element in discussion_links:
                    title = link_element.text.strip()
                    url = link_element.get_attribute("href")
                    
                    # Armazena como (título, url, modelo_original)
                    item = (title, url, modelo_de_busca)
                    
                    # Verifica se o título não está vazio e se o item não é duplicado
                    if title and item not in all_results:
                        all_results.append(item)
                        novos_links += 1
                
                print(f"Novos links coletados nesta página: {novos_links}. Total acumulado: {len(all_results)}")
                
                # Tenta encontrar o botão "Próximo"
                next_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "li.ipsPagination_next a")))
                print("Clicando no botão 'Próximo'...")
                next_button.click()
                time.sleep(3) # Pausa para a página carregar
            
            except Exception as e:
                print(f"Botão 'Próximo' não encontrado ou desabilitado para '{modelo_de_busca}'. Fim da paginação.")
                break # Sai do while True (fim da paginação para o modelo atual)
        
    except Exception as e:
        print(f"Ocorreu um erro FATAL na busca pelo modelo '{modelo_de_busca}': {e}")
        import traceback
        traceback.print_exc()
        continue # Pula para o próximo modelo

# --- FIM DO LOOP ---

# Salva TODOS os resultados acumulados em um único arquivo CSV
if all_results:
    print("\n--- SALVANDO TODOS OS RESULTADOS ACUMULADOS ---")
    with open(caminho_saida, 'w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow(['Título da Discussão', 'Link da Discussão', 'Modelo Buscado']) # Cabeçalho do CSV
        for title, url, modelo in all_results:
            writer.writerow([title, url, modelo])

    print(f"\nResultados salvos com sucesso em {caminho_saida}. Total de resultados: {len(all_results)}")
else:
    print("Nenhum resultado foi coletado para salvar.")

# --- Passo 3: Encerrar o Navegador ---
print("Fechando o navegador.")
driver.quit()
