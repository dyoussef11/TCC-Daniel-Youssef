import sys
from pathlib import Path
import csv
import time
import random
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException
from selenium.common.exceptions import StaleElementReferenceException
import undetected_chromedriver as uc
import traceback

# --- CONFIGURAÇÃO DE CAMINHOS ---
# Obtém o caminho absoluto da pasta do script atual.
caminho_script = Path(__file__).resolve().parent
# Acessa a pasta raiz do projeto subindo dois níveis.
caminho_raiz_projeto = caminho_script.parent.parent
# Adiciona o caminho da raiz ao caminho de busca do Python.
sys.path.append(str(caminho_raiz_projeto))

# Tenta importar config, se falhar define diretórios locais para evitar erro
try:
    from config import DIRETORIO_DADOS_WEBSCRAPPING, DIRETORIO_CSV_DATASET_FINAL
except ImportError:
    DIRETORIO_DADOS_WEBSCRAPPING = caminho_script / 'dados_webscrapping'
    DIRETORIO_CSV_DATASET_FINAL = caminho_script / 'dataset'

DIRETORIO_DADOS_WEBSCRAPPING.mkdir(parents=True, exist_ok=True)
caminho_saida = DIRETORIO_DADOS_WEBSCRAPPING / 'links_discussoes_Dell_Brasil_UNICO_MODELO.csv'
caminho_modelos_concluidos = DIRETORIO_DADOS_WEBSCRAPPING / 'modelo_concluido_Dell_Brasil.txt'

# --- FUNÇÕES AUXILIARES ---

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
    """Salva a lista de links no arquivo CSV, ANEXANDO os dados."""
    
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
                
            # Os resultados são uma lista de tuplas (title, url, modelo)
            writer.writerows(resultados)
            
        print(f"Resultados do modelo '{modelo_de_busca}' APENDADOS ao arquivo de saída.")
    except Exception as e:
        print(f"ERRO ao salvar resultados incrementais para o modelo '{modelo_de_busca}': {e}")


# --- CONFIGURAÇÃO DE BUSCA MANUAL ---

# Definimos manualmente o modelo (sem aspas aqui, o script adiciona aspas de busca depois)
modelo_alvo_string = "Dell G7 15 7588"

# Criamos a lista com apenas este item
modelos_a_buscar = [modelo_alvo_string]

# Ajuste de variáveis para compatibilidade com os prints originais
modelos_a_buscar_bruto = modelos_a_buscar 

print(f"--- MODO MANUAL ---")
print(f"Buscando apenas pelo modelo: '{modelo_alvo_string}'")

# --- Configurações iniciais do Selenium ---
chrome_options = Options()
# chrome_options.add_argument("--headless") # Descomente se quiser rodar sem interface
chrome_options.add_argument("--window-size=1920,1080")
chrome_options.add_argument("--blink-settings=imagesEnabled=false")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--no-sandbox")

# Inicializa o driver
driver = uc.Chrome(version_main=141, options=chrome_options)
wait = WebDriverWait(driver, 30)

site_url = "https://www.dell.com/community/pt/categories/comunidade-da-dell"

cookie_popup_fechado = False

# --- SELETORES (MANTIDOS ORIGINAIS) ---
SELETOR_DIGITAR = 'input[placeholder="Pesquisar"]'
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


# --- LOOP PRINCIPAL ---
try:
    for i, modelo_de_busca in enumerate(modelos_a_buscar):
        # Reinicia a lista de links para o modelo atual
        current_model_results = [] 
        links_modelo_atual = 0

        # Pausa Estratégica se houver mais de um modelo (não se aplica aqui, mas mantido a lógica)
        if i > 0:
            sleep_time = random.uniform(2, 5) 
            print(f"Pausando por {sleep_time:.2f} segundos.")
            time.sleep(sleep_time)
        
        # Formata o termo para busca avançada (adiciona aspas para busca exata)
        termo_de_busca = f'"{modelo_de_busca}"'
        
        # --- LOG DE INÍCIO DE BUSCA ---
        print(f"\n{'='*70}")
        print(f"INICIANDO BUSCA: Modelo '{modelo_de_busca}'")
        print(f"{'='*70}")

        driver.get(site_url)

        try:
            # 1. Fecha o pop-up de cookies se ele existir (apenas na primeira iteração)
            if not cookie_popup_fechado:
                try:
                    cookie_button = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.ID, SELETOR_COOKIE)))
                    cookie_button.click()
                    time.sleep(1)
                    cookie_popup_fechado = True
                    print("Pop-up de cookies fechado.")
                except:
                    print("Pop-up de cookies não encontrado ou já fechado.")
                    pass
            
            # 2. INSERÇÃO E BUSCA
            print("Aguardando o campo de busca...")
            barra_de_busca = wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, SELETOR_DIGITAR))
            )
            barra_de_busca.click()

            # Lógica para evitar Stale Element
            barra_de_busca_atualizada = driver.find_element(By.CSS_SELECTOR, SELETOR_DIGITAR)
            
            barra_de_busca_atualizada.clear()
            barra_de_busca_atualizada.send_keys(termo_de_busca)
            
            print(f"Texto '{termo_de_busca}' inserido no campo de busca.")
            
            # Clica no botão de busca
            print("Aguardando o botão de busca...")
            botao_de_busca = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, SELETOR_BUSCA)))
            botao_de_busca.click()
            
            print("Pesquisa realizada com sucesso! Aguardando resultados...")
            time.sleep(random.uniform(3, 5))

            # 3. FILTRO DE TIPO DE CONVERSA (PUBLICACÕES)
            print("Aguardando e aplicando filtro 'Publicações'...")
            tipo_de_conversa_dropdown = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, SELETOR_DROPDOWN_TIPO_CONVERSA)))
            tipo_de_conversa_dropdown.click()
            
            publicacoes_option = wait.until(EC.element_to_be_clickable((By.XPATH, SELETOR_OPCAO_PUBLICACOES)))
            publicacoes_option.click()
            print("Opção 'Publicações' selecionada.")
            time.sleep(random.uniform(2, 4))


            # 4. FILTRO DE CATEGORIA (NOTEBOOKS/LAPTOPS)
            print("\n--- APLICANDO FILTRO DE CATEGORIA ---")
            
            filtro_categoria_container = wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, SELETOR_CONTAINER_FILTRO_CATEGORIA)) 
            )
            filtro_categoria_container.click()
            
            print("Aguardando a opção 'Notebooks/Laptops'...")
            
            laptops_option = wait.until(
                EC.element_to_be_clickable((By.XPATH, SELETOR_OPCAO_NOTEBOOKS_LAPTOPS))
            )
            laptops_option.click() 
            print("Opção 'Notebooks/Laptops' selecionada e filtro aplicado.")

            time.sleep(random.uniform(1, 2)) 
            
            # --- INÍCIO DA EXTRAÇÃO DE LINKS ---
            print("\n--- INICIANDO COLETA DE LINKS ---")
            
            pagina_atual = 1
            while True:
                # Extrai os links da página atual
                print(f"Coletando links da página {pagina_atual}...")
                
                try:
                    # Tenta esperar que PELO MENOS um elemento de discussão esteja presente
                    discussion_elements = WebDriverWait(driver, 10).until(
                        EC.presence_of_all_elements_located((By.CSS_SELECTOR, SELETOR_ELEMENTOS_DISCUSSAO))
                    )
                except TimeoutException:
                    discussion_elements = []

                # Verifica zero resultados na primeira página
                if not discussion_elements and pagina_atual == 1:
                    print(f"**ALERTA: Zero resultados para o modelo '{modelo_de_busca}'.**")
                    break
                elif not discussion_elements:
                    # Se não há links, mas não é a primeira página (fim da paginação)
                    break 

                
                novos_links_coletados = 0
                for element in discussion_elements:
                    try:
                        link = element.get_attribute("href")
                        title = element.get_attribute("title")
                        
                        if link and title:
                            item_data = (title, link, modelo_de_busca)
                            
                            if item_data not in current_model_results:
                                current_model_results.append(item_data)
                                novos_links_coletados += 1
                                links_modelo_atual += 1
                    except StaleElementReferenceException:
                         print("Aviso: StaleElementReferenceException detectada.")
                         break
                    except Exception as e:
                         print(f"Erro ao extrair link/título: {e}")
                         continue
                
                print(f"Novos links coletados nesta página: {novos_links_coletados}. Total: {links_modelo_atual}")

                # Tenta encontrar o botão "Próximo"
                try:
                    next_button = WebDriverWait(driver, 2).until(EC.element_to_be_clickable((By.CSS_SELECTOR, SELETOR_NEXT_BUTTON)))
                    
                    if 'disabled' in next_button.get_attribute('class'):
                         print("Botão 'Próximo' desabilitado. Fim da paginação.")
                         break

                    print("Clicando no botão 'Próximo'...")
                    driver.execute_script("arguments[0].click();", next_button)
                    pagina_atual += 1
                    time.sleep(random.uniform(1.5, 3)) # Pausa para a próxima página carregar
                    
                except (TimeoutException, NoSuchElementException, ElementClickInterceptedException):
                    print("Botão 'Próximo' não encontrado ou desabilitado. Fim da paginação.")
                    break
                except Exception as e:
                    print(f"Erro inesperado na paginação: {e}")
                    break
                
            # --- SALVAMENTO ---
            # 1. Salva os resultados do modelo ATUAL (incrementalmente)
            salvar_resultados_incrementais(caminho_saida, current_model_results, modelo_de_busca)

            # 2. Marca o modelo como concluído
            marcar_modelo_concluido(caminho_modelos_concluidos, modelo_de_busca)
            print(f"Modelo '{modelo_de_busca}' finalizado com sucesso.")
        
        except Exception as e:
            print(f"Ocorreu um erro FATAL na busca pelo modelo '{modelo_de_busca}'.")
            traceback.print_exc()
            continue

except KeyboardInterrupt:
    print("\n[INTERRUPÇÃO DETECTADA] Encerrando o processo de forma segura...")
except Exception as e:
    print(f"\n[ERRO FATAL] Ocorreu um erro inesperado: {e}")
    traceback.print_exc()

finally:
    if driver:
        driver.quit()
    print("Processo concluído/interrompido. Navegador fechado.")