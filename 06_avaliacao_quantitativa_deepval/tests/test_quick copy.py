# test_no_query_type.py
import asyncio
import sys
from pathlib import Path


from core.paths import VALIDACAO_SCRIPT, AVALIACAO_SCRIPT, VETORIZATION_DATA
import sys
sys.path.append(str(VALIDACAO_SCRIPT))
sys.path.append(str(AVALIACAO_SCRIPT))
from RAG_Temporal_V9 import SpecialistTimeAwareRAG


async def test():
    print("🚀 Testando V9 SEM query_type detection\n")
    
    rag = SpecialistTimeAwareRAG(
        VETORIZATION_DATA / 'base_conhecimento_multilingueV7.json',
        variant_name="V9_HYBRID_AUDITOR"
    )
    
    test_cases = [
        ("Does Lenovo Legion 5 15ACH6 have Thunderbolt 4?", "2025-06-01"),
        ("What is the maximum RAM for Acer AN515-56?", "2025-06-01"),
        ("Does the Nitro 5 have Thunderbolt 4?", "2025-06-01"),
        ("Why does my laptop thermal throttle?", "2025-06-01"),
    ]
    
    for query, ref_date in test_cases:
        print("\n" + "=" * 70)
        print(f"📝 Query: {query}")
        result = await rag.search(query, ref_date)
        print(f"\n📄 Resposta:")
        print(f"{result['answer'][:400]}")
        print(f"\n📋 Audit: {result.get('audit_trail', 'N/A')[:200]}")
        print("=" * 70)

if __name__ == "__main__":
    asyncio.run(test())