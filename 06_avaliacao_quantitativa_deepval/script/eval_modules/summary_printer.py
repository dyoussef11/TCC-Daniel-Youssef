"""reporting/summary_printer.py - Impressão de resumo no console"""

from typing import List, Dict


class SummaryPrinter:
    """Imprime resumo da avaliação comparativa"""
    
    @staticmethod
    def print_summary(results_table: List[Dict]):
        print("\n" + "=" * 80)
        print("✅ AVALIAÇÃO COMPARATIVA CONCLUÍDA")
        print("=" * 80)
        
        SummaryPrinter._print_metric_analysis(results_table)
        SummaryPrinter._print_behavioral_analysis(results_table)
        SummaryPrinter._print_recommendation()
    
    @staticmethod
    def _print_metric_analysis(results_table: List[Dict]):
        traditional = [r for r in results_table if r.get("Test_Type") != "behavioral"]
        
        if not traditional:
            return
        
        print("\n📊 ANÁLISE DE GANHO DO V9 SOBRE V1:")
        metrics = ["Faithfulness", "Answer_Rel", "C_Relevancia"]
        
        for metric in metrics:
            v1_scores = [r.get(f"V1_{metric}_Score", 0) for r in traditional if isinstance(r.get(f"V1_{metric}_Score"), (int, float))]
            v9_scores = [r.get(f"V9_{metric}_Score", 0) for r in traditional if isinstance(r.get(f"V9_{metric}_Score"), (int, float))]
            
            if v1_scores and v9_scores:
                v1_avg = sum(v1_scores) / len(v1_scores)
                v9_avg = sum(v9_scores) / len(v9_scores)
                gain = v9_avg - v1_avg
                gain_pct = (gain / v1_avg * 100) if v1_avg > 0 else 0
                
                symbol = "🟢" if gain > 0.05 else "🔴" if gain < -0.05 else "⚪"
                print(f"   {symbol} {metric}: V1={v1_avg:.3f} → V9={v9_avg:.3f} ({gain:+.3f} / {gain_pct:+.1f}%)")
    
    @staticmethod
    def _print_behavioral_analysis(results_table: List[Dict]):
        behavioral = [r for r in results_table if r.get("Test_Type") == "behavioral"]
        
        if not behavioral:
            return
        
        v1_passed = sum(1 for r in behavioral if r.get("V1_Behavioral_Passed"))
        v9_passed = sum(1 for r in behavioral if r.get("V9_Behavioral_Passed"))
        
        print(f"\n📊 TESTES COMPORTAMENTAIS ({len(behavioral)} casos):")
        print(f"   V1 (Vanilla): {v1_passed}/{len(behavioral)} ({v1_passed/len(behavioral)*100:.0f}%)")
        print(f"   V9 (Temporal): {v9_passed}/{len(behavioral)} ({v9_passed/len(behavioral)*100:.0f}%)")
        
        if v9_passed < v1_passed:
            print(f"   ⚠️ V9 é MAIS RESTRITIVO (SKU lock) - comportamento esperado")
        elif v9_passed > v1_passed:
            print(f"   ✅ V9 tem MELHOR ADERÊNCIA às regras comportamentais")
    
    @staticmethod
    def _print_recommendation():
        print("\n" + "=" * 80)
        print("🎯 RECOMENDAÇÃO FINAL")
        print("=" * 80)
        print("""
        ✅ Use V9 (Temporal) para:
           - Suporte técnico com SKU específico
           - E-commerce e catálogo de produtos
           - Cenários que exigem precisão e rastreabilidade
        
        ✅ Use V1 (Vanilla) para:
           - Chat geral e FAQs
           - Troubleshooting conceitual
           - Quando o usuário NÃO tem o SKU
        
        📌 Trade-off: V9 é mais PRECISO, V1 é mais ÚTIL
        """)