"""
main_engine.py
Classe principal do RAG Temporal - orquestra todos os componentes.
"""

import json
import numpy as np
import ollama
import asyncio
import re
import gc
from pathlib import Path
from datetime import datetime
from typing import Dict, Union, Optional, List, Tuple

from core.paths import VALIDACAO_CONFIG

from modules.core.config import RAGConfig
from modules.core.cache_manager import CacheManager
from modules.core.embeddings import EmbeddingManager
from modules.core.data_loader import DataLoader
from modules.core.faiss_manager import FAISSManager
from modules.core.context_builder import ContextBuilder

from modules.temporal.temporal_scoring import TemporalScorer
from modules.temporal.fallback_search import FallbackSearcher

from modules.query.query_expansion import QueryExpander

from modules.prompts.prompt_manager import PromptManager

from modules.audit.auditor import ResponseAuditor


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
        flat_dict_path = VALIDACAO_CONFIG / 'dictionary_synonyms_flat_v3.json'
        self.query_expander = QueryExpander(
            flat_dict_path=flat_dict_path,
            max_terms=self.config.max_synonym_terms
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
        """
        Obtém embedding com cache.
        """
        return await self.cache_manager.get_embedding(
            query, 
            self.embedding_manager.compute_embedding
        )
    
    # No RAG_Temporal_V9.py - modifique o método search

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
        
        # 3. Busca FAISS
        search_results = self.faiss_manager.search(
            query_vector, 
            k=self.config.search_top_k
        )
        
        # 4. Scoring temporal
        scored_results = self._apply_temporal_scoring(
            search_results, ref_dt, query_vector
        )
        
        # 5. Fallback se necessário
        final_results = await self._apply_fallback_if_needed(
            scored_results, query_vector, ref_dt
        )
        
        # 6. Construção de contexto
        context_str = self.context_builder.build_context(final_results)
        
        # 7. Geração de resposta (O PROMPT FAZ TUDO!)
        response = await self._generate_response(context_str, query, ref_date)
        
        # 8. Extração de auditoria
        audited_response = self.auditor.extract_audit(response)
        
        # 9. Montagem do resultado
        result = self._build_result(
            audited_response, final_results, expanded_query, 
            ref_dt, scored_results
        )
        
        self._cleanup()
        return result

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
    
    # main_engine.py - _generate_response()
    async def _generate_response(self, context_str: str, query: str, 
                        ref_date: str) -> str:
    
        # ✅ AGORA usa o prompt_template do JSON
        sys_prompt = self.prompt_manager.build_system_prompt()
        
        # ✅ Adiciona exemplos few-shot se disponíveis
        few_shot = self.prompt_manager.get_examples_for_few_shot()
        if few_shot:
            sys_prompt += "\n" + few_shot
        
        # ✅ Adiciona instruções de formato de auditoria
        audit_format = self.prompt_manager.get_audit_format_instructions()
        if audit_format:
            sys_prompt += "\n" + audit_format
        
        # ✅ Usa o template do JSON para user prompt
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
                "fallback_used": self.fallback_searcher.should_activate(scored_results),
                "best_temporal_gap_years": round(final_results[0]['temporal_gap'], 2) if final_results else 0,
                "recent_docs_count": sum(1 for r in final_results if r.get('temporal_gap', 0) < 0.5),
                **penalty_stats
            }
        }
    
    
    
    def _cleanup(self) -> None:
        """Limpeza de memória."""
        gc.collect()