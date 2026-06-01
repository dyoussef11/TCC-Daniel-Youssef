"""
Módulos internos do RAG Temporal
Organizados por responsabilidade:
- core: Núcleo do sistema
- temporal: Componentes temporais
- query: Processamento de queries
- prompts: Gerenciamento de prompts
- audit: Auditoria e validação
"""

# Core
from modules.config import RAGConfig
from modules.cache_manager import CacheManager
from modules.embeddings import EmbeddingManager
from modules.faiss_manager import FAISSManager
from modules.data_loader import DataLoader
from modules.context_builder import ContextBuilder

# Temporal
from modules.temporal_scoring import TemporalScorer
from modules.fallback_search import FallbackSearcher

# Query
from modules.query_expansion import QueryExpander

# Prompts
from modules.prompt_manager import PromptManager

# Audit
from modules.auditor import ResponseAuditor

__all__ = [
    'RAGConfig',
    'CacheManager',
    'EmbeddingManager',
    'FAISSManager',
    'DataLoader',
    'ContextBuilder',
    'TemporalScorer',
    'FallbackSearcher',
    'QueryExpander',
    'PromptManager',
    'ResponseAuditor'
]