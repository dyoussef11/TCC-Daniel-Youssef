import sys
from pathlib import Path
import csv
import time
import random # Importar para pausas aleatórias
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException
from selenium.common.exceptions import StaleElementReferenceException # Importação útil
import undetected_chromedriver as uc
import traceback # Importar para melhor rastreamento de erro

# Obtém o caminho absoluto da pasta do script atual.
caminho_script = Path(__file__).resolve().parent
# Acessa a pasta raiz do projeto subindo dois níveis.
caminho_raiz_projeto = caminho_script.parent.parent
# Adiciona o caminho da raiz ao caminho de busca do Python.
sys.path.append(str(caminho_raiz_projeto))

# Agora a importação do módulo 'config' deve funcionar.
from config import DIRETORIO_DADOS_WEBSCRAPPING, DIRETORIO_CSV_DATASET_FINAL
from modelo_de_busca import ler_e_filtrar_modelos

# --- CONFIGURAÇÃO DE ARQUIVOS E CHECKPOINT ---
caminho_saida = DIRETORIO_DADOS_WEBSCRAPPING / 'links_discussoes_Dell_Ingles.csv'
caminho_entrada = DIRETORIO_CSV_DATASET_FINAL / 'dataset_laptops.csv'
# NOVO: Caminho para o arquivo de rastreamento de progresso
caminho_modelos_concluidos = DIRETORIO_DADOS_WEBSCRAPPING / 'modelos_concluidos_Dell_Ingles.txt'

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
                
            # Os resultados já são uma lista de tuplas (title, url, modelo)
            writer.writerows(resultados)
            
        print(f"Resultados do modelo '{modelo_de_busca}' APENDADOS ao arquivo de saída.")
    except Exception as e:
        print(f"ERRO ao salvar resultados incrementais para o modelo '{modelo_de_busca}': {e}")
        # traceback.print_exc()

# --- Configuração de Busca e Filtro de CSV (MODIFICADO PARA RETOMADA) ---
MARCA_ALVO = 'DELL'
TIPO_NOTEBOOK = 'Gamer'
modelos_a_buscar_bruto= ler_e_filtrar_modelos(caminho_entrada, MARCA_ALVO, TIPO_NOTEBOOK)
# 1. Carregar modelos já concluídos de execuções anteriores
modelos_concluidos = carregar_modelos_concluidos(caminho_modelos_concluidos)
print(f"Progresso carregado. {len(modelos_concluidos)} modelos DELL já foram processados.")


# 3. Filtra os modelos brutos para pular os concluídos
modelos_a_buscar = [
    modelo for modelo in modelos_a_buscar_bruto 
    if modelo not in modelos_concluidos
]

if not modelos_a_buscar and modelos_a_buscar_bruto:
    print("Todos os modelos DELL no CSV já foram processados. Processo encerrado.")
    sys.exit()
elif not modelos_a_buscar:
    print(f"Não foram encontrados modelos para a marca '{MARCA_ALVO}' no arquivo CSV ou houve um erro na leitura. Saindo.")
    sys.exit()

print(f"Iniciando busca para {len(modelos_a_buscar)} de {len(modelos_a_buscar_bruto)} modelos totais.")

# --- Configurações iniciais do Selenium ---
chrome_options = Options()
# chrome_options.add_argument("--headless") # Mantido comentado conforme seu original
chrome_options.add_argument("--window-size=1920,1080")
chrome_options.add_argument("--blink-settings=imagesEnabled=false")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument(f"user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.75 Safari/537.36")

# Inicializa o driver (fora do bloco try/except principal para ser acessível no finally)
driver = uc.Chrome(version_main=141, options=chrome_options)
wait = WebDriverWait(driver, 15) # Usamos o wait mais longo

site_url = "https://www.dell.com/community/en/categories/dell-community"

# --- SELETORES EM VARIÁVEIS ---
SELETOR_COOKIE = "onetrust-accept-btn-handler"
SELETOR_DIGITAR_BUSCA = 'input[placeholder="Search"]'
SELETOR_BOTAO_BUSCA = ".search-input__submit-button-lg.search-input__submit-button__right"
SELETOR_DROPDOWN_TIPO_CONVERSA = ".conversation-types-filter__dropdown .Select-control"
SELETOR_OPCAO_POSTS = "//div[contains(@class, 'Select-option') and contains(., 'Posts')]"
SELETOR_CONTAINER_FILTRO_CATEGORIA = ".category-hierarchy-filter"
SELETOR_OPCAO_LAPTOPS = "//div[contains(@class, 'category-hierarchy-filter__option flex center-y') and contains(., 'Laptops')]"
SELETOR_ELEMENTOS_DISCUSSAO = "section.conversation-card .conversation-card__details a[title]"
SELETOR_NEXT_BUTTON = 'li[title="Next"]'

# --- LOOP PRINCIPAL ENVOLTO POR TRY/FINALLY PARA ENCERRAMENTO SEGURO ---
try:
    for i, modelo_de_busca in enumerate(modelos_a_buscar):
        # Reinicia a lista de resultados para o modelo atual
        current_model_results = []
        
        # Pausa Estratégica e Aleatória (Anti-Bloqueio)
        if i > 0:
            sleep_time = random.uniform(2, 5) 
            print(f"Pausando por {sleep_time:.2f} segundos antes da busca do próximo modelo.")
            time.sleep(sleep_time)

        # Formata o termo para busca avançada
        termo_de_busca = f'"{modelo_de_busca}"'
        
        # --- LOG DE INÍCIO DE BUSCA ---
        print(f"\n{'='*70}")
        print(f"INICIANDO BUSCA (Dell Community INGLES) {i+1}/{len(modelos_a_buscar)} (Total de {len(modelos_a_buscar_bruto)}): Modelo '{modelo_de_busca}'")
        print(f"{'='*70}")
        
        driver.get(site_url)

        try:
            # 1. Fecha o pop-up de cookies se ele existir
            try:
                cookie_button = wait.until(EC.element_to_be_clickable((By.ID, SELETOR_COOKIE)))
                cookie_button.click()
                time.sleep(1)
                print("Pop-up de cookies fechado.")
            except:
                print("Pop-up de cookies não encontrado ou já fechado.")
                pass

            # 2. BLOCO DE BUSCA
            print("Aguardando o campo de busca...")
            barra_de_busca = wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, SELETOR_DIGITAR_BUSCA))
            )
            barra_de_busca.click()

            # Tenta re-capturar ou usa o elemento original para enviar chaves
            try:
                 barra_de_busca_atualizada = driver.find_element(By.CSS_SELECTOR, SELETOR_DIGITAR_BUSCA)
            except NoSuchElementException:
                 barra_de_busca_atualizada = barra_de_busca
            
            barra_de_busca_atualizada.clear()
            barra_de_busca_atualizada.send_keys(termo_de_busca)
            
            print(f"Texto '{termo_de_busca}' inserido no campo de busca.")
            
            # Clica no botão de busca
            botao_de_busca = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, SELETOR_BOTAO_BUSCA)))
            botao_de_busca.click()
            
            print("Pesquisa realizada com sucesso!")
            time.sleep(random.uniform(2, 4)) # Pausa mais robusta após a busca

            # 3. FILTRO DE TIPO DE CONVERSA (POSTS)
            print("Aguardando e aplicando filtro 'Posts'...")
            tipo_de_conversa_dropdown = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, SELETOR_DROPDOWN_TIPO_CONVERSA)))
            tipo_de_conversa_dropdown.click()
            
            publicacoes_option = wait.until(EC.element_to_be_clickable((By.XPATH, SELETOR_OPCAO_POSTS)))
            publicacoes_option.click()
            print("Opção 'Posts' selecionada.")
            time.sleep(random.uniform(2, 3))


            # 4. FILTRO DE CATEGORIA (LAPTOPS)
            print("\n--- APLICANDO FILTRO DE CATEGORIA ---")
            filtro_categoria_container = wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, SELETOR_CONTAINER_FILTRO_CATEGORIA))
            )
            filtro_categoria_container.click()
            
            laptops_option = wait.until(
                EC.element_to_be_clickable((By.XPATH, SELETOR_OPCAO_LAPTOPS))
            )
            laptops_option.click()
            print("Opção 'Laptops' selecionada e filtro aplicado.")
            time.sleep(random.uniform(2, 4)) # Pausa para carregamento do filtro
            
            # --- INÍCIO DA EXTRAÇÃO DE LINKS ---
            print("\n--- INICIANDO COLETA DE LINKS ---")

            while True:
                # Extrai os links da página atual
                print("Coletando links da página atual...")
                
                try:
                     discussion_elements = WebDriverWait(driver, 10).until(
                        EC.presence_of_all_elements_located((By.CSS_SELECTOR, SELETOR_ELEMENTOS_DISCUSSAO))
                    )
                except TimeoutException:
                    print("Timeout: Nenhum resultado encontrado nesta página após o filtro. Fim da coleta para o modelo.")
                    break
                
                novos_links_coletados = 0
                for element in discussion_elements:
                    try:
                        link = element.get_attribute("href")
                        title = element.get_attribute("title")
                        
                        if link and title:
                            item_data = (title, link, modelo_de_busca)
                            # Adiciona à lista local do modelo atual
                            current_model_results.append(item_data)
                            novos_links_coletados += 1
                    except StaleElementReferenceException:
                         print("Aviso: StaleElementReferenceException detectada. Reiniciando a coleta de elementos.")
                         break # Sai do loop for e tenta re-localizar os elementos no loop while
                    except Exception as e:
                         # Captura outros erros de extração de atributos
                         print(f"Erro ao extrair link/título de um elemento: {e}")
                         continue
                
                print(f"Novos links coletados: {novos_links_coletados}. Total de links acumulados para o modelo: {len(current_model_results)}")

                # Tenta encontrar o botão "Próximo"
                try:
                    next_button = WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.CSS_SELECTOR, SELETOR_NEXT_BUTTON)))
                    
                    if 'disabled' in next_button.get_attribute('class'):
                         print("Botão 'Next' desabilitado. Fim da paginação.")
                         break

                    print("Clicando no botão 'Next'...")
                    driver.execute_script("arguments[0].click();", next_button)
                    time.sleep(random.uniform(1, 2)) # Pausa para a próxima página carregar
                    
                except (TimeoutException, NoSuchElementException, ElementClickInterceptedException):
                    print("Botão 'Next' não encontrado ou desabilitado. Fim da paginação.")
                    break
                except Exception as e:
                    print(f"Erro inesperado na paginação: {e}")
                    break
                
            # --- PONTO CRUCIAL DE SALVAMENTO DE CHECKPOINT ---
            # 1. Salva os resultados do modelo ATUAL (incrementalmente)
            salvar_resultados_incrementais(caminho_saida, current_model_results, modelo_de_busca)

            # 2. Marca o modelo como concluído SOMENTE se o processamento terminou
            marcar_modelo_concluido(caminho_modelos_concluidos, modelo_de_busca)
            print(f"Modelo '{modelo_de_busca}' marcado como CONCLUÍDO. Progresso salvo.")
        
        except Exception as e:
            print(f"Ocorreu um erro FATAL na busca pelo modelo '{modelo_de_busca}'. Pulando para o próximo.")
            traceback.print_exc()
            continue # Pula para o próximo modelo

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