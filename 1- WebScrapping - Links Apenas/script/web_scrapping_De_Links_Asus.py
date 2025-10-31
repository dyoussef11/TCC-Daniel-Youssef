import sys
from pathlib import Path
import csv
import time
import random # Importar random para pausas anti-bloqueio
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
import traceback # Importar para melhor rastreamento de erro

# --- Configuração de Caminhos e Módulos (Mantida) ---
caminho_script = Path(__file__).resolve().parent
caminho_raiz_projeto = caminho_script.parent.parent
sys.path.append(str(caminho_raiz_projeto))

from config import DIRETORIO_DADOS_WEBSCRAPPING, DIRETORIO_CSV_DATASET_FINAL
from modelo_de_busca import ler_e_filtrar_modelos

# --- CONFIGURAÇÃO DE ARQUIVOS (AJUSTADOS PARA ZENTALK PT) ---
caminho_saida = DIRETORIO_DADOS_WEBSCRAPPING / 'links_discussoes_Asus_ZenTalk_PT.csv'
# NOVO: Caminho para o arquivo de rastreamento de progresso
caminho_modelos_concluidos = DIRETORIO_DADOS_WEBSCRAPPING / 'modelos_concluidos_Asus_ZenTalk_PT.txt'

caminho_entrada = DIRETORIO_CSV_DATASET_FINAL / 'dataset_laptops_UNICOS.csv'

# Garante que os diretórios de saída existam
caminho_saida.parent.mkdir(parents=True, exist_ok=True)
caminho_entrada.parent.mkdir(parents=True, exist_ok=True)

# --- Configuração de Busca ---
MARCA_ALVO = 'ASUS'
TIPO_NOTEBOOK = 'Gamer'

# --- FUNÇÕES DE CHECKPOINTING E PROGRESSO (MANTIDAS) ---

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
    
    # Converte a lista de tuplas (título, link, modelo) para uma lista de dicionários
    # para usar csv.DictWriter de forma mais segura
    dict_resultados = [
        {'Título da Discussão': r[0], 'Link da Discussão': r[1], 'Modelo Buscado': r[2]}
        for r in resultados
    ]
    
    if not dict_resultados:
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
                
            writer.writerows(dict_resultados)
            
        print(f"Resultados do modelo '{modelo_de_busca}' APENDADOS ao arquivo de saída.")
    except Exception as e:
        print(f"ERRO ao salvar resultados incrementais para o modelo '{modelo_de_busca}': {e}")


# 1. Carregar modelos já concluídos de execuções anteriores
modelos_concluidos = carregar_modelos_concluidos(caminho_modelos_concluidos)
print(f"Progresso carregado. {len(modelos_concluidos)} modelos ASUS já foram processados.")

# 2. Lê todos os modelos do CSV
modelos_a_buscar_bruto = ler_e_filtrar_modelos(caminho_entrada, MARCA_ALVO, TIPO_NOTEBOOK)

# 3. Filtra os modelos brutos para pular os concluídos
modelos_a_buscar = [
    modelo for modelo in modelos_a_buscar_bruto 
    if modelo not in modelos_concluidos
]

if not modelos_a_buscar and modelos_a_buscar_bruto:
    print("Todos os modelos ASUS no CSV já foram processados. Processo encerrado.")
    sys.exit()
elif not modelos_a_buscar:
    print(f"Não foram encontrados modelos para a marca '{MARCA_ALVO}' no arquivo CSV ou houve um erro na leitura. Saindo.")
    sys.exit()

print(f"Iniciando busca para {len(modelos_a_buscar)} de {len(modelos_a_buscar_bruto)} modelos totais.")

# --- Configurações iniciais do Selenium (Mantidas) ---
chrome_options = Options()
# chrome_options.add_argument("--headless")
chrome_options.add_argument("--window-size=1920,1080")
chrome_options.add_argument("--blink-settings=imagesEnabled=false")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--no-sandbox") 
chrome_options.add_argument(f"user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.75 Safari/537.36")


# Inicializa o driver (fora do try/except principal para ser acessível no finally)
service = ChromeService(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=chrome_options)
# Aumentei o timeout para 30s, o que é seguro para páginas que demoram
wait = WebDriverWait(driver, 30) 
print(f'{modelos_a_buscar_bruto}')
# ====================================================================
# URL AJUSTADA PARA ZENTALK PORTUGUÊS (CATEGORIA)
# ====================================================================
site_url = "https://zentalk.asus.com/t5/comunidade-em-portugu%C3%AAs/ct-p/pt"
# ====================================================================

# --- Seletores (Mantidos do ROG Forum) ---
SELETOR_COOKIE_ASUS = "div.btn-asus.btn-ok.btn-read-ck" # Botão de aceitar cookies

SELETOR_INPUT = 'input[aria-label="Pesquisar"]' # Campo de texto da busca

SELETOR_BUSCA = 'input[name="submitContext"]' # Botão de busca

SELETOR_LINKS_DISCUSSAO = 'a[class="page-link lia-link-navigation lia-custom-event"]' # Seletor para os links individuais

SELETOR_PAGINACAO_PROXIMO = 'a[aria-label="Próxima página"]' # Seletor do botão Próximo

# Esta lista precisa ser mantida globalmente ou carregada na inicialização
all_discussion_links = [] 

# --- LOOP PRINCIPAL ENVOLTO POR TRY/FINALLY ---
try:
    for i, modelo_de_busca in enumerate(modelos_a_buscar):
        # Reinicia a lista de resultados para o modelo atual
        current_model_results = []
        
        # Pausa Estratégica e Aleatória entre modelos
        if i > 0:
            sleep_time = random.uniform(1, 2) 
            print(f"Pausando por {sleep_time:.2f} segundos antes da busca do próximo modelo.")
            time.sleep(sleep_time)

        termo_de_busca = f'"{modelo_de_busca}"'
        
        print(f"\n{'='*70}")
        print(f"INICIANDO BUSCA (ASUS BRASIL) {i+1}/{len(modelos_a_buscar)}: Modelo '{modelo_de_busca}'")
        print(f"{'='*70}")

        driver.get(site_url) # Vai para a página da categoria ZenTalk
        
        try:
            # 1. Fecha o pop-up de cookies
            print("Verificando e fechando o pop-up de cookies da ASUS...")
            try:
                # O seletor SELETOR_COOKIE_ASUS precisa ser ajustado por você para o ZenTalk (Khoros/Lithium)
                # O seletor provável do ZenTalk é: ".popover-button.btn.btn-primary.btn-ok"
                cookie_button = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.CSS_SELECTOR, SELETOR_COOKIE_ASUS)))
                cookie_button.click()
                print("Pop-up de cookies fechado.")
                time.sleep(1) 
            except (TimeoutException, NoSuchElementException):
                print("Pop-up de cookies não encontrado ou já fechado.")
                pass
            
            # 2. Insere o termo de busca no campo de texto
            # O seletor SELETOR_INPUT precisa ser ajustado por você para o ZenTalk
            print("Aguardando e inserindo termo de busca...")
            barra_de_busca = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, SELETOR_INPUT))) 
            barra_de_busca.clear()
            barra_de_busca.send_keys(termo_de_busca)
            

            # 4. Clica no botão de busca
            # O seletor SELETOR_BUSCA precisa ser ajustado por você para o ZenTalk
            print("Aguardando e clicando no botão de busca...")
            botao_de_busca = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, SELETOR_BUSCA)))
            botao_de_busca.click()
            
            print("Pesquisa realizada com sucesso! Aguardando resultados...")
            time.sleep(random.uniform(2, 4)) 

            # --- INÍCIO DA EXTRAÇÃO DE LINKS ---
            print("\n--- INICIANDO COLETA DE LINKS ---")

            pagina_atual = 1
            while True:
                print(f"Coletando links da página {pagina_atual}...")
                
                # O seletor SELETOR_LINKS_DISCUSSAO precisa ser ajustado por você para o ZenTalk
                try:
                    discussion_elements = WebDriverWait(driver, 10).until(
                        EC.presence_of_all_elements_located((By.CSS_SELECTOR, SELETOR_LINKS_DISCUSSAO))
                    )
                except TimeoutException:
                    print("Nenhum resultado encontrado nesta página (Timeout). Fim da coleta.")
                    break 
                
                novos_links_coletados = 0
                
                for element in discussion_elements:
                    try:
                        link = element.get_attribute("href")
                        title = element.text.strip().replace('\n', ' ') 
                        
                        if link and title:
                            item_data = (title, link, modelo_de_busca)
                            current_model_results.append(item_data)
                            novos_links_coletados += 1
                    except Exception as e:
                        print(f"Erro ao extrair dados de um elemento: {e}")
                        continue
                
                print(f"Links coletados na Pág {pagina_atual}: {novos_links_coletados}. Total coletado para o modelo: {len(current_model_results)}")
                
                # Tenta encontrar o botão "Próximo" para a paginação
                # O seletor SELETOR_PAGINACAO_PROXIMO precisa ser ajustado por você para o ZenTalk
                try:
                    next_button = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, SELETOR_PAGINACAO_PROXIMO))
                    )
                    
                    driver.execute_script("arguments[0].click();", next_button)
                    print("Clicando no botão 'Próximo'...")
                    
                    pagina_atual += 1
                    time.sleep(random.uniform(3, 5)) 
                    
                except (TimeoutException, NoSuchElementException):
                    print("Botão 'Próximo' não encontrado ou desabilitado. Fim da paginação.")
                    break 
                except Exception as e:
                    print(f"Erro ao tentar avançar a página: {e}. Finalizando busca.")
                    break

            
            # --- PONTO CRUCIAL DE SALVAMENTO DE CHECKPOINT ---
            # 1. Salva os resultados do modelo ATUAL (incrementalmente)
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
    driver.quit()
    print("Processo concluído/interrompido. Navegador fechado.")