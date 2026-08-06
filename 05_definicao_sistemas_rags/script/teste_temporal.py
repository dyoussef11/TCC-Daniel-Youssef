import numpy as np
from datetime import datetime
from typing import Dict, List, Tuple, Set

# Reimportando ou declarando as classes ajustadas conforme o seu arquivo
from RAG_Temporal_V9_3 import TemporalScorer, FallbackSearcher

def executar_teste_personalizado():
    print("=" * 70)
    print("🧪 INICIANDO TESTE PERSONALIZADO: RE-RANKING TEMPORAL & FALLBACK")
    print("=" * 70)

    # 1. Configurações Iniciais
    ref_date = datetime.strptime("2026-06-24", "%Y-%m-%d")
    
    # Instanciando o Scorer com a correção lógica (QUANTO MAIOR A DISTÂNCIA L2, PIOR)
    # Se a distância L2 aumenta, o documento fica "mais longe" (pior) no ranking.
    scorer = TemporalScorer(
        yearly_penalty_rate=0.04,        # 4% de acréscimo na distância por ano
        recency_threshold=3,
        low_coverage_multiplier=0.3
    )
    
    fallback_searcher = FallbackSearcher(
        similarity_threshold=1.2,
        max_fallback_docs=2,
        old_doc_threshold_years=2.0
    )

    # 2. Mock de Documentos (Simulando o retorno do FAISS)
    # No FAISS IndexFlatL2: MENOR distância = MELHOR match semântico.
    documents_mock = [
        {
            "id": 101,
            "title": "Manual Alpha V1 (Legado)",
            "date_iso": "2022-06-24", # 4 anos atrás
            "semantic_distance": 0.50 # Excelente match semântico
        },
        {
            "id": 102,
            "title": "Manual Alpha V3 (Atualizado)",
            "date_iso": "2026-01-24", # ~0.4 anos atrás (Recente)
            "semantic_distance": 0.65 # Match semântico ligeiramente pior
        },
        {
            "id": 103,
            "title": "Documento Antigo Aleatório",
            "date_iso": "2020-06-24", # 6 anos atrás
            "semantic_distance": 1.30 # Ruim semanticamente e velho
        }
    ]

    print(f"📅 Data de Referência do Sistema: {ref_date.strftime('%Y-%m-%d')}\n")
    print("📌 [ETAPA 1] Distâncias Semânticas Originais (Retorno Direto do FAISS):")
    for doc in documents_mock:
        print(f"   • {doc['title']} | Distância L2 original: {doc['semantic_distance']:.4f} | Data: {doc['date_iso']}")
    
    # 3. Aplicando o Score Temporal
    scored_results = []
    print("\n⚡ [ETAPA 2] Aplicando Penalidade Temporal Adaptativa:")
    
    for doc in documents_mock:
        gap = scorer.calculate_temporal_gap(doc["date_iso"], ref_date)
        
        # Como no FAISS menor distância é melhor, se quisermos penalizar, 
        # precisamos AUMENTAR a distância de documentos velhos.
        base_penalty = 1.0 + (gap * scorer.yearly_penalty_rate)
        
        # Multiplicador de recência fixado em 1.0 para este exemplo isolado
        recency_multiplier = 1.0 
        final_penalty = 1.0 + (base_penalty - 1.0) * recency_multiplier
        
        # A distância final aumenta (piora) proporcionalmente ao tempo
        final_distance = doc["semantic_distance"] * final_penalty
        
        scored_results.append({
            'doc': doc,
            'idx': doc['id'],
            'semantic_score': doc['semantic_distance'], # distância original
            'final_score': final_distance,             # nova distância
            'temporal_gap': gap,
            'penalty_applied': final_penalty - 1.0,
            'date': doc['date_iso']
        })
        
        print(f"   • {doc['title']}:")
        print(f"     -> Idade (Gap): {gap:.2f} anos")
        print(f"     -> Penalidade Calculada: +{((final_penalty - 1.0)*100):.1f}% na distância")
        print(f"     -> Distância: {doc['semantic_distance']:.4f} ➔ {final_distance:.4f}")

    # Ordena os resultados: menor distância (melhor) primeiro
    scored_results.sort(key=lambda x: x['final_score'])

    print("\n🔄 [ETAPA 3] Ranking Após Penalidade Temporal:")
    for i, res in enumerate(scored_results):
        print(f"   {i+1}º: {res['doc']['title']} | Nova Distância: {res['final_score']:.4f} (Antes: {res['semantic_score']:.4f})")

    # 4. Testando o Gatilho do Fallback Searcher
    print("\n🔍 [ETAPA 4] Verificando Condição de Fallback:")
    # Forçando o cenário onde o melhor documento é velho para testar a ativação:
    best_doc_age = scored_results[0]['temporal_gap']
    recent_docs_count = sum(1 for r in scored_results if r['temporal_gap'] < 0.5)
    
    print(f"   • Idade do melhor documento atual: {best_doc_age:.2f} anos")
    print(f"   • Quantidade de documentos bem recentes (< 0.5 anos): {recent_docs_count}")
    
    should_activate = fallback_searcher.should_activate(scored_results)
    print(f"   • O Fallback deve ser ativado? {'🟢 SIM' if should_activate else '🔴 NÃO'}")

if __name__ == "__main__":
    executar_teste_personalizado()