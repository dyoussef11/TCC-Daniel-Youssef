import json
import numpy as np
import faiss
import torch
import sys
import re
from datetime import datetime
from pathlib import Path
import time


# --- BOOTSTRAP DE CAMINHO DO PROJETO ---
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.paths import (

VETORIZATION_DATA,
VALIDACAO_DATA


)



CAMINHO_BASE = VETORIZATION_DATA / 'base_conhecimento_multilingue.json'


# Importe sua classe do script principal
from RAG_Final_Refinado import SpecialistTimeAwareRAG 

def executar_bateria_testes(rag_instance, casos_teste):
    print(f"Iniciando validação de {len(casos_teste)} casos...")
    resultados = []

    for i, caso in enumerate(casos_teste):
        print(f"[{i+1}/{len(casos_teste)}] Processando Query: {caso['pergunta']}")
        print(f"    📅 Data Simulada: {caso['data']}")
        
        inicio = time.time()
        resposta = rag_instance.search(caso['pergunta'], caso['data'])
        fim = time.time()
        
        # Exibe a resposta no console para acompanhamento em tempo real
        print(f"    🤖 Resposta IA:\n{resposta[:200]}...") 
        print(f"    ⏱️ Tempo: {round(fim - inicio, 2)}s\n")
        
        tempo_processamento = fim - inicio
        
        resultados.append({
            "id": i + 1,
            "pergunta": caso['pergunta'],
            "data_simulada": caso['data'],
            "resposta_rag": resposta,
            "tempo_segundos": round(tempo_processamento, 2)
        })

    # Salva os resultados para análise no TCC
    with open(VALIDACAO_DATA / "resultados_validacao.json", "w", encoding="utf-8") as f:
        json.dump(resultados, f, indent=4, ensure_ascii=False)
    
    print("\n>>> Validação concluída. Resultados salvos em 'resultados_validacao.json'.")

if __name__ == "__main__":
    # Inicializa seu RAG (Certifique-se que o caminho da base está correto)
    rag = SpecialistTimeAwareRAG(CAMINHO_BASE)

    # Defina casos que cubram diferentes anos para provar a consciência temporal
    # 30 Casos de Teste (6 por bloco) - Validação TCC UFSM
    casos = [
        # # --- BLOCO 1: THERMAL EVOLUTION (G7 7588) ---
        # # {"pergunta": "Does the Dell G7 7588 have overheating issues?", "data": "2018-07-15"},
        # # {"pergunta": "Is thermal throttling a problem during gaming on G7?", "data": "2018-10-10"},
        # # {"pergunta": "How does thermal paste replacement affect G7 temps?", "data": "2019-03-20"},
        # # {"pergunta": "Is undervolting required to keep the G7 cool?", "data": "2019-08-05"},
        # # {"pergunta": "Are the fans loud under heavy load on the G7 7588?", "data": "2020-04-12"},
        # {"pergunta": "What is the long-term thermal durability of the G7?", "data": "2025-01-01"},

        # # # --- BLOCO 2: BIOS AND PERFORMANCE ---
        # {"pergunta": "Is the performance stable on the early BIOS versions?", "data": "2025-01-01"},
        # {"pergunta": "Are there performance drops after BIOS 1.3.3 update?", "data": "2025-01-01"},
        # {"pergunta": "Does BIOS 1.9.0 restrict undervolting on the G7?", "data": "2025-01-01"},
        # {"pergunta": "What are the common BIOS problems for G7 7588?", "data": "2020-05-10"},
        # {"pergunta": "Does the latest BIOS improve fan control behavior?", "data": "2025-01-01"},
        # {"pergunta": "Is there a significant FPS drop after recent updates?", "data": "2025-01-01"},

        # # # --- BLOCO 3: BATTERY AND POWER ---
        # {"pergunta": "How long does the G7 7588 battery last on light use?", "data": "2018-07-25"},
        # {"pergunta": "Is the power adapter overheating during heavy usage?", "data": "2025-01-01"},
        # {"pergunta": "What is the battery wear level after 1 year of use?", "data": "2025-01-01"},
        # {"pergunta": "Does the G7 battery life improve with Linux?", "data": "2025-01-01"},
        # {"pergunta": "Are there reports of battery swelling for the G7?", "data": "2025-01-01"},
        # {"pergunta": "Is it worth replacing the battery with a 3rd party one?", "data": "2025-01-01"},

        # # # --- BLOCO 4: COMPONENTS AND UPGRADES ---
        # # {"pergunta": "How does the GTX 1050 Ti perform in modern games?", "data": "2018-09-12"},
        # # {"pergunta": "Does the G7 support NVMe Gen3 x4 speeds?", "data": "2025-01-01"},
        # # {"pergunta": "What is the maximum RAM supported by G7 7588?", "data": "2019-04-18"},
        # {"pergunta": "Can I upgrade the 60Hz screen to a 144Hz panel?", "data": "2025-01-01"},
        # {"pergunta": "Is the Intel 9560 WiFi card stable on the Dell G7?", "data": "2020-01-15"},
        # {"pergunta": "Does the G7 work well with Thunderbolt 3 eGPUs?", "data": "2025-01-01"},

        # # # --- BLOCO 5: OTHER MODELS (VALIDATION) ---
        # # {"pergunta": "Does the Dell G3 3579 have hinge durability issues?", "data": "2018-08-15"},
        # {"pergunta": "Is the Dell G5 5587 cooling better than the G7?", "data": "2025-01-01"},
        # # {"pergunta": "What are the common screen bleed issues on G-Series?", "data": "2019-05-05"},
        # {"pergunta": "Is the new G5 5590 worth the upgrade from G7 7588?", "data": "2025-01-01"},
        # # {"pergunta": "Does the Dell G3 have keyboard backlight issues?", "data": "2020-02-05"},
        # {"pergunta": "What are the main complaints about the Dell G-Series?", "data": "2025-01-01"}

        # # --- BLOCO 6: MSI STEALTH GS77 (VALIDATION) ---
        {"pergunta": "What should I do if an ember lands on my GS77 screen?", "data": "2026-01-01"},
        {"pergunta": "Are there reports of MSI denying warranty for ethernet port water damage?", "data": "2026-01-01"},
        {"pergunta": "Does the MSI Stealth GS77 have issues booting with the backplate on?", "data": "2026-01-01"},
        {"pergunta": "What is the maximum RAM and SSD upgrade for the Stealth GS77?", "data": "2026-01-01"},
        {"pergunta": "Is the GS77 cooling better or worse than the Zephyrus M16?", "data": "2026-01-01"},
        {"pergunta": "How to fix repeating keys on the MSI GS77 Stealth keyboard?", "data": "2026-01-01"}
    ]
    
    executar_bateria_testes(rag, casos)