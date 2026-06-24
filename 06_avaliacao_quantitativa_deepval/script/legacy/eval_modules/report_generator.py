"""reporting/report_generator.py - Geração de relatórios em diferentes formatos"""

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import pandas as pd


class ReportGenerator:
    """
    Gera relatórios da avaliação comparativa em múltiplos formatos.
    Suporta: TXT (detalhado), CSV (dados brutos), MD (documentação)
    """
    
    def __init__(self, output_dir: Path, timestamp: str):
        self.output_dir = output_dir
        self.timestamp = timestamp
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_all_reports(self, results_table: List[Dict], config, test_suite_stats: Dict) -> Dict:
        """Gera todos os tipos de relatório e retorna os caminhos"""
        return {
            "csv": self._generate_csv(results_table),
            "txt": self._generate_txt(results_table, config, test_suite_stats),
            "md": self._generate_md(results_table, config, test_suite_stats),
            "summary_json": self._generate_summary_json(results_table)
        }
    
    def _generate_csv(self, results_table: List[Dict]) -> Path:
        """Gera arquivo CSV com dados brutos"""
        csv_path = self.output_dir / f"COMPARATIVO_V1_VS_V9_{self.timestamp}.csv"
        pd.DataFrame(results_table).to_csv(csv_path, index=False)
        return csv_path
    
    def _generate_txt(self, results_table: List[Dict], config, test_suite_stats: Dict) -> Path:
        """Gera relatório detalhado em TXT com justificativas"""
        txt_path = self.output_dir / f"RELATORIO_COMPARATIVO_{self.timestamp}.txt"
        
        with open(txt_path, 'w', encoding='utf-8') as f:
            self._write_txt_header(f, config, test_suite_stats)
            
            for row in results_table:
                self._write_txt_case(f, row)
            
            self._write_txt_summary(f, results_table)
            self._write_txt_recommendation(f)
        
        return txt_path
    
    def _generate_md(self, results_table: List[Dict], config, test_suite_stats: Dict) -> Path:
        """Gera relatório em Markdown para documentação"""
        md_path = self.output_dir / f"RELATORIO_COMPARATIVO_{self.timestamp}.md"
        
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(f"# Relatório Comparativo: V1 (Vanilla) vs V9 (Temporal)\n\n")
            f.write(f"**Data:** {self.timestamp}\n")
            f.write(f"**Base:** {config.base_path.name}\n")
            f.write(f"**Total de casos:** {test_suite_stats['total']}\n\n")
            
            f.write("## Resumo dos Resultados\n\n")
            self._write_md_summary(f, results_table)
            
            f.write("\n## Análise Detalhada\n\n")
            self._write_md_metrics_table(f, results_table)
            self._write_md_behavioral_table(f, results_table)
            
            f.write("\n## Recomendação\n\n")
            self._write_md_recommendation(f)
        
        return md_path
    
    def _generate_summary_json(self, results_table: List[Dict]) -> Path:
        """Gera JSON com resumo estatístico"""
        import json
        
        json_path = self.output_dir / f"RESUMO_{self.timestamp}.json"
        
        # Calcula estatísticas
        traditional = [r for r in results_table if r.get("Test_Type") != "behavioral"]
        behavioral = [r for r in results_table if r.get("Test_Type") == "behavioral"]
        
        summary = {
            "timestamp": self.timestamp,
            "total_cases": len(results_table),
            "traditional_cases": len(traditional),
            "behavioral_cases": len(behavioral),
            "metrics": {},
            "behavioral": {}
        }
        
        # Métricas tradicionais
        if traditional:
            metrics = ["Faithfulness", "Answer_Rel", "C_Relevancia", "C_Precision", "C_Recall"]
            for metric in metrics:
                v1_scores = [r.get(f"V1_{metric}_Score", 0) for r in traditional if isinstance(r.get(f"V1_{metric}_Score"), (int, float))]
                v9_scores = [r.get(f"V9_{metric}_Score", 0) for r in traditional if isinstance(r.get(f"V9_{metric}_Score"), (int, float))]
                
                summary["metrics"][metric] = {
                    "v1_avg": sum(v1_scores) / len(v1_scores) if v1_scores else 0,
                    "v9_avg": sum(v9_scores) / len(v9_scores) if v9_scores else 0,
                    "v1_count": len(v1_scores),
                    "v9_count": len(v9_scores)
                }
        
        # Comportamentais
        if behavioral:
            v1_passed = sum(1 for r in behavioral if r.get("V1_Behavioral_Passed"))
            v9_passed = sum(1 for r in behavioral if r.get("V9_Behavioral_Passed"))
            
            summary["behavioral"] = {
                "v1_passed": v1_passed,
                "v9_passed": v9_passed,
                "total": len(behavioral),
                "v1_rate": v1_passed / len(behavioral) if behavioral else 0,
                "v9_rate": v9_passed / len(behavioral) if behavioral else 0
            }
        
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        
        return json_path
    
    def _write_txt_header(self, f, config, test_suite_stats: Dict):
        f.write("=" * 80 + "\n")
        f.write("RELATÓRIO COMPARATIVO: V1 (Vanilla) vs V9 (Temporal)\n")
        f.write("=" * 80 + "\n")
        f.write(f"Data: {self.timestamp}\n")
        f.write(f"Base: {config.base_path}\n")
        f.write(f"Avaliador: {config.evaluator_model}\n")
        f.write(f"Modelo LLM: {config.model_name}\n")
        f.write(f"Temperature: {config.temperature}\n")
        f.write("-" * 80 + "\n")
        f.write(f"Total de casos: {test_suite_stats['total']}\n")
        f.write(f"├── Tradicionais: {test_suite_stats['traditional']}\n")
        f.write(f"└── Comportamentais: {test_suite_stats['behavioral']}\n")
        f.write("=" * 80 + "\n\n")
    
    def _write_txt_case(self, f, row: Dict):
        """Escreve um caso de teste com todas as justificativas"""
        f.write(f"\n{'='*60}\n")
        f.write(f"ID: {row.get('ID', 'unknown')}\n")
        f.write(f"Test Type: {row.get('Test_Type', 'traditional')}\n")
        f.write(f"Query: {row.get('Query', '')}\n")
        
        # Respostas
        f.write(f"\n--- V1 (VANILLA) ---\n")
        f.write(f"Answer: {row.get('V1_Answer', '')[:800]}\n")
        
        if row.get('Test_Type') == 'behavioral':
            f.write(f"Behavioral Passed: {row.get('V1_Behavioral_Passed', False)}\n")
            f.write(f"Behavioral Reason: {row.get('V1_Behavioral_Reason', '')}\n")
        else:
            f.write(f"\n--- V1 MÉTRICAS ---\n")
            for metric in ["Faithfulness", "Answer_Rel", "C_Relevancia", "C_Precision", "C_Recall"]:
                score = row.get(f"V1_{metric}_Score", 0)
                reason = row.get(f"V1_{metric}_Reason", "No reason provided")
                f.write(f"{metric}: {score:.3f}\n")
                f.write(f"  Reason: {reason[:500]}\n")
        
        f.write(f"\n--- V9 (TEMPORAL) ---\n")
        f.write(f"Answer: {row.get('V9_Answer', '')[:800]}\n")
        
        if row.get('Test_Type') == 'behavioral':
            f.write(f"Behavioral Passed: {row.get('V9_Behavioral_Passed', False)}\n")
            f.write(f"Behavioral Reason: {row.get('V9_Behavioral_Reason', '')}\n")
        else:
            f.write(f"\n--- V9 MÉTRICAS ---\n")
            for metric in ["Faithfulness", "Answer_Rel", "C_Relevancia", "C_Precision", "C_Recall"]:
                score = row.get(f"V9_{metric}_Score", 0)
                reason = row.get(f"V9_{metric}_Reason", "No reason provided")
                f.write(f"{metric}: {score:.3f}\n")
                f.write(f"  Reason: {reason}\n")
        
        f.write("-" * 60 + "\n")
    
    def _write_txt_summary(self, f, results_table: List[Dict]):
        f.write("\n" + "=" * 80 + "\n")
        f.write("RESUMO DOS RESULTADOS\n")
        f.write("=" * 80 + "\n")
        
        # Métricas médias
        traditional = [r for r in results_table if r.get("Test_Type") != "behavioral"]
        if traditional:
            f.write("\n📊 MÉTRICAS MÉDIAS (DeepEval):\n")
            for metric in ["Faithfulness", "Answer_Rel", "C_Relevancia", "C_Precision", "C_Recall"]:
                v1_scores = [r.get(f"V1_{metric}_Score", 0) for r in traditional if isinstance(r.get(f"V1_{metric}_Score"), (int, float))]
                v9_scores = [r.get(f"V9_{metric}_Score", 0) for r in traditional if isinstance(r.get(f"V9_{metric}_Score"), (int, float))]
                if v1_scores and v9_scores:
                    v1_avg = sum(v1_scores) / len(v1_scores)
                    v9_avg = sum(v9_scores) / len(v9_scores)
                    variation = v9_avg - v1_avg
                    arrow = "↑" if variation > 0 else "↓" if variation < 0 else "→"
                    f.write(f"  {metric}: V1={v1_avg:.3f} {arrow} V9={v9_avg:.3f} (Δ {variation:+.3f})\n")
        
        # Comportamentais
        behavioral = [r for r in results_table if r.get("Test_Type") == "behavioral"]
        if behavioral:
            v1_passed = sum(1 for r in behavioral if r.get("V1_Behavioral_Passed"))
            v9_passed = sum(1 for r in behavioral if r.get("V9_Behavioral_Passed"))
            f.write(f"\n📊 TESTES COMPORTAMENTAIS:\n")
            f.write(f"  V1: {v1_passed}/{len(behavioral)} ({v1_passed/len(behavioral)*100:.0f}%)\n")
            f.write(f"  V9: {v9_passed}/{len(behavioral)} ({v9_passed/len(behavioral)*100:.0f}%)\n")
            
            # Detalhar quais passaram/ falharam
            f.write(f"\n  Detalhamento:\n")
            for row in behavioral:
                test_id = row.get('ID', 'unknown')
                v1_status = "✅" if row.get('V1_Behavioral_Passed') else "❌"
                v9_status = "✅" if row.get('V9_Behavioral_Passed') else "❌"
                f.write(f"    {test_id}: V1 {v1_status} | V9 {v9_status}\n")
                f.write(f"      V1 Reason: {row.get('V1_Behavioral_Reason', '')[:200]}\n")
                f.write(f"      V9 Reason: {row.get('V9_Behavioral_Reason', '')[:200]}\n")
    
    def _write_txt_recommendation(self, f):
        f.write("\n" + "=" * 80 + "\n")
        f.write("🎯 RECOMENDAÇÃO FINAL\n")
        f.write("=" * 80 + "\n")
        f.write("""
        ✅ Use V9 (Temporal) para:
           - Suporte técnico com SKU específico
           - E-commerce e catálogo de produtos
           - Cenários que exigem precisão e rastreabilidade
        
        ✅ Use V1 (Vanilla) para:
           - Chat geral e FAQs
           - Troubleshooting conceitual
           - Quando o usuário NÃO tem o SKU
        
        📌 Conclusão: V9 é SUPERIOR em precisão e controle de alucinação.
                       V1 é SUPERIOR em utilidade e abrangência.
        """)
    
    def _write_md_summary(self, f, results_table: List[Dict]):
        behavioral = [r for r in results_table if r.get("Test_Type") == "behavioral"]
        traditional = [r for r in results_table if r.get("Test_Type") != "behavioral"]
        
        if behavioral:
            v9_passed = sum(1 for r in behavioral if r.get("V9_Behavioral_Passed"))
            f.write(f"- **Testes Comportamentais (SKU lock):** {v9_passed}/{len(behavioral)} passaram ({v9_passed/len(behavioral)*100:.0f}%)\n")
        
        if traditional:
            v9_faith = sum(r.get("V9_Faithfulness_Score", 0) for r in traditional) / len(traditional)
            f.write(f"- **Faithfulness médio:** {v9_faith:.3f}\n")
    
    def _write_md_metrics_table(self, f, results_table: List[Dict]):
        f.write("### Métricas DeepEval\n\n")
        f.write("| Métrica | V1 (Vanilla) | V9 (Temporal) | Variação |\n")
        f.write("|---------|--------------|---------------|----------|\n")
        
        traditional = [r for r in results_table if r.get("Test_Type") != "behavioral"]
        if traditional:
            for metric in ["Faithfulness", "Answer_Rel", "C_Relevancia", "C_Precision", "C_Recall"]:
                v1_scores = [r.get(f"V1_{metric}_Score", 0) for r in traditional]
                v9_scores = [r.get(f"V9_{metric}_Score", 0) for r in traditional]
                if v1_scores:
                    v1_avg = sum(v1_scores) / len(v1_scores)
                    v9_avg = sum(v9_scores) / len(v9_scores)
                    variation = v9_avg - v1_avg
                    emoji = "🟢" if variation > 0 else "🔴" if variation < 0 else "⚪"
                    f.write(f"| {metric} | {v1_avg:.3f} | {v9_avg:.3f} | {emoji} {variation:+.3f} |\n")
    
    def _write_md_behavioral_table(self, f, results_table: List[Dict]):
        behavioral = [r for r in results_table if r.get("Test_Type") == "behavioral"]
        if not behavioral:
            return
        
        f.write("\n### Testes Comportamentais\n\n")
        f.write("| ID | Comportamento Esperado | V1 | V9 | V1 Reason | V9 Reason |\n")
        f.write("|----|----------------------|----|----|-----------|-----------|\n")
        
        for row in behavioral:
            test_id = row.get('ID', 'unknown')
            expected = row.get('Expected_Behavior', 'unknown')[:30]
            v1_status = "✅" if row.get('V1_Behavioral_Passed') else "❌"
            v9_status = "✅" if row.get('V9_Behavioral_Passed') else "❌"
            v1_reason = row.get('V1_Behavioral_Reason', '').replace('|', '\\|')
            v9_reason = row.get('V9_Behavioral_Reason', '').replace('|', '\\|')
            f.write(f"| {test_id} | {expected} | {v1_status} | {v9_status} | {v1_reason} | {v9_reason} |\n")
    
    def _write_md_recommendation(self, f):
        f.write("""
## 🎯 Recomendação Final

| Caso de Uso | Melhor Escolha | Motivo |
|-------------|----------------|--------|
| Chat geral / FAQ | V1 (Vanilla) | Mais útil e abrangente |
| Suporte com SKU | V9 (Temporal) | Mais preciso, sem alucinação |
| E-commerce / Catálogo | V9 (Temporal) | Rastreável e consistente |
| Troubleshooting | V1 (Vanilla) | Pode usar conhecimento interno |
| Atendimento técnico | V9 (Temporal) | Auditoria completa |

### Conclusão

- **V9 é superior para casos que exigem PRECISÃO e RASTREABILIDADE**
- **V1 é melhor para CASOS GERAIS onde utilidade > precisão**
- **O trade-off é intencional e deve guiar a escolha de acordo com o caso de uso**
""")