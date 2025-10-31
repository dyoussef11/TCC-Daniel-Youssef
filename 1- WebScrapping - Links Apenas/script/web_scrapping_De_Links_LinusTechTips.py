import sys
from pathlib import Path
import csv
import time
import random # [MODIFICAÇÃO] Importar random para pausas aleatórias
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
from selenium.webdriver.chrome.options import Options
import traceback # Importar para melhor rastreamento de erro
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager

# Obtém o caminho absoluto da pasta do script atual.
caminho_script = Path(__file__).resolve().parent
caminho_raiz_projeto = caminho_script.parent.parent
sys.path.append(str(caminho_raiz_projeto))

# Agora a importação do módulo 'config' e 'modelo_de_busca' deve funcionar.
from config import DIRETORIO_DADOS_WEBSCRAPPING, DIRETORIO_CSV_DATASET_FINAL
from modelo_de_busca import ler_e_filtrar_modelos 

# --- CONFIGURAÇÃO DE ARQUIVOS E CHECKPOINT ---
caminho_saida = DIRETORIO_DADOS_WEBSCRAPPING / 'links_discussoes_LinusTechTips.csv'
caminho_modelos_concluidos = DIRETORIO_DADOS_WEBSCRAPPING / 'modelos_concluidos_Linus_Tech_Tips.txt'
caminho_entrada = DIRETORIO_CSV_DATASET_FINAL / 'dataset_laptops.csv'

# --- FUNÇÕES DE CHECKPOINTING E PROGRESSO ---

def carregar_modelos_concluidos(path: Path) -> set:
    """Carrega modelos já processados de um arquivo de texto para retomar o progresso."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            # Retorna um set para buscas O(1) rápidas e para garantir unicidade
            return {line.strip() for line in f if line.strip()}
    except FileNotFoundError:
        return set()

def marcar_modelo_concluido(path: Path, modelo: str):
    """Adiciona um modelo à lista de concluídos."""
    # Abre o arquivo para anexar (append)
    with open(path, 'a', encoding='utf-8') as f:
        f.write(modelo + '\n')

def salvar_resultados_incrementais(path: Path, resultados: list, modelo_de_busca: str):
    """Salva os resultados do modelo atual no arquivo CSV, anexando os dados."""
    
    if not resultados:
        print(f"Nenhum resultado para salvar para o modelo '{modelo_de_busca}'.")
        return

    # Verifica se o arquivo existe ou está vazio para decidir se deve escrever o cabeçalho
    escrever_cabecalho = not path.exists() or path.stat().st_size == 0

    try:
        with open(path, 'a', newline='', encoding='utf-8') as file:
            fieldnames = ['Título da Discussão', 'Link da Discussão', 'Modelo Buscado']
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            
            if escrever_cabecalho:
                writer.writeheader()
                
            writer.writerows(resultados)
            
        print(f"Resultados do modelo '{modelo_de_busca}' APENDADOS ao arquivo de saída.")
    except Exception as e:
        print(f"ERRO ao salvar resultados incrementais para o modelo '{modelo_de_busca}': {e}")
        # traceback.print_exc()

MARCA_ALVO = None
TIPO_NOTEBOOK = 'Gamer'
modelos_a_buscar_bruto = ler_e_filtrar_modelos(caminho_entrada, MARCA_ALVO, TIPO_NOTEBOOK)


# 1. Carregar modelos já concluídos de execuções anteriores
modelos_concluidos = carregar_modelos_concluidos(caminho_modelos_concluidos)
print(f"Progresso carregado. {len(modelos_concluidos)} modelos já foram processados.")

# 2. Lê todos os modelos do CSV
modelos_a_buscar_bruto = ler_e_filtrar_modelos(caminho_entrada, MARCA_ALVO, TIPO_NOTEBOOK)

# 3. Filtra os modelos brutos para pular os concluídos
modelos_a_buscar = [
    modelo for modelo in modelos_a_buscar_bruto 
    if modelo not in modelos_concluidos
]

if not modelos_a_buscar and modelos_a_buscar_bruto:
    print("Todos os modelos no CSV já foram processados. Processo encerrado.")
    sys.exit()
elif not modelos_a_buscar:
    print(f"Não foram encontrados modelos para a marca '{MARCA_ALVO}' no arquivo CSV ou houve um erro na leitura. Saindo.")
    sys.exit()

print(f"Iniciando busca para {len(modelos_a_buscar)} de {len(modelos_a_buscar_bruto)} modelos totais.")

# --- CONSTANTES DE CONFIGURAÇÃO E DADOS ---
SITE_URL = "https://linustechtips.com/search/"

# --- DECLARAÇÕES DE HTML EM VARIÁVEIS (Seletores) ---
SELETOR_CAMPO_BUSCA = "q" 
SELETOR_LINKS_RESULTADO = "ol.ipsStream a[data-linktype='link']"
SELETOR_BOTAO_PROXIMA_PAGINA = "li.pagination-next a"

# Use undetected-chromedriver instead of standard Selenium
chrome_options = Options()
chrome_options.add_argument("--headless") 
chrome_options.add_argument("--window-size=1920,1080")
chrome_options.add_argument("--blink-settings=imagesEnabled=false")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument(f"user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.75 Safari/537.36")


# Inicializa o driver APENAS UMA VEZ.
driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=chrome_options)
wait = WebDriverWait(driver, 15)

try:
    for i, modelo_de_busca in enumerate(modelos_a_buscar):
        # Reinicia a lista de resultados para o modelo atual
        current_model_results = []
        
        # Pausa Estratégica e Aleatória entre modelos
        if i > 0:
            sleep_time = random.uniform(1, 3) 
            print(f"Pausando por {sleep_time:.2f} segundos antes da busca do próximo modelo.")
            time.sleep(sleep_time)

        # Formata o termo de busca: o nome do modelo entre aspas para busca exata
        termo_de_busca = f'{modelo_de_busca}'
        
        # ======================================================================================
        # ADIÇÃO DO LOG SOLICITADO
        # ======================================================================================
        print(f"\n{'='*70}")
        print(f"INICIANDO BUSCA (Linus Tech Tips) {i+1}/{len(modelos_a_buscar)} (Total de {len(modelos_a_buscar_bruto)}): Modelo '{modelo_de_busca}'")
        print(f"{'='*70}")
        # ======================================================================================

        # 1. Navegar para a página de busca (necessário a cada novo termo)
        driver.get(SITE_URL)

        try:
            print("Aguardando o campo de busca...")
            barra_de_busca = wait.until(EC.presence_of_element_located((By.NAME, SELETOR_CAMPO_BUSCA)))

            # 2. Realiza a busca
            actions = ActionChains(driver)
            actions.move_to_element(barra_de_busca).click().send_keys(termo_de_busca).send_keys(Keys.ENTER).perform()
            print(f"Texto '{termo_de_busca}' inserido. Pesquisa iniciada. Aguardando resultados...")

            # --- INICIANDO EXTRAÇÃO DE DADOS ---
            while True:
                try:
                    # Espera que os resultados carreguem
                    discussion_titles_elements = WebDriverWait(driver, 10).until(
                        EC.presence_of_all_elements_located((By.CSS_SELECTOR, SELETOR_LINKS_RESULTADO))
                    )
                    
                    # Verifica explicitamente se não há resultados
                    if not discussion_titles_elements and ('page=1' in driver.current_url or 'search/?type=post' in driver.current_url):
                        print("Zero resultados encontrados na primeira página. Finalizando coleta para o modelo.")
                        break

                except TimeoutException:
                    print("Timeout no carregamento dos links. Tentando encontrar o botão Próximo...")
                
                novos_links = 0
                print("Coletando títulos e links da página atual...")
                
                # Re-localizar elementos para evitar StaleElementReferenceException
                current_elements = driver.find_elements(By.CSS_SELECTOR, SELETOR_LINKS_RESULTADO)
                
                for element in current_elements:
                    try:
                        link = element.get_attribute("href")
                        title = element.text.strip()
                        
                        result_data = {
                            "Título da Discussão": title, 
                            "Link da Discussão": link,
                            "Modelo Buscado": modelo_de_busca # Usa o modelo do loop
                        }
                        
                        # Check for and prevent duplicate entries in the current session
                        # Se o checkpoint estivesse carregando dados, faríamos a unicidade globalmente.
                        if not any(d['Link da Discussão'] == link for d in current_model_results):
                            current_model_results.append(result_data)
                            novos_links += 1
                            
                    except StaleElementReferenceException:
                        continue # Pula o elemento instável
                    except Exception as e:
                        print(f"Erro ao ler elemento: {e}")
                        continue
                
                print(f"Novos links coletados: {novos_links}. Total de resultados coletados para o modelo: {len(current_model_results)}")

                # Tenta encontrar o botão "Próximo" para paginação
                try:
                    next_button = WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.CSS_SELECTOR, SELETOR_BOTAO_PROXIMA_PAGINA)))
                    
                    # Clica via JS para maior robustez
                    driver.execute_script("arguments[0].click();", next_button)
                    print("Clicando no botão 'Próximo'...")
                    
                    # Pausa aleatória na paginação
                    sleep_time_page = random.uniform(1, 2) 
                    time.sleep(sleep_time_page)
                    
                except (TimeoutException, NoSuchElementException):
                    print("Botão 'Próximo' não encontrado ou tempo de espera esgotado. Fim da paginação.")
                    break
                except Exception as e:
                    print(f"Ocorreu um erro durante a paginação. Finalizando. Detalhe do erro: {e}")
                    break
            
            # --- PONTO CRUCIAL DE SALVAMENTO DE CHECKPOINT ---
            # 1. Salva os resultados do modelo ATUAL (incrementalmente)
            salvar_resultados_incrementais(caminho_saida, current_model_results, modelo_de_busca)

            # 2. Marca o modelo como concluído SOMENTE se o processamento terminou
            marcar_modelo_concluido(caminho_modelos_concluidos, modelo_de_busca)
            print(f"Modelo '{modelo_de_busca}' marcado como CONCLUÍDO. Progresso salvo.")
            
        except Exception as e:
            print(f"Ocorreu um erro durante a busca pelo modelo '{modelo_de_busca}'. Pulando para o próximo. Erro: {e}")
            traceback.print_exc()
            continue # Pula para o próximo modelo

except KeyboardInterrupt:
    print("\n[INTERRUPÇÃO DETECTADA] Encerrando o processo de forma segura...")
except Exception as e:
    print(f"Ocorreu um erro FATAL: {e}")
    traceback.print_exc()

finally:
    # Always close the browser
    if driver:
        driver.quit()
    print("Processo concluído/interrompido. Navegador fechado.")