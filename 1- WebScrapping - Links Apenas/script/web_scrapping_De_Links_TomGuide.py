import sys
from pathlib import Path
import csv
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options

# Obtém o caminho absoluto da pasta do script atual.
caminho_script = Path(__file__).resolve().parent

# Acessa a pasta raiz do projeto subindo dois níveis.
caminho_raiz_projeto = caminho_script.parent.parent

# Adiciona o caminho da raiz ao caminho de busca do Python.
sys.path.append(str(caminho_raiz_projeto))

# Agora a importação dos módulos 'config' e 'modelo_de_busca' deve funcionar.
from config import DIRETORIO_DADOS_WEBSCRAPPING, DIRETORIO_CSV_MODELOS_NOTEBOOKS
# Importa a função de leitura de modelos
from modelo_de_busca import ler_e_filtrar_modelos 

caminho_saida = DIRETORIO_DADOS_WEBSCRAPPING / 'links_discussoes_Tom_Guide.csv'
caminho_entrada = DIRETORIO_CSV_MODELOS_NOTEBOOKS / 'modelos_de_busca.csv'

# --- Configuração de Busca e Filtro de CSV ---
# Se MARCA_ALVO for None ou '', todos os modelos do CSV serão usados.
# Para buscar todos:
MARCA_ALVO = None 

# Lê e filtra os modelos do CSV
modelos_a_buscar = ler_e_filtrar_modelos(caminho_entrada, MARCA_ALVO)

if not modelos_a_buscar:
    print(f"Não foram encontrados modelos para a marca '{MARCA_ALVO}' no arquivo CSV ou houve um erro na leitura. Saindo.")
    sys.exit()

# --- Configurações iniciais do Selenium (CORRIGIDO PARA HEADLESS) ---
chrome_options = Options()
# Adiciona os argumentos para execução em modo headless e otimizações
chrome_options.add_argument("--headless")
chrome_options.add_argument("--window-size=1920,1080")
chrome_options.add_argument("--blink-settings=imagesEnabled=false")
chrome_options.add_argument("--disable-gpu")

# Inicializa o driver usando Service e Options
driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=chrome_options)
site_url = "https://forums.tomsguide.com/search/"
wait = WebDriverWait(driver, 20)

all_results = [] # Armazena {"Título": titulo, "Link": link, "Modelo Buscado": modelo}

# --- LOOP PRINCIPAL: Itera sobre cada modelo lido do CSV ---
for i, modelo_de_busca in enumerate(modelos_a_buscar):
    # Formata o termo de busca: o nome do modelo entre aspas para busca exata
    termo_de_busca = f'"{modelo_de_busca}"'
    
    print(f"\n{'='*70}")
    print(f"INICIANDO BUSCA {i+1}/{len(modelos_a_buscar)}: Modelo '{modelo_de_busca}'")
    print(f"{'='*70}")
    
    # 1. Navegar para a página de busca (necessário a cada novo termo)
    driver.get(site_url)

    try:
        # --- Realizar a busca ---
        print("Aguardando o campo de busca...")
        
        # Espera que o campo de busca esteja visível e clicável (By.NAME é o termo correto)
        barra_de_busca = wait.until(EC.element_to_be_clickable((By.NAME, "keywords")))

        # Clica no campo, limpa e envia o termo (Solução robusta, embora ActionChains funcione aqui)
        barra_de_busca.click()
        barra_de_busca.clear()
        barra_de_busca.send_keys(termo_de_busca)

        # Pressiona Enter para iniciar a busca
        barra_de_busca.send_keys(Keys.ENTER)
        
        print(f"Texto '{termo_de_busca}' inserido no campo de busca. Pesquisa iniciada.")
        time.sleep(3) # Pausa para a página de resultados carregar

        # --- INÍCIO DA EXTRAÇÃO DE DADOS PARA O MODELO ATUAL ---
        print("\n--- INICIANDO COLETA DE TÍTULOS E LINKS ---")
        
        while True:
            # Tenta encontrar todos os títulos de discussão
            discussion_titles = wait.until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "h3.contentRow-title a"))
            )
            
            novos_links_coletados = 0
            
            for element in discussion_titles:
                try:
                    link = element.get_attribute("href")
                    title = element.text.strip()
                    
                    # Cria o dicionário de resultado
                    result_data = {"Título": title, "Link": link, "Modelo Buscado": modelo_de_busca}
                    
                    # Garante a unicidade globalmente, verificando apenas o link
                    if not any(item['Link'] == link for item in all_results):
                        all_results.append(result_data)
                        novos_links_coletados += 1
                        
                except Exception as e:
                    print(f"Erro ao extrair dados de um elemento: {e}")
                    continue
            
            print(f"Página processada. Novos links: {novos_links_coletados}. Total acumulado: {len(all_results)}")

            # Tenta encontrar o botão "Próximo" para a paginação
            try:
                # O Tom's Guide/XenForo usa "li.pagination-next a" ou "a[rel='next']"
                next_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a[rel='next']")))
                next_button.click()
                print("Clicando no botão 'Próximo'...")
                time.sleep(3) # Pausa para a nova página carregar

            except (TimeoutException, NoSuchElementException):
                print(f"Botão 'Próximo' não encontrado ou desabilitado para '{modelo_de_busca}'. Fim da paginação.")
                break # Sai do loop while True (fim da paginação)

    except Exception as e:
        print(f"Ocorreu um erro fatal durante a busca pelo modelo '{modelo_de_busca}': {e}")
        # import traceback; traceback.print_exc()
        continue # Pula para o próximo modelo

# --- FIM DO LOOP ---

# Salva TODOS os resultados acumulados em um único arquivo CSV
if all_results:
    print("\n--- SALVANDO TODOS OS RESULTADOS ACUMULADOS ---")
    with open(caminho_saida, 'w', newline='', encoding='utf-8') as file:
        fieldnames = ['Título', 'Link', 'Modelo Buscado']
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_results)
        
    print(f"\nDados salvos com sucesso em '{caminho_saida}'. Total de resultados: {len(all_results)}")
else:
    print("Nenhum resultado foi coletado para salvar.")

driver.quit()
print("Processo concluído. Navegador fechado.")
