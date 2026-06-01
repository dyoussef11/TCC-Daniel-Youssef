# test_rag_expansion.py
import asyncio
from pathlib import Path
from core.paths import VALIDACAO_SCRIPT, VETORIZATION_DATA
import sys
sys.path.append(str(VALIDACAO_SCRIPT))
from RAG_Temporal_V8_CPUMode_CacheReady import SpecialistTimeAwareRAG
from RAG_BaseLine import VanillaRAG

async def test():
    base_path = VETORIZATION_DATA / 'base_conhecimento_multilingueV7.json'
    
    # Temporal COM expansão (padrão)
    rag_temporal = SpecialistTimeAwareRAG(base_path, use_expansion=True)
    
    # Temporal SEM expansão (para comparar)
    rag_temporal_no_exp = SpecialistTimeAwareRAG(base_path, use_expansion=False)
    
    # Vanilla SEM expansão (baseline puro)
    rag_vanilla = VanillaRAG(base_path, use_expansion=False)
    
    # Vanilla COM expansão (para ver ganho só da expansão)
    rag_vanilla_exp = VanillaRAG(base_path, use_expansion=True)
    
    query = "HP Victus 15"
    
    print("=" * 60)
    print(f"Query: {query}")
    print("=" * 60)
    
    # Testa Temporal com expansão
    result = await rag_temporal.search(query)
    print(f"\n🔹 Temporal COM expansão:")
    print(f"   Query normalizada: {result['normalized_query']}")
    print(f"   Documentos: {result['diagnostic']['num_documents_retrieved']}")
    print(f"   Resposta: {result['answer'][:200]}...")
    
    # Testa Temporal sem expansão
    result_no_exp = await rag_temporal_no_exp.search(query)
    print(f"\n🔹 Temporal SEM expansão:")
    print(f"   Documentos: {result_no_exp['diagnostic']['num_documents_retrieved']}")
    
    # Testa Vanilla com expansão
    result_vanilla_exp = await rag_vanilla_exp.search(query)
    print(f"\n🔹 Vanilla COM expansão:")
    print(f"   Documentos: {result_vanilla_exp['diagnostic']['num_documents_retrieved']}")
    
    # Testa Vanilla sem expansão
    result_vanilla = await rag_vanilla.search(query)
    print(f"\n🔹 Vanilla SEM expansão:")
    print(f"   Documentos: {result_vanilla['diagnostic']['num_documents_retrieved']}")

if __name__ == "__main__":
    asyncio.run(test())