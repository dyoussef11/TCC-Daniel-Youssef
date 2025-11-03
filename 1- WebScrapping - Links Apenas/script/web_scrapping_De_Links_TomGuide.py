import sys
from pathlib import Path
import csv
import time
import random # [MODIFICAÇÃO] Importar random para pausas anti-bloqueio
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
import traceback # Importar para melhor rastreamento de erro

# Obtém o caminho absoluto da pasta do script atual.
caminho_script = Path(__file__).resolve().parent

# Acessa a pasta raiz do projeto subindo dois níveis.
caminho_raiz_projeto = caminho_script.parent.parent

# Adiciona o caminho da raiz ao caminho de busca do Python.
sys.path.append(str(caminho_raiz_projeto))

# Agora a importação dos módulos 'config' e 'modelo_de_busca' deve funcionar.
from config import DIRETORIO_DADOS_WEBSCRAPPING, DIRETORIO_CSV_DATASET_FINAL
# Importa a função de leitura de modelos
from modelo_de_busca import ler_e_filtrar_modelos 

caminho_saida = DIRETORIO_DADOS_WEBSCRAPPING / 'links_discussoes_Tom_Guide.csv'
caminho_entrada = DIRETORIO_CSV_DATASET_FINAL / 'dataset_laptops_UNICOS.csv'

MARCA_ALVO = None
TIPO_NOTEBOOK = 'Gamer'
# Lê e filtra os modelos do CSV
modelos_a_buscar = ler_e_filtrar_modelos(caminho_entrada, MARCA_ALVO, TIPO_NOTEBOOK)

if not modelos_a_buscar:
    print(f"Não foram encontrados modelos para a marca '{MARCA_ALVO}' no arquivo CSV ou houve um erro na leitura. Saindo.")
    sys.exit()

# --- DECLARAÇÕES DE HTML EM VARIÁVEIS (Facilidade de Manutenção) ---

SITE_URL = "https://forums.tomsguide.com/search/"

# --- Seletores de Ação ---
SELETOR_CAMPO_BUSCA = "keywords" # Name do campo de input de busca (Usado com By.NAME)

# --- Seletores de Resultados e Paginação ---
SELETOR_LINKS_TITULOS = "h3.contentRow-title a" # Link/Título de cada resultado de busca (CSS)
SELETOR_BOTAO_PROXIMA_PAGINA = "a[rel='next']" # Link para a próxima página (CSS)


# --- Configurações iniciais do Selenium (OTIMIZAÇÃO DE VELOCIDADE/ANTI-BLOQUEIO) ---
chrome_options = Options()
# Modo headless ativo para maior velocidade
chrome_options.add_argument("--headless")
chrome_options.add_argument("--window-size=1920,1080")
chrome_options.add_argument("--blink-settings=imagesEnabled=false")
chrome_options.add_argument("--disable-gpu")
# [MODIFICAÇÃO] Adicionar User-Agent para simular um navegador normal
chrome_options.add_argument(f"user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.75 Safari/537.36")


# Inicializa o driver usando Service e Options
driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=chrome_options)
# [MODIFICAÇÃO] Reduzir o tempo de espera implícita de 20s para 15s (mais rápido no headless)
wait = WebDriverWait(driver, 15)

all_results = [] # Armazena {"Título": titulo, "Link": link, "Modelo Buscado": modelo}

# --- LOOP PRINCIPAL: Itera sobre cada modelo lido do CSV ---
for i, modelo_de_busca in enumerate(modelos_a_buscar):
    # [MODIFICAÇÃO] PAUSA ESTRATÉGICA E ALEATÓRIA ENTRE MODELOS
    # CRUCIAL para evitar rate limiting em buscas consecutivas.
    if i > 0:
        sleep_time = random.uniform(0, 1) 
        print(f"Pausando por {sleep_time:.2f} segundos antes da busca do próximo modelo.")
        time.sleep(sleep_time)

    # Formata o termo de busca: o nome do modelo entre aspas para busca exata
    termo_de_busca = f'{modelo_de_busca}'
    
    print(f"\n{'='*70}")
    print(f"INICIANDO BUSCA (Tom's Guide) {i+1}/{len(modelos_a_buscar)}: Modelo '{modelo_de_busca}'")
    print(f"{'='*70}")
    
    # 1. Navegar para a página de busca (necessário a cada novo termo)
    driver.get(SITE_URL)

    try:
        # --- Realizar a busca ---
        print("Aguardando o campo de busca...")
        
        # Espera que o campo de busca esteja visível e clicável (Usa a constante SELETOR_CAMPO_BUSCA)
        barra_de_busca = wait.until(EC.element_to_be_clickable((By.NAME, SELETOR_CAMPO_BUSCA)))

        # Clica no campo, limpa e envia o termo
        barra_de_busca.click()
        barra_de_busca.clear()
        barra_de_busca.send_keys(termo_de_busca)

        # Pressiona Enter para iniciar a busca
        barra_de_busca.send_keys(Keys.ENTER)
        
        print(f"Texto '{termo_de_busca}' inserido no campo de busca. Pesquisa iniciada. Aguardando resultados...")
        # [MODIFICAÇÃO] Remover time.sleep(3). O próximo wait cuidará do carregamento.

        # --- INÍCIO DA EXTRAÇÃO DE DADOS PARA O MODELO ATUAL ---
        print("\n--- INICIANDO COLETA DE TÍTULOS E LINKS ---")
        
        while True:
            try:
                # Tenta encontrar todos os títulos de discussão (Usa a constante SELETOR_LINKS_TITULOS)
                # [MODIFICAÇÃO] Tempo de espera reduzido para 10s (mais ágil)
                discussion_titles = WebDriverWait(driver, 3).until(
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, SELETOR_LINKS_TITULOS))
                )
            except TimeoutException:
                 # Se não encontrar resultados na primeira página, considera que não há resultados.
                 # O código de paginação abaixo cuida do caso de não haver mais páginas.
                 if not driver.find_elements(By.CSS_SELECTOR, SELETOR_LINKS_TITULOS):
                     print(f"Zero resultados encontrados para o modelo '{modelo_de_busca}' nesta página. Fim da coleta.")
                     break
                 # Se houve timeout mas encontrou alguns elementos (erro no carregamento), tenta continuar
                 print("Timeout no carregamento dos links. Tentando encontrar o botão Próximo...")


            novos_links_coletados = 0
            
            # Recarrega os elementos para evitar StaleElementReferenceException, se necessário
            discussion_titles = driver.find_elements(By.CSS_SELECTOR, SELETOR_LINKS_TITULOS)
            
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

            # Tenta encontrar o botão "Próximo" para a paginação (Usa a constante SELETOR_BOTAO_PROXIMA_PAGINA)
            try:
                # [MODIFICAÇÃO] Aumentar timeout para o botão para 5s (era 2s) para maior robustez
                next_button = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.CSS_SELECTOR, SELETOR_BOTAO_PROXIMA_PAGINA)))
                
                # Clica usando JS para maior confiabilidade no headless
                driver.execute_script("arguments[0].click();", next_button)
                print("Clicando no botão 'Próximo'...")
                
                # [MODIFICAÇÃO] Pausa aleatória na paginação (Anti-Bloqueio)
                sleep_time_page = random.uniform(2, 4)
                time.sleep(sleep_time_page) 
                print(f"Pausa de {sleep_time_page:.2f} segundos para nova página carregar.")

            except (TimeoutException, NoSuchElementException):
                print(f"Botão 'Próximo' não encontrado ou desabilitado para '{modelo_de_busca}'. Fim da paginação.")
                break # Sai do loop while True (fim da paginação)

    except Exception as e:
        print(f"Ocorreu um erro fatal durante a busca pelo modelo '{modelo_de_busca}': {e}")
        traceback.print_exc()
        continue # Pula para o próximo modelo

# --- FIM DO LOOP ---

# Salva TODOS os resultados acumulados em um único arquivo CSV
if all_results:
    print("\n--- SALVANDO TODOS OS RESULTADOS ACUMULADOS ---")
    with open(caminho_saida, 'w', newline='', encoding='utf-8') as file:
        fieldnames = ['Título', 'Link da Discussão', 'Modelo Buscado']
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_results)
        
    print(f"\nDados salvos com sucesso em '{caminho_saida}'. Total de resultados: {len(all_results)}")
else:
    print("Nenhum resultado foi coletado para salvar.")

driver.quit()
print("Processo concluído. Navegador fechado.")