#!/usr/bin/env python3
"""
test_rag_debug_v2.py
Diagnóstico separado: primeiro achar o modelo, depois ver a resposta sobre RAM.
"""

import asyncio
import json
import sys
import numpy as np
from pathlib import Path

from core.paths import VETORIZATION_DATA, VALIDACAO_SCRIPT, AVALIACAO_SCRIPT

for path in [VALIDACAO_SCRIPT, AVALIACAO_SCRIPT]:
    if str(path) not in sys.path:
        sys.path.append(str(path))


from RAG_BaseLineV2 import VanillaRAG
from RAG_Temporal_V9_3 import SpecialistTimeAwareRAG

BASE_PATH = VETORIZATION_DATA / 'base_vetorizada' / 'base_conhecimento_multilingueV9.json'
QUERY_COMPLETA = "What is the maximum RAM for Dell G15 5530?"
QUERY_MODELO = "Dell G15 5530"  # Apenas o modelo, sem atributos

async def debug_search(rag, query, ref_date=None):
    """Realiza a busca e retorna o resultado."""
    if ref_date:
        return await rag.search(query, ref_date=ref_date)
    return await rag.search(query)

def obter_documentos_modelo(metadata_list, termo_busca):
    """Retorna documentos cujo 'model' ou 'title' contenha o termo."""
    docs = []
    for doc in metadata_list:
        model = doc.get('metadata', {}).get('model', '')
        title = doc.get('metadata', {}).get('title', '')
        if termo_busca.lower() in model.lower() or termo_busca.lower() in title.lower():
            docs.append(doc)
    return docs

async def main():
    print("=" * 80)
    print("🔍 DIAGNÓSTICO - SEPARANDO MODELO E PERGUNTA")
    print("=" * 80)

    # Carregar metadados
    meta_path = BASE_PATH.with_suffix('.meta.json')
    with open(meta_path) as f:
        metadata = json.load(f)
    print(f"📚 Total de documentos na base: {len(metadata)}")

    # ========================================================================
    # ETAPA 1: VERIFICAR SE O MODELO EXISTE NA BASE
    # ========================================================================
    print("\n" + "=" * 50)
    print("📌 ETAPA 1: O modelo 'Dell G15 5530' existe na base?")
    print("=" * 50)

    docs_g15 = obter_documentos_modelo(metadata, "G15 5530")
    if docs_g15:
        print(f"✅ Encontrados {len(docs_g15)} documentos com 'G15 5530':")
        for d in docs_g15[:3]:
            model = d['metadata'].get('model', 'N/A')
            title = d['metadata'].get('title', 'N/A')
            date = d.get('date_iso', 'N/A')
            print(f"   - Model: {model}")
            print(f"     Title: {title}")
            print(f"     Date: {date}")
            # Mostra as primeiras 200 palavras do texto original
            texto = d.get('original_text', '')[:200].replace('\n', ' ')
            print(f"     Texto: {texto}...\n")
    else:
        print("❌ Nenhum documento com 'G15 5530' encontrado na base.")
        # Tenta buscar apenas "5530"
        docs_5530 = obter_documentos_modelo(metadata, "5530")
        if docs_5530:
            print(f"   🔍 Encontrados {len(docs_5530)} documentos com '5530':")
            for d in docs_5530[:3]:
                print(f"      - Model: {d['metadata'].get('model', 'N/A')}")
        else:
            print("   ❌ Nenhum documento com '5530' encontrado.")

    # ========================================================================
    # ETAPA 2: BUSCAR APENAS PELO MODELO (sem RAM)
    # ========================================================================
    print("\n" + "=" * 50)
    print("📌 ETAPA 2: Busca apenas pelo modelo (sem 'RAM')")
    print("=" * 50)

    # Carrega os RAGs
    vanilla = VanillaRAG(BASE_PATH, use_expansion=False)
    temporal = SpecialistTimeAwareRAG(BASE_PATH, variant_name="V9_HYBRID_MIXED_AUDITOR", use_expansion=True)

    print("\n🔎 VanillaRAG - Buscando por 'Dell G15 5530':")
    res_vanilla_modelo = await debug_search(vanilla, QUERY_MODELO)
    print(f"   Fontes recuperadas: {len(res_vanilla_modelo.get('sources', []))}")
    print("   Títulos:")
    for i, title in enumerate(res_vanilla_modelo.get('titles', [])[:10]):
        print(f"      {i+1}. {title}")

    # Verifica se algum título contém G15 5530
    found_in_vanilla = any("G15" in t and "5530" in t for t in res_vanilla_modelo.get('titles', []))
    print(f"   {'✅' if found_in_vanilla else '❌'} Documento com 'G15 5530' encontrado: {found_in_vanilla}")

    print("\n🔎 TemporalRAG - Buscando por 'Dell G15 5530' (ref_date=2024-06-01):")
    res_temporal_modelo = await debug_search(temporal, QUERY_MODELO, ref_date="2024-06-01")
    print(f"   Fontes recuperadas: {len(res_temporal_modelo.get('sources', []))}")
    print("   Títulos:")
    for i, title in enumerate(res_temporal_modelo.get('titles', [])[:10]):
        print(f"      {i+1}. {title}")

    found_in_temporal = any("G15" in t and "5530" in t for t in res_temporal_modelo.get('titles', []))
    print(f"   {'✅' if found_in_temporal else '❌'} Documento com 'G15 5530' encontrado: {found_in_temporal}")

    # ========================================================================
    # ETAPA 3: BUSCA COMPLETA (com RAM) - para comparar
    # ========================================================================
    print("\n" + "=" * 50)
    print("📌 ETAPA 3: Busca completa (com 'RAM')")
    print("=" * 50)

    print("\n🔎 VanillaRAG - Busca completa:")
    res_vanilla_completa = await debug_search(vanilla, QUERY_COMPLETA)
    print(f"   Fontes recuperadas: {len(res_vanilla_completa.get('sources', []))}")
    print("   Títulos:")
    for i, title in enumerate(res_vanilla_completa.get('titles', [])[:10]):
        print(f"      {i+1}. {title}")

    found_complete_vanilla = any("G15" in t and "5530" in t for t in res_vanilla_completa.get('titles', []))
    print(f"   {'✅' if found_complete_vanilla else '❌'} Documento com 'G15 5530' encontrado: {found_complete_vanilla}")

    print("\n🔎 TemporalRAG - Busca completa (ref_date=2024-06-01):")
    res_temporal_completa = await debug_search(temporal, QUERY_COMPLETA, ref_date="2024-06-01")
    print(f"   Fontes recuperadas: {len(res_temporal_completa.get('sources', []))}")
    print("   Títulos:")
    for i, title in enumerate(res_temporal_completa.get('titles', [])[:10]):
        print(f"      {i+1}. {title}")

    found_complete_temporal = any("G15" in t and "5530" in t for t in res_temporal_completa.get('titles', []))
    print(f"   {'✅' if found_complete_temporal else '❌'} Documento com 'G15 5530' encontrado: {found_complete_temporal}")

    # ========================================================================
    # ETAPA 4: Análise de similaridade (se o documento existe)
    # ========================================================================
    if docs_g15:
        print("\n" + "=" * 50)
        print("📌 ETAPA 4: Análise de similaridade do documento G15 5530")
        print("=" * 50)

        # Pega o primeiro documento G15 5530
        doc_g15 = docs_g15[0]
        # O embedding do documento está no .npy? Podemos carregar e comparar.
        npy_path = BASE_PATH.with_suffix('.npy')
        vectors = np.load(npy_path)
        # Precisamos do índice do documento no .npy. O .meta.json tem a ordem igual.
        # Encontra o índice
        idx = None
        for i, d in enumerate(metadata):
            if d['id'] == doc_g15['id']:
                idx = i
                break
        if idx is not None:
            doc_vector = vectors[idx]
            # Calcular embedding da query
            from RAG_BaseLineV2 import EmbeddingManager
            emb_manager = EmbeddingManager()
            query_vector = await emb_manager.compute_embedding(QUERY_COMPLETA)
            # Distância L2
            dist = np.linalg.norm(query_vector - doc_vector)
            print(f"   Distância L2 entre a query e o documento G15 5530: {dist:.4f}")
            # Distância para outros documentos (média)
            outras_distancias = []
            for i, vec in enumerate(vectors[:100]):
                if i == idx:
                    continue
                outras_distancias.append(np.linalg.norm(query_vector - vec))
            media_outras = np.mean(outras_distancias)
            print(f"   Média das distâncias para 100 documentos aleatórios: {media_outras:.4f}")
            print(f"   ✅ Distância do G15 é {'menor' if dist < media_outras else 'maior'} que a média.")
        else:
            print("   ⚠️ Não foi possível encontrar o índice do documento G15 5530 no .npy")

    print("\n" + "=" * 80)
    print("🔍 FIM DO DIAGNÓSTICO")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())