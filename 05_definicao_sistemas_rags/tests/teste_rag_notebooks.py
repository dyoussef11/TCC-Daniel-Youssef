import numpy as np
from datetime import datetime

class TemporalScorerOriginal:
    def __init__(self, yearly_penalty_rate: float = 0.04):
        self.yearly_penalty_rate = yearly_penalty_rate
    
    def score(self, semantic_score: float, temporal_gap: float) -> float:
        if temporal_gap <= 0: return semantic_score
        return semantic_score * (1.0 + (temporal_gap * self.yearly_penalty_rate))

class FallbackSearcherMock:
    def __init__(self, old_doc_threshold_years: float = 2.0):
        self.old_doc_threshold_years = old_doc_threshold_years
    
    def should_activate(self, top_doc_gap: float, recent_count: int) -> bool:
        return top_doc_gap > self.old_doc_threshold_years and recent_count < 2

def simular_dimensoes_tempo():
    print("=" * 95)
    print("📊 ANALISANDO AS DIMENSÕES DE TEMPO DO ALGORITMO ORIGINAL")
    print("=" * 95)

    ref_date = datetime.strptime("2026-06-24", "%Y-%m-%d")
    scorer = TemporalScorerOriginal(yearly_penalty_rate=0.04)
    fallback = FallbackSearcherMock(old_doc_threshold_years=2.0)

    # Base de dados dividida por Dimensões Temporais
    # Todas possuem um match semântico idêntico inicial (0.50) para isolarmos o efeito do tempo
    historico_casos = [
        # --- DIMENSÃO 1: CURTO PRAZO (0 a 2 anos) ---
        {"title": "Caso A (Lançado Há 6 Meses)", "date_iso": "2025-12-24", "l2_orig": 0.50, "dimensao": "Curto Prazo (<2y)"},
        {"title": "Caso B (Lançado Há 1.5 Ano)", "date_iso": "2024-12-24", "l2_orig": 0.50, "dimensao": "Curto Prazo (<2y)"},
        
        # --- DIMENSÃO 2: MÉDIO PRAZO (2 a 5 anos) ---
        {"title": "Caso C (Lançado Há 3 Anos)", "date_iso": "2023-06-24", "l2_orig": 0.50, "dimensao": "Médio Prazo (2y-5y)"},
        {"title": "Caso D (Lançado Há 5 Anos)", "date_iso": "2021-06-24", "l2_orig": 0.50, "dimensao": "Médio Prazo (2y-5y)"},
        
        # --- DIMENSÃO 3: LONGO PRAZO / LEGADO (5 a 15+ anos) ---
        {"title": "Asus Zenbook Ux325Ea (2011)", "date_iso": "2011-06-24", "l2_orig": 0.50, "dimensao": "Longo Prazo (15y)"}
    ]

    print(f"📅 Data de Análise: {ref_date.strftime('%Y-%m-%d')}\n")
    print(f"{'DOCUMENTO':<30} | {'DIMENSÃO':<18} | {'GAP (ANOS)':<10} | {'PENALIDADE':<10} | {'L2 FINAL':<8}")
    print("-" * 95)

    scored_docs = []
    for caso in historico_casos:
        doc_dt = datetime.strptime(caso["date_iso"], "%Y-%m-%d")
        gap = (ref_date - doc_dt).days / 365.25
        
        l2_final = scorer.score(caso["l2_orig"], gap)
        penalidade_pcent = (gap * scorer.yearly_penalty_rate) * 100
        
        scored_docs.append({**caso, "gap": gap, "l2_final": l2_final, "penalty_pcent": penalidade_pcent})
        print(f"{caso['title']:<30} | {caso['dimensao']:<18} | {gap:<10.2f} | +{penalidade_pcent:<8.1f}% | {l2_final:.4f}")

    print("\n" + "="*50)
    print("🔍 ANÁLISE DE COMPORTAMENTO POR SUB-LISTAS DE BUSCA")
    print("="*50)

    # Cenário 1: Se o Top 1 for de Curto Prazo (Caso A)
    recentes_c1 = sum(1 for d in scored_docs if d["gap"] < 0.5)
    print(f"🟢 Cenário 1 (Se o topo for recente): Top 1 Gap = {scored_docs[0]['gap']:.2f}y")
    print(f"   ↳ Fallback Ativado? {'🟢 SIM' if fallback.should_activate(scored_docs[0]['gap'], recentes_c1) else '🔴 NÃO (Perfeito, o algoritmo resolveu sozinho!)'}")

    # Cenário 2: Se a base só tiver o documento de Médio Prazo (Caso C) no topo
    recentes_c2 = 0
    print(f"\n🟡 Cenário 2 (Se o topo for de Médio Prazo): Top 1 Gap = {scored_docs[2]['gap']:.2f}y")
    print(f"   ↳ Fallback Ativado? {'🟢 SIM (Excelente, trazendo reforços recentes do índice)' if fallback.should_activate(scored_docs[2]['gap'], recentes_c2) else '🔴 NÃO'}")

    # Cenário 3: Se o único match exato for o Asus de Longo Prazo (2011)
    recentes_c3 = 0
    print(f"\n🚨 Cenário 3 (Se o topo for o Legado de 15 anos): Top 1 Gap = {scored_docs[4]['gap']:.2f}y")
    print(f"   ↳ Distância desfigurada de {scored_docs[4]['l2_orig']:.2f} para {scored_docs[4]['l2_final']:.2f}")
    print(f"   ↳ Fallback Ativado? {'🟢 SIM (Obrigatório, mas o documento sofreu penalidade excessiva)' if fallback.should_activate(scored_docs[4]['gap'], recentes_c3) else '🔴 NÃO'}")

if __name__ == "__main__":
    simular_dimensoes_tempo()