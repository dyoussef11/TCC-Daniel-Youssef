import sys
from pathlib import Path
import csv
import time
import random 
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException
import undetected_chromedriver as uc
from webdriver_manager.chrome import ChromeDriverManager
import traceback 

# --- CONFIGURAÇÃO DE CAMINHOS E LEITURA DE DADOS (Presume-se que módulos existem) ---

# Obtém o caminho absoluto da pasta do script atual.
caminho_script = Path(__file__).resolve().parent

# Acessa a pasta raiz do projeto subindo dois níveis.
caminho_raiz_projeto = caminho_script.parent.parent

# Adiciona o caminho da raiz ao caminho de busca do Python.
sys.path.append(str(caminho_raiz_projeto))

# Importações de módulos de configuração (Ajuste se necessário)
try:
    from config import DIRETORIO_DADOS_WEBSCRAPPING, DIRETORIO_CSV_DATASET_FINAL
    from modelo_de_busca import ler_e_filtrar_modelos 
except ImportError as e:
    print(f"Erro de importação de módulos de configuração. Verifique 'config' e 'modelo_de_busca': {e}")
    sys.exit()

caminho_saida = DIRETORIO_DADOS_WEBSCRAPPING / 'links_discussoes_ClubeHardware.csv'
caminho_entrada = DIRETORIO_CSV_DATASET_FINAL / 'dataset_laptops_UNICOS.csv'

MARCA_ALVO = None
TIPO_NOTEBOOK = 'Gamer'
modelos_a_buscar = ler_e_filtrar_modelos(caminho_entrada, MARCA_ALVO, TIPO_NOTEBOOK)

if not modelos_a_buscar:
    print(f"Não foram encontrados modelos para a marca '{MARCA_ALVO}' no arquivo CSV. Saindo.")
    sys.exit()

# --- DECLARAÇÕES DE HTML EM VARIÁVEIS ---
SITE_URL = "https://www.clubedohardware.com.br/search/"

SELETOR_BOTAO_FECHAR_POPUP_AD = 'span[class="__lxG__splash-close"]' 
SELETOR_CAMPO_BUSCA = 'input[name="q"]' 
MENSAGEM_DE_ERRO = 'div[id="elErrorMessage"]' # Seletor da mensagem de "Aguarde %s segundos"
SELETOR_LINKS_RESULTADO = "a[data-linktype='link'][data-searchable]" 
SELETOR_BOTAO_PROXIMA_PAGINA = "li.ipsPagination_next a" 

# --- INICIALIZAÇÃO DO SELENIUM ---
chrome_options = Options()
chrome_options.add_argument("--window-size=1920,1080")
chrome_options.add_argument("--blink-settings=imagesEnabled=false")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument(f"user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.75 Safari/537.36")

try:
    # Usando undetected_chromedriver para maior resiliência anti-bot
    driver = uc.Chrome(service=ChromeService(ChromeDriverManager().install()), options=chrome_options)
except Exception as e:
    print(f"Erro ao inicializar o WebDriver: {e}")
    sys.exit()

wait = WebDriverWait(driver, 30)

all_results = [] 
cookie_popup_fechado = False 

# --- INÍCIO DO LOOP PRINCIPAL SOBRE OS MODELOS ---
for i, modelo_de_busca in enumerate(modelos_a_buscar):
    termo_de_busca = f'{modelo_de_busca}'
    
    # PAUSA ESTRATÉGICA ENTRE MODELOS para evitar Rate Limiting de forma proativa
    if i > 0:
        sleep_time = random.uniform(7, 12) 
        print(f"Pausando por {sleep_time:.2f} segundos antes da busca do próximo modelo.")
        time.sleep(sleep_time)

    print(f"\n{'='*60}")
    print(f"INICIANDO BUSCA (Clube Hardware) {i+1}/{len(modelos_a_buscar)}: Modelo '{modelo_de_busca}'")
    print(f"{'='*60}")
    
    # 1. Navegar para a página de busca
    driver.get(SITE_URL)
    print(f"Página acessada: {SITE_URL}. Aguardando o carregamento...")

    try:
        # --- A: Tratar o Pop-up de Anúncio (Apenas na primeira iteração) ---
        if not cookie_popup_fechado:
            try:
                print("Verificando se há um pop-up de anúncio...")
                close_ad_btn = WebDriverWait(driver, 15).until(EC.element_to_be_clickable((By.CSS_SELECTOR, SELETOR_BOTAO_FECHAR_POPUP_AD)))
                close_ad_btn.click()
                print("Pop-up de anúncio fechado.")
            except:
                print("Nenhum pop-up de anúncio encontrado ou ele já foi fechado.")
                pass
            
            cookie_popup_fechado = True 
        
        # --- C: Achar o campo de busca e preencher com o texto ---
        print("Aguardando o campo de busca...")
        barra_de_busca = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, SELETOR_CAMPO_BUSCA)))

        barra_de_busca.click()
        barra_de_busca.clear()
        barra_de_busca.send_keys(termo_de_busca)
        print(f"Texto '{termo_de_busca}' inserido no campo de busca.")
        
        # --- D: Pressionar Enter para iniciar a busca ---
        barra_de_busca.send_keys(Keys.ENTER)
        print("Tecla ENTER pressionada. Pesquisa iniciada com sucesso! Aguardando resultados...")

        # --- INÍCIO DA EXTRAÇÃO DE LINKS E PAGINAÇÃO ---
        print("\n--- INICIANDO COLETA E PAGINAÇÃO ---")

        while True:
            print("\n" + "-"*50)
            print("Coletando links e títulos da página atual...")
            
            url_proxima_pagina = None 

            try:
                # 1. COLETA DE LINKS
                discussion_links = WebDriverWait(driver, 15).until( 
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, SELETOR_LINKS_RESULTADO))
                )

                novos_links = 0
                for link_element in discussion_links:
                    title = link_element.text.strip()
                    url = link_element.get_attribute("href")
                    item = (title, url, modelo_de_busca)
                    
                    if title and item not in all_results:
                        all_results.append(item)
                        novos_links += 1
                
                print(f"Novos links coletados nesta página: {novos_links}. Total acumulado: {len(all_results)}")
                
                # --- VERIFICAÇÃO DE FIM DE PAGINAÇÃO ---
                if novos_links == 0:
                    print("Nenhum link NOVO coletado nesta página. Assumindo fim da paginação para este modelo.")
                    break # SAI DO while True DE PAGINAÇÃO
                
                # 2. OBTENÇÃO DA URL DA PRÓXIMA PÁGINA
                next_button_element = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, SELETOR_BOTAO_PROXIMA_PAGINA))
                )
                url_proxima_pagina = next_button_element.get_attribute("href")
                
            except TimeoutException:
                print(f"Botão 'Próximo' não encontrado. Fim da paginação.")
                break 
            
            except Exception as e_coleta:
                print(f"Erro inesperado durante a coleta de links: {e_coleta}")
                break 

            # =================================================================
            # 3. TRATAMENTO DE RATE LIMIT E NAVEGAÇÃO RESILIENTE
            # =================================================================
            
            # Se a URL não for válida, interrompe (medida de segurança)
            if not url_proxima_pagina:
                 print("URL da próxima página é inválida. Fim da paginação.")
                 break

            MAX_TENTATIVAS = 5
            tentativa_atual = 0
            sucesso_navegacao = False

            while not sucesso_navegacao and tentativa_atual < MAX_TENTATIVAS:
                tentativa_atual += 1
                print(f"\n[RATE LIMIT CHECK] Tentativa de navegação #{tentativa_atual}...")
                
                # Navega diretamente para a URL
                driver.get(url_proxima_pagina)
                
                try:
                    # Espera (curta) pela MENSAGEM DE ERRO (Se aparecer, significa que houve Rate Limit)
                    WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, MENSAGEM_DE_ERRO))
                    )
                    
                    # ERRO ENCONTRADO
                    print(f"!!! ERRO DE RATE LIMIT DETECTADO na tentativa {tentativa_atual}.")
                    time_sleep_rate_limit = random.uniform(50, 70) 
                    print(f"Pausando por {time_sleep_rate_limit:.2f} segundos antes de retentar...")
                    time.sleep(time_sleep_rate_limit) 
                    
                except TimeoutException:
                    # Se o erro NÃO foi encontrado (TimeoutException no wait de 5s):
                    sucesso_navegacao = True 
                    print(f"Nenhuma mensagem de erro detectada. Navegação bem-sucedida.")

                except Exception as e_nav:
                    print(f"Erro inesperado durante a navegação/verificação do erro: {e_nav}. Pausando 5s antes de retentar.")
                    time.sleep(5) 
                    
            # 4. TRATAMENTO FINAL PÓS-TENTATIVAS
            if not sucesso_navegacao:
                # Falha após todas as retentativas (Rate Limit persistente)
                print(f"Falha ao navegar após {MAX_TENTATIVAS} tentativas. Abortando paginação.")
                break 
            else:
                print("Continuando o loop de coleta na nova página.")
                # Pausa randômica de "usuário humano" entre páginas
                time.sleep(random.uniform(5, 10)) 
        
    except Exception as e_fatal:
        print(f"Ocorreu um erro FATAL na busca pelo modelo '{modelo_de_busca}': {e_fatal}")
        traceback.print_exc()
        continue # Pula para o próximo modelo

# --- FIM DO LOOP E SALVAMENTO ---
Nome_do_Site = 'ClubeHardware'
# Salva TODOS os resultados acumulados em um único arquivo CSV
if all_results:
    print("\n--- SALVANDO TODOS OS RESULTADOS ACUMULADOS ---")
    try:
        with open(caminho_saida, 'w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow(['Título da Discussão', 'Link da Discussão', 'Modelo Buscado', 'Site_Origem']) 
            for title, url, modelo in all_results:
                writer.writerow([title, url, modelo, Nome_do_Site])

        print(f"\nResultados salvos com sucesso em {caminho_saida}. Total de resultados: {len(all_results)}")
    except Exception as e_save:
        print(f"Erro ao salvar o arquivo CSV: {e_save}")
else:
    print("Nenhum resultado foi coletado para salvar.")

# --- Encerrar o Navegador ---
print("Fechando o navegador.")
driver.quit()