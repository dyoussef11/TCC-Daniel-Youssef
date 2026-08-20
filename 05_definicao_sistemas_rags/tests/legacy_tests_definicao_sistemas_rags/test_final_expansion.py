# test_final_expansion.py - CORRIGIDO
import sys
from pathlib import Path

RAG_PATH = Path("C:/Users/Daniel Youssef/Documents/Backup/Notebook-Forum-Sentimento/05_definicao_sistemas_rags/script")
if str(RAG_PATH) not in sys.path:
    sys.path.insert(0, str(RAG_PATH))

from core.paths import VALIDACAO_CONFIG
from modules.query.query_expansion import QueryExpander


def test_expansion():
    print("=" * 80)
    print("🧪 TESTE FINAL DE EXPANSÃO")
    print("=" * 80)
    
    expander_v9 = QueryExpander(
        hierarchical_path=VALIDACAO_CONFIG / 'dictionary_synonyms_hierarchical_v4.json',
        flat_dict_path=VALIDACAO_CONFIG / 'dictionary_synonyms_flat_v9.json',
        max_terms=3,
        variant="temporal"
    )
    
    test_queries = [
        "Does Lenovo Legion 5 15ACH6 have Thunderbolt 4?",
        "What is the maximum RAM for Acer AN515-56?",
        "Does the Nitro 5 have Thunderbolt 4?",
        "How many M.2 SSD slots does the Acer Nitro 5 AN515-56 have?",
        "What processor does Dell G7 7588 have?",
        "Why does my laptop thermal throttle?",
    ]
    
    print("\n📊 RESULTADOS:\n")
    print("| Query | Tem SKU? | Expandiu? | Termos adicionados |")
    print("|-------|----------|-----------|-------------------|")
    
    for query in test_queries:
        original = query[:50] + "..." if len(query) > 50 else query
        has_sku = expander_v9.has_specific_sku(query)
        
        # Inicializa variáveis
        added_terms = "NENHUM"
        expandiu = "❌"
        result = query
        
        if has_sku:
            added_terms = "NENHUM (SKU detectado)"
            expandiu = "❌"
        else:
            result = expander_v9.expand_query(query)
            if result != query:
                added = result[len(query):].strip()
                added_terms = added[:40] + "..." if len(added) > 40 else added
                expandiu = "✅"
            else:
                added_terms = "NENHUM"
                expandiu = "❌"
        
        sku_status = "✅ SIM" if has_sku else "❌ NÃO"
        print(f"| {original} | {sku_status} | {expandiu} | {added_terms} |")


def test_expansion_detailed():
    """Versão detalhada para debug."""
    print("\n" + "=" * 80)
    print("🔍 TESTE DETALHADO DE EXPANSÃO")
    print("=" * 80)
    
    expander_v9 = QueryExpander(
        hierarchical_path=VALIDACAO_CONFIG / 'dictionary_synonyms_hierarchical_v4.json',
        flat_dict_path=VALIDACAO_CONFIG / 'dictionary_synonyms_flat_v9.json',
        max_terms=3,
        variant="temporal"
    )
    
    test_queries = [
        "Does Lenovo Legion 5 15ACH6 have Thunderbolt 4?",
        "What is the maximum RAM for Acer AN515-56?",
        "Does the Nitro 5 have Thunderbolt 4?",
        "How many M.2 SSD slots does the Acer Nitro 5 AN515-56 have?",
        "What processor does Dell G7 7588 have?",
        "Why does my laptop thermal throttle?",
    ]
    
    for query in test_queries:
        print(f"\n{'='*60}")
        print(f"📝 QUERY: {query}")
        print(f"{'-'*40}")
        
        has_sku, sku, brand = expander_v9.has_exact_sku(query)
        
        if has_sku:
            print(f"🔒 SKU detectado: {sku}")
            print(f"   → NÃO será expandida")
            result = query
        else:
            print(f"✅ Nenhum SKU detectado")
            result = expander_v9.expand_query(query)
            
            if result != query:
                added = result[len(query):].strip()
                print(f"   → EXPANDIDA: +{len(added.split())} termos")
                print(f"   → Termos adicionados: {added}")
            else:
                print(f"   → NÃO expandida (sem sinônimos)")
        
        print(f"{'='*60}")


if __name__ == "__main__":
    test_expansion()
    test_expansion_detailed()