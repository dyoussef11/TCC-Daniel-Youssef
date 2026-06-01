"""
cache_manager.py
Gerenciamento de cache LRU interno e cache externo.
"""

import numpy as np
from functools import lru_cache
from typing import Dict, Optional, Any
import asyncio

class CacheManager:
    """Gerencia cache interno LRU e cache externo."""
    
    def __init__(self, external_cache: Any = None, maxsize: int = 200):
        self.external_cache = external_cache
        self._cache_func = lru_cache(maxsize=maxsize)(self._compute_embedding)
        
    def _compute_embedding(self, query: str) -> np.ndarray:
        """
        Método placeholder para ser sobrescrito.
        O decorador @lru_cache será aplicado na subclasse.
        """
        raise NotImplementedError("Subclasses devem implementar _compute_embedding")
    
    async def get_embedding(self, query: str, compute_func) -> np.ndarray:
        """
        Obtém embedding com prioridade para cache externo.
        
        Args:
            query: Texto da query
            compute_func: Função para computar embedding se não estiver em cache
        """
        # 1. Verifica cache externo
        if self.external_cache:
            cached = self.external_cache.get(query)
            if cached is not None:
                return cached
        
        # 2. Verifica cache interno / computa
        embedding = await asyncio.to_thread(compute_func, query)
        
        # 3. Salva no cache externo
        if self.external_cache:
            self.external_cache.set(query, embedding)
        
        return embedding
    
    def get_stats(self) -> Dict:
        """Retorna estatísticas dos caches."""
        stats = {
            "internal_hits": 0,
            "internal_misses": 0,
            "internal_currsize": 0,
            "external_cache_size": 0
        }
        
        if hasattr(self._cache_func, 'cache_info'):
            cache_info = self._cache_func.cache_info()
            stats.update({
                "internal_hits": cache_info.hits,
                "internal_misses": cache_info.misses,
                "internal_currsize": cache_info.currsize
            })
        
        if self.external_cache:
            external_stats = self.external_cache.stats()
            stats["external_cache_size"] = external_stats.get('size', 0)
        
        return stats
    
    def clear(self) -> None:
        """Limpa o cache interno."""
        if hasattr(self._cache_func, 'cache_clear'):
            self._cache_func.cache_clear()