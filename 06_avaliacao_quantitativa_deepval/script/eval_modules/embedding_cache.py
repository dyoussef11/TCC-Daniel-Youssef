"""core/embedding_cache.py - Cache de embeddings LRU"""

import hashlib
import pickle
from pathlib import Path
from typing import Dict, Optional, Any

import numpy as np


class EmbeddingCache:
    """Cache LRU para embeddings de queries"""
    
    def __init__(self, cache_dir: Path, max_size: int = 1000):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_size = max_size
        self._cache: Dict[str, np.ndarray] = {}
        self._load_existing()
    
    def _get_key(self, query: str) -> str:
        return hashlib.md5(query.encode()).hexdigest()
    
    def _get_path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.pkl"
    
    def _load_existing(self) -> None:
        for path in self.cache_dir.glob("*.pkl"):
            if len(self._cache) >= self.max_size:
                break
            try:
                with open(path, 'rb') as f:
                    self._cache[path.stem] = pickle.load(f)
            except:
                pass
    
    def get(self, query: str) -> Optional[np.ndarray]:
        key = self._get_key(query)
        if key in self._cache:
            return self._cache[key].copy()
        return None
    
    def set(self, query: str, embedding: np.ndarray) -> None:
        key = self._get_key(query)
        
        if len(self._cache) >= self.max_size:
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
            (self.cache_dir / f"{oldest_key}.pkl").unlink(missing_ok=True)
        
        self._cache[key] = embedding.copy()
        with open(self._get_path(key), 'wb') as f:
            pickle.dump(embedding, f)
    
    def stats(self) -> Dict:
        return {
            "size": len(self._cache),
            "max_size": self.max_size,
            "directory": str(self.cache_dir)
        }