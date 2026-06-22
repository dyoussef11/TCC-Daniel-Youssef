#!/usr/bin/env python3
"""
test_debug_model_fields.py
Diagnóstico: verifica como os campos 'model' e 'summary' influenciam a recuperação.
O título é ignorado, pois muitas vezes não contém o modelo.
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
MODELO_BUSCA = "Asus Proart P16"  # termo a procurar (exemplo)

def carregar_metadados():
    meta_path = BASE_PATH.with_suffix('.meta.json')
    with open(meta_path) as f:
        return json.load(f)

def buscar_por_campo(metadata, termo, campo):
    """Retorna documentos onde o campo contém o termo (case-insensitive)."""
    resultados = []
    for doc in metadata:
        valor = doc.get('metadata', {}).get(campo, '')
        if termo.lower() in valor.lower():
            resultados.append(doc)
    return resultados

async def main():
    print("=" * 80)
    print(f"🔍 DIAGNÓSTICO - CAMPO 'model' vs 'summary' para '{MODELO_BUSCA}'")
    print("=" * 80)

    # Carrega metadados
    metadata = carregar_metadados()
    print(f"📚 Total de documentos: {len(metadata)}")

    # 1. Contagem por campo (ignorando title)
    docs_model = buscar_por_campo(metadata, MODELO_BUSCA, 'model')
    docs_summary = buscar_por_campo(metadata, MODELO_BUSCA, 'summary')

    print(f"\n📊 Documentos contendo '{MODELO_BUSCA}':")
    print(f"   - Campo 'model': {len(docs_model)}")
    print(f"   - Campo 'summary': {len(docs_summary)}")

    # 2. Exibe os 3 primeiros de cada campo (com title apenas para referência, mas sem contar)
    print("\n📝 Exemplos (primeiros 3):")
    
    print("\n--- Campo 'model' ---")
    for d in docs_model[:3]:
        print(f"  Model: {d['metadata'].get('model', 'N/A')}")
        print(f"  Summary: {d['metadata'].get('summary', 'N/A')[:150]}...")
        print(f"  (Title: {d['metadata'].get('title', 'N/A')})")
        print()

    print("\n--- Campo 'summary' ---")
    for d in docs_summary[:3]:
        print(f"  Model: {d['metadata'].get('model', 'N/A')}")
        print(f"  Summary: {d['metadata'].get('summary', 'N/A')[:150]}...")
        print(f"  (Title: {d['metadata'].get('title', 'N/A')})")
        print()

    # 3. Verifica quantos documentos têm o modelo no campo 'model' (confiável)
    print(f"\n✅ Documentos com modelo EXATO no campo 'model': {len(docs_model)}")

    # 4. Teste de busca real
    print("\n" + "=" * 80)
    print("🔎 TESTE DE BUSCA REAL (VanillaRAG e TemporalRAG)")
    print("=" * 80)

    vanilla = VanillaRAG(BASE_PATH, use_expansion=False)
    temporal = SpecialistTimeAwareRAG(BASE_PATH, variant_name="V9_HYBRID_MIXED_AUDITOR", use_expansion=False)

    consultas = [
        MODELO_BUSCA,   # "Asus Proart P16"
        f"{MODELO_BUSCA} memory",
        f"{MODELO_BUSCA} RAM",
        "Proart P16 H7606WP",
    ]

    for consulta in consultas:
        print(f"\n🔹 Consulta: '{consulta}'")

        # Vanilla
        res_v = await vanilla.search(consulta)
        titles_v = res_v.get('titles', [])
        print(f"   VanillaRAG: {len(titles_v)} documentos recuperados")
        print("   Títulos (primeiros 5):")
        for i, t in enumerate(titles_v[:5]):
            print(f"      {i+1}. {t}")
        # Verifica se algum título contém o modelo (apenas como referência)
        found_v = any(MODELO_BUSCA.lower() in t.lower() for t in titles_v)
        print(f"   {'✅' if found_v else '❌'} Documento com '{MODELO_BUSCA}' no título: {found_v}")
        # Verifica se algum documento recuperado tem o modelo no campo 'model'
        # (não temos acesso direto, mas podemos inferir pelos títulos que podem conter o modelo)
        # Vamos tentar ver se algum título contém "Proart P16" (sem a marca completa)
        found_in_model = any("Proart P16" in t for t in titles_v)
        print(f"   {'✅' if found_in_model else '❌'} Documento com 'Proart P16' no título: {found_in_model}")

        # Temporal
        res_t = await temporal.search(consulta, ref_date="2024-06-01")
        titles_t = res_t.get('titles', [])
        print(f"   TemporalRAG: {len(titles_t)} documentos recuperados")
        print("   Títulos (primeiros 5):")
        for i, t in enumerate(titles_t[:5]):
            print(f"      {i+1}. {t}")
        found_t = any(MODELO_BUSCA.lower() in t.lower() for t in titles_t)
        print(f"   {'✅' if found_t else '❌'} Documento com '{MODELO_BUSCA}' no título: {found_t}")
        found_in_model_t = any("Proart P16" in t for t in titles_t)
        print(f"   {'✅' if found_in_model_t else '❌'} Documento com 'Proart P16' no título: {found_in_model_t}")

    print("\n" + "=" * 80)
    print("🔍 FIM DO DIAGNÓSTICO")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())