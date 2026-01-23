class TimeAwareRetriever:
    def __init__(self, vector_store, temporal_index):
        self.vector_store = vector_store
        self.temporal_index = temporal_index
        
    def retrieve(self, query, time_constraint=None, top_k=10):
        # Busca semântica básica
        semantic_results = self.vector_store.similarity_search(query, k=top_k*2)
        
        # Aplicar filtros temporais se fornecidos
        if time_constraint:
            filtered_results = self._apply_time_filter(semantic_results, time_constraint)
        else:
            filtered_results = semantic_results
        
        # Re-ranker com consciência temporal
        reranked = self._temporal_rerank(filtered_results, query)
        
        return reranked[:top_k]
    
    def _apply_time_filter(self, results, time_constraint):
        """Filtrar resultados por restrição temporal"""
        filtered = []
        for result in results:
            doc_time = self._extract_time_from_metadata(result.metadata)
            if self._is_within_time_constraint(doc_time, time_constraint):
                filtered.append(result)
        return filtered
    
    def _temporal_rerank(self, results, query):
        """Reordenar considerando relevância temporal"""
        # Implementar lógica de reranking
        # Ex: dar peso maior para documentos mais recentes ou do período específico
        return sorted(results, key=lambda x: x.score * self._temporal_decay(x.timestamp))