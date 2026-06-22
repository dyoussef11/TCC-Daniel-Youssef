#!/usr/bin/env python3
"""
test_temporal_debug.py
Diagnóstico detalhado do TemporalRAG:
- Exibe documentos recuperados com seus gaps e penalidades
- Mostra se o fallback foi ativado
- Compara com a busca do VanillaRAG
- Verifica a ordenação final
"""

import asyncio
import json
import sys
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

from core.paths import VETORIZATION_DATA, VALIDACAO_SCRIPT, AVALIACAO_SCRIPT

for path in [VALIDACAO_SCRIPT, AVALIACAO_SCRIPT]:
    if str(path) not in sys.path:
        sys.path.append(str(path))

from RAG_BaseLineV2 import VanillaRAG
from RAG_Temporal_V9_3 import SpecialistTimeAwareRAG, TemporalScorer

BASE_PATH = VETORIZATION_DATA / 'base_conhecimento_multilingueV9.json'
QUERY = "What is the maximum RAM for Dell G15 5530?"
REF_DATE = "2026-06-01"

async def main():
    print("=" * 80)
    print("🔍 DIAGNÓSTICO DO TEMPORALRAG - PENALIDADE E FALLBACK")
    print("=" * 80)

    # Carrega VanillaRAG para comparação
    print("\n📥 Carregando VanillaRAG...")
    vanilla = VanillaRAG(BASE_PATH, use_expansion=False)

    print("\n📥 Carregando TemporalRAG...")
    temporal = SpecialistTimeAwareRAG(BASE_PATH, variant_name="V9_HYBRID_MIXED_AUDITOR", use_expansion=True)

    # ========================================================================
    # 1. BUSCA NO VANILLARAG (referência)
    # ========================================================================
    print("\n" + "=" * 50)
    print("📌 1. BUSCA NO VANILLARAG (k=50, sem filtro)")
    print("=" * 50)

    res_vanilla = await vanilla.search(QUERY)
    print(f"   Total de documentos retornados: {len(res_vanilla.get('sources', []))}")
    print("   Primeiros 10 títulos:")
    for i, title in enumerate(res_vanilla.get('titles', [])[:10]):
        print(f"      {i+1}. {title}")

    # Verifica se o G15 5530 está entre eles
    found_vanilla = any("G15" in t and "5530" in t for t in res_vanilla.get('titles', []))
    print(f"   {'✅' if found_vanilla else '❌'} Documento com 'G15 5530' encontrado: {found_vanilla}")

    # ========================================================================
    # 2. BUSCA NO TEMPORALRAG - ACESSANDO OS RESULTADOS BRUTOS
    # ========================================================================
    print("\n" + "=" * 50)
    print("📌 2. BUSCA NO TEMPORALRAG (com penalidade temporal)")
    print("=" * 50)

    # Precisamos acessar o método search e capturar os resultados internos.
    # O método search atual retorna apenas a resposta final, não os resultados brutos.
    # Vamos modificar temporariamente o código do TemporalRAG para expor os resultados.
    # Como isso não é possível, faremos uma abordagem alternativa: chamar o search_pipeline diretamente.
    # Mas o search_pipeline é privado. Vamos criar uma versão de teste que imprime os dados.

    # A abordagem mais simples: criar uma subclasse ou modificar o método search para retornar mais info.
    # Como não queremos modificar o arquivo original, faremos um teste que chama o método search e
    # depois acessa os atributos internos (com reflexão) para extrair os dados.

    # Infelizmente, o método search não expõe scored_results. Vamos modificar o script para
    # criar uma versão local do TemporalRAG que imprime os detalhes.

    # Para este diagnóstico, faremos uma cópia local do método search com prints.

    # ========================================================================
    # 3. EXECUÇÃO DIRETA DO PIPELINE (usando o objeto temporal)
    # ========================================================================

    # Vamos usar o temporal.search e depois inspecionar os atributos internos
    # Mas o search não armazena os resultados. Precisamos de uma solução melhor.

    # Para o diagnóstico, vamos reimplementar temporariamente a lógica de search
    # em um script separado, copiando as partes relevantes.

    # Por simplicidade, faremos uma chamada ao temporal e depois
    # simularemos a busca usando o mesmo índice para obter os resultados brutos.

    # Vamos acessar o índice FAISS e o data_loader do temporal.
    index = temporal.faiss_manager.index
    data_loader = temporal.data_loader

    # Gerar embedding da query
    from RAG_BaseLineV2 import EmbeddingManager
    emb_mgr = EmbeddingManager()
    query_vec = await emb_mgr.compute_embedding(QUERY)

    # Busca no índice
    search_results = index.search(query_vec.reshape(1, -1), k=50)
    distances, indices = search_results

    # Aplicar penalidade temporal (usando o scorer do temporal)
    scorer = temporal.temporal_scorer
    ref_dt = datetime.strptime(REF_DATE, "%Y-%m-%d")

    scored = []
    for idx, dist in zip(indices[0], distances[0]):
        if idx == -1:
            continue
        doc = data_loader.documents[idx]
        metadata = doc.get('metadata', {})
        # Usa a mesma lógica do temporal para pegar a data
        if metadata.get('priorizacao_recentes', False):
            doc_date = metadata.get('data_processamento', doc.get('date_iso', '2024-01-01'))
        else:
            doc_date = metadata.get('data_post_original', doc.get('date_iso', '2024-01-01'))
        temporal_gap = scorer.calculate_temporal_gap(doc_date, ref_dt)
        recency_multiplier = 1.0  # simplificado
        final_score, penalty, status = scorer.score_document(dist, temporal_gap, recency_multiplier)
        scored.append({
            'idx': idx,
            'title': metadata.get('title', 'Unknown'),
            'model': metadata.get('model', 'Unknown'),
            'distance': dist,
            'temporal_gap': temporal_gap,
            'penalty': penalty,
            'final_score': final_score,
            'status': status,
            'date': doc_date,
            'text': doc.get('original_text', '')[:100]
        })

    # Ordenar por final_score
    scored.sort(key=lambda x: x['final_score'])

    print(f"   Total de documentos com penalidade aplicada: {len(scored)}")
    print(f"   Primeiros 10 após ordenação (final_score):")
    for i, item in enumerate(scored[:10]):
        print(f"      {i+1}. {item['title'][:60]}...")
        print(f"          gap={item['temporal_gap']:.2f}, penalty={item['penalty']:.4f}, final_score={item['final_score']:.4f}")

    # Verifica se o G15 5530 está entre os scored
    found_g15 = any("G15" in item['title'] and "5530" in item['title'] for item in scored)
    if found_g15:
        # Encontra a posição
        for i, item in enumerate(scored):
            if "G15" in item['title'] and "5530" in item['title']:
                print(f"   ✅ Documento G15 5530 encontrado na posição {i+1} (após penalidade)")
                print(f"      gap={item['temporal_gap']:.2f}, penalty={item['penalty']:.4f}, final_score={item['final_score']:.4f}")
                break
    else:
        print("   ❌ Documento G15 5530 NÃO encontrado entre os documentos com penalidade.")
        # Verifica se ele estava na lista original (antes da penalidade)
        # Busca no search_results original (sem penalidade)
        for idx, dist in zip(indices[0], distances[0]):
            if idx == -1:
                continue
            doc = data_loader.documents[idx]
            title = doc.get('metadata', {}).get('title', '')
            if "G15" in title and "5530" in title:
                print(f"   ⚠️ O documento G15 5530 estava na busca original (posição {list(indices[0]).index(idx)+1}), mas foi penalizado e saiu do top10.")
                print(f"      distance={dist:.4f}")
                # Verifica se ele foi removido pelo fallback ou penalidade
                break

    # ========================================================================
    # 4. VERIFICAÇÃO DO FALLBACK
    # ========================================================================
    print("\n" + "=" * 50)
    print("📌 3. VERIFICAÇÃO DO FALLBACK")
    print("=" * 50)

    # O fallback é ativado se best_doc_age > 2.0 e recent_docs_count < 2
    # Vamos ver qual é o melhor gap entre os 10 primeiros
    if scored:
        best_gap = scored[0]['temporal_gap']
        recent_docs = sum(1 for item in scored[:10] if item['temporal_gap'] < 0.5)
        print(f"   Melhor gap: {best_gap:.2f}")
        print(f"   Documentos recentes (gap<0.5) nos top10: {recent_docs}")
        fallback_trigger = best_gap > 2.0 and recent_docs < 2
        print(f"   Fallback ativado? {'✅ SIM' if fallback_trigger else '❌ NÃO'}")

    # ========================================================================
    # 5. COMPARAÇÃO COM A CONFIGURAÇÃO ATUAL
    # ========================================================================
    print("\n" + "=" * 50)
    print("📌 4. ANÁLISE DA CONFIGURAÇÃO")
    print("=" * 50)

    print("   Configurações atuais do TemporalRAG:")
    print(f"      search_top_k: {temporal.config.search_top_k}")
    print(f"      max_results_returned: {temporal.config.max_results_returned}")
    print(f"      yearly_penalty_rate: {temporal.config.yearly_penalty_rate}")
    print(f"      old_doc_threshold_years: {temporal.config.old_doc_threshold_years}")
    print(f"      similarity_threshold: {temporal.config.similarity_threshold}")

    print("\n   Sugestões de ajuste:")
    if scored and found_g15 is False:
        print("   - Aumentar search_top_k para 100 para capturar mais documentos.")
        print("   - Aumentar max_results_returned para 15.")
        print("   - Reduzir yearly_penalty_rate para 0.02 para penalizar menos documentos antigos.")
        print("   - Aumentar old_doc_threshold_years para 3.0 para ativar fallback apenas para documentos muito antigos.")
    else:
        print("   - Nenhum ajuste necessário.")

    print("\n" + "=" * 80)
    print("🔍 FIM DO DIAGNÓSTICO")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())