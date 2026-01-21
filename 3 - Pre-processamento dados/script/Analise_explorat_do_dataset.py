import sys
import json
import time
import datetime
import pandas as pd
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter # <--- NOVO: Import necessário para contagem
import praw

# --- 1. CONFIGURAÇÕES E CAMINHOS ---
caminho_script = Path(__file__).resolve().parent
caminho_raiz_projeto = caminho_script.parent.parent 
sys.path.append(str(caminho_raiz_projeto))

try:
    from config import DIRETORIO_DADOS_EXTRACAO_QA
except ImportError:
    print("Aviso: Módulos de configuração não encontrados. Usando caminhos locais.")
    DIRETORIO_CSV_DATASET_FINAL = caminho_script / 'dados_entrada'
    DIRETORIO_DADOS_EXTRACAO_QA = caminho_script / 'dados_saida'
    def ler_e_filtrar_modelos(caminho, marca, tipo): return []

CAMINHO_ENTRADA_JSON = DIRETORIO_DADOS_EXTRACAO_QA / 'reddit_dados_estruturados_modelo.json'

with open(CAMINHO_ENTRADA_JSON, 'r', encoding='utf-8') as f:
    dados = json.load(f)

# 'record_path' diz ao pandas para entrar na lista 'posts' e criar uma linha para cada post
df = pd.json_normalize(dados, record_path='posts')
print(df.to_string)

# Agora a coluna existe
soma_total = df['total_comentarios'].sum()

print(f"Colunas disponíveis: {df.columns.tolist()}")
print(f"Soma de todos os 'total_comentarios': {soma_total}")