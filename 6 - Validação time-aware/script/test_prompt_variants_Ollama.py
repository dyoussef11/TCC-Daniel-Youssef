import asyncio
import json
import sys
import time
from pathlib import Path

# --- BOOTSTRAP DE CAMINHO DO PROJETO ---
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.paths import (

VALIDACAO_DATA,
VALIDACAO_CONFIG,
VETORIZATION_DATA

)

# Importamos a versão Ollama que é assíncrona
from RAG_Final_Refinado_Ollama import SpecialistTimeAwareRAG


CAMINHO_BASE = VETORIZATION_DATA / 'base_conhecimento_multilingue.json'
OUTPUT_COMPARISON = VALIDACAO_DATA / 'prompt_comparison_results.txt'

# Caso de Teste para o TCC
# TEST_QUERY = "What is the maximum RAM and SSD upgrade for the Stealth GS77"
TEST_QUERY = "Is the GS77 cooling better or worse than the Zephyrus M16?"
TEST_DATE = "2026-01-01"

async def run_comparison():
    print(f"--- Starting Optimized Comparison (Ollama Edition) ---")
    
    # Instancia o RAG (O carregamento do FAISS/Embedding é rápido e síncrono no __init__)
    try:
        rag = SpecialistTimeAwareRAG(CAMINHO_BASE) 
    except Exception as e:
        print(f"❌ Error initializing RAG: {e}")
        return

    # Carregar as variantes do arquivo de configuração
    caminho_prompts = VALIDACAO_CONFIG / 'prompt_variants.json'
    with open(caminho_prompts, 'r', encoding='utf-8') as f:
        variants_dict = json.load(f)
        variants = variants_dict.keys()

    comparison_report = []

    for variant in variants:
        print(f"Testing Variant: {variant}...")
        try:
            # Muda a persona (Configuração interna rápida)
            rag.set_variant(variant)
            
            start = time.time()
            # AGUARDA a resposta da IA (Ollama)
            response = await rag.search(TEST_QUERY, TEST_DATE)
            duration = time.time() - start
            
            comparison_report.append({
                "variant": variant,
                "duration": round(duration, 2),
                "response": response
            })
            print(f"    ✅ Completed in {duration:.2f}s")
            
        except Exception as e:
            print(f"    ❌ Error testing {variant}: {e}")

    # Salva o Relatório de Comparação Qualitativa
    print(f"\n💾 Writing results to {OUTPUT_COMPARISON.name}...")
    with open(OUTPUT_COMPARISON, 'w', encoding='utf-8') as f:
        f.write(f"PROMPT VARIANT COMPARISON REPORT\n")
        f.write(f"Query: {TEST_QUERY} | Date: {TEST_DATE}\n")
        f.write("="*60 + "\n\n")
        
        for item in comparison_report:
            f.write(f"VERSION: {item['variant']} ({item['duration']}s)\n")
            f.write(f"RESULT:\n{item['response']}\n")
            f.write("-" * 60 + "\n\n")

    print(f"✅ Process finished successfully!")

if __name__ == "__main__":
    # Inicia o loop assíncrono para permitir o uso de 'await'
    asyncio.run(run_comparison())