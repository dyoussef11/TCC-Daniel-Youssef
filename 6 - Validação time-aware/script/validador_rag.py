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


# Importe sua classe do script principal
from RAG_Final_Refinado import SpecialistTimeAwareRAG 

def executar_bateria_testes(rag_instance, casos_teste):
    print(f"Iniciando validação de {len(casos_teste)} casos...")
    resultados = []

    for i, caso in enumerate(casos_teste):
        print(f"[{i+1}/{len(casos_teste)}] Testando: {caso['pergunta']} | Data: {caso['data']}")
        
        inicio = time.time()
        resposta = rag_instance.search(caso['pergunta'], caso['data'])
        fim = time.time()
        
        tempo_processamento = fim - inicio
        
        resultados.append({
            "id": i + 1,
            "pergunta": caso['pergunta'],
            "data_simulada": caso['data'],
            "resposta_rag": resposta,
            "tempo_segundos": round(tempo_processamento, 2)
        })

    # Salva os resultados para análise no TCC
    with open(DIRETORIO_DADOS_VALID_SIST_TIMERAG / "resultados_validacao.json", "w", encoding="utf-8") as f:
        json.dump(resultados, f, indent=4, ensure_ascii=False)
    
    print("\n>>> Validação concluída. Resultados salvos em 'resultados_validacao.json'.")

if __name__ == "__main__":
    # Inicializa seu RAG (Certifique-se que o caminho da base está correto)
    rag = SpecialistTimeAwareRAG(CAMINHO_BASE)

    # Defina casos que cubram diferentes anos para provar a consciência temporal
    casos = [
        {"pergunta": "Does the Dell G7 7588 have overheating issues?", "data": "2018-07-15"},
        {"pergunta": "Does the Dell G7 7588 have overheating issues?", "data": "2019-12-01"},
        {"pergunta": "What are the common BIOS problems for G7 7588?", "data": "2020-05-10"},
        {"pergunta": "Is the battery life acceptable for G7 7588?", "data": "2018-09-20"}
    ]
    
    executar_bateria_testes(rag, casos)