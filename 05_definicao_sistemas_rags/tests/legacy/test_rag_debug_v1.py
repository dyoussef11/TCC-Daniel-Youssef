#!/usr/bin/env python3
"""
test_rag_debug.py
Versão de diagnóstico para investigar por que o Dell G15 5530 não está sendo recuperado.
"""

import asyncio
import sys
from pathlib import Path

from core.paths import VETORIZATION_DATA
from RAG_BaseLineV2 import VanillaRAG
from RAG_Temporal_V9_3 import SpecialistTimeAwareRAG

BASE_PATH = VETORIZATION_DATA / 'base_conhecimento_multilingueV9.json'
QUERY = "What is the maximum RAM for Dell G15 5530?"

async def debug_search(rag, query, ref_date=None):
    """Realiza a busca e retorna os resultados com metadados."""
    if ref_date:
        result = await rag.search(query, ref_date=ref_date)
    else:
        result = await rag.search(query)
    # Extrai os documentos recuperados com seus metadados
    docs = []
    # No VanillaRAG, os documentos estão em result['sources'] ou result['titles']
    # Mas queremos os metadados completos. Vamos acessar a lista de resultados brutos.
    # Como cada RAG tem estrutura diferente, faremos uma abordagem genérica.
    if hasattr(rag, 'base_dados'):
        # Para VanillaRAG, usamos scored_results (não exposto, mas podemos acessar via atributos internos)
        # Vamos fazer uma busca manual para ter controle.
        # Como o método search não retorna os índices, faremos uma segunda consulta usando o índice diretamente.
        # Melhor: usar o método search e depois acessar os metadados a partir dos títulos.
        pass
    return result

async def main():
    print("=" * 80)
    print("🔍 DIAGNÓSTICO DE RECUPERAÇÃO - Dell G15 5530")
    print("=" * 80)

    # 1. Carregar os RAGs
    print("\n📥 Carregando VanillaRAG...")
    vanilla = VanillaRAG(BASE_PATH, use_expansion=False)
    print("📥 Carregando TemporalRAG...")
    temporal = SpecialistTimeAwareRAG(BASE_PATH, variant_name="V9_HYBRID_MIXED_AUDITOR", use_expansion=False)

    # 2. Busca no VanillaRAG
    print("\n🔎 BUSCA NO VANILLARAG:")
    result_vanilla = await vanilla.search(QUERY)
    print(f"   Resposta (primeiros 200 chars): {result_vanilla['answer'][:200]}...")
    print(f"   Número de fontes: {len(result_vanilla.get('sources', []))}")
    print("\n   📋 Títulos das fontes recuperadas:")
    for i, title in enumerate(result_vanilla.get('titles', [])):
        print(f"      {i+1}. {title}")

    # Verifica se algum título contém "G15" e "5530"
    found = False
    for title in result_vanilla.get('titles', []):
        if "G15" in title and "5530" in title:
            found = True
            print(f"      ✅ ENCONTRADO: {title}")
            break
    if not found:
        print("      ⚠️ Nenhum título com 'G15' e '5530' encontrado.")

    # 3. Busca no TemporalRAG (com data)
    print("\n🔎 BUSCA NO TEMPORALRAG (ref_date=2024-06-01):")
    result_temporal = await temporal.search(QUERY, ref_date="2024-06-01")
    print(f"   Resposta (primeiros 200 chars): {result_temporal['answer'][:200]}...")
    print(f"   Número de fontes: {len(result_temporal.get('sources', []))}")
    print("\n   📋 Títulos das fontes recuperadas:")
    for i, title in enumerate(result_temporal.get('titles', [])):
        print(f"      {i+1}. {title}")

    found = False
    for title in result_temporal.get('titles', []):
        if "G15" in title and "5530" in title:
            found = True
            print(f"      ✅ ENCONTRADO: {title}")
            break
    if not found:
        print("      ⚠️ Nenhum título com 'G15' e '5530' encontrado.")

    # 4. Busca alternativa: apenas "G15 5530" sem "Dell"
    print("\n🔎 BUSCA ALTERNATIVA: 'G15 5530 RAM' (sem 'Dell')")
    alt_query = "G15 5530 RAM"
    result_alt = await vanilla.search(alt_query)
    print(f"   Resposta (primeiros 200 chars): {result_alt['answer'][:200]}...")
    print("\n   📋 Títulos das fontes recuperadas:")
    for i, title in enumerate(result_alt.get('titles', [])):
        print(f"      {i+1}. {title}")
        if "G15" in title and "5530" in title:
            print(f"      ✅ ENCONTRADO! {title}")

    # 5. Verificar se existem documentos com modelo "Dell G15 5530" na base
    print("\n🔎 VERIFICANDO SE O DOCUMENTO EXISTE NA BASE:")
    # Acessa os metadados diretamente
    meta_path = BASE_PATH.with_suffix('.meta.json')
    import json
    with open(meta_path) as f:
        metadata = json.load(f)
    docs_g15 = []
    for doc in metadata:
        model = doc.get('metadata', {}).get('model', '')
        if 'G15' in model and '5530' in model:
            docs_g15.append(doc)
    if docs_g15:
        print(f"   ✅ Encontrados {len(docs_g15)} documentos com modelo contendo 'G15' e '5530':")
        for d in docs_g15[:3]:
            print(f"      - Model: {d['metadata'].get('model')}")
            print(f"        Title: {d['metadata'].get('title')}")
            print(f"        Date: {d.get('date_iso')}")
    else:
        print("   ❌ Nenhum documento com 'G15' e '5530' encontrado nos metadados.")
        # Tenta buscar apenas por "G15"
        docs_g15_any = [d for d in metadata if 'G15' in d.get('metadata', {}).get('model', '')]
        print(f"   🔍 Documentos com 'G15' no modelo: {len(docs_g15_any)}")
        for d in docs_g15_any[:3]:
            print(f"      - Model: {d['metadata'].get('model')}")

    # 6. Teste com um modelo que sabemos que existe (ex: Acer Nitro 5)
    print("\n🔎 TESTE DE CONTROLE: 'Acer Nitro 5 AN515-58'")
    control_query = "What is the maximum RAM for Acer Nitro 5 AN515-58?"
    result_control = await vanilla.search(control_query)
    print(f"   Resposta (primeiros 200 chars): {result_control['answer'][:200]}...")
    print("\n   📋 Títulos das fontes recuperadas:")
    for i, title in enumerate(result_control.get('titles', [])):
        print(f"      {i+1}. {title}")

    print("\n" + "=" * 80)
    print("🔍 FIM DO DIAGNÓSTICO")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())