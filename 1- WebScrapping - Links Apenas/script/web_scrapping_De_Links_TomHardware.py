import sys
from pathlib import Path
import csv
import time
import random
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
import traceback 

# --- FUNÇÕES DE CHECKPOINTING E PROGRESSO (NOVAS) ---

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
            fieldnames = ['Título', 'Link', 'Modelo Buscado']
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            
            if escrever_cabecalho:
                writer.writeheader()
                
            writer.writerows(resultados)
            
        print(f"Resultados do modelo '{modelo_de_busca}' APENDADOS ao arquivo de saída.")
    except Exception as e:
        print(f"ERRO ao salvar resultados incrementais para o modelo '{modelo_de_busca}': {e}")
        # traceback.print_exc()

# --- CONFIGURAÇÕES DE CAMINHO ---
caminho_script = Path(__file__).resolve().parent
caminho_raiz_projeto = caminho_script.parent.parent
sys.path.append(str(caminho_raiz_projeto))

from config import DIRETORIO_DADOS_WEBSCRAPPING, DIRETORIO_CSV_DATASET_FINAL
from modelo_de_busca import ler_e_filtrar_modelos 

caminho_saida = DIRETORIO_DADOS_WEBSCRAPPING / 'links_discussoes_Tom_Hardware.csv'
caminho_modelos_concluidos = DIRETORIO_DADOS_WEBSCRAPPING / 'modelos_concluidos_Tom_Hardware.txt'
caminho_entrada = DIRETORIO_CSV_DATASET_FINAL / 'dataset_laptops.csv'

# --- Configuração de Busca e Filtro de CSV (MODIFICADO PARA RETOMADA) ---
MARCA_ALVO = None
TIPO_NOTEBOOK = 'Gamer' 


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

# --- DECLARAÇÕES DE HTML ---
SITE_URL = "https://forums.tomshardware.com/search/"
SELETOR_CAMPO_BUSCA = "keywords" 
SELETOR_LINKS_TITULOS = "h3.contentRow-title a" 
SELETOR_BOTAO_PROXIMA_PAGINA = "a[rel='next']" 

# --- Configurações iniciais do Selenium ---
chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--window-size=1920,1080")
chrome_options.add_argument("--blink-settings=imagesEnabled=false")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument(f"user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.75 Safari/537.36")

# Inicializa o driver (fora do bloco try/except principal para ser acessível no finally)
driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=chrome_options)
wait = WebDriverWait(driver, 15)

# --- LOOP PRINCIPAL ENVOLTO POR TRY/FINALLY PARA ENCERRAMENTO SEGURO ---
try:
    for i, modelo_de_busca in enumerate(modelos_a_buscar):
        # Reinicia a lista de resultados para o modelo atual
        current_model_results = []
        
        # Pausa Estratégica
        if i > 0:
            sleep_time = random.uniform(0, 1) 
            print(f"Pausando por {sleep_time:.2f} segundos antes da busca do próximo modelo.")
            time.sleep(sleep_time)
            
        termo_de_busca = f'"{modelo_de_busca}"'
        
        print(f"\n{'='*70}")
        print(f"INICIANDO BUSCA (Tom Hardware) {i+1}/{len(modelos_a_buscar)} (Total de {len(modelos_a_buscar_bruto)}): Modelo '{modelo_de_busca}'")
        print(f"{'='*70}")
        
        # 1. Navegar para a página de busca
        driver.get(SITE_URL)

        try:
            # --- Realizar a busca ---
            barra_de_busca = wait.until(EC.element_to_be_clickable((By.NAME, SELETOR_CAMPO_BUSCA)))
            barra_de_busca.click()
            barra_de_busca.clear()
            barra_de_busca.send_keys(termo_de_busca)
            barra_de_busca.send_keys(Keys.ENTER)
            
            print(f"Pesquisa iniciada. Aguardando resultados...")

            # --- INÍCIO DA EXTRAÇÃO DE DADOS ---
            while True:
                try:
                    # Espera pelos resultados da página
                    discussion_titles = WebDriverWait(driver, 10).until(
                        EC.presence_of_all_elements_located((By.CSS_SELECTOR, SELETOR_LINKS_TITULOS))
                    )
                except TimeoutException:
                    # Se não houver resultados após o timeout, verifica se o site indicou 0 resultados
                    if not driver.find_elements(By.CSS_SELECTOR, SELETOR_LINKS_TITULOS):
                        print(f"Zero resultados encontrados para o modelo '{modelo_de_busca}' nesta página. Fim da coleta.")
                        break
                    print("Timeout no carregamento dos links. Tentando encontrar o botão Próximo...")
                
                novos_links_coletados = 0
                
                # Recarrega os elementos (boa prática)
                discussion_titles = driver.find_elements(By.CSS_SELECTOR, SELETOR_LINKS_TITULOS)
                
                for element in discussion_titles:
                    try:
                        link = element.get_attribute("href")
                        title = element.text.strip()
                        
                        result_data = {"Título": title, "Link": link, "Modelo Buscado": modelo_de_busca}
                        
                        # Simplesmente adiciona, confiando no filtro de modelos concluídos para a retomada
                        current_model_results.append(result_data)
                        novos_links_coletados += 1
                            
                    except Exception as e:
                        print(f"Erro ao extrair dados de um elemento: {e}")
                        continue
                
                print(f"Página processada. Novos links: {novos_links_coletados}. Total coletado para o modelo: {len(current_model_results)}")

                # Tenta encontrar o botão "Próximo" para a paginação
                try:
                    next_button = WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.CSS_SELECTOR, SELETOR_BOTAO_PROXIMA_PAGINA)))
                    
                    # Clica usando JS para maior confiabilidade no headless
                    driver.execute_script("arguments[0].click();", next_button)
                    print("Clicando no botão 'Próximo'...")
                    
                    sleep_time_page = random.uniform(0, 1)
                    time.sleep(sleep_time_page) 
                    print(f"Pausa de {sleep_time_page:.2f} segundos para nova página carregar.")

                except (TimeoutException, NoSuchElementException):
                    print(f"Botão 'Próximo' não encontrado ou desabilitado para '{modelo_de_busca}'. Fim da paginação.")
                    break # Sai do loop while True (fim da paginação)
            
            # --- PONTO CRUCIAL DE SALVAMENTO DE CHECKPOINT ---
            # 1. Salva os resultados do modelo ATUAL (incrementalmente)
            salvar_resultados_incrementais(caminho_saida, current_model_results, modelo_de_busca)

            # 2. Marca o modelo como concluído SOMENTE se o processamento terminou
            marcar_modelo_concluido(caminho_modelos_concluidos, modelo_de_busca)
            print(f"Modelo '{modelo_de_busca}' marcado como CONCLUÍDO. Progresso salvo.")


        except Exception as e:
            print(f"Ocorreu um erro durante a busca pelo modelo '{modelo_de_busca}': {e}")
            traceback.print_exc()
            continue # Pula para o próximo modelo

except KeyboardInterrupt:
    print("\n[INTERRUPÇÃO DETECTADA] Encerrando o processo de forma segura...")
except Exception as e:
    print(f"\n[ERRO FATAL] Ocorreu um erro inesperado: {e}")
    traceback.print_exc()

finally:
    # Garante que o driver seja fechado, mesmo em caso de erro ou interrupção
    driver.quit()
    print("Processo concluído/interrompido. Navegador fechado.")