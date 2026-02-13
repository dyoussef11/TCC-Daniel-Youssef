import json
import sys
import time
from pathlib import Path
# from RAG_Final_Refinado import SpecialistTimeAwareRAG
from RAG_Final_Refinado_Ollama import SpecialistTimeAwareRAG

# --- BOOTSTRAP DE CAMINHO DO PROJETO ---
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.paths import (

VALIDACAO_DATA,
VALIDACAO_CONFIG,
VETORIZATION_DATA
)

CAMINHO_BASE =  VETORIZATION_DATA/ 'base_conhecimento_multilingue.json'
OUTPUT_COMPARISON = VALIDACAO_DATA / 'prompt_comparison_results.txt'

# Test Case: Using the MSI Stealth GS77 "Ember" incident or general thermal query
# TEST_QUERY = "What should I do if an ember lands on my GS77 screen?"
TEST_QUERY = "What is the maximum RAM and SSD upgrade for the Stealth GS77"
TEST_DATE = "2026-01-01"

def run_comparison():
    print(f"--- Starting Optimized Comparison ---")
    
    # MUDANÇA 1: Instanciar o RAG fora do loop (carrega pesos uma única vez)
    rag = SpecialistTimeAwareRAG(CAMINHO_BASE) 

    # Carregar as variantes do arquivo de configuração
    caminho_prompts = VALIDACAO_CONFIG / 'prompt_variants.json'
    with open(caminho_prompts, 'r', encoding='utf-8') as f:
        variants = json.load(f).keys()

    comparison_report = []

    for variant in variants:
        print(f"Testing Variant: {variant}...")
        try:
            # MUDANÇA 2: Usar o método set_variant em vez de criar novo objeto
            rag.set_variant(variant)
            
            start = time.time()
            response = rag.search(TEST_QUERY, TEST_DATE)
            duration = time.time() - start
            
            comparison_report.append({
                "variant": variant,
                "duration": round(duration, 2),
                "response": response
            })
        except Exception as e:
            print(f"❌ Error testing {variant}: {e}")

    # Save Comparison Report
    with open(OUTPUT_COMPARISON, 'w', encoding='utf-8') as f:
        f.write(f"PROMPT VARIANT COMPARISON REPORT\n")
        f.write(f"Query: {TEST_QUERY} | Date: {TEST_DATE}\n")
        f.write("="*60 + "\n\n")
        
        for item in comparison_report:
            f.write(f"VERSION: {item['variant']} ({item['duration']}s)\n")
            f.write(f"RESULT:\n{item['response']}\n")
            f.write("-" * 60 + "\n\n")

    print(f"\n✅ Comparison complete! View results in: {OUTPUT_COMPARISON.name}")

if __name__ == "__main__":
    run_comparison()