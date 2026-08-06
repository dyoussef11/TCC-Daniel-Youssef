"""
fallback_search.py
Mecanismo de fallback sem penalidade temporal.
"""

import numpy as np
from datetime import datetime
from typing import Dict, List, Set, Optional

class FallbackSearcher:
    """Executa busca sem penalidade temporal para documentos antigos."""
    
    def __init__(self, similarity_threshold: float = 1.2,
                 max_fallback_docs: int = 3,
                 old_doc_threshold_years: float = 2.0):
        self.similarity_threshold = similarity_threshold
        self.max_fallback_docs = max_fallback_docs
        self.old_doc_threshold_years = old_doc_threshold_years
    
    def should_activate(self, scored_results: List[Dict]) -> bool:
        """
        Verifica se o fallback deve ser ativado.
        
        Critérios:
        1. Melhor documento é muito antigo (> threshold)
        2. Poucos documentos recentes (< 2)
        
        Args:
            scored_results: Resultados com score temporal
            
        Returns:
            bool: True se deve ativar fallback
        """
        if not scored_results:
            return False
        
        best_doc_age = scored_results[0].get('temporal_gap', 0)
        recent_docs_count = sum(1 for r in scored_results if r.get('temporal_gap', 0) < 0.5)
        
        return (best_doc_age > self.old_doc_threshold_years and 
                recent_docs_count < 2)
    
    async def semantic_only_search(self, query_vector: np.ndarray, 
                                   index, all_docs: List[Dict],
                                   ref_date: datetime,
                                   existing_ids: Set[int]) -> List[Dict]:
        """
        Busca adicional ignorando penalidade temporal.
        
        Args:
            query_vector: Vetor da query
            index: Índice FAISS
            all_docs: Todos os documentos
            ref_date: Data de referência
            existing_ids: IDs já selecionados
            
        Returns:
            List[Dict]: Resultados do fallback
        """
        # Busca mais ampla
        k_search = self.max_fallback_docs * 3
        distances, indices = index.search(query_vector, k=k_search)
        
        fallback_results = []
        
        for i, idx in enumerate(indices[0]):
            if idx == -1:
                continue
            
            doc = all_docs[idx]
            doc_id = doc.get('id', idx)
            
            # Evita duplicatas
            if doc_id in existing_ids:
                continue
            
            semantic_score = distances[0][i]
            
            # Score máximo para aceitar no fallback (ligeiramente mais relaxado)
            if semantic_score < self.similarity_threshold * 1.1:
                doc_date = doc.get('date_iso', '2024-01-01')[:10]
                temporal_gap = self._calculate_gap(doc_date, ref_date)
                
                fallback_results.append({
                    'doc': doc,
                    'semantic_score': semantic_score,
                    'final_score': semantic_score * 1.05,  # Penalidade simbólica
                    'temporal_gap': temporal_gap,
                    'temporal_status': "fallback_no_penalty",
                    'penalty_applied': 0.05,
                    'date': doc_date
                })
        
        # Ordena por score semântico
        fallback_results.sort(key=lambda x: x['semantic_score'])
        
        return fallback_results[:self.max_fallback_docs]
    
    def _calculate_gap(self, doc_date: str, ref_date: datetime) -> float:
        """Calcula gap temporal."""
        try:
            doc_dt = datetime.strptime(doc_date[:10], "%Y-%m-%d")
            return (ref_date - doc_dt).days / 365.25
        except (ValueError, IndexError):
            return 0.0