import hashlib, pickle, json, asyncio
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import numpy as np

from core.paths import AVALIACAO_DATA, VETORIZATION_DATA


@dataclass
class EvalConfig:
    """Configurações extraídas do seu eval_config.py"""
    # base_path: Path = Path(VETORIZATION_DATA / "base_conhecimento_multilingueV7.json")
    base_path: Path = Path(VETORIZATION_DATA / "base_conhecimento_multilingueV8.json")
    cache_dir: Path = Path(AVALIACAO_DATA / "cache")
    output_dir: Path = Path(AVALIACAO_DATA / "resultadosV2")
    model_name: str = "phi3.5:latest"
    timestamp: str = datetime.now().strftime("%Y%m%d_%H%M")

class EmbeddingCache:
    """Versão simplificada do seu embedding_cache.py"""
    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache = {}

    def get(self, query: str):
        key = hashlib.md5(query.encode()).hexdigest()
        path = self.cache_dir / f"{key}.pkl"
        if path.exists():
            with open(path, 'rb') as f: return pickle.load(f)
        return None

    def set(self, query: str, embedding: np.ndarray):
        key = hashlib.md5(query.encode()).hexdigest()
        with open(self.cache_dir / f"{key}.pkl", 'wb') as f:
            pickle.dump(embedding, f)

class BehavioralAnalyzer:
    """Versão compacta do seu behavioral_analyzer.py"""
    def analyze(self, test_case: Dict, resp_v1: str, resp_v9: str) -> Tuple[bool, bool]:
        forbidden = test_case.get("forbidden_patterns", [])
        required = test_case.get("required_patterns", [])
        
        def check(text: str):
            text = text.lower()
            has_forbidden = any(p.lower() in text for p in forbidden)
            has_required = all(p.lower() in text for p in required)
            return has_required and not has_forbidden

        return check(resp_v1), check(resp_v9)