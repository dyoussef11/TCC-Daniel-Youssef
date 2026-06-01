# RAG_Temporal_V8_CPUMode_CacheReady.py
"""
RAG Temporal com penalidade temporal adaptativa e fallback inteligente.
Preserva informações semanticamente relevantes mesmo quando documentos são antigos.
"""

import json
import faiss
import ijson
import numpy as np
import ollama
import asyncio
import re
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, Union, Optional, List, Tuple
import gc
from functools import lru_cache

from core.paths import VALIDACAO_CONFIG, VETORIZATION_DATA


class SpecialistTimeAwareRAG:
    """
    Engine RAG com Auditoria Silenciosa e Normalização por Sinônimos.
    Aplica penalidade temporal adaptativa com fallback inteligente.
    
    Características:
    - Penalidade temporal suave (3% ao ano)
    - Redução automática de penalidade para domínios com pouca cobertura
    - Fallback sem penalidade quando documentos são muito antigos
    - Merge inteligente entre resultados primários e fallback
    """
    
    def __init__(self, json_path: Union[str, Path], variant_name: str = "V9_HYBRID_AUDITOR", 
            embedding_cache=None, use_expansion: bool = True) -> None:
        self.dimension: int = 1024
        self.caminho_prompts: Path = VALIDACAO_CONFIG / 'prompt_rag_temporal_hybrid_V9.json'
        self.variant_name = variant_name
        self.use_expansion = use_expansion

        # Configurações do modelo
        self.current_model = "phi3.5:latest"
        self.temperature = 0.0
        self.search_top_k = 20  # Aumentado para ter margem para fallback
        self.similarity_threshold = 1.2
        
        # Configurações de temporalidade adaptativa
        self.yearly_penalty_rate = 0.03  # 3% ao ano (mais suave que 4%)
        self.old_doc_threshold_years = 2.0  # Ativa fallback após 2 anos
        self.recency_threshold = 3  # Documentos recentes necessários para penalidade cheia
        self.low_coverage_penalty_multiplier = 0.3  # 30% da penalidade quando cobertura é baixa
        self.fallback_semantic_threshold = 1.15  # Score máximo para aceitar fallback
        self.max_fallback_docs = 3  # Máximo de documentos do fallback a adicionar
        
        # Cache externo
        self.external_cache = embedding_cache
        
        print(f"--- 🧠 RAG ENGINE ATIVADA (Variante: {variant_name}) ---")
        print(f"   Temporal config: {self.yearly_penalty_rate*100}%/year penalty, fallback after {self.old_doc_threshold_years}y")
        
        # Inicializa cliente CPU para embeddings
        self._init_cpu_embedding_client()
        print(f"✅ BGE-M3 configurado para rodar na CPU")
        
        if self.external_cache:
            cache_stats = self.external_cache.stats()
            print(f"✅ Cache externo conectado ({cache_stats['size']} embeddings pré-carregados)")
        
        # Carregar base e dicionário de sinônimos
        self.base_dados = []
        self._load_base_dados(json_path)
        
        # Carregar dicionário de expansão de SKU
        self.synonym_dict = self._load_synonym_dict()

        # Inicializar Index FAISS
        self.index = faiss.IndexFlatL2(self.dimension)
        if self.base_dados:
            vectors = np.array([d['vector'] for d in self.base_dados]).astype('float32')
            self.index.add(vectors)
            print(f"✅ Index FAISS criado com {self.index.ntotal} vetores")

        # Carregar Prompts
        self._load_prompts()

    def _load_base_dados(self, json_path: Union[str, Path]) -> None:
        """Carrega base de dados com tratamento de erro."""
        try:
            with open(json_path, 'rb') as f:
                for item in ijson.items(f, 'item'):
                    self.base_dados.append(item)
            print(f"✅ Base carregada: {len(self.base_dados)} documentos.")
        except Exception as e:
            print(f"❌ Erro ao carregar base: {e}")
            self.base_dados = []

    def _load_synonym_dict(self) -> Dict[str, List[str]]:
        """Carrega dicionário de sinônimos para expansão de SKU."""
        synonym_path = VALIDACAO_CONFIG / 'dictionary_synonyms_refinedV3.json'
        try:
            with open(synonym_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"⚠️ Dicionário de sinônimos não encontrado: {synonym_path}")
            return {}
        except Exception as e:
            print(f"⚠️ Erro ao carregar sinônimos: {e}")
            return {}

    def _load_prompts(self) -> None:
        """Carrega prompts do sistema."""
        try:
            with open(self.caminho_prompts, 'r', encoding='utf-8') as f:
                self.prompts = json.load(f)
        except FileNotFoundError:
            print(f"⚠️ Arquivo de prompt não encontrado: {self.caminho_prompts}")
            self.prompts = {
                self.variant_name: {
                    "system_role": "You are a technical specialist assistant.",
                    "constraints": [
                        "Answer only based on the provided context",
                        "Be concise and technical"
                    ]
                }
            }

    def _init_cpu_embedding_client(self):
        """Inicializa cliente Ollama que força o BGE-M3 a usar apenas CPU."""
        original_cuda = os.environ.get('CUDA_VISIBLE_DEVICES')
        original_num_gpu = os.environ.get('OLLAMA_NUM_GPU')
        
        os.environ['CUDA_VISIBLE_DEVICES'] = '-1'
        os.environ['OLLAMA_NUM_GPU'] = '0'
        
        from ollama import Client
        self._cpu_ollama_client = Client(host='http://localhost:11434')
        
        if original_cuda is not None:
            os.environ['CUDA_VISIBLE_DEVICES'] = original_cuda
        else:
            os.environ.pop('CUDA_VISIBLE_DEVICES', None)
        
        if original_num_gpu is not None:
            os.environ['OLLAMA_NUM_GPU'] = original_num_gpu
        else:
            os.environ.pop('OLLAMA_NUM_GPU', None)
        
        try:
            test_result = self._cpu_ollama_client.embeddings(model="bge-m3:latest", prompt="test")
            if 'embedding' in test_result:
                print(f"✅ Conexão com BGE-M3 (CPU) estabelecida - dimensão: {len(test_result['embedding'])}")
        except Exception as e:
            print(f"⚠️ BGE-M3 pode não estar disponível: {e}")
    
    @lru_cache(maxsize=200)
    def _get_embedding_cached(self, query: str) -> np.ndarray:
        """Obtém embedding com cache LRU interno."""
        result = self._cpu_ollama_client.embeddings(
            model="bge-m3:latest", 
            prompt=query
        )
        return np.array(result['embedding'], dtype=np.float32)
    
    async def _get_embedding(self, query: str) -> np.ndarray:
        """
        Obtém embedding de forma assíncrona.
        PRIORIZA O CACHE EXTERNO!
        """
        if self.external_cache:
            cached = self.external_cache.get(query)
            if cached is not None:
                return cached
        
        embedding = await asyncio.to_thread(self._get_embedding_cached, query)
        
        if self.external_cache:
            self.external_cache.set(query, embedding)
        
        return embedding
    
    async def get_embedding_public(self, query: str) -> np.ndarray:
        """Método público para acesso externo."""
        return await self._get_embedding(query)
    
    def get_cache_stats(self) -> Dict:
        """Retorna estatísticas do cache interno."""
        cache_info = self._get_embedding_cached.cache_info()
        return {
            "internal_hits": cache_info.hits,
            "internal_misses": cache_info.misses,
            "internal_currsize": cache_info.currsize,
            "external_cache_size": self.external_cache.stats()['size'] if self.external_cache else 0
        }

    def _expand_query_with_synonyms(self, query: str, max_terms: int = 5) -> str:
        """
        Expande a query usando o dicionário flat hierárquico.
        """
        if not self.use_expansion:  # ← se desligado, retorna query original
            return query
    
        if not hasattr(self, '_flat_dict'):
            self._flat_dict = self._load_flat_dictionary()
        
        if not self._flat_dict:
            return query
        
        query_lower = query.lower()
        
        # Encontra a melhor chave correspondente
        best_key = None
        best_match_len = 0
        
        for key in self._flat_dict.keys():
            if key in query_lower:
                if len(key) > best_match_len:
                    best_match_len = len(key)
                    best_key = key
        
        if not best_key:
            return query
        
        synonyms = self._flat_dict[best_key]
        
        # Filtra termos
        new_terms = []
        for term in synonyms:
            term_lower = term.lower()
            if term_lower not in query_lower and len(term) >= 3:
                if term not in ['gaming', 'laptop', 'notebook', 'edition']:
                    new_terms.append(term)
        
        if not new_terms:
            return query
        
        new_terms = new_terms[:max_terms]
        return f"{query} {' '.join(new_terms)}"
    
    def _load_flat_dictionary(self) -> Dict:
        """Carrega o dicionário flat hierárquico."""
        # Tenta as duas versões
        dict_path = VALIDACAO_CONFIG / 'dictionary_synonyms_flat_v3.json'
        if not dict_path.exists():
            dict_path = VALIDACAO_CONFIG / 'dictionary_synonyms_flat.json'
        
        try:
            with open(dict_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"⚠️ Dicionário flat não encontrado: {dict_path}")
            return {}

    def _count_recent_docs_in_domain(self, doc: Dict, ref_dt: datetime) -> int:
        """
        Conta quantos documentos do mesmo modelo/domínio são mais recentes.
        Usado para ajustar penalidade: se o domínio é mal coberto, penaliza menos.
        """
        model_name = doc.get('metadata', {}).get('model', '')
        if not model_name:
            return self.recency_threshold  # Padrão neutro
        
        count = 0
        for other in self.base_dados:
            other_model = other.get('metadata', {}).get('model', '')
            if other_model == model_name:
                other_date = other.get('date_iso', '2024-01-01')[:10]
                try:
                    other_dt = datetime.strptime(other_date, "%Y-%m-%d")
                    if other_dt > ref_dt:
                        count += 1
                except:
                    pass
        
        return min(count, self.recency_threshold * 2)

    async def _semantic_only_search(self, query: str, ref_dt: datetime, query_vector: np.ndarray, 
                                     existing_ids: set) -> List[Dict]:
        """
        Busca adicional IGNORANDO penalidade temporal.
        Usada como fallback quando não há documentos recentes.
        """
        # Busca mais ampla para fallback
        distances, indices = self.index.search(query_vector, k=self.search_top_k + 5)
        
        fallback_results = []
        
        for i, idx in enumerate(indices[0]):
            if idx == -1:
                continue
            
            doc = self.base_dados[idx]
            doc_id = doc.get('id', idx)
            
            # Evita duplicatas
            if doc_id in existing_ids:
                continue
            
            semantic_score = distances[0][i]
            
            # Aceita documentos com score ligeiramente pior que o threshold
            if semantic_score < self.similarity_threshold * 1.1:
                doc_date = doc.get('date_iso', '2024-01-01')[:10]
                try:
                    doc_dt = datetime.strptime(doc_date, "%Y-%m-%d")
                    temporal_gap = (ref_dt - doc_dt).days / 365.25
                except:
                    temporal_gap = 0
                
                fallback_results.append({
                    'doc': doc,
                    'semantic_score': semantic_score,
                    'final_score': semantic_score * 1.05,  # Penalidade simbólica mínima
                    'temporal_gap': temporal_gap,
                    'temporal_status': "fallback_no_penalty",
                    'date': doc_date
                })
        
        # Ordena por score semântico
        fallback_results.sort(key=lambda x: x['semantic_score'])
        
        return fallback_results[:self.max_fallback_docs]

    def _merge_search_results(self, primary: List[Dict], fallback: List[Dict]) -> List[Dict]:
        """
        Merge inteligente de resultados primários (com penalidade) e fallback (sem penalidade).
        Preserva os melhores de cada tipo.
        """
        if not fallback:
            return primary[:8]
        
        if not primary:
            return fallback[:8]
        
        # IDs já presentes
        existing_ids = {r['doc'].get('id', i) for i, r in enumerate(primary)}
        
        merged = primary[:4].copy()  # Mantém os top 4 do primário
        
        # Adiciona fallback que não estão duplicados
        for fb in fallback:
            if len(merged) >= 8:
                break
            fb_id = fb['doc'].get('id', hash(fb['date']))
            if fb_id not in existing_ids:
                merged.append(fb)
                existing_ids.add(fb_id)
        
        # Reordena por final_score
        merged.sort(key=lambda x: x['final_score'])
        
        return merged[:8]

    def _extract_sku_from_query(self, query: str) -> Optional[str]:
        """
        Extrai o SKU/modelo da query usando padrões conhecidos.
        Ex: "Acer Nitro 5 AN515-56" -> "AN515-56"
        """
        # Padrões comuns de SKU
        patterns = [
            r'([A-Z]{2,4}-\d{3,4}[A-Z]*)',  # AN515-56, G513QY
            r'([A-Z]{1,2}\d{3,4}[A-Z]*)',    # G513, XPS15
            r'(\d{4}[A-Z]{2,3})',             # 15ACH6
        ]
        
        for pattern in patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                return match.group(1).upper()
        
        return None

    def _extrair_auditoria(self, full_response: str) -> Dict[str, str]:
        """Extrai auditoria e resposta limpa do output do modelo."""
        audit_match = re.search(r"AUDIT:(.*?)(?=ANSWER:|$)", full_response, re.DOTALL | re.IGNORECASE)
        answer_match = re.search(r"ANSWER:(.*)", full_response, re.DOTALL | re.IGNORECASE)
        
        return {
            "audit_log": audit_match.group(1).strip() if audit_match else "No audit log provided.",
            "clean_answer": answer_match.group(1).strip() if answer_match else full_response.strip()
        }

    async def search(self, query: str, ref_date: str = "2026-03-23"):
        """
        Executa busca RAG com penalidade temporal adaptativa e fallback inteligente.
        
        Args:
            query: Pergunta do usuário
            ref_date: Data de referência para cálculo temporal (formato YYYY-MM-DD)
        
        Returns:
            Dict com resposta, trilha de auditoria, fontes e metadados
        """
        ref_dt = datetime.strptime(ref_date, "%Y-%m-%d")
        
        # 1. Expande query com sinônimos
        expanded_query = self._expand_query_with_synonyms(query)
        
        # 2. Embedding (USA CACHE!)
        query_vector_1d = await self._get_embedding(expanded_query)
        query_vector = query_vector_1d.reshape(1, -1)

        # 3. Busca no FAISS (primeira passagem)
        distances, indices = self.index.search(query_vector, k=self.search_top_k)
        
        scored_results = []
        domain_penalty_adjustments = {}
        
        for i, idx in enumerate(indices[0]):
            if idx == -1:
                continue
            
            doc = self.base_dados[idx]
            doc_id = doc.get('id', idx)
            semantic_score = distances[0][i]
            
            # Pula documentos semanticamente muito ruins
            if semantic_score > self.similarity_threshold * 1.3:
                continue

            # Extrai data do documento
            doc_date_str = doc.get('date_iso', '2024-01-01')[:10]
            try:
                doc_dt = datetime.strptime(doc_date_str, "%Y-%m-%d")
            except:
                doc_dt = datetime(2024, 1, 1)
            
            # Calcula GAP temporal (em anos)
            temporal_gap = (ref_dt - doc_dt).days / 365.25
            
            # ============================================================
            # DUAL-MODE SCORING COM FALLBACK INTELIGENTE
            # ============================================================
            
            if temporal_gap <= 0:
                # Documento é do futuro ou mesma data
                final_score = semantic_score
                temporal_status = "future_or_current"
                penalty_applied = 0
            else:
                # Documento é mais antigo que a referência
                
                # Calcula ajuste por domínio (cacheado)
                if doc_id not in domain_penalty_adjustments:
                    recent_count = self._count_recent_docs_in_domain(doc, ref_dt)
                    # Quanto mais documentos recentes no domínio, MAIOR a penalidade
                    # Domínios com pouca cobertura sofrem penalidade reduzida
                    recency_penalty_multiplier = max(
                        self.low_coverage_penalty_multiplier,
                        min(1.0, recent_count / self.recency_threshold)
                    )
                    domain_penalty_adjustments[doc_id] = recency_penalty_multiplier
                
                recency_multiplier = domain_penalty_adjustments[doc_id]
                
                # Penalidade base (suave)
                base_penalty = 1.0 + (temporal_gap * self.yearly_penalty_rate)
                
                # Penalidade final com ajuste por escassez
                final_penalty = 1.0 + (base_penalty - 1.0) * recency_multiplier
                final_score = semantic_score * final_penalty
                
                temporal_status = f"old_gap_{temporal_gap:.1f}y_penalty_{final_penalty:.2f}"
                penalty_applied = final_penalty - 1.0
            
            scored_results.append({
                'doc': doc,
                'semantic_score': semantic_score,
                'final_score': final_score,
                'temporal_gap': temporal_gap,
                'temporal_status': temporal_status,
                'penalty_applied': penalty_applied,
                'date': doc_date_str
            })
        
        # Ordena por final_score (menor = melhor)
        scored_results.sort(key=lambda x: x['final_score'])
        
        # ============================================================
        # FALLBACK: Quando não há documentos recentes suficientes
        # ============================================================
        
        # Verifica se o melhor documento tem gap temporal significativo
        best_doc_age = scored_results[0]['temporal_gap'] if scored_results else 999
        
        # Verifica quantos documentos recentes (gap < 0.5 anos) temos
        recent_docs_count = sum(1 for r in scored_results if r['temporal_gap'] < 0.5)
        
        # Ativa fallback se:
        # 1. Melhor documento é muito antigo (> threshold) E
        # 2. Poucos documentos recentes (< 2)
        if best_doc_age > self.old_doc_threshold_years and recent_docs_count < 2:
            existing_ids = {r['doc'].get('id', i) for i, r in enumerate(scored_results)}
            
            fallback_results = await self._semantic_only_search(
                expanded_query, ref_dt, query_vector, existing_ids
            )
            
            if fallback_results:
                # Merge dos resultados
                scored_results = self._merge_search_results(scored_results, fallback_results)
                
                # Marca no diagnóstico que usou fallback
                fallback_used = True
            else:
                fallback_used = False
        else:
            fallback_used = False
            # Se não precisou de fallback, apenas limita o número
            scored_results = scored_results[:8]
        
        # Se mesmo assim não tem resultados, faz busca mais ampla
        if len(scored_results) == 0:
            distances, indices = self.index.search(query_vector, k=5)
            for i, idx in enumerate(indices[0]):
                if idx != -1:
                    doc = self.base_dados[idx]
                    doc_date_str = doc.get('date_iso', '2024-01-01')[:10]
                    scored_results.append({
                        'doc': doc,
                        'semantic_score': distances[0][i],
                        'final_score': distances[0][i],
                        'temporal_gap': 0,
                        'temporal_status': "emergency_fallback",
                        'penalty_applied': 0,
                        'date': doc_date_str
                    })

        # ============================================================
        # CONSTRUÇÃO DO CONTEXTO E RESPOSTA
        # ============================================================
        
        # Constroi contexto rico para o LLM
        context_parts = []
        for i, r in enumerate(scored_results):
            meta = r['doc'].get('metadata', {})
            titulo = meta.get('title') or meta.get('model') or f"Source_{i}"
            text = r['doc']['original_text']
            if len(text) > 2000:
                text = text[:2000] + "..."
            
            # Adiciona informação de antiguidade no contexto
            age_indicator = ""
            if r['temporal_gap'] > 1.0:
                age_indicator = f" [NOTE: This document is {r['temporal_gap']:.1f} years old]"
            
            context_parts.append(
                f"[[ID_{i} | DATE: {r['date']}{age_indicator} | TITLE: {titulo}]]\n{text}"
            )
        context_str = "\n\n".join(context_parts)

        # Prepara prompt
        variant = self.prompts.get(self.variant_name, {})
        constraints_text = "\n".join(f"- {c}" for c in variant.get('constraints', []))
        
        sys_prompt = f"""{variant.get('system_role', 'You are a technical specialist assistant.')}

CRITICAL RULES:
{constraints_text if constraints_text else '- Answer only based on the provided context\n- Be concise and technical'}

TEMPORAL AWARENESS:
- Some documents may be older than the reference date. This is noted in the context.
- If the only available information is from older documents, use it but note the age.
- Do not hallucinate or infer specifications not present in the context.

MANDATORY OUTPUT FORMAT:
AUDIT: [List source IDs used with dates. Note if any documents were older than reference date]
ANSWER: [Clean technical response]"""

        user_content = f"""CONTEXT:
{context_str}

QUERY: {query}

REFERENCE DATE: {ref_date}

Generate your response following the exact format specified."""

        # Gera resposta
        response = await asyncio.to_thread(
            ollama.chat,
            model=self.current_model,
            messages=[
                {'role': 'system', 'content': sys_prompt},
                {'role': 'user', 'content': user_content}
            ],
            options={"temperature": self.temperature, "top_p": 0.9},
            keep_alive=0
        )
        
        full_text = response['message']['content']
        extracted = self._extrair_auditoria(full_text)

        # Adiciona diagnóstico temporal ao audit_trail
        temporal_diagnostic = f" [Temporal: best_gap={best_doc_age:.1f}y, fallback_used={fallback_used}]"
        audit_with_diagnostic = extracted["audit_log"] + temporal_diagnostic

        return {
            "answer": extracted["clean_answer"],
            "audit_trail": audit_with_diagnostic,
            "titles": [r['doc'].get('metadata', {}).get('title', 'Unknown') for r in scored_results],
            "sources": [r['doc']['original_text'] for r in scored_results],
            "retrieved_metadata": [r['doc'].get('metadata', {}) for r in scored_results],
            "normalized_query": expanded_query,
            "diagnostic": {
                "num_documents_retrieved": len(scored_results),
                "cpu_embeddings": True,
                "cache_used": self.external_cache is not None,
                "fallback_used": fallback_used,
                "best_temporal_gap_years": round(best_doc_age, 2),
                "recent_docs_count": recent_docs_count,
                "avg_penalty_applied": round(sum(r.get('penalty_applied', 0) for r in scored_results) / max(len(scored_results), 1), 4)
            }
        }