"""config/eval_config.py - Configurações centralizadas"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict

from core.paths import VETORIZATION_DATA, AVALIACAO_DATA


@dataclass
class EvalConfig:
    """Configuração centralizada para avaliação comparativa"""
    
    # Dados
    # base_path: Path = VETORIZATION_DATA / 'base_conhecimento_multilingueV7.json'
    # base_path: Path = VETORIZATION_DATA / 'base_conhecimento_multilingueV7.json'
    #base_path: Path = VETORIZATION_DATA / 'base_conhecimento_multilingueV8.json'
    base_path: Path = VETORIZATION_DATA / 'base_vetorizada' / 'base_conhecimento_multilingueV9.json'
    evaluator_model: str = "qwen3:4b-instruct"
    
    # Cache
    cache_dir: Path = AVALIACAO_DATA / "cache"
    embedding_cache_size: int = 1000
    
    # RAGs
    vanilla_use_expansion: bool = False  # V1 não expande
    temporal_use_expansion: bool = True  # V9 expande
    # temporal_variant: str = "V9_HYBRID_AUDITOR"
    temporal_variant: str = "V9_HYBRID_MIXED_AUDITOR"
    
    # Modelo
    model_name: str = "phi3.5:latest"
    temperature: float = 0.0
    top_p: float = 0.9
    search_top_k: int = 20
    
    # Métricas
    concurrent_metrics: int = 3

    metric_thresholds: Dict[str, float] = field(default_factory=lambda: {
        "C_Precision": 0.8,
        "C_Relevancia": 0.8,
        "C_Recall": 0.8,
        "Faithfulness": 0.9,
        "Answer_Rel": 0.8
    })
    
    @property
    def timestamp(self) -> str:
        return datetime.now().strftime("%Y%m%d_%H%M")
    
    @property
    def output_dir(self) -> Path:
        dir_path = AVALIACAO_DATA / "resultados"
        dir_path.mkdir(parents=True, exist_ok=True)
        return dir_path