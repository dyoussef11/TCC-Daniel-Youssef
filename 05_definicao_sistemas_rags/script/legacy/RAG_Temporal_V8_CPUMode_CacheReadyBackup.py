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
from typing import Dict, Union, Optional
import gc
from functools import lru_cache

from core.paths import VALIDACAO_CONFIG, VETORIZATION_DATA


class SpecialistTimeAwareRAG:
    """
    Engine RAG com Auditoria Silenciosa e Normalização por Sinônimos.
    Aplica penalidade temporal e expansão de SKU para maior precisão técnica.
    
    MODIFICADO: BGE-M3 forçado a rodar na CPU, com suporte a cache externo.
    """
    
    def __init__(self, json_path: Union[str, Path], variant_name: str = "V9_HYBRID_AUDITOR", embedding_cache=None) -> None:
    # def __init__(self, json_path: Union[str, Path], variant_name: str = "V8_HYBRID_AUDITOR", embedding_cache=None) -> None:
        self.dimension: int = 1024
        self.caminho_prompts: Path = VALIDACAO_CONFIG / 'prompt_rag_temporal_hybrid_V8Backup.json'
        self.caminho_prompts: Path = VALIDACAO_CONFIG / 'prompt_rag_temporal_hybrid_V9.json'
        self.variant_name = variant_name

        # No seu RAG_Temporal_V8_CPUMode_CacheReady.py
        self.current_model = "phi3.5:latest"  # ← o melhor!
        self.temperature = 0.0  # ← temperatura zero!
        self.search_top_k = 10  # ← mais rápido, mesmo resultado que 10
        self.similarity_threshold = 1.2  # ← tanto faz
        
        # Cache externo
        self.external_cache = embedding_cache
        
        print(f"--- 🧠 RAG ENGINE ATIVADA (Variante: {variant_name}) ---")
        
        # Inicializa cliente CPU para embeddings
        self._init_cpu_embedding_client()
        print(f"✅ BGE-M3 configurado para rodar na CPU")
        
        if self.external_cache:
            cache_stats = self.external_cache.stats()
            print(f"✅ Cache externo conectado ({cache_stats['size']} embeddings pré-carregados)")
        
        # Carregar base
        self.base_dados = []
        try:
            with open(json_path, 'rb') as f:
                for item in ijson.items(f, 'item'):
                    self.base_dados.append(item)
            print(f"✅ Base carregada: {len(self.base_dados)} documentos.")
        except Exception as e:
            print(f"❌ Erro ao carregar base: {e}")
            self.base_dados = []

        # Inicializar Index FAISS
        self.index = faiss.IndexFlatL2(self.dimension)
        if self.base_dados:
            vectors = np.array([d['vector'] for d in self.base_dados]).astype('float32')
            self.index.add(vectors)
            print(f"✅ Index FAISS criado com {self.index.ntotal} vetores")

        # Carregar Prompts
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

    def _extrair_auditoria(self, full_response: str) -> Dict[str, str]:
        audit_match = re.search(r"AUDIT:(.*?)(?=ANSWER:|$)", full_response, re.DOTALL | re.IGNORECASE)
        answer_match = re.search(r"ANSWER:(.*)", full_response, re.DOTALL | re.IGNORECASE)
        
        return {
            "audit_log": audit_match.group(1).strip() if audit_match else "No audit log provided.",
            "clean_answer": answer_match.group(1).strip() if answer_match else full_response.strip()
        }

    async def search(self, query: str, ref_date: str = "2026-03-23"):
        """Executa busca RAG."""
        ref_dt = datetime.strptime(ref_date, "%Y-%m-%d")
        
        # 1. Embedding (USA CACHE!)
        query_vector_1d = await self._get_embedding(query)
        query_vector = query_vector_1d.reshape(1, -1)

        # 2. Busca no FAISS
        distances, indices = self.index.search(query_vector, k=self.search_top_k)
        
        scored_results = []
        for i, idx in enumerate(indices[0]):
            if idx == -1: 
                continue
            
            doc = self.base_dados[idx]
            dist_score = distances[0][i]
            
            if dist_score > self.similarity_threshold:
                continue

            doc_date_str = doc.get('date_iso', '2024-01-01')[:10]
            doc_dt = datetime.strptime(doc_date_str, "%Y-%m-%d")
            diff_years = max(0, (ref_dt - doc_dt).days / 365.25)
            
            time_penalty = 1.0 + (diff_years * 0.04)
            final_score = dist_score * time_penalty
            
            scored_results.append({
                'doc': doc, 
                'score': final_score,
                'date': doc_date_str
            })

        scored_results = sorted(scored_results, key=lambda x: x['score'])[:10]
        
        if len(scored_results) == 0:
            distances, indices = self.index.search(query_vector, k=5)
            for i, idx in enumerate(indices[0]):
                if idx != -1:
                    doc = self.base_dados[idx]
                    doc_date_str = doc.get('date_iso', '2024-01-01')[:10]
                    scored_results.append({
                        'doc': doc,
                        'score': distances[0][i],
                        'date': doc_date_str
                    })

        # Contexto
        context_parts = []
        for i, r in enumerate(scored_results):
            meta = r['doc'].get('metadata', {})
            titulo = meta.get('title') or meta.get('model') or f"Source_{i}"
            text = r['doc']['original_text']
            if len(text) > 2000:
                text = text[:2000] + "..."
            
            context_parts.append(
                f"[[ID_{i} | DATE: {r['date']} | TITLE: {titulo}]]\n{text}"
            )
        context_str = "\n\n".join(context_parts)

        # Prompt
        variant = self.prompts.get(self.variant_name, {})
        constraints_text = "\n".join(f"- {c}" for c in variant.get('constraints', []))
        
        sys_prompt = f"""{variant.get('system_role', 'You are a technical specialist assistant.')}

CRITICAL RULES:
{constraints_text if constraints_text else '- Answer only based on the provided context\n- Be concise and technical'}

MANDATORY OUTPUT FORMAT:
AUDIT: [List source IDs used with dates]
ANSWER: [Clean technical response]"""

        user_content = f"""CONTEXT:
{context_str}

QUERY: {query}

REFERENCE DATE: {ref_date}

Generate your response following the exact format specified."""

        # ⭐ CORRIGIDO: messages completo
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

        return {
            "answer": extracted["clean_answer"],
            "audit_trail": extracted["audit_log"],
            "titles": [r['doc'].get('metadata', {}).get('title', 'Unknown') for r in scored_results],
            "sources": [r['doc']['original_text'] for r in scored_results],
            "retrieved_metadata": [r['doc'].get('metadata', {}) for r in scored_results],
            "normalized_query": query,
            "diagnostic": {
                "num_documents_retrieved": len(scored_results),
                "cpu_embeddings": True,
                "cache_used": self.external_cache is not None
            }
        }