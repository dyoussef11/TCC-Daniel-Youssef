import json
import pandas as pd
import json
import numpy as np
import faiss
import torch
import sys
import re
from datetime import datetime
from pathlib import Path
import time



# --- CONFIGURAÇÃO ---
caminho_script = Path(__file__).resolve().parent
caminho_raiz_projeto = caminho_script.parent.parent 
sys.path.append(str(caminho_raiz_projeto))
try:
    from config import DIRETORIO_DADOS_SIST_TIMERAG,DIRETORIO_DADOS_VALID_SIST_TIMERAG
except ImportError:
    DIRETORIO_DADOS_SIST_TIMERAG = caminho_script / 'dados_saida'

CAMINHO_BASE = DIRETORIO_DADOS_SIST_TIMERAG / 'base_conhecimento_multilingue.json'



def analisar_resultados(arquivo_json):
    with open(arquivo_json, "r", encoding="utf-8") as f:
        dados = json.load(f)
    
    df = pd.DataFrame(dados)
    
    print("--- RELATÓRIO DE DESEMPENHO (ETAPA 3) ---")
    print(f"Total de Testes: {len(df)}")
    print(f"Tempo Médio de Resposta: {df['tempo_segundos'].mean():.2f} segundos")
    print(f"Tempo Máximo: {df['tempo_segundos'].max():.2f}s")
    print(f"Tempo Mínimo: {df['tempo_segundos'].min():.2f}s")
    
    # Exporta para CSV para facilitar a criação de tabelas no seu TCC (LaTeX/Word)
    df.to_csv(DIRETORIO_DADOS_VALID_SIST_TIMERAG / "metricas_tcc.csv", index=False)
    print("\nDados exportados para 'metricas_tcc.csv'.")

if __name__ == "__main__":
    analisar_resultados(DIRETORIO_DADOS_VALID_SIST_TIMERAG / "resultados_validacao.json")