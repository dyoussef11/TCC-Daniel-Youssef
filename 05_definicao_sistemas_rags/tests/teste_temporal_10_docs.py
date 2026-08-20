import numpy as np
from datetime import datetime

# Simulação das classes estruturais do seu projeto para execução direta
class TemporalScorer:
    def __init__(self, yearly_penalty_rate: float = 0.04):
        self.yearly_penalty_rate = yearly_penalty_rate
    
    def calculate_temporal_gap(self, doc_date: str, ref_date: datetime) -> float:
        try:
            doc_dt = datetime.strptime(doc_date[:10], "%Y-%m-%d")
            return (ref_date - doc_dt).days / 365.25
        except:
            return 0.0

class FallbackSearcher:
    def __init__(self, old_doc_threshold_years: float = 2.0):
        self.old_doc_threshold_years = old_doc_threshold_years
    
    def should_activate(self, scored_results: list) -> bool:
        if not scored_results:
            return False
        best_doc_age = scored_results[0].get('temporal_gap', 0)
        recent_docs_count = sum(1 for r in scored_results if r.get('temporal_gap', 0) < 0.5)
        return best_doc_age > self.old_doc_threshold_years and recent_docs_count < 2

def executar_super_teste():
    print("=" * 90)
    print("🧪 SUPER TESTE EXPANDIDO: 10 CENÁRIOS DE RE-RANKING TEMPORAL")
    print("=" * 90)

    ref_date = datetime.strptime("2026-06-24", "%Y-%m-%d")
    scorer = TemporalScorer(yearly_penalty_rate=0.04) # 4% ao ano
    fallback_searcher = FallbackSearcher(old_doc_threshold_years=2.0)

    # 10 Documentos simulando diferentes comportamentos de busca (FAISS L2)
    base_documentos = [
        {"id": 1, "title": "Doc A: Match Perfeito mas Muito Antigo", "date_iso": "2016-06-24", "semantic_distance": 0.20},
        {"id": 2, "title": "Doc B: Excelente Semântica e Idade Média", "date_iso": "2022-06-24", "semantic_distance": 0.45},
        {"id": 3, "title": "Doc C: Boa Semântica e Recente", "date_iso": "2025-12-24", "semantic_distance": 0.58},
        {"id": 4, "title": "Doc D: Lançado Ontem (Hiper-Recente)", "date_iso": "2026-06-23", "semantic_distance": 0.62},
        {"id": 5, "title": "Doc E: Match Justo de 1 Ano Atrás", "date_iso": "2025-06-24", "semantic_distance": 0.65},
        {"id": 6, "title": "Doc F: Data Futura (Erro de sistema/Anacronismo)", "date_iso": "2027-01-01", "semantic_distance": 0.70},
        {"id": 7, "title": "Doc G: Semântica Mediana e Antigo", "date_iso": "2020-01-01", "semantic_distance": 0.85},
        {"id": 8, "title": "Doc H: Quase Ruim mas Recente", "date_iso": "2026-03-01", "semantic_distance": 1.10},
        {"id": 9, "title": "Doc I: Ruim Semântica e Velho", "date_iso": "2018-05-15", "semantic_distance": 1.40},
        {"id": 10, "title": "Doc J: Totalmente Irrelevante", "date_iso": "2026-06-01", "semantic_distance": 1.95},
    ]

    print(f"📅 Data de Referência: {ref_date.strftime('%Y-%m-%d')}\n")
    
    # Processando e aplicando penalidades
    scored_results = []
    for doc in base_documentos:
        gap = scorer.calculate_temporal_gap(doc["date_iso"], ref_date)
        
        # Lógica do código: se o documento for futuro ou hoje, gap <= 0 -> sem penalidade
        if gap <= 0:
            final_penalty = 1.0
        else:
            final_penalty = 1.0 + (gap * scorer.yearly_penalty_rate)
            
        final_distance = doc["semantic_distance"] * final_penalty
        
        scored_results.append({
            'doc': doc,
            'semantic_score': doc['semantic_distance'],
            'final_score': final_distance,
            'temporal_gap': gap,
            'penalty_pcent': (final_penalty - 1.0) * 100
        })

    # Exibindo o antes e depois detalhado
    print(f"{'DOCUMENTO':<42} | {'S. DIST':<7} | {'GAP (Y)':<7} | {'PENALTY':<7} | {'FINAL L2':<8}")
    print("-" * 90)
    for res in scored_results:
        print(f"{res['doc']['title']:<42} | {res['semantic_score']:<7.4f} | {max(0.0, res['temporal_gap']):<7.2f} | +{res['penalty_pcent']:<5.1f}% | {res['final_score']:<8.4f}")

    # Ordenando (Menor distância L2 = Melhor documento)
    scored_results.sort(key=lambda x: x['final_score'])

    print("\n" + "="*50)
    print("🏆 RANKING FINAL APÓS RE-RANKING TEMPORAL")
    print("="*50)
    for idx, res in enumerate(scored_results):
        medalha = "🥇" if idx == 0 else "🥈" if idx == 1 else "🥉" if idx == 2 else f"{idx+1}º"
        print(f"{medalha:<3} {res['doc']['title']:<42} -> L2 Final: {res['final_score']:.4f} (Original: {res['semantic_score']:.4f})")

    print("\n" + "="*50)
    print("🔍 ANÁLISE DE GATILHO DO FALLBACK")
    print("="*50)
    best_doc = scored_results[0]
    recent_docs_count = sum(1 for r in scored_results if r['temporal_gap'] < 0.5 and r['temporal_gap'] >= 0)
    
    print(f"• Melhor Documento Eleito: '{best_doc['doc']['title']}'")
    print(f"• Idade do Melhor Documento: {max(0.0, best_doc['temporal_gap']):.2f} anos")
    print(f"• Documentos muito recentes no Top 10 (< 0.5 anos): {recent_docs_count}")
    
    ativar_fallback = fallback_searcher.should_activate(scored_results)
    status_fb = "🟢 ATIVADO (O topo é antigo ou faltam novidades confiáveis!)" if ativar_fallback else "🔴 DESATIVADO (O topo é recente o suficiente!)"
    print(f"• Status do Fallback: {status_fb}")

if __name__ == "__main__":
    executar_super_teste()