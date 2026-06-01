# test_quick.py
import asyncio

from core.paths import VETORIZATION_DATA
from core.paths import VALIDACAO_SCRIPT, AVALIACAO_SCRIPT
import sys
sys.path.append(str(VALIDACAO_SCRIPT))
sys.path.append(str(AVALIACAO_SCRIPT))
from RAG_Temporal_V9 import SpecialistTimeAwareRAG

async def test():
    rag = SpecialistTimeAwareRAG(
        # VETORIZATION_DATA / 'base_conhecimento_multilingueV7.json',
        VETORIZATION_DATA / 'base_conhecimento_multilingueV8.json',
        # variant_name="V9_HYBRID_AUDITOR"
        variant_name="V9_HYBRID_MIXED_AUDITOR"
    )
    
    # Teste específico
    query = "Does Lenovo Legion 5 15ACH6 have Thunderbolt 4?"
    result = await rag.search(query, "2025-06-01")
    
    print(f"\nQuery: {query}")
    print(f"Answer: {result['answer']}")
    print(f"Audit: {result.get('audit_trail', 'N/A')}")

asyncio.run(test())