"""
search_pipeline.py
Pipeline de busca do RAG Temporal.
"""

from datetime import datetime
from typing import Dict, List, Tuple, Optional

import numpy as np


class SearchPipeline:
    """
    Gerencia o pipeline de busca: FAISS → temporal scoring → fallback → merge.
    """
    
    def __init__(self, faiss_manager, data_loader, temporal_scorer,
                 fallback_searcher, context_builder, config):
        self.faiss_manager = faiss_manager
        self.data_loader = data_loader
        self.temporal_scorer = temporal_scorer
        self.fallback_searcher = fallback_searcher
        self.context_builder = context_builder
        self.config = config
    
    async def execute(self, query_vector: np.ndarray, query: str,
                     ref_dt: datetime, expanded_query: str) -> List[Dict]:
        """
        Executa o pipeline completo de busca.
        
        Args:
            query_vector: Vetor da query
            query: Query original
            ref_dt: Data de referência
            expanded_query: Query expandida (pode ser igual à original)
            
        Returns:
            Lista de resultados finais (já com contexto)
        """
        # 1. Busca FAISS
        search_results = self.faiss_manager.search(
            query_vector, 
            k=self.config.search_top_k
        )
        
        # 2. Scoring temporal
        scored_results = self._apply_temporal_scoring(
            search_results, ref_dt, query_vector
        )
        
        # 3. Fallback se necessário
        final_results = await self._apply_fallback_if_needed(
            scored_results, query_vector, ref_dt
        )
        
        return final_results
    
    def _apply_temporal_scoring(self, search_results: List[Tuple], 
                                ref_dt: datetime, 
                                query_vector: np.ndarray) -> List[Dict]:
        """Aplica scoring temporal nos resultados."""
        domain_recency_cache = {}
        scored_results = []
        
        for idx, distance in search_results:
            doc = self.data_loader.documents[idx]
            doc_id = doc.get('id', idx)
            doc_date = doc.get('date_iso', '2024-01-01')[:10]
            
            # Gap temporal
            temporal_gap = self.temporal_scorer.calculate_temporal_gap(doc_date, ref_dt)
            
            # Recência do domínio (cacheada)
            if doc_id not in domain_recency_cache:
                model = doc.get('metadata', {}).get('model', '')
                domain_recency_cache[doc_id] = self.temporal_scorer.calculate_domain_recency(
                    model, ref_dt, self.data_loader.documents
                )
            
            recency_multiplier = domain_recency_cache[doc_id]
            
            # Score final
            final_score, penalty, status = self.temporal_scorer.score_document(
                distance, temporal_gap, recency_multiplier
            )
            
            scored_results.append({
                'doc': doc,
                'idx': idx,
                'semantic_score': distance,
                'final_score': final_score,
                'temporal_gap': temporal_gap,
                'temporal_status': status,
                'penalty_applied': penalty,
                'recency_multiplier': recency_multiplier,
                'date': doc_date
            })
        
        # Ordena por score final
        scored_results.sort(key=lambda x: x['final_score'])
        
        return scored_results
    
    async def _apply_fallback_if_needed(self, scored_results: List[Dict],
                                       query_vector: np.ndarray,
                                       ref_dt: datetime) -> List[Dict]:
        """Aplica fallback se necessário."""
        
        if self.fallback_searcher.should_activate(scored_results):
            self.config.log("🔄 Ativando fallback sem penalidade temporal...")
            
            existing_ids = {r['idx'] for r in scored_results}
            
            fallback_results = await self.fallback_searcher.semantic_only_search(
                query_vector.reshape(1, -1),
                self.faiss_manager.index,
                self.data_loader.documents,
                ref_dt,
                existing_ids
            )
            
            if fallback_results:
                return self._merge_results(scored_results, fallback_results)
        
        # Sem fallback, retorna top resultados
        return scored_results[:self.config.max_results_returned]
    
    def _merge_results(self, primary: List[Dict], fallback: List[Dict]) -> List[Dict]:
        """Mescla resultados primários e fallback."""
        existing_ids = {r['doc'].get('id', r['idx']) for r in primary}
        merged = primary[:4]  # Top 4 do primário
        
        for fb in fallback:
            if len(merged) >= self.config.max_results_returned:
                break
            
            fb_id = fb['doc'].get('id', hash(fb.get('date', '')))
            if fb_id not in existing_ids:
                merged.append(fb)
                existing_ids.add(fb_id)
        
        merged.sort(key=lambda x: x['final_score'])
        return merged[:self.config.max_results_returned]