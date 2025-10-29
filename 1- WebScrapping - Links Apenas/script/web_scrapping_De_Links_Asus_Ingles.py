import sys
from pathlib import Path
import csv
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# --- Configuração de Caminhos e Módulos (Mantida) ---
# Obtém o caminho absoluto da pasta do script atual.
caminho_script = Path(__file__).resolve().parent

# Acessa a pasta raiz do projeto subindo dois níveis.
caminho_raiz_projeto = caminho_script.parent.parent

# Adiciona o caminho da raiz ao caminho de busca do Python.
sys.path.append(str(caminho_raiz_projeto))

# Agora a importação do módulo 'config' e 'modelo_de_busca' deve funcionar.
# Assumindo que essas importações são essenciais para o setup.

from config import DIRETORIO_DADOS_WEBSCRAPPING, DIRETORIO_CSV_DATASET_FINAL
from modelo_de_busca import ler_e_filtrar_modelos




caminho_saida = DIRETORIO_DADOS_WEBSCRAPPING / 'links_discussoes_Asus_Ingles.csv'
caminho_entrada = DIRETORIO_CSV_DATASET_FINAL / 'dataset_laptops.csv'
# Garante que os diretórios de saída existam
caminho_saida.parent.mkdir(parents=True, exist_ok=True)
caminho_entrada.parent.mkdir(parents=True, exist_ok=True)

# --- Configuração de Busca ---
MARCA_ALVO = 'ASUS'

# Lê e filtra os modelos do CSV
modelos_a_buscar = ler_e_filtrar_modelos(caminho_entrada, MARCA_ALVO)

if not modelos_a_buscar:
    print(f"Não foram encontrados modelos para a marca '{MARCA_ALVO}' no arquivo CSV ou houve um erro na leitura. Saindo.")
    # Se a lista estiver vazia, usa um modelo padrão para demonstração
    # if MARCA_ALVO == 'Asus':
    #      modelos_a_buscar = ['ROG Zephyrus G14 GA401']
    #      print("Usando modelo de fallback para demonstração: ['ROG Zephyrus G14 GA401']")
    # else:
    #     sys.exit()

# --- Configurações iniciais do Selenium (CORRIGIDAS) ---
chrome_options = Options()
# Adiciona os argumentos para execução em modo headless e otimizações
chrome_options.add_argument("--headless") # Modo Headless ativado
chrome_options.add_argument("--window-size=1920,1080")
chrome_options.add_argument("--blink-settings=imagesEnabled=false")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--no-sandbox") # Essencial para alguns ambientes headless

# Inicializa o driver corretamente com as opções headless
service = ChromeService(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=chrome_options)
driver = webdriver.Chrome()
wait = WebDriverWait(driver, 30)

site_url = "https://rog-forum.asus.com/t5/laptops/ct-p/NB_DT_Phones"

# --- Seletores do Fórum ASUS ROG ---
SELETOR_INPUT = 'input[placeholder="Search all content"]' # Campo de texto da busca
SELETOR_BUSCA = 'input[id="submitContext"]' # Botão de busca
SELETOR_COOKIE_ASUS = "div.btn-asus.btn-ok.btn-read-ck" # Botão de aceitar cookies
SELETOR_DROPDOWN_GRANULARIDADE = By.ID, 'searchGranularity' # Dropdown para selecionar "Posts"
SELETOR_OPCAO_POSTS = "#searchGranularity option:nth-child(2)" # A 2ª opção é tipicamente "Posts"
SELETOR_LINKS_DISCUSSAO = ".lia-message-view-message-search-item .MessageSubject h2 a.page-link" # NOVO: Seletor para os links individuais

all_discussion_links = []

# Função para salvar os links no CSV (refatorada para ser mais limpa)
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
    termo_de_busca = f'"{modelo_de_busca}"'
    
    print(f"\n{'='*70}")
    print(f"INICIANDO BUSCA {i+1}/{len(modelos_a_buscar)}: Modelo '{modelo_de_busca}'")
    print(f"{'='*70}")

    driver.get(site_url)
    
    try:
        # 1. Fecha o pop-up de cookies se ele existir
        print("Verificando e fechando o pop-up de cookies da ASUS...")
        try:
            cookie_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, SELETOR_COOKIE_ASUS)))
            cookie_button.click()
            print("Pop-up de cookies fechado.")
            time.sleep(1) 
        except (TimeoutException, NoSuchElementException):
            print("Pop-up de cookies não encontrado ou já fechado.")
            pass
        
        # 2. Insere o termo de busca no campo de texto
        print("Aguardando e inserindo termo de busca...")
        barra_de_busca = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, SELETOR_INPUT))) 
        barra_de_busca.clear()
        barra_de_busca.send_keys(termo_de_busca)
        
        # 3. Seleciona a opção "Posts" no dropdown de granularidade (se necessário)
        print("Selecionando a opção 'Posts'...")
        try:
            # Espera o dropdown estar presente
            wait.until(EC.presence_of_element_located(SELETOR_DROPDOWN_GRANULARIDADE))
            
            # Espera a opção "Posts" estar clicável e clica nela
            publicacoes_option = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, SELETOR_OPCAO_POSTS)))
            publicacoes_option.click()
            print("Opção 'Posts' selecionada.")
        except Exception as e:
            # Em alguns casos, o fórum pode fazer a busca automaticamente,
            # ou o elemento pode não estar disponível imediatamente.
            print(f"Aviso: Não foi possível selecionar 'Posts'. Tentando continuar. Erro: {e}")

        # 4. Clica no botão de busca
        print("Aguardando e clicando no botão de busca...")
        botao_de_busca = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, SELETOR_BUSCA)))
        botao_de_busca.click()
        
        print("Pesquisa realizada com sucesso! Aguardando resultados...")
        time.sleep(3) # Pausa extra para garantir que a página de resultados carregue.

        # --- INÍCIO DA EXTRAÇÃO DE LINKS ---
        print("\n--- INICIANDO COLETA DE LINKS ---")

        pagina_atual = 1
        while True:
            print(f"Coletando links da página {pagina_atual}...")
            
            # Tenta encontrar todos os links de discussão usando o seletor CORRIGIDO
            try:
                discussion_elements = wait.until(
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, SELETOR_LINKS_DISCUSSAO))
                )
            except TimeoutException:
                print("Nenhum resultado encontrado nesta página (Timeout).")
                break # Sai do loop se não encontrar resultados
            
            novos_links_coletados = 0
            for element in discussion_elements:
                link = element.get_attribute("href")
                # Usa .text para obter o título visível do link
                title = element.text.strip().replace('\n', ' ') 
                
                if link and title:
                    item_data = (title, link, modelo_de_busca)
                    # Garante que o link não seja duplicado na lista global
                    if item_data not in all_discussion_links:
                        all_discussion_links.append(item_data)
                        novos_links_coletados += 1
            
            print(f"Links coletados na Pág {pagina_atual}: {novos_links_coletados}. Total geral: {len(all_discussion_links)}")
            
            # Tenta salvar os links incrementalmente
            salvar_links_csv(caminho_saida, all_discussion_links)

            # Tenta encontrar o botão "Próximo" para a paginação
            try:
                # O seletor foi mantido pois parece correto para Lithium/Khoros
                next_button = WebDriverWait(driver, 2).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "li.pagination-next:not(.pagination-disabled) a"))
                )
                print("Clicando no botão 'Próximo'...")
                next_button.click()
                pagina_atual += 1
                time.sleep(3) # Pausa para a página carregar
            except (TimeoutException, NoSuchElementException):
                print("Botão 'Próximo' não encontrado ou desabilitado. Fim da paginação.")
                break # Sai do loop de paginação
            except Exception as e:
                print(f"Erro ao tentar avançar a página: {e}. Finalizando busca.")
                break


    except Exception as e:
        print(f"Ocorreu um erro no loop principal para o modelo '{modelo_de_busca}': {e}")
        import traceback
        traceback.print_exc()

# --- FINALIZAÇÃO ---
print("\nProcesso de web scraping concluído.")
print("Aguardando 5 segundos antes de fechar o driver.")
time.sleep(5)
driver.quit()
