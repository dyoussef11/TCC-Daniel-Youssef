# test_v9_expansion.py
import sys
from pathlib import Path
from core.paths import VALIDACAO_SCRIPT, VETORIZATION_DATA
import sys
sys.path.append(str(VALIDACAO_SCRIPT))
from RAG_Temporal_V9_3 import SpecialistTimeAwareRAG


async def test():
    print("🚀 Testando V9 com expansão correta\n")
    
    rag = SpecialistTimeAwareRAG(
        VETORIZATION_DATA / 'base_conhecimento_multilingueV8.json',
        # VETORIZATION_DATA / 'base_conhecimento_multilingueV7.json',
        variant_name="V9_HYBRID_MIXED_AUDITOR",
        use_expansion=True  # Liga a expansão
    )
    
    queries = [
        "Does Lenovo Legion 5 15ACH6 have Thunderbolt 4?",
        "Does the Nitro 5 have Thunderbolt 4?",
    ]
    
    for query in queries:
        print("\n" + "=" * 60)
        print(f"Q: {query}")
        result = await rag.search(query, "2025-06-01")
        print(f"Query expandida: {result.get('normalized_query', query)}")
        print(f"Resposta: {result['answer']}...")

if __name__ == "__main__":
    import asyncio
    asyncio.run(test())