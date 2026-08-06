"""
temporal_scoring.py
Sistema de penalidade temporal adaptativa.
"""

from datetime import datetime
from typing import Dict, List, Tuple, Optional

class TemporalScorer:
    """Aplica penalidade temporal adaptativa baseada em idade e cobertura do domínio."""
    
    def __init__(self, yearly_penalty_rate: float = 0.03,
                 recency_threshold: int = 3,
                 low_coverage_multiplier: float = 0.3):
        self.yearly_penalty_rate = yearly_penalty_rate
        self.recency_threshold = recency_threshold
        self.low_coverage_multiplier = low_coverage_multiplier
        
    def calculate_temporal_gap(self, doc_date: str, ref_date: datetime) -> float:
        """
        Calcula o gap temporal em anos.
        
        Args:
            doc_date: Data do documento (YYYY-MM-DD)
            ref_date: Data de referência
            
        Returns:
            float: Gap em anos
        """
        try:
            doc_dt = datetime.strptime(doc_date[:10], "%Y-%m-%d")
            return (ref_date - doc_dt).days / 365.25
        except (ValueError, IndexError):
            return 0.0
    
    def calculate_domain_recency(self, doc_model: str, ref_date: datetime, 
                                 all_docs: List[Dict]) -> float:
        """
        Calcula o fator de recência do domínio.
        
        Quanto mais documentos recentes, MAIOR o multiplicador (mais penalidade).
        Domínios com pouca cobertura recebem penalidade reduzida.
        
        Args:
            doc_model: Modelo do documento
            ref_date: Data de referência
            all_docs: Todos os documentos para contar recência
            
        Returns:
            float: Multiplicador de penalidade (0.3 a 1.0)
        """
        if not doc_model:
            return 1.0  # Sem modelo, penalidade padrão
        
        recent_count = 0
        for other in all_docs:
            other_model = other.get('metadata', {}).get('model', '')
            if other_model == doc_model:
                other_date = other.get('date_iso', '2024-01-01')[:10]
                try:
                    other_dt = datetime.strptime(other_date, "%Y-%m-%d")
                    if other_dt > ref_date:
                        recent_count += 1
                except ValueError:
                    pass
        
        # Mais documentos recentes = maior penalidade para os antigos
        recency_ratio = min(recent_count / self.recency_threshold, 1.0)
        
        # Multiplicador: mínimo = low_coverage, máximo = 1.0
        return max(self.low_coverage_multiplier, recency_ratio)
    
    def score_document(self, semantic_score: float, temporal_gap: float, 
                      recency_multiplier: float) -> Tuple[float, float, str]:
        """
        Calcula o score final de um documento.
        
        Args:
            semantic_score: Score de similaridade semântica
            temporal_gap: Gap temporal em anos
            recency_multiplier: Multiplicador baseado na cobertura do domínio
            
        Returns:
            Tuple[float, float, str]: (final_score, penalty_applied, status)
        """
        if temporal_gap <= 0:
            # Documento futuro ou mesma data
            return semantic_score, 0.0, "future_or_current"
        
        # Cálculo da penalidade
        base_penalty = 1.0 + (temporal_gap * self.yearly_penalty_rate)
        final_penalty = 1.0 + (base_penalty - 1.0) * recency_multiplier
        final_score = semantic_score * final_penalty
        
        penalty_applied = final_penalty - 1.0
        status = f"old_gap_{temporal_gap:.1f}y_penalty_{final_penalty:.2f}"
        
        return final_score, penalty_applied, status
    
    def get_penalty_stats(self, scored_results: List[Dict]) -> Dict:
        """
        Calcula estatísticas de penalidade dos resultados.
        
        Args:
            scored_results: Lista de resultados pontuados
            
        Returns:
            Dict: Estatísticas de penalidade
        """
        if not scored_results:
            return {"avg_penalty": 0, "max_penalty": 0, "docs_with_penalty": 0}
        
        penalties = [r.get('penalty_applied', 0) for r in scored_results]
        docs_with_penalty = sum(1 for p in penalties if p > 0)
        
        return {
            "avg_penalty": round(sum(penalties) / len(penalties), 4),
            "max_penalty": round(max(penalties), 4),
            "docs_with_penalty": docs_with_penalty,
            "total_docs": len(scored_results)
        }