import sys
from pathlib import Path
import csv
import time
import random 
import pandas as pd # Adicionar import pandas para uso fora do notebook
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options

# --- CONFIGURAÇÃO INICIAL (LÓGICA FORNECIDA) ---

# Obtém o caminho absoluto da pasta do script atual.
caminho_script = Path(__file__).resolve().parent
caminho_raiz_projeto = caminho_script.parent.parent
sys.path.append(str(caminho_raiz_projeto))

# --- DEPENDÊNCIAS DO PROJETO (Assumindo que estão na raiz) ---
try:
    from config import DIRETORIO_DADOS_WEBSCRAPPING, DIRETORIO_CSV_DATASET_FINAL
    # IMPORT SIMULADO DA FUNÇÃO DE LEITURA
    # NOTA: Assumindo que 'modelo_de_busca.py' existe e tem 'ler_e_filtrar_modelos'
    from modelo_de_busca import ler_e_filtrar_modelos 
except ImportError as e:
    print(f"Erro de importação. Verifique se 'config.py' e 'modelo_de_busca.py' estão na raiz: {e}")
    sys.exit()

# --- VARIÁVEIS DE PATHS E FILTROS ---
caminho_saida = DIRETORIO_DADOS_WEBSCRAPPING / 'links_discussoes_ClubeHardware.csv'
caminho_entrada = DIRETORIO_CSV_DATASET_FINAL / 'dataset_laptops_UNICOS.csv'


SITE_URL = "https://forum.adrenaline.com.br/search/?type=post"

MARCA_ALVO = None
TIPO_NOTEBOOK = 'Gamer'

# --- FUNÇÃO DE SALVAMENTO REUSÁVEL ---

def salvar_dados_csv(data_list, output_path):
    """Salva a lista de dicionários no caminho especificado."""
    if not data_list:
        print("Aviso: Lista de links vazia. Nada para salvar.")
        return
        
    try:
        # Garante que o diretório de saída existe
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Usa DICTWRITER para salvar os dados
        with open(output_path, "w", newline="", encoding="utf-8") as file:
            fieldnames = ['Título', 'Link da Discussão', 'Modelo Buscado']
            writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(data_list)
        
        print(f"\n[SALVAMENTO AUTOMÁTICO] Dados salvos com sucesso em '{output_path}'. Total de links: {len(data_list)}")
        return True
        
    except Exception as e:
        print(f"\n[ERRO FATAL DE SALVAMENTO] Ocorreu um erro ao salvar o arquivo CSV: {e}")
        return False

# --- PREPARAÇÃO ---

# Lê e filtra os modelos do CSV
# NOTA: Esta função precisa estar implementada em 'modelo_de_busca.py'
modelos_a_buscar = ler_e_filtrar_modelos(caminho_entrada, MARCA_ALVO, TIPO_NOTEBOOK)

if not modelos_a_buscar:
    print(f"Não foram encontrados modelos para a marca '{MARCA_ALVO}' no arquivo CSV ou houve um erro na leitura. Saindo.")
    sys.exit()

# Variável de acumulação de links
todos_os_links_Adrenaline = [] 

# Variável de controle de cookies
cookie_popup_fechado = False

# --- DECLARAÇÕES DE HTML (Mantidas) ---
SELETOR_BOTAO_COOKIES = "a.js-noticeDismiss" 
SELETOR_ICONE_BUSCA = "a.p-navgroup-link--search" 
SELETOR_CAMPO_BUSCA = "keywords" 
 
SELETOR_RESULTADOS_LISTA_AUSENTE = '//div[text()="Nenhum resultado encontrado."]' 
SELETOR_RESULTADOS_LISTA_PRESENTE = 'li[class="block-row block-row--separated js-inlineModContainer"]'
SELETOR_RESULTADO_LINK_TITULO = "h3.contentRow-title a" 
SELETOR_BOTAO_PROXIMA_PAGINA = "a.pageNav-jump.pageNav-jump--next"
SELETOR_CAMPO_FILTRO_FORUM_TOPICO  = "c[nodes][]"
ID_FORUM_NOTEBOOKS_TOPICO = "175" 

# --- Configurações iniciais do Selenium (Mantidas) ---
chrome_options = Options()
chrome_options.add_argument("--headless") 
chrome_options.add_argument("--window-size=1920,1080")
chrome_options.add_argument("--blink-settings=imagesEnabled=false")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument(f"user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.75 Safari/537.36")


driver = None # Inicializa driver fora do bloco try


# --- INÍCIO DO PROCESSO PRINCIPAL COM TRATAMENTO DE INTERRUPÇÃO ---

try:
    # Inicializa o driver dentro do bloco try
    driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=chrome_options)
    wait = WebDriverWait(driver, 15)
    
    # --- LOOP PRINCIPAL: Itera sobre cada modelo lido do CSV ---
    for i, modelo_de_busca in enumerate(modelos_a_buscar):
        termo_de_busca = f'"{modelo_de_busca}"'
        
        # [PAUSA ESTRATÉGICA E ALEATÓRIA]
        if i > 0:
            sleep_time = random.uniform(0, 1) 
            # [ADICIONADO] Salvamento parcial após um número de modelos
            if i % 10 == 0: # Salva a cada 10 modelos
                print(f"\n--- PAUSA E SALVAMENTO PARCIAL (Modelo {i}/{len(modelos_a_buscar)}) ---")
                salvar_dados_csv(todos_os_links_Adrenaline, caminho_saida)
                print(f"Pausando por {sleep_time:.2f} segundos antes da busca do próximo modelo.")
            else:
                 time.sleep(sleep_time)

        print(f"\n{'='*70}")
        print(f"INICIANDO BUSCA (ADRENALNE) {i+1}/{len(modelos_a_buscar)}: Modelo '{modelo_de_busca}'")
        print(f"{'='*70}")
        
        # --- Passo 1: Configurar Filtros e Realizar a busca (Lógica Mantida) ---
        try:
            print("Acessando a página de busca do fórum...")
            driver.get(SITE_URL) 

            # Lida com o pop-up de cookies uma única vez (Mantido)
            if not cookie_popup_fechado:
                try:
                    cookie_button = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.CSS_SELECTOR, SELETOR_BOTAO_COOKIES)))
                    if cookie_button:
                        driver.execute_script("arguments[0].click();", cookie_button)
                        cookie_popup_fechado = True
                except:
                    pass 

            # 1. SELEÇÃO DO FÓRUM "NOTEBOOKS" (FILTRO) (Mantido)
            select_element = wait.until(
                EC.presence_of_element_located((By.NAME, SELETOR_CAMPO_FILTRO_FORUM_TOPICO ))
            )
            forum_select = Select(select_element)
            forum_select.select_by_value(ID_FORUM_NOTEBOOKS_TOPICO)
            
            # 2. INSERÇÃO DO TERMO DE BUSCA (Mantido)
            search_icon = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, SELETOR_ICONE_BUSCA)))
            search_icon.click()

            search_input = wait.until(EC.visibility_of_element_located((By.NAME, SELETOR_CAMPO_BUSCA)))
            search_input.clear()
            search_input.send_keys(termo_de_busca)
            search_input.send_keys(Keys.ENTER)
            
            print("Pesquisa iniciada com sucesso! Aguardando a página de resultados...")

        except Exception as e:
            print(f"Erro na fase de busca inicial para '{modelo_de_busca}': {e}. Pulando para o próximo modelo.")
            continue 

        # --- Passo 2: Coletar links de todas as páginas de resultados (Lógica Mantida) ---
        pagina_atual = 1
        while True:
            # Lógica de extração de links (Mantida)
            try:
                 WebDriverWait(driver, 7).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, SELETOR_RESULTADOS_LISTA_PRESENTE)))
            except TimeoutException:
                 try:
                     WebDriverWait(driver, 3).until(
                         EC.presence_of_element_located((By.XPATH, SELETOR_RESULTADOS_LISTA_AUSENTE)) 
                     )
                     print(f"Zero resultados encontrados para o modelo '{modelo_de_busca}'. Pulando para o próximo modelo.")
                     break
                 except TimeoutException:
                     print(f"Erro inesperado ou timeout grave no carregamento da página de resultados para o modelo '{modelo_de_busca}'.")
                     break

            resultados = driver.find_elements(By.CSS_SELECTOR, SELETOR_RESULTADOS_LISTA_PRESENTE)
            if not resultados:
                break

            novos_links_coletados = 0
            
            for resultado in resultados:
                try:
                    titulo_elemento = resultado.find_element(By.CSS_SELECTOR, SELETOR_RESULTADO_LINK_TITULO)
                    link = titulo_elemento.get_attribute("href")
                    
                    if not any(item['Link'] == link for item in todos_os_links_Adrenaline):
                        todos_os_links_Adrenaline.append({
                            "Título": titulo_elemento.text.strip(), 
                            "Link": link, 
                            "Modelo Buscado": modelo_de_busca
                        })
                        novos_links_coletados += 1
                except NoSuchElementException:
                    continue 
                except Exception as e:
                    print(f"Erro ao extrair link em resultado individual: {e}")
                    continue
            
            print(f"Página {pagina_atual} processada. Novos links: {novos_links_coletados}. Total acumulado: {len(todos_os_links_Adrenaline)}")
            pagina_atual += 1

            # Lógica de paginação (Mantida)
            try:
                proxima_pagina_link = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, SELETOR_BOTAO_PROXIMA_PAGINA))
                )
                driver.execute_script("arguments[0].click();", proxima_pagina_link)
                time.sleep(random.uniform(1, 2)) 
            except (TimeoutException, NoSuchElementException):
                print("Não há mais páginas. Fim da coleta para o modelo atual.")
                break 
            except Exception as e:
                print(f"Coleta de links finalizada ou ocorreu um erro inesperado na paginação: {e}")
                break

    # --- FIM DO LOOP PRINCIPAL ---

except KeyboardInterrupt:
    # --- Passo 3A: Salvamento em caso de INTERRUPÇÃO MANUAL (Ctrl+C) ---
    print("\n\n[INTERRUPÇÃO DETECTADA] Salvando dados acumulados antes de finalizar...")
    salvar_dados_csv(todos_os_links_Adrenaline, caminho_saida)
    
except Exception as e:
    # --- Passo 3B: Salvamento em caso de ERRO INESPERADO (Timeout, WebDriver, etc.) ---
    print(f"\n\n[ERRO CRÍTICO NO PROCESSO] Salvando dados acumulados. Erro: {e}")
    salvar_dados_csv(todos_os_links_Adrenaline, caminho_saida)

finally:
    # --- Passo 3C: Salvamento Final (Se o script rodar até o fim) ---
    if driver and not todos_os_links_Adrenaline: # Se o loop principal foi completado sem interrupção e sem erros.
        print("\n[PROCESSO FINALIZADO COM SUCESSO] Salvando dados finais...")
        salvar_dados_csv(todos_os_links_Adrenaline, caminho_saida)

    # --- Passo 4: Encerrar o navegador ---
    if driver:
        driver.quit()
        print("Processo concluído. Navegador fechado.")
    else:
        print("Processo concluído sem inicializar o navegador.")