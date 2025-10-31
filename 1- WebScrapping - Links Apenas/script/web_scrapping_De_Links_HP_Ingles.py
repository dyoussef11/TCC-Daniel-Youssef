import sys
from pathlib import Path
import csv
import time
import random # Importado para pausas anti-bloqueio
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
import undetected_chromedriver as uc
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException
from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.common.keys import Keys
import traceback

# --- Configuração de Caminhos e Módulos (Mantida) ---
caminho_script = Path(__file__).resolve().parent
caminho_raiz_projeto = caminho_script.parent.parent
sys.path.append(str(caminho_raiz_projeto))

from config import DIRETORIO_DADOS_WEBSCRAPPING, DIRETORIO_CSV_DATASET_FINAL
from modelo_de_busca import ler_e_filtrar_modelos

# --- CONFIGURAÇÃO DE ARQUIVOS E CHECKPOINT ---
caminho_saida = DIRETORIO_DADOS_WEBSCRAPPING / 'links_discussoes_HP_Ingles.csv'
caminho_entrada = DIRETORIO_CSV_DATASET_FINAL / 'dataset_laptops.csv'
# NOVO: Caminho para o arquivo de rastreamento de progresso
caminho_modelos_concluidos = DIRETORIO_DADOS_WEBSCRAPPING / 'modelos_concluidos_HP_Ingles.txt'

# Garante que os diretórios de saída existam
caminho_saida.parent.mkdir(parents=True, exist_ok=True)

# --- FUNÇÕES DE CHECKPOINTING E PROGRESSO (NOVAS) ---

def carregar_modelos_concluidos(path: Path) -> set:
    """Carrega modelos já processados de um arquivo de texto para retomar o progresso."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return {line.strip() for line in f if line.strip()}
    except FileNotFoundError:
        return set()

def marcar_modelo_concluido(path: Path, modelo: str):
    """Adiciona um modelo à lista de concluídos."""
    with open(path, 'a', encoding='utf-8') as f:
        f.write(modelo + '\n')

def salvar_resultados_incrementais(path: Path, resultados: list, modelo_de_busca: str):
    """Salva a lista de links no arquivo CSV, anexando os dados."""
    
    if not resultados:
        print(f"Nenhum resultado para salvar para o modelo '{modelo_de_busca}'.")
        return

    # Verifica se o arquivo existe ou está vazio para decidir se deve escrever o cabeçalho
    escrever_cabecalho = not path.exists() or path.stat().st_size == 0

    try:
        # Usa 'a' (append) para anexar os novos dados
        with open(path, 'a', newline='', encoding='utf-8') as file:
            fieldnames = ['Título da Discussão', 'Link da Discussão', 'Modelo Buscado']
            writer = csv.writer(file)
            
            if escrever_cabecalho:
                writer.writerow(fieldnames)
                
            for title, url, modelo in resultados:
                writer.writerow([title, url, modelo])
            
        print(f"Resultados do modelo '{modelo_de_busca}' APENDADOS ao arquivo de saída.")
    except Exception as e:
        print(f"ERRO ao salvar resultados incrementais para o modelo '{modelo_de_busca}': {e}")
        # traceback.print_exc()

# --- Configuração de Busca e Retomada ---
MARCA_ALVO = 'HP'
TIPO_NOTEBOOK = 'Gamer'
modelos_a_buscar_bruto= ler_e_filtrar_modelos(caminho_entrada, MARCA_ALVO, TIPO_NOTEBOOK)

# 1. Carregar modelos já concluídos de execuções anteriores
modelos_concluidos = carregar_modelos_concluidos(caminho_modelos_concluidos)
print(f"Progresso carregado. {len(modelos_concluidos)} modelos HP já foram processados.")



# 3. Filtra os modelos brutos para pular os concluídos
modelos_a_buscar = [
    modelo for modelo in modelos_a_buscar_bruto 
    if modelo not in modelos_concluidos
]

if not modelos_a_buscar and modelos_a_buscar_bruto:
    print("Todos os modelos HP no CSV já foram processados. Processo encerrado.")
    sys.exit()
elif not modelos_a_buscar:
    print(f"Não foram encontrados modelos para a marca '{MARCA_ALVO}' no arquivo CSV ou houve um erro na leitura. Saindo.")
    sys.exit()

print(f"Iniciando busca para {len(modelos_a_buscar)} de {len(modelos_a_buscar_bruto)} modelos totais.")


# --- Configurações iniciais do Selenium ---
chrome_options = Options()
# Mantido em headless para agilidade, mas pode ser desativado para debug
chrome_options.add_argument("--headless") 
chrome_options.add_argument("--window-size=1920,1080")
chrome_options.add_argument("--blink-settings=imagesEnabled=false")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--no-sandbox")

# Inicializa o driver (fora do try principal para ser acessível no finally)
driver = uc.Chrome(service=ChromeService(ChromeDriverManager().install()), options=chrome_options)
# Aumentado o timeout para 30s para maior segurança
wait = WebDriverWait(driver, 30) 

site_url = "https://h30434.www3.hp.com/"

# --- Seletores do Fórum HP ---
SELETOR_INPUT = 'input[placeholder="Search all content"]'
SELETOR_COOKIE_HP = 'button[id*="onetrust-accept-btn-handler"]'
SELETOR_LINKS_DISCUSSAO = 'a[class*="page-link lia-link-navigation lia-custom-event"]'
SELETOR_PROXIMA_PAGINA = '//a[@aria-label="Next Page"]'

# Lista para armazenar todos os links coletados (para unicidade *dentro* da sessão)
all_discussion_links = [] 

# --- LOOP PRINCIPAL ENVOLTO POR TRY/FINALLY ---
try:
    for i, modelo_de_busca in enumerate(modelos_a_buscar):
        # Reinicia a lista de resultados para o modelo atual
        current_model_results = []
        
        # Pausa Estratégica e Aleatória entre modelos
        if i > 0:
            sleep_time = random.uniform(2, 5) 
            print(f"Pausando por {sleep_time:.2f} segundos antes da busca do próximo modelo.")
            time.sleep(sleep_time)

        termo_de_busca = f'"{modelo_de_busca}"'
        
        print(f"\n{'='*70}")
        print(f"INICIANDO BUSCA {i+1}/{len(modelos_a_buscar)}: Modelo '{modelo_de_busca}'")
        print(f"{'='*70}")

        driver.get(site_url)
        
        try:
            # 1. Fecha o pop-up de cookies
            print("Verificando e fechando o pop-up de cookies...")
            try:
                cookie_button = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, SELETOR_COOKIE_HP)))
                time.sleep(1) # Pequena pausa para garantir que o elemento esteja estável
                cookie_button.click()
                print("Pop-up de cookies fechado.")
                time.sleep(1) 
            except (TimeoutException, NoSuchElementException):
                print("Pop-up de cookies não encontrado ou já fechado.")
                pass
            
            # 2. Insere o termo de busca no campo de texto e inicia a pesquisa
            print("Aguardando e inserindo termo de busca...")
            barra_de_busca = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, SELETOR_INPUT)))
            barra_de_busca.clear()
            barra_de_busca.send_keys(termo_de_busca)
            barra_de_busca.send_keys(Keys.ENTER) # Inicia a busca
            
            # Pausa para o carregamento dos resultados
            time.sleep(random.uniform(3, 5))

            # --- INÍCIO DA EXTRAÇÃO DE LINKS ---
            print("\n--- INICIANDO COLETA DE LINKS ---")

            pagina_atual = 1
            while True:
                print(f"Coletando links da página {pagina_atual}...")
                
                # Re-localiza a lista de elementos em CADA PÁGINA
                try:
                    discussion_elements = WebDriverWait(driver, 15).until(
                        EC.presence_of_all_elements_located((By.CSS_SELECTOR, SELETOR_LINKS_DISCUSSAO))
                    )
                except TimeoutException:
                    print("Nenhum resultado encontrado nesta página (Timeout). Fim da coleta.")
                    break 
                
                novos_links_coletados = 0
                
                # Itera sobre a lista FRESCA
                for element in discussion_elements:
                    try:
                        link = element.get_attribute("href")
                        title = element.text.strip().replace('\n', ' ') 
                    except StaleElementReferenceException:
                        print("Aviso: Elemento Stale encontrado. Pulando este link.")
                        continue 
                    
                    if link and title and not link.endswith('#'): 
                        item_data = (title, link, modelo_de_busca)
                        # Garante que não haja duplicidade *dentro* da sessão atual
                        if item_data not in current_model_results:
                            current_model_results.append(item_data)
                            novos_links_coletados += 1
                
                print(f"Links coletados na Pág {pagina_atual}: {novos_links_coletados}. Total coletado para o modelo: {len(current_model_results)}")

                # Tenta encontrar o botão "Próximo" para a paginação
                try:
                    # Tenta encontrar o botão via XPATH (mais robusto)
                    next_button = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((By.XPATH, SELETOR_PROXIMA_PAGINA))
                    )
                    
                    try:
                        next_button.click()
                        print("Clicando no botão 'Próximo' (tentativa normal)...")
                    except ElementClickInterceptedException:
                        # Força o JS se o clique normal falhar
                        print("Botão interceptado! Tentando clicar via JavaScript...")
                        driver.execute_script("arguments[0].click();", next_button)
                        
                    pagina_atual += 1
                    time.sleep(random.uniform(3, 5)) # Pausa para o carregamento da próxima página
                
                except (TimeoutException, NoSuchElementException):
                    print("Botão 'Próximo' não encontrado ou desabilitado. Fim da paginação.")
                    break
                
            # --- PONTO CRUCIAL DE SALVAMENTO DE CHECKPOINT ---
            # 1. Salva os resultados do modelo ATUAL (incrementalmente)
            # Nota: A lista current_model_results é a lista de tuplas (título, link, modelo)
            salvar_resultados_incrementais(caminho_saida, current_model_results, modelo_de_busca)

            # 2. Marca o modelo como concluído SOMENTE se o processamento terminou
            marcar_modelo_concluido(caminho_modelos_concluidos, modelo_de_busca)
            print(f"Modelo '{modelo_de_busca}' marcado como CONCLUÍDO. Progresso salvo.")


        except Exception as e:
            print(f"Ocorreu um erro durante a busca pelo modelo '{modelo_de_busca}': {e}")
            traceback.print_exc()
            # O modelo não é marcado como concluído, permitindo a retomada dele na próxima execução
            continue 

except KeyboardInterrupt:
    print("\n[INTERRUPÇÃO DETECTADA] Encerrando o processo de forma segura...")
except Exception as e:
    print(f"\n[ERRO FATAL] Ocorreu um erro inesperado: {e}")
    traceback.print_exc()

finally:
    # Garante que o driver seja fechado, mesmo em caso de erro ou interrupção
    if driver:
        driver.quit()
    print("Processo concluído/interrompido. Navegador fechado.")