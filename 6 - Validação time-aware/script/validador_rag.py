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
# from RAG_Final_Refinadocopy import SpecialistTimeAwareRAG 
# from RAG_Final_Refinadocopycopy import SpecialistTimeAwareRAG 
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
    # 30 Casos de Teste (6 por bloco) - Validação TCC UFSM
    casos = [
        # --- BLOCO 1: THERMAL EVOLUTION (G7 7588) ---
        # {"pergunta": "Does the Dell G7 7588 have overheating issues?", "data": "2018-07-15"},
        # {"pergunta": "Is thermal throttling a problem during gaming on G7?", "data": "2018-10-10"},
        # {"pergunta": "How does thermal paste replacement affect G7 temps?", "data": "2019-03-20"},
        # {"pergunta": "Is undervolting required to keep the G7 cool?", "data": "2019-08-05"},
        # {"pergunta": "Are the fans loud under heavy load on the G7 7588?", "data": "2020-04-12"},
        {"pergunta": "What is the long-term thermal durability of the G7?", "data": "2025-01-01"},

        # # --- BLOCO 2: BIOS AND PERFORMANCE ---
        {"pergunta": "Is the performance stable on the early BIOS versions?", "data": "2025-01-01"},
        {"pergunta": "Are there performance drops after BIOS 1.3.3 update?", "data": "2025-01-01"},
        {"pergunta": "Does BIOS 1.9.0 restrict undervolting on the G7?", "data": "2025-01-01"},
        {"pergunta": "What are the common BIOS problems for G7 7588?", "data": "2020-05-10"},
        {"pergunta": "Does the latest BIOS improve fan control behavior?", "data": "2025-01-01"},
        {"pergunta": "Is there a significant FPS drop after recent updates?", "data": "2025-01-01"},

        # # --- BLOCO 3: BATTERY AND POWER ---
        {"pergunta": "How long does the G7 7588 battery last on light use?", "data": "2018-07-25"},
        {"pergunta": "Is the power adapter overheating during heavy usage?", "data": "2025-01-01"},
        {"pergunta": "What is the battery wear level after 1 year of use?", "data": "2025-01-01"},
        {"pergunta": "Does the G7 battery life improve with Linux?", "data": "2025-01-01"},
        {"pergunta": "Are there reports of battery swelling for the G7?", "data": "2025-01-01"},
        {"pergunta": "Is it worth replacing the battery with a 3rd party one?", "data": "2025-01-01"},

        # # --- BLOCO 4: COMPONENTS AND UPGRADES ---
        # {"pergunta": "How does the GTX 1050 Ti perform in modern games?", "data": "2018-09-12"},
        # {"pergunta": "Does the G7 support NVMe Gen3 x4 speeds?", "data": "2025-01-01"},
        # {"pergunta": "What is the maximum RAM supported by G7 7588?", "data": "2019-04-18"},
        {"pergunta": "Can I upgrade the 60Hz screen to a 144Hz panel?", "data": "2025-01-01"},
        {"pergunta": "Is the Intel 9560 WiFi card stable on the Dell G7?", "data": "2020-01-15"},
        {"pergunta": "Does the G7 work well with Thunderbolt 3 eGPUs?", "data": "2025-01-01"},

        # # --- BLOCO 5: OTHER MODELS (VALIDATION) ---
        # {"pergunta": "Does the Dell G3 3579 have hinge durability issues?", "data": "2018-08-15"},
        {"pergunta": "Is the Dell G5 5587 cooling better than the G7?", "data": "2025-01-01"},
        # {"pergunta": "What are the common screen bleed issues on G-Series?", "data": "2019-05-05"},
        {"pergunta": "Is the new G5 5590 worth the upgrade from G7 7588?", "data": "2025-01-01"},
        # {"pergunta": "Does the Dell G3 have keyboard backlight issues?", "data": "2020-02-05"},
        {"pergunta": "What are the main complaints about the Dell G-Series?", "data": "2025-01-01"}
    ]
    
    executar_bateria_testes(rag, casos)