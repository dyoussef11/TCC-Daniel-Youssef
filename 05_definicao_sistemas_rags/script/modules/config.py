"""
config.py
Configurações centralizadas do RAG Temporal.
"""

from datetime import datetime
from pathlib import Path
from typing import Union

from core.paths import VALIDACAO_CONFIG

class RAGConfig:
    """Configurações do RAG Engine."""
    
    def __init__(self, variant_name: str = "V9_HYBRID_AUDITOR"):
        # Modelo e dimensões
        self.embedding_dimension: int = 1024
        self.current_model: str = "phi3.5:latest"
        self.embedding_model: str = "bge-m3:latest"
        
        # Busca
        self.search_top_k: int = 20
        self.similarity_threshold: float = 1.2
        self.max_context_chars: int = 2000
        
        # Temporalidade adaptativa
        self.yearly_penalty_rate: float = 0.03
        self.old_doc_threshold_years: float = 2.0
        self.recency_threshold: int = 3
        self.low_coverage_penalty_multiplier: float = 0.3
        self.fallback_semantic_threshold: float = 1.15
        self.max_fallback_docs: int = 3
        self.max_results_returned: int = 8
        
        # Expansão de query
        self.use_expansion: bool = True
        self.max_synonym_terms: int = 5
        
        # Modelo
        self.temperature: float = 0.0
        self.top_p: float = 0.9
        
        # Variante e prompts
        self.variant_name: str = variant_name
        self.prompts_dir: Path = VALIDACAO_CONFIG
        # self.prompts_dir: Path = Path(__file__).parent.parent / 'core' / 'paths'
        
        # Logging
        self.verbose: bool = True

    def log(self, message: str) -> None:
        """Log condicional baseado em verbose."""
        if self.verbose:
            print(message)