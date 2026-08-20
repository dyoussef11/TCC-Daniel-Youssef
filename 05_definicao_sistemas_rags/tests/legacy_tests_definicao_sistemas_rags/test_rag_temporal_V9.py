"""
exemplo_uso.py
Exemplo de uso do RAG Temporal refatorado.
"""

import asyncio
from pathlib import Path
from core.paths import VALIDACAO_SCRIPT, VETORIZATION_DATA
import sys
sys.path.append(str(VALIDACAO_SCRIPT))
from RAG_Temporal_V9_3 import SpecialistTimeAwareRAG
from core.paths import VETORIZATION_DATA

async def main():
    # Configuração
    json_path = Path(VETORIZATION_DATA / "base_conhecimento_multilingueV8.json")
    # json_path = Path(VETORIZATION_DATA / "base_conhecimento_multilingueV7.json")
    
    # Inicialização
    rag = SpecialistTimeAwareRAG(
        json_path=json_path,
        variant_name="V9_HYBRID_MIXED_AUDITOR",
        embedding_cache=None,  # Opcional: seu cache externo
        use_expansion=True
    )
    
    # Buscas de exemplo
    queries = [
        "Acer Nitro 5 AN515-56 specifications",
        "Gaming laptop with RTX 3060 performance",
        "Latest Dell XPS thermal issues"
    ]
    
    for query in queries:
        print(f"\n{'='*60}")
        print(f"Query: {query}")
        print('='*60)
        
        result = await rag.search(
            query=query,
            ref_date="2026-04-28"
        )
        
        # Resultados
        # print(f"\n📝 Resposta: {result['answer'][:200]}...")
        print(f"\n📝 Resposta: {result['answer']}...")
        print(f"\n📊 Diagnóstico:")
        for key, value in result['diagnostic'].items():
            print(f"   {key}: {value}")
        
        print(f"\n🔍 Fontes utilizadas: {len(result['sources'])}")
        print(f"📅 Melhor gap temporal: {result['diagnostic']['best_temporal_gap_years']} anos")
        print(f"🔄 Fallback usado: {result['diagnostic']['fallback_used']}")
        print(f"⚖️ Penalidade média: {result['diagnostic']['avg_penalty']}")

if __name__ == "__main__":
    asyncio.run(main())