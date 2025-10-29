import sys
import os
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
# from config import DIRETORIO_DADOS_WEBSCRAPPING,DIRETORIO_DADOS_EXTRACAO_QA


import undetected_chromedriver as uc
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup
import pandas as pd
from selenium.common.exceptions import TimeoutException, NoSuchElementException



import requests
from bs4 import BeautifulSoup

# from config import DIRETORIO_DADOS_WEBSCRAPPING,DIRETORIO_DADOS_EXTRACAO_QA

# caminho_saida = DIRETORIO_DADOS_WEBSCRAPPING / 'analise_beatiful_soup'

# url_ingles = "https://rog-forum.asus.com/t5/laptops/ct-p/NB_DT_Phones"
# url_ingles = "https://rog-forum.asus.com/t5/forums/searchpage/tab/message?advanced=false&allow_punctuation=false&filter=location&location=category:NB_DT_Phones&q=%22ROG%20Zephyrus%20G14%20GA401%22"
# url_ingles = "https://community.acer.com/pt"

url_ingles = "https://community.acer.com/pt"
nome_arquivo = "acer_community_page.html" # Nome do arquivo que será salvo

print(f"Fazendo requisição GET para: {url_ingles}")

# 1. Faz a requisição HTTP para BAIXAR o conteúdo.
try:
    response = requests.get(url_ingles, timeout=10)
    response.raise_for_status() # Verifica se a requisição foi bem-sucedida
    
    # O conteúdo HTML está em response.text
    html_content = response.text

    # --- NOVO PASSO: SALVAR O CONTEÚDO BAIXADO EM UM ARQUIVO ---
    try:
        with open(nome_arquivo, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"\nConteúdo HTML baixado e salvo com sucesso em: {os.path.abspath(nome_arquivo)}")
    except IOError as e:
        print(f"Erro ao salvar o arquivo: {e}")

    # 2. Continua com a análise (opcional, mas útil para verificar o conteúdo)
    soup = BeautifulSoup(html_content, 'html.parser')
    print("Conteúdo HTML analisado com BeautifulSoup.")

    # 3. Exemplo de análise
    # inputs_encontrados = soup.find_all('input') # Procurando por inputs reais
    # print(f"\nTotal de elementos <input> encontrados: {len(inputs_encontrados)}")
    
    # ... O restante da sua análise original (omitido para brevidade, mas pode ser mantido)

except requests.exceptions.RequestException as e:
    print(f"Erro ao fazer a requisição HTTP: {e}")