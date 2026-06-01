"""
rag_engine.py
Classe principal do RAG Temporal - versão reduzida.
"""

import gc
from pathlib import Path
from datetime import datetime
from typing import Dict, Union, Optional, List, Tuple

import numpy as np
import ollama
import asyncio

from core.paths import VALIDACAO_CONFIG

from modules.config import RAGConfig
from modules.cache_manager import CacheManager
from modules.embeddings import EmbeddingManager
from modules.data_loader import DataLoader
from modules.faiss_manager import FAISSManager
from modules.context_builder import ContextBuilder

from modules.temporal_scoring import TemporalScorer
from modules.fallback_search import FallbackSearcher
from modules.search_pipeline import SearchPipeline

from modules.query_expansion import QueryExpander

from modules.prompt_manager import PromptManager

from modules.auditor import ResponseAuditor


class SpecialistTimeAwareRAG:
    """
    Engine RAG com Auditoria Silenciosa e Normalização por Sinônimos.
    Aplica penalidade temporal adaptativa com fallback inteligente.
    """
    
    def __init__(self, json_path: Union[str, Path], 
                variant_name: str = "V9_HYBRID_AUDITOR",
                embedding_cache=None, 
                use_expansion: bool = True):
        
        # Inicializa configurações
        self.config = RAGConfig(variant_name)
        self.config.use_expansion = use_expansion
        
        print(f"--- 🧠 RAG ENGINE ATIVADA (Variante: {variant_name}) ---")
        print(f"   Temporal config: {self.config.yearly_penalty_rate*100}%/year penalty, "
            f"fallback after {self.config.old_doc_threshold_years}y")
        
        # Inicializa componentes
        self._init_components(json_path, embedding_cache)
        
        # Pipeline de busca
        self.search_pipeline = SearchPipeline(
            faiss_manager=self.faiss_manager,
            data_loader=self.data_loader,
            temporal_scorer=self.temporal_scorer,
            fallback_searcher=self.fallback_searcher,
            context_builder=self.context_builder,
            config=self.config
        )
        
        print(f"✅ Sistema inicializado com {len(self.data_loader.documents)} documentos")
    
    def _init_components(self, json_path: Union[str, Path], embedding_cache) -> None:
        """Inicializa todos os componentes do sistema."""
        
        # Gerenciador de cache
        self.cache_manager = CacheManager(external_cache=embedding_cache)
        
        # Gerenciador de embeddings
        self.embedding_manager = EmbeddingManager(
            model=self.config.embedding_model
        )
        
        # Carregamento de dados
        self.data_loader = DataLoader()
        self.data_loader.load_documents(json_path)
        
        # Gerenciador FAISS
        self.faiss_manager = FAISSManager(
            dimension=self.config.embedding_dimension
        )
        
        if self.data_loader.documents:
            self.faiss_manager.build_index(self.data_loader.documents)
        
        # Expansão de query
        hierarchical_dict_path = VALIDACAO_CONFIG / 'dictionary_synonyms_hierarchical_v4.json'
        flat_dict_path = VALIDACAO_CONFIG / 'dictionary_synonyms_flat_v9.json'

        self.query_expander = QueryExpander(
            hierarchical_path=hierarchical_dict_path,
            flat_dict_path=flat_dict_path,
            max_terms=self.config.max_synonym_terms,
            variant="temporal"
        )
        
        # Sistema de scoring temporal
        self.temporal_scorer = TemporalScorer(
            yearly_penalty_rate=self.config.yearly_penalty_rate,
            recency_threshold=self.config.recency_threshold,
            low_coverage_multiplier=self.config.low_coverage_penalty_multiplier
        )
        
        # Sistema de fallback
        self.fallback_searcher = FallbackSearcher(
            similarity_threshold=self.config.similarity_threshold,
            max_fallback_docs=self.config.max_fallback_docs,
            old_doc_threshold_years=self.config.old_doc_threshold_years
        )
        
        # Gerenciador de prompts
        self.prompt_manager = PromptManager(
            variant_name=self.config.variant_name,
            prompts_dir=self.config.prompts_dir
        )
        
        # Auditor de resposta
        self.auditor = ResponseAuditor()
        
        # Construtor de contexto
        self.context_builder = ContextBuilder(
            max_chars=self.config.max_context_chars
        )
    
    async def _get_embedding(self, query: str) -> np.ndarray:
        """Obtém embedding com cache."""
        return await self.cache_manager.get_embedding(
            query, 
            self.embedding_manager.compute_embedding
        )
    
    async def search(self, query: str, ref_date: str = "2026-03-23") -> Dict:
        """
        Executa busca RAG completa.
        O comportamento é controlado APENAS pelo prompt system.
        """
        print(f"🔍 Processando: {query[:60]}...")
        ref_dt = datetime.strptime(ref_date, "%Y-%m-%d")
        
        # 1. Expansão de query
        expanded_query = query
        if self.config.use_expansion:
            expanded_query = self.query_expander.expand_query(query)
            if expanded_query != query:
                print(f"📝 Query expandida: {expanded_query[:80]}...")
        
        # 2. Embedding
        query_vector = await self._get_embedding(expanded_query)
        
        # 3. Busca via pipeline
        final_results = await self.search_pipeline.execute(
            query_vector=query_vector,
            query=query,
            ref_dt=ref_dt,
            expanded_query=expanded_query
        )
        
        # 4. Construção de contexto
        context_str = self.context_builder.build_context(final_results)
        
        # 5. Geração de resposta
        response = await self._generate_response(context_str, query, ref_date)
        
        # 6. Extração de auditoria
        audited_response = self.auditor.extract_audit(response)
        
        # 7. Montagem do resultado
        result = self._build_result(
            audited_response, final_results, expanded_query, 
            ref_dt, []
        )
        
        self._cleanup()
        return result
    
    async def _generate_response(self, context_str: str, query: str, 
                        ref_date: str) -> str:
        """Gera resposta usando prompt do JSON."""
        
        sys_prompt = self.prompt_manager.build_system_prompt()
        
        few_shot = self.prompt_manager.get_examples_for_few_shot()
        if few_shot:
            sys_prompt += "\n" + few_shot
        
        audit_format = self.prompt_manager.get_audit_format_instructions()
        if audit_format:
            sys_prompt += "\n" + audit_format
        
        user_content = self.prompt_manager.build_user_prompt(
            context_str, query, ref_date
        )
        
        response = await asyncio.to_thread(
            ollama.chat,
            model=self.config.current_model,
            messages=[
                {'role': 'system', 'content': sys_prompt},
                {'role': 'user', 'content': user_content}
            ],
            options={
                "temperature": self.config.temperature, 
                "top_p": self.config.top_p
            },
            keep_alive=0
        )
        
        return response['message']['content']
    
    def _build_result(self, audited_response: Dict, final_results: List[Dict],
                     expanded_query: str, ref_dt: datetime,
                     scored_results: List[Dict]) -> Dict:
        """Constrói o dicionário de resultado final."""
        
        penalty_stats = self.temporal_scorer.get_penalty_stats(final_results)
        
        fallback_used = False
        if hasattr(self.fallback_searcher, 'should_activate'):
            fallback_used = self.fallback_searcher.should_activate([])
        
        return {
            "answer": audited_response["clean_answer"],
            "audit_trail": audited_response["audit_log"],
            "titles": [r['doc'].get('metadata', {}).get('title', 'Unknown') 
                      for r in final_results],
            "sources": [r['doc'].get('original_text', '') for r in final_results],
            "retrieved_metadata": [r['doc'].get('metadata', {}) for r in final_results],
            "normalized_query": expanded_query,
            "diagnostic": {
                "num_documents_retrieved": len(final_results),
                "cpu_embeddings": True,
                "cache_used": self.cache_manager.external_cache is not None,
                "fallback_used": fallback_used,
                "best_temporal_gap_years": round(final_results[0]['temporal_gap'], 2) if final_results else 0,
                "recent_docs_count": sum(1 for r in final_results if r.get('temporal_gap', 0) < 0.5),
                **penalty_stats
            }
        }
    
    def _cleanup(self) -> None:
        """Limpeza de memória."""
        gc.collect()