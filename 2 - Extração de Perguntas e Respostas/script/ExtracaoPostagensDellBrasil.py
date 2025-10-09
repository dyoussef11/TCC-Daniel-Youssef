import sys
from pathlib import Path

# Obtém o caminho absoluto da pasta do script atual.
# Exemplo: 'C:\...\Buscar_Web\1- WebScrapping\script'
caminho_script = Path(__file__).resolve().parent

# Acessa a pasta raiz do projeto subindo dois níveis.
# Exemplo: 'C:\...\Buscar_Web'
caminho_raiz_projeto = caminho_script.parent.parent

# Adiciona o caminho da raiz ao caminho de busca do Python.
sys.path.append(str(caminho_raiz_projeto))

# Agora a importação do módulo 'config' deve funcionar.
from config import DIRETORIO_DADOS_LINKS

import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
import csv

def extrair_dados_postagens():
    # Configurar o driver
    
    
    
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--blink-settings=imagesEnabled=false")
    chrome_options.add_argument("--disable-gpu")
    driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=chrome_options)
    wait = WebDriverWait(driver, 15)
    # Lista para armazenar apenas os links das discussões
    links_discussoes = []
    try:
        with open('Separação_de_links/Comunidade_Dell/LinksFinaisComunidadeDell/links_ComunidadeDell_7588.csv', 'r', encoding='utf-8') as file:
            reader = csv.reader(file)
            next(reader)  # Pular cabeçalho
            for row in reader:
                if row:
                    links_discussoes.append(row[0])
        print(f"Total de links para processar: {len(links_discussoes)}")
    except FileNotFoundError:
        print("Arquivo CSV 'links_discussoes_dellBrasil.csv' não encontrado! Rode o primeiro script para gerar a lista de links.")
        return

    # Lista para armazenar os dados extraídos (título, link, conteúdo)
    dados_postagens = []

    try:
        for i, link in enumerate(links_discussoes, 1):
            print(f"\nProcessando link {i}/{len(links_discussoes)}: {link}")
            
            try:
                # Abrir a página da discussão
                driver.get(link)
                
                # Fechar pop-up de cookies se existir
                try:
                    cookie_button = wait.until(EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler")))
                    cookie_button.click()
                    time.sleep(1)
                except:
                    pass
                
                # Extrair título da postagem
                try:
                    # Seletor para o título dentro da página de discussão
                    titulo_element = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "h1.conversation-balloon__content__title")))
                    titulo = titulo_element.text.strip()
                except Exception as e:
                    titulo = "Título não encontrado"
                
                # Extrair corpo do texto da postagem original
                try:
                    # Seletor para o corpo do texto da postagem original
                    corpo_element = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.conversation-balloon__content__text")))
                    corpo_texto = corpo_element.text.strip()
                except Exception as e:
                    corpo_texto = "Corpo do texto não encontrado"
                
                # Armazenar dados
                dados_postagens.append({
                    'link': link,
                    'titulo': titulo,
                    'corpo_texto': corpo_texto
                })
                
                print(f"✓ Título: {titulo[:50]}...")
                print(f"✓ Texto extraído: {len(corpo_texto)} caracteres")
                
            except Exception as e:
                print(f"✗ Erro ao processar link {link}: {e}")
                dados_postagens.append({
                    'link': link,
                    'titulo': 'ERRO',
                    'corpo_texto': f'Erro na extração: {str(e)}'
                })
            
            # Pausa entre requisições
            time.sleep(1)
    
    finally:
        # Fechar o driver
        driver.quit()
    
    # Salvar os dados em um novo CSV
    try:
        with open('2 - Extração de Perguntas e Respostas/data/dados_postagens_dellBrasil.csv', 'w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow(['Link', 'Título', 'Corpo do Texto'])
            
            for dado in dados_postagens:
                writer.writerow([
                    dado['link'],
                    dado['titulo'],
                    dado['corpo_texto']
                ])
        
        print(f"\n✅ Dados salvos com sucesso! Total de postagens processadas: {len(dados_postagens)}")
        
    except Exception as e:
        print(f"Erro ao salvar CSV: {e}")

# Executar a função
if __name__ == "__main__":
    extrair_dados_postagens()