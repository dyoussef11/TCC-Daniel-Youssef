import numpy as np
from datetime import datetime

class ScorerOriginal:
    def __init__(self, yearly_penalty_rate: float = 0.04):
        self.yearly_penalty_rate = yearly_penalty_rate
        
    def score(self, semantic_score: float, temporal_gap: float) -> float:
        if temporal_gap <= 0:
            return semantic_score
        # Penalidade linear seca (igual para todo mundo)
        base_penalty = 1.0 + (temporal_gap * self.yearly_penalty_rate)
        return semantic_score * base_penalty

class ScorerComAtenuacao:
    def __init__(self, yearly_penalty_rate: float = 0.04):
        self.yearly_penalty_rate = yearly_penalty_rate
        
    def score(self, semantic_score: float, temporal_gap: float) -> float:
        if temporal_gap <= 0:
            return semantic_score
        
        base_penalty_growth = temporal_gap * self.yearly_penalty_rate
        
        # Atenuação: quanto menor o score semântico (melhor), menos ele sofre.
        # Limitamos em 0.3 para que documentos ultra-perfeitos ainda tenham uma micro-penalidade.
        fator_atenuacao = max(0.3, semantic_score) 
        
        final_penalty = 1.0 + (base_penalty_growth * fator_atenuacao)
        return semantic_score * final_penalty

def executar_teste_comparativo():
    print("=" * 95)
    print("🔬 TESTE COMPARATIVO: PENALIDADE SECA (ORIGINAL) vs. PENALIDADE COM ATENUAÇÃO SEMÂNTICA")
    print("=" * 95)

    ref_date = datetime.strptime("2026-06-24", "%Y-%m-%d")
    orig_scorer = ScorerOriginal(yearly_penalty_rate=0.04)
    smart_scorer = ScorerComAtenuacao(yearly_penalty_rate=0.04)

    # Cenário Clássico:
    # Doc 1: Excelente match semântico (0.45), mas tem 4 anos de idade.
    # Doc 2: Match mediano/fraco (0.62), mas foi lançado há 3 meses.
    docs = [
        {"title": "Doc Velho (Excelente Semântica)", "date_iso": "2022-06-24", "l2_original": 0.45},
        {"title": "Doc Novo (Semântica Questionável)", "date_iso": "2026-03-24", "l2_original": 0.62}
    ]

    results_original = []
    results_atenuado = []

    for d in docs:
        doc_dt = datetime.strptime(d["date_iso"], "%Y-%m-%d")
        gap = (ref_date - doc_dt).days / 365.25
        
        # Lógica Original
        l2_orig_scored = orig_scorer.score(d["l2_original"], gap)
        results_original.append({"title": d["title"], "l2_final": l2_orig_scored, "gap": gap, "orig": d["l2_original"]})
        
        # Lógica Com Atenuação
        l2_smart_scored = smart_scorer.score(d["l2_original"], gap)
        results_atenuado.append({"title": d["title"], "l2_final": l2_smart_scored, "gap": gap, "orig": d["l2_original"]})

    # Ordenando os rankings (menor L2 ganha)
    results_original.sort(key=lambda x: x["l2_final"])
    results_atenuado.sort(key=lambda x: x["l2_final"])

    # --- OUTPUT DOS RESULTADOS ---
    print(f"📅 Data de Referência: {ref_date.strftime('%Y-%m-%d')}\n")
    
    print("❌ [RANKING ORIGINAL - PENALIDADE SECA]")
    print(f"   {'Pos':<4} | {'Documento':<32} | {'GAP (Anos)':<10} | {'L2 Original':<12} | {'L2 Final':<10}")
    print("   " + "-" * 75)
    for idx, r in enumerate(results_original):
        print(f"   {idx+1}º   | {r['title']:<32} | {r['gap']:<10.2f} | {r['orig']:<12.4f} | {r['l2_final']:.4f}")
    
    print("\n" + "~"*95 + "\n")
    
    print("🟢 [RANKING CORRIGIDO - COM ATENUAÇÃO SEMÂNTICA]")
    print(f"   {'Pos':<4} | {'Documento':<32} | {'GAP (Anos)':<10} | {'L2 Original':<12} | {'L2 Final':<10}")
    print("   " + "-" * 75)
    for idx, r in enumerate(results_atenuado):
        print(f"   {idx+1}º   | {r['title']:<32} | {r['gap']:<10.2f} | {r['orig']:<12.4f} | {r['l2_final']:.4f}")

    print("\n💡 CONCLUSÃO DIAGNÓSTICA:")
    if results_original[0]["title"] != results_atenuado[0]["title"]:
        print(f"   ↳ 🚨 O ranking INVERTEU! A atenuação impediu que o '{results_original[0]['title']}' \n"
              f"     ganhasse o topo injustamente apenas por critério temporal básico.")
    else:
        print("   ↳ Os rankings mantiveram as posições, mas repare na folga/distância métrica entre os nós.")

if __name__ == "__main__":
    executar_teste_comparativo()