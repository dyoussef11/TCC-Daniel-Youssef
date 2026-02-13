import json
import numpy as np
import faiss
import torch
import sys
import re
import asyncio
import time
from datetime import datetime
from pathlib import Path

# --- BOOTSTRAP DE CAMINHO DO PROJETO ---
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.paths import (

VETORIZATION_DATA,
VALIDACAO_DATA


)

CAMINHO_BASE = VETORIZATION_DATA / 'base_conhecimento_multilingue.json'
CAMINHO_SAIDA_RESULTADOS = VALIDACAO_DATA / "resultados_validacao.json"

# Importar a classe atualizada
# from RAG_Final_Refinado import SpecialistTimeAwareRAG 
from RAG_Final_Refinado_Ollama import SpecialistTimeAwareRAG 

async def executar_bateria_testes(rag_instance, casos_teste):
    """Executa os testes de forma assíncrona para suportar o Ollama."""
    print(f"🚀 Iniciando validação de {len(casos_teste)} casos com Ollama...")
    resultados = []

    for i, caso in enumerate(casos_teste):
        print(f"[{i+1}/{len(casos_teste)}] Query: {caso['pergunta']}")
        
        inicio = time.time()
        try:
            # CHAMADA ASSÍNCRONA AO NOVO RAG
            resposta = await rag_instance.search(caso['pergunta'], caso['data'])
            fim = time.time()
            
            tempo_proc = fim - inicio
            
            resultados.append({
                "id": i + 1,
                "pergunta": caso['pergunta'],
                "data_simulada": caso['data'],
                "resposta_rag": resposta,
                "tempo_segundos": round(tempo_proc, 2)
            })
            print(f"    ✅ Concluído em {tempo_proc:.2f}s")
            
        except Exception as e:
            print(f"    ❌ Erro no caso {i+1}: {e}")

    return resultados

async def main():
    # 1. Instanciar o RAG (O carregamento do FAISS ainda é síncrono no __init__)
    rag = SpecialistTimeAwareRAG(CAMINHO_BASE)

    # 2. Definir Casos de Teste (Seus blocos originais)
    casos_teste = [
        # --- BLOCO: MSI STEALTH GS77 ---
        {"pergunta": "What is the maximum RAM and SSD upgrade for the Stealth GS77?", "data": "2026-01-01"},
        {"pergunta": "What should I do if an ember lands on my GS77 screen?", "data": "2026-01-01"},
        {"pergunta": "Are there reports of MSI denying warranty for ethernet port water damage?", "data": "2026-01-01"},
        {"pergunta": "My GS77 is lagging in creative apps, is 64GB RAM the solution?", "data": "2026-01-01"},
        
        # --- BLOCO: DELL G7 7588 (HISTÓRICO) ---
        {"pergunta": "Common thermal issues with Dell G7 7588 i7-8750H?", "data": "2025-01-01"},
        {"pergunta": "Best BIOS version for undervolting the G7 7588?", "data": "2025-01-01"}
    ]

    # 3. Executar Processamento
    # DIRETORIO_DADOS_VALID_SIST_TIMERAG.mkdir(parents=True, exist_ok=True)
    
    resultados_finais = await executar_bateria_testes(rag, casos_teste)

    # 4. Salvar Resultados para o gerar_metricas.py
    with open(CAMINHO_SAIDA_RESULTADOS, "w", encoding="utf-8") as f:
        json.dump(resultados_finais, f, ensure_ascii=False, indent=4)
    
    print(f"\n✅ Validação finalizada. Resultados salvos em: {CAMINHO_SAIDA_RESULTADOS}")

if __name__ == "__main__":
    # Inicia o loop de eventos assíncrono
    asyncio.run(main())