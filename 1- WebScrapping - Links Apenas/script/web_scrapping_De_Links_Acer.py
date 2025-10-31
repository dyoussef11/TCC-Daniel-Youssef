import sys
from pathlib import Path
import csv
import time
import random # NOVO: Importar random para atrasos humanos
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
# REMOVER: from webdriver_manager.chrome import ChromeDriverManager
# REMOVER: from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
import undetected_chromedriver as uc
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException
import traceback

# --- Configuração de Caminhos e Módulos (Mantida) ---
# Obtém o caminho absoluto da pasta do script atual.
caminho_script = Path(__file__).resolve().parent

# Acessa a pasta raiz do projeto subindo dois níveis.
caminho_raiz_projeto = caminho_script.parent.parent

# Adiciona o caminho da raiz ao caminho de busca do Python.
sys.path.append(str(caminho_raiz_projeto))

# Agora a importação do módulo 'config' e 'modelo_de_busca' deve funcionar.
from config import DIRETORIO_DADOS_WEBSCRAPPING, DIRETORIO_CSV_DATASET_FINAL
from modelo_de_busca import ler_e_filtrar_modelos

caminho_saida = DIRETORIO_DADOS_WEBSCRAPPING / 'links_discussoes_Acer.csv'
caminho_entrada = DIRETORIO_CSV_DATASET_FINAL / 'dataset_laptops_UNICOS.csv'
# Garante que os diretórios de saída existam
caminho_saida.parent.mkdir(parents=True, exist_ok=True)
caminho_entrada.parent.mkdir(parents=True, exist_ok=True)

# --- Configuração de Busca ---
MARCA_ALVO = 'ACER'
TIPO_NOTEBOOK = 'Gamer'
modelos_a_buscar = ler_e_filtrar_modelos(caminho_entrada, MARCA_ALVO, TIPO_NOTEBOOK)
print(f'{modelos_a_buscar}')

if not modelos_a_buscar:
    print(f"Não foram encontrados modelos para a marca '{MARCA_ALVO}' no arquivo CSV ou houve um erro na leitura. Saindo.")
    sys.exit() # Adicionado para sair do script

# --- NOVO: Função para Atraso Humano ---
def human_delay(min_sec=2, max_sec=4):
    """Pausa com um tempo aleatório para simular um comportamento humano."""
    sleep_time = random.uniform(min_sec, max_sec)
    time.sleep(sleep_time)

# --- Configurações iniciais do Selenium (Otimizado para UC) ---
chrome_options = Options()
# Mantido sem headless, pois aumenta a chance de sucesso contra CAPTCHA/deteção.
# Se precisar, descomente abaixo, mas pode reduzir a eficácia anti-bot:
# chrome_options.add_argument("--headless") 
chrome_options.add_argument("--window-size=1920,1080")
chrome_options.add_argument("--blink-settings=imagesEnabled=false")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-blink-features=AutomationControlled") 
# O UC faz o trabalho de User-Agent, mas uma explícita não custa:
# chrome_options.add_argument(f"user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")

# Inicializa o driver: o UC cuida da versão e do serviço, tornando o código mais limpo.
driver = uc.Chrome(version = 141, options=chrome_options) 
wait = WebDriverWait(driver, 30)

site_url = "https://community.acer.com/pt"

SELETOR_INPUT = 'input[aria-label="Pesquisar Texto"]'
SELETOR_BUSCA = 'button[class*="SearchBar-styles-left"]' 
SELETOR_COOKIE_ACER = 'button[id="onetrust-accept-btn-handler"]'
SELETOR_OPCAO_POLLS = '//span[text()="Enquetes"]' 
SELETOR_OPCAO_IDEAS = '//span[text()="ideias"]' 
SELETOR_FILTER = '//button[text()= "Filtrar"]' 
SELETOR_LINKS_DISCUSSAO = 'h3[href*="/discussion/"]'
SELETOR_PROXIMA_PAGINA = '//button[text()= "Próximo"]' 
SELETOR_DE_BUSCA_VAZIA = '//div[text()= "Nenhum resultado encontrado."]'

all_discussion_links = []

# Função para salvar os links no CSV (mantida)
def salvar_links_csv(caminho, links):
    """Salva a lista de links no arquivo CSV."""
    with open(caminho, 'w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow(['Título da Discussão', 'Link da Discussão', 'Modelo Buscado'])
        for title, url, modelo in links:
            writer.writerow([title, url, modelo])
    print(f"\nLinks salvos com sucesso em {caminho}. Total de links: {len(links)}")


# --- LOOP PRINCIPAL: Itera sobre cada modelo lido do CSV ---
for i, modelo_de_busca in enumerate(modelos_a_buscar):
    termo_de_busca = f'{modelo_de_busca}'
    
    print(f"\n{'='*70}")
    print(f"INICIANDO BUSCA (ACER BRASIL) {i+1}/{len(modelos_a_buscar)}: Modelo '{modelo_de_busca}'")
    print(f"{'='*70}")

    driver.get(site_url)
    human_delay(3, 5) # NOVO: Pausa maior e aleatória após navegação inicial
    
    try:
        # 1. Fecha o pop-up de cookies se ele existir
        print("Verificando e fechando o pop-up de cookies...")
        try:
            cookie_button = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, SELETOR_COOKIE_ACER)))
            human_delay(0.5, 1.5) # Pausa rápida antes do clique
            cookie_button.click()
            print("Pop-up de cookies fechado.")
            
        except (TimeoutException, NoSuchElementException):
            print("Pop-up de cookies não encontrado ou já fechado.")
            pass
        
        # 2. Insere o termo de busca no campo de texto
        print("Aguardando e inserindo termo de busca...")
        barra_de_busca = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, SELETOR_INPUT)))
        barra_de_busca.clear()
        barra_de_busca.send_keys(termo_de_busca)
        human_delay(1, 2) # Pausa antes do clique
        
        # 3. Clica no botão de busca
        print("Aguardando e clicando no botão de busca...")
        botao_de_busca = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, SELETOR_BUSCA)))
        botao_de_busca.click()
        
        print("Pesquisa realizada com sucesso! Aguardando resultados...")
        human_delay(4, 7) # NOVO: Pausa maior e mais variável para carregamento de resultados

        # *** INÍCIO DA CORREÇÃO DE BUSCA VAZIA ***    
        try:
            # Usa um WebDriverWait mais curto (ex: 8 segundos) para checar a mensagem de erro
            WebDriverWait(driver, 8).until(
                EC.presence_of_element_located((By.XPATH, SELETOR_DE_BUSCA_VAZIA))
            )
            # Se a execução chegar aqui, significa que o elemento de busca vazia FOI encontrado
            print("Resultado VAZIO encontrado. Pulando para o próximo modelo na lista.")
            continue # <--- AQUI ESTÁ A CORREÇÃO: Pula o restante do loop e vai para o próximo modelo
            
        except TimeoutException:
            # Se o elemento de busca vazia NÃO for encontrado após 8 segundos, 
            # é porque assumimos que há resultados.
            print("Resultados encontrados. Prosseguindo com a filtragem...")
            pass

        # 4. Clica no Chechbox de Polls USANDO JAVASCRIPT
        print("Aguardando e clicando no botão de Polls (via JS)...")
        try:
            elemento_polls = wait.until(EC.presence_of_element_located((By.XPATH, SELETOR_OPCAO_POLLS)))
            driver.execute_script("arguments[0].click();", elemento_polls)
            print("Checkbox 'Polls' clicado via JavaScript.")
            human_delay(1, 2) # Pausa para processamento do clique
        except Exception as e:
            print(f"Erro ao clicar em 'Polls' (JS): {e}")
            pass 

        # 5. Clica no Chechbox de Ideas USANDO JAVASCRIPT
        print("Aguardando e clicando no botão de IDEAS (via JS)...")
        try:
            elemento_ideas = wait.until(EC.presence_of_element_located((By.XPATH, SELETOR_OPCAO_IDEAS)))
            driver.execute_script("arguments[0].click();", elemento_ideas)
            print("Checkbox 'Ideas' clicado via JavaScript.")
            human_delay(1, 2) # Pausa para processamento do clique
        except Exception as e:
            print(f"Erro ao clicar em 'Ideas' (JS): {e}")
            pass

        # 6. Clica no botão de Filter
        print("Aguardando e clicando no botão de Filter...")
        try:
            botao_filter = wait.until(EC.element_to_be_clickable((By.XPATH, SELETOR_FILTER)))
            botao_filter.click()
            print("Botão 'Filter' clicado com sucesso!")
            human_delay(3, 5) # Pausa maior para carregamento após o filtro
        except ElementClickInterceptedException:
             # Se o Filter for interceptado, tente JS também
             driver.execute_script("arguments[0].click();", botao_filter)
             print("Botão 'Filter' clicado via JavaScript (após interceptação)!")
             human_delay(3, 5) # Pausa maior para carregamento após o filtro
        except Exception as e:
            print(f"Erro ao clicar no botão 'Filter': {e}")
            pass 

        # --- INÍCIO DA EXTRAÇÃO DE LINKS ---
        print("\n--- INICIANDO COLETA DE LINKS ---")

        pagina_atual = 1
        while True:
            print(f"Coletando links da página {pagina_atual}...")
            
            # Tenta encontrar todos os links <a>
            try:
                discussion_elements = wait.until(
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, SELETOR_LINKS_DISCUSSAO))
                )
            except TimeoutException:
                print("Nenhum resultado encontrado nesta página (Timeout).")
                break 
            
            novos_links_coletados = 0
            for element in discussion_elements:
                link = element.get_attribute("href")
                title = element.text.strip().replace('\n', ' ') 
                
                if "/discussion/" not in link:
                    continue
                
                if link and title:
                    item_data = (title, link, modelo_de_busca)
                    if item_data not in all_discussion_links:
                        all_discussion_links.append(item_data)
                        novos_links_coletados += 1
            
            print(f"Links coletados na Pág {pagina_atual}: {novos_links_coletados}. Total geral: {len(all_discussion_links)}")
            
            # Salva os links incrementalmente
            salvar_links_csv(caminho_saida, all_discussion_links)

            # Tenta encontrar o botão "Próximo" para a paginação
            try:
                next_button = WebDriverWait(driver, 2).until(
                    EC.element_to_be_clickable((By.XPATH, SELETOR_PROXIMA_PAGINA))
                )
                print("Clicando no botão 'Próximo'...")
                next_button.click()
                pagina_atual += 1
                human_delay(2, 3) # NOVO: Pausa humana entre as páginas
            except (TimeoutException, NoSuchElementException):
                print("Botão 'Próximo' não encontrado ou desabilitado. Fim da paginação.")
                break
            except Exception as e:
                print(f"Erro ao tentar avançar a página: {e}. Finalizando busca.")
                break


    except Exception as e:
        print(f"Ocorreu um erro no loop principal para o modelo '{modelo_de_busca}': {e}")
        traceback.print_exc()

# --- FINALIZAÇÃO ---
print("\nProcesso de web scraping concluído.")
print("Aguardando 5 segundos antes de fechar o driver.")
time.sleep(5)
driver.quit()