#!/usr/bin/env python3
"""
test_debug_fields_only.py
Diagnóstico focado em 'model' e 'summary' (ignora 'title').
Verifica se o RAG recupera documentos onde o termo está nesses campos.
"""

import asyncio
import json
from pathlib import Path
import sys

from core.paths import VETORIZATION_DATA, VALIDACAO_SCRIPT, AVALIACAO_SCRIPT

for path in [VALIDACAO_SCRIPT, AVALIACAO_SCRIPT]:
    if str(path) not in sys.path:
        sys.path.append(str(path))
        
from RAG_BaseLineV2 import VanillaRAG
from RAG_Temporal_V9_3 import SpecialistTimeAwareRAG

BASE_PATH = VETORIZATION_DATA / 'base_conhecimento_multilingueV9.json'

def carregar_metadados():
    meta_path = BASE_PATH.with_suffix('.meta.json')
    with open(meta_path) as f:
        return json.load(f)

def termo_em_campo(termo, valor):
    """Verifica se termo está contido no valor (case-insensitive)."""
    return termo.lower() in valor.lower() if valor else False

def contar_em_resultados(resultados, termo, campos=['model', 'summary']):
    """Conta quantos documentos têm o termo em cada campo."""
    contagem = {campo: 0 for campo in campos}
    total = len(resultados)
    for doc in resultados:
        metadata = doc.get('metadata', {})
        for campo in campos:
            valor = metadata.get(campo, '')
            if termo_em_campo(termo, valor):
                contagem[campo] += 1
    return contagem, total

async def main():
    print("=" * 80)
    print("🔍 DIAGNÓSTICO - FOCADO EM 'model' E 'summary' (ignorando 'title')")
    print("=" * 80)

    metadata = carregar_metadados()
    print(f"📚 Total de documentos: {len(metadata)}")

    # Termos a buscar
    termos = [
        "Asus Proart P16 ram",
        "Proart P16",
        "Proart P16 H7606WP",
    ]

    # Carrega RAGs
    print("\n📥 Carregando RAGs...")
    vanilla = VanillaRAG(BASE_PATH, use_expansion=False)
    temporal = SpecialistTimeAwareRAG(BASE_PATH, variant_name="V9_HYBRID_MIXED_AUDITOR", use_expansion=False)

    for termo in termos:
        print("\n" + "=" * 60)
        print(f"🔎 TERMO: '{termo}'")
        print("=" * 60)

        # VanillaRAG
        res_v = await vanilla.search(termo)
        print("\n   VanillaRAG:")
        titulos_v = res_v.get('titles', [])
        print(f"   Documentos recuperados: {len(titulos_v)}")
        # Para cada título, encontrar o documento correspondente nos metadados
        docs_encontrados_v = []
        for titulo in titulos_v:
            # Busca o primeiro documento com esse título (pode haver duplicatas, mas é uma aproximação)
            encontrado = None
            for d in metadata:
                if d.get('metadata', {}).get('title', '') == titulo:
                    encontrado = d
                    break
            if encontrado:
                docs_encontrados_v.append(encontrado)
        # Agora contar nos campos model e summary
        contagem_v, total_v = contar_em_resultados(docs_encontrados_v, termo, ['model', 'summary'])
        print(f"   Documentos com termo em 'model': {contagem_v['model']}/{total_v}")
        print(f"   Documentos com termo em 'summary': {contagem_v['summary']}/{total_v}")
        print("   Títulos (primeiros 5):")
        for i, t in enumerate(titulos_v[:5]):
            print(f"      {i+1}. {t}")

        # TemporalRAG
        res_t = await temporal.search(termo, ref_date="2024-06-01")
        titulos_t = res_t.get('titles', [])
        print(f"\n   TemporalRAG:")
        print(f"   Documentos recuperados: {len(titulos_t)}")
        docs_encontrados_t = []
        for titulo in titulos_t:
            encontrado = None
            for d in metadata:
                if d.get('metadata', {}).get('title', '') == titulo:
                    encontrado = d
                    break
            if encontrado:
                docs_encontrados_t.append(encontrado)
        contagem_t, total_t = contar_em_resultados(docs_encontrados_t, termo, ['model', 'summary'])
        print(f"   Documentos com termo em 'model': {contagem_t['model']}/{total_t}")
        print(f"   Documentos com termo em 'summary': {contagem_t['summary']}/{total_t}")
        print("   Títulos (primeiros 5):")
        for i, t in enumerate(titulos_t[:5]):
            print(f"      {i+1}. {t}")

    print("\n" + "=" * 80)
    print("🔍 FIM DO DIAGNÓSTICO")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())