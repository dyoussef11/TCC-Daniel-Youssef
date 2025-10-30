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
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException, NoSuchElementException
# [MODIFICAÇÃO] Importar traceback para debug de erro fatal
import traceback 

# Obtém o caminho absoluto da pasta do script atual.
caminho_script = Path(__file__).resolve().parent

# Acessa a pasta raiz do projeto subindo dois níveis.
caminho_raiz_projeto = caminho_script.parent.parent

# Adiciona o caminho da raiz ao caminho de busca do Python.
sys.path.append(str(caminho_raiz_projeto))

# Agora a importação do módulo 'config' e 'modelo_de_busca' deve funcionar.
from config import DIRETORIO_DADOS_WEBSCRAPPING, DIRETORIO_CSV_DATASET_FINAL
from modelo_de_busca import ler_e_filtrar_modelos

caminho_saida = DIRETORIO_DADOS_WEBSCRAPPING / 'links_discussoes_ClubeHardware.csv'
caminho_entrada = DIRETORIO_CSV_DATASET_FINAL / 'dataset_laptops.csv'

# --- Configuração de Busca ---
MARCA_ALVO = None

# Lê e filtra os modelos do CSV
modelos_a_buscar = ler_e_filtrar_modelos(caminho_entrada, MARCA_ALVO)

if not modelos_a_buscar:
    print(f"Não foram encontrados modelos para a marca '{MARCA_ALVO}' no arquivo CSV ou houve um erro na leitura. Saindo.")
    sys.exit()

# --- DECLARAÇÕES DE HTML EM VARIÁVEIS (Facilidade de Manutenção) ---

SITE_URL = "https://www.clubedohardware.com.br/search/"

# --- Seletores de Ação ---
SELETOR_BOTAO_FECHAR_POPUP_AD = "span.__lxG__splash-close" # Botão fechar anúncio/pop-up
SELETOR_RADIO_TODAS_PALAVRAS = "elField_andOr_full_label_and" # ID do LABEL para 'Contenham todas as palavras'
SELETOR_CAMPO_BUSCA = "q" # Name do campo de input de busca (Usado com By.NAME)

# --- Seletores de Resultados e Paginação ---
SELETOR_LINKS_RESULTADO = "a[data-linktype='link'][data-searchable]" # Link de cada resultado de busca
SELETOR_BOTAO_PROXIMA_PAGINA = "li.ipsPagination_next a" # Link para a próxima página

# --- Configurações iniciais do Selenium (OTIMIZAÇÃO DE VELOCIDADE/ANTI-BLOQUEIO) ---
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

all_results = [] # Armazena tuplas de (titulo, link, modelo) de forma acumulativa
cookie_popup_fechado = False # Flag para fechar o pop-up apenas uma vez

# --- INÍCIO DO LOOP PRINCIPAL SOBRE OS MODELOS ---
for i, modelo_de_busca in enumerate(modelos_a_buscar):
    # Formata o termo para pesquisa exata
    termo_de_busca = f'"{modelo_de_busca}"'
    
    # [MODIFICAÇÃO] PAUSA ESTRATÉGICA E ALEATÓRIA ENTRE MODELOS
    # Crucial para evitar rate limiting
    if i > 0:
        sleep_time = random.uniform(7, 12) # Pausa maior entre 7 e 12 segundos
        print(f"Pausando por {sleep_time:.2f} segundos antes da busca do próximo modelo.")
        time.sleep(sleep_time)

    print(f"\n{'='*60}")
    print(f"INICIANDO BUSCA {i+1}/{len(modelos_a_buscar)}: Modelo '{modelo_de_busca}' com termo: {termo_de_busca}")
    print(f"{'='*60}")
    
    # 1. Navegar para a página de busca (necessário a cada novo termo)
    driver.get(SITE_URL)
    print(f"Página acessada: {SITE_URL}. Aguardando o carregamento...")

    try:
        # --- A: Tratar o Pop-up de Anúncio (Apenas na primeira iteração) ---
        if not cookie_popup_fechado:
            try:
                print("Verificando se há um pop-up de anúncio...")
                # Usa a variável de seletor
                # [MODIFICAÇÃO] Reduzir tempo de espera do pop-up
                close_ad_btn = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.CSS_SELECTOR, SELETOR_BOTAO_FECHAR_POPUP_AD)))
                close_ad_btn.click()
                print("Pop-up de anúncio fechado.")
                # [MODIFICAÇÃO] Remover time.sleep(1) e confiar no próximo wait
            except:
                print("Nenhum pop-up de anúncio encontrado ou ele já foi fechado.")
                pass
            
            # Marca como fechado
            cookie_popup_fechado = True 
        
        # --- B: Clicar na opção "Contenham todas as palavras" ---
        print("Selecionando a opção 'Contenham todas as palavras'...")
        
        # Usa a variável de seletor (By.ID)
        radio_label = wait.until(EC.element_to_be_clickable((By.ID, SELETOR_RADIO_TODAS_PALAVRAS)))
        
        # Clica no LABEL usando JavaScript para evitar problemas de cobertura/tamanho
        driver.execute_script("arguments[0].click();", radio_label)
        print("Opção selecionada via JavaScript no LABEL.")


        # --- C: Achar o campo de busca e preencher com o texto ---
        print("Aguardando o campo de busca...")

        # Espera até que o campo de busca esteja visível e clicável (Usa a variável de seletor - By.NAME)
        barra_de_busca = wait.until(EC.element_to_be_clickable((By.NAME, SELETOR_CAMPO_BUSCA)))

        # Clica no campo para dar o foco, depois limpa e digita
        barra_de_busca.click()
        barra_de_busca.clear()
        barra_de_busca.send_keys(termo_de_busca)

        print(f"Texto '{termo_de_busca}' inserido no campo de busca.")
        
        # --- D: Pressionar Enter para iniciar a busca ---
        barra_de_busca.send_keys(Keys.ENTER)
        print("Tecla ENTER pressionada. Pesquisa iniciada com sucesso! Aguardando resultados...")

        # --- INÍCIO DA EXTRAÇÃO DE LINKS PARA O MODELO ATUAL ---
        print("\n--- INICIANDO COLETA DE LINKS ---")

        while True:
            # [MODIFICAÇÃO] Aumentar o timeout para resultados iniciais (pode demorar após o ENTER)
            print("Coletando links e títulos da página atual...")
            
            try:
                # Espera que os links de resultado estejam presentes (Usa a variável de seletor)
                discussion_links = WebDriverWait(driver, 10).until(
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, SELETOR_LINKS_RESULTADO))
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
                
                # Tenta encontrar o botão "Próximo" (Usa a variável de seletor)
                # [MODIFICAÇÃO] Reduzir o tempo de espera do botão 'Próximo' para 5s (antes era 2s com sleep fixo)
                next_button = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.CSS_SELECTOR, SELETOR_BOTAO_PROXIMA_PAGINA)))
                print("Clicando no botão 'Próximo'...")
                
                # Clica via JS para maior confiabilidade
                driver.execute_script("arguments[0].click();", next_button)
                # [MODIFICAÇÃO] Pausa menor e aleatória na paginação (dentro de um modelo)
                time.sleep(random.uniform(2, 4)) 
            
            except TimeoutException:
                 # Captura especificamente Timeout, que geralmente significa que o botão "Próximo" não apareceu
                print(f"Botão 'Próximo' não encontrado ou desabilitado para '{modelo_de_busca}'. Fim da paginação.")
                break # Sai do while True (fim da paginação para o modelo atual)
            
            except Exception as e:
                # Outros erros inesperados na coleta ou paginação
                print(f"Erro inesperado na coleta/paginação para '{modelo_de_busca}': {e}")
                break 
        
    except Exception as e:
        print(f"Ocorreu um erro FATAL na busca pelo modelo '{modelo_de_busca}': {e}")
        traceback.print_exc()
        continue # Pula para o próximo modelo

# --- FIM DO LOOP ---

# Salva TODOS os resultados acumulados em um único arquivo CSV
if all_results:
    print("\n--- SALVANDO TODOS OS RESULTADOS ACUMULADOS ---")
    # [MODIFICAÇÃO] Adicionado encoding="utf-8" ao open
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