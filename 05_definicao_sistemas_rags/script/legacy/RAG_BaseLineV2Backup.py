#!/usr/bin/env python3
"""
Unified RAG Baseline (VanillaRAG) - Optimized Async Version
"""

import asyncio
import json
import time
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union, Any

import faiss
import ijson
import numpy as np
import ollama
from ollama import AsyncClient

from core.paths import VALIDACAO_CONFIG, VETORIZATION_DATA


class CacheManager:
    """Gerencia cache interno LRU e cache externo de forma eficiente."""
    def __init__(self, external_cache: Any = None, maxsize: int = 200):
        self.external_cache = external_cache

    async def get_embedding(self, query: str, compute_func) -> np.ndarray:
        if self.external_cache:
            cached = self.external_cache.get(query)
            if cached is not None:
                if isinstance(cached, list):
                    return np.array(cached, dtype=np.float32)
                return cached

        # Executa a função computacional (que agora é uma coroutine nativa)
        embedding = await compute_func(query)

        if self.external_cache:
            self.external_cache.set(query, embedding)

        return embedding


class DataLoader:
    """Carrega documentos JSON de forma otimizada."""
    def __init__(self):
        self.documents: List[Dict] = []
        self.stats = {"total_loaded": 0, "with_vectors": 0, "with_metadata": 0, "with_dates": 0, "errors": 0}

    def load_documents(self, json_path: Union[str, Path]) -> List[Dict]:
        path = VETORIZATION_DATA / "base_conhecimento_multilingueV9.json"
        if not path.exists():
            raise FileNotFoundError(f"Arquivo não encontrado: {json_path}")

        self.documents = []
        self.stats = {k: 0 for k in self.stats}

        # Otimização: Leitura binária em bloco rápido
        with open(path, 'rb') as f:
            for item in ijson.items(f, 'item'):
                processed = self._process_document(item)
                if processed:
                    self.documents.append(processed)
                    self.stats["total_loaded"] += 1

        print(f"✅ Base carregada: {len(self.documents)} documentos")
        print(f"   📊 Stats: {self.stats['total_loaded']} docs | {self.stats['with_vectors']} vectors")
        return self.documents

    def _process_document(self, doc: Dict) -> Optional[Dict]:
        try:
            processed = doc.copy()
            if 'vector' in processed:
                self.stats["with_vectors"] += 1

            if 'metadata' not in processed:
                processed['metadata'] = {
                    'title': doc.get('title', doc.get('original_text', '')[:100].strip()),
                    'model': doc.get('model', ''),
                    'brand': doc.get('brand', ''),
                    'category': doc.get('category', '')
                }
            else:
                self.stats["with_metadata"] += 1

            processed['date_iso'] = processed.get('date_iso', '2024-01-01')[:10]
            self.stats["with_dates"] += 1

            if 'id' not in processed:
                processed['id'] = hash(processed.get('original_text', '')) % 1000000

            return processed
        except Exception:
            self.stats["errors"] += 1
            return None


class EmbeddingManager:
    """Gerencia embeddings nativamente assíncronos via Ollama Client."""
    def __init__(self, model: str = "bge-m3:latest", host: str = "http://localhost:11434"):
        self.model = model
        self.host = host
        self.dimension = 1024
        # Instanciação do cliente assíncrono nativo
        self.async_client = AsyncClient(host=self.host)

    async def compute_embedding(self, text: str) -> np.ndarray:
        if not text or not text.strip():
            text = " "
        try:
            # Chamada assíncrona real e nativa
            result = await self.async_client.embeddings(model=self.model, prompt=text)
            embedding = np.array(result['embedding'], dtype=np.float32)
            if np.isnan(embedding).any():
                return np.zeros(self.dimension, dtype=np.float32)
            return embedding
        except Exception:
            return np.zeros(self.dimension, dtype=np.float32)


class FAISSManager:
    """Gerencia índice FAISS para busca vetorial acelerada."""
    def __init__(self, dimension: int = 1024):
        self.dimension = dimension
        self.index: Optional[faiss.IndexFlatL2] = None

    def build_index(self, documents: List[Dict]) -> None:
        if not documents: return
        vectors = []
        for doc in documents:
            if 'vector' in doc:
                vec = np.array(doc['vector'], dtype=np.float32)
                if len(vec) == self.dimension:
                    vectors.append(vec)
        
        if vectors:
            self.index = faiss.IndexFlatL2(self.dimension)
            self.index.add(np.array(vectors).astype('float32'))
            print(f"✅ Índice FAISS criado com {self.index.ntotal} vetores.")


class VanillaRAG:
    """Versão Baseline Otimizada com chamadas 100% Async."""
    _semaphore = asyncio.Semaphore(1) 
    def __init__(self, json_path: Union[str, Path],
                 variant_name: str = "V1_VANILLA_MIXED_EQUITABLE",
                 embedding_cache=None, use_expansion: bool = False):
        self.use_expansion = use_expansion
        self.embedding_cache = embedding_cache
        self.cache_manager = CacheManager(external_cache=embedding_cache)
        self.embedding_manager = EmbeddingManager()
        
        self.data_loader = DataLoader()
        self.data_loader.load_documents(json_path)
        self.base_dados = self.data_loader.documents

        self.faiss_manager = FAISSManager(dimension=1024)
        self.faiss_manager.build_index(self.base_dados)
        self.index = self.faiss_manager.index

        self.caminho_prompts = VALIDACAO_CONFIG / 'prompt_rag_vanilla_V1.json'
        self.prompts = self._load_prompts()
        self.variant_name = variant_name

    def _load_prompts(self) -> Dict:
        try:
            with open(self.caminho_prompts, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}

    async def search(self, query: str, ref_date: str = "2026-03-23") -> Dict:
        # Busca o embedding utilizando a esteira assíncrona
        query_vector_1d = await self.cache_manager.get_embedding(
            query, self.embedding_manager.compute_embedding
        )
        query_vector = query_vector_1d.reshape(1, -1)

        distances, indices = self.index.search(query_vector, k=20)
        scored_results = []
        for i, idx in enumerate(indices[0]):
            if idx != -1 and distances[0][i] < 1.2:
                scored_results.append({'doc': self.base_dados[idx], 'score': distances[0][i]})

        if not scored_results:
            distances, indices = self.index.search(query_vector, k=5)
            for i, idx in enumerate(indices[0]):
                if idx != -1:
                    scored_results.append({'doc': self.base_dados[idx], 'score': distances[0][i]})

        context_parts = [f"[[SOURCE_{i}]]\n{r['doc']['original_text'][:2000]}" for i, r in enumerate(scored_results[:5])]
        context_str = "\n\n".join(context_parts)

        variant = self.prompts.get(self.variant_name, {})
        sys_prompt = variant.get('system_role', 'You are a technical specialist assistant.')
        constraints = variant.get('constraints', [])
        if constraints:
            sys_prompt += "\n\nRULES:\n" + "\n".join(f"- {c}" for c in constraints)

        template = variant.get('prompt_template', "CONTEXT:\n{context}\n\nUSER_QUERY:\n{query}\n\nRESPONSE:")
        user_content = template.format(context=context_str, query=query, ref_date=ref_date)

        # OTIMIZAÇÃO: Chamada assíncrona nativa ao Ollama Chat
        response = await self.embedding_manager.async_client.chat(
            model="phi3.5:latest",
            messages=[
                {'role': 'system', 'content': sys_prompt},
                {'role': 'user', 'content': user_content}
            ],
            options={"temperature": 0.0, "top_p": 0.9}
        )

        return {
            "answer": response['message']['content'],
            "sources": [r['doc']['original_text'] for r in scored_results],
            "titles": [r['doc'].get('metadata', {}).get('title', 'Unknown') for r in scored_results],
            "normalized_query": query
        }