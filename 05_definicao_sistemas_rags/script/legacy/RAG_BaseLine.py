#!/usr/bin/env python3
"""
Unified RAG Baseline (VanillaRAG) - Single File Version
Includes: CacheManager, DataLoader, EmbeddingManager, FAISSManager, VanillaRAG
Dependencies: faiss, numpy, ollama, ijson, asyncio
"""

import asyncio
import json
import os
import time
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union, Any, Iterator

import ollama

import faiss
import ijson
import numpy as np
from ollama import Client

# ----------------------------------------------------------------------
# Configuration (adjust as needed)
# ----------------------------------------------------------------------
from core.paths import VALIDACAO_CONFIG, VETORIZATION_DATA

# ----------------------------------------------------------------------
# CacheManager
# ----------------------------------------------------------------------
class CacheManager:
    """Gerencia cache interno LRU e cache externo."""

    def __init__(self, external_cache: Any = None, maxsize: int = 200):
        self.external_cache = external_cache
        self._cache_func = lru_cache(maxsize=maxsize)(self._compute_embedding)

    def _compute_embedding(self, query: str) -> np.ndarray:
        """Placeholder, to be overridden or replaced."""
        raise NotImplementedError("Subclasses devem implementar _compute_embedding")

    async def get_embedding(self, query: str, compute_func) -> np.ndarray:
        if self.external_cache:
            cached = self.external_cache.get(query)
            if cached is not None:
                # Garante que seja numpy array
                if isinstance(cached, list):
                    return np.array(cached, dtype=np.float32)
                return cached

        embedding = await asyncio.to_thread(compute_func, query)

        if self.external_cache:
            self.external_cache.set(query, embedding)

        return embedding

    def get_stats(self) -> Dict:
        stats = {
            "internal_hits": 0,
            "internal_misses": 0,
            "internal_currsize": 0,
            "external_cache_size": 0
        }
        if hasattr(self._cache_func, 'cache_info'):
            ci = self._cache_func.cache_info()
            stats.update({
                "internal_hits": ci.hits,
                "internal_misses": ci.misses,
                "internal_currsize": ci.currsize
            })
        if self.external_cache:
            external_stats = self.external_cache.stats()
            stats["external_cache_size"] = external_stats.get('size', 0)
        return stats

    def clear(self) -> None:
        if hasattr(self._cache_func, 'cache_clear'):
            self._cache_func.cache_clear()

# ----------------------------------------------------------------------
# DataLoader
# ----------------------------------------------------------------------
class DataLoader:
    """Carrega documentos JSON com suporte a streaming."""

    def __init__(self):
        self.documents: List[Dict] = []
        self.stats = {
            "total_loaded": 0,
            "with_vectors": 0,
            "with_metadata": 0,
            "with_dates": 0,
            "errors": 0
        }

    def load_documents(self, json_path: Union[str, Path]) -> List[Dict]:
        path = VETORIZATION_DATA / "base_conhecimento_multilingueV9.json"
        if not path.exists():
            raise FileNotFoundError(f"Arquivo não encontrado: {json_path}")

        self.documents = []
        self.stats = {k: 0 for k in self.stats}

        with open(path, 'rb') as f:
            for item in ijson.items(f, 'item'):
                processed = self._process_document(item)
                if processed:
                    self.documents.append(processed)
                    self.stats["total_loaded"] += 1

        print(f"✅ Base carregada: {len(self.documents)} documentos")
        self._print_stats()
        return self.documents

    def _process_document(self, doc: Dict) -> Optional[Dict]:
        try:
            processed = doc.copy()
            if 'vector' in processed:
                self.stats["with_vectors"] += 1

            if 'metadata' not in processed:
                processed['metadata'] = self._extract_metadata(doc)
            else:
                self.stats["with_metadata"] += 1

            if 'date_iso' in processed:
                processed['date_iso'] = processed['date_iso'][:10]
                self.stats["with_dates"] += 1
            else:
                processed['date_iso'] = '2024-01-01'

            if 'id' not in processed:
                processed['id'] = hash(processed.get('original_text', '')) % 1000000

            return processed
        except Exception as e:
            self.stats["errors"] += 1
            print(f"⚠️ Erro ao processar documento: {e}")
            return None

    def _extract_metadata(self, doc: Dict) -> Dict:
        metadata = {}
        for key in ['title', 'model', 'brand', 'category']:
            if key in doc:
                metadata[key] = doc[key]
        if 'original_text' in doc and 'title' not in metadata:
            metadata['title'] = doc['original_text'][:100].strip()
        return metadata

    def _print_stats(self) -> None:
        s = self.stats
        print(f"   📊 Stats: {s['total_loaded']} docs | "
              f"{s['with_vectors']} vectors | {s['with_metadata']} metadata | "
              f"{s['with_dates']} dates | {s['errors']} errors")

    def get_document_by_id(self, doc_id: int) -> Optional[Dict]:
        for doc in self.documents:
            if doc.get('id') == doc_id:
                return doc
        return None

    def filter_by_metadata(self, key: str, value: str) -> List[Dict]:
        return [doc for doc in self.documents
                if doc.get('metadata', {}).get(key, '').lower() == value.lower()]

    def get_date_range(self) -> tuple:
        dates = [doc['date_iso'] for doc in self.documents if 'date_iso' in doc]
        return (min(dates), max(dates)) if dates else (None, None)

# ----------------------------------------------------------------------
# EmbeddingManager
# ----------------------------------------------------------------------
class EmbeddingManager:
    """Gerencia embeddings via Ollama (CPU)."""

    def __init__(self, model: str = "bge-m3:latest", host: str = "http://localhost:11434"):
        self.model = model
        self.host = host
        self.dimension: Optional[int] = None
        self._init_client()

    def _init_client(self) -> None:
        # REMOVA ou COMENTE todo o bloco que força CPU:
        # self._original_cuda = os.environ.get('CUDA_VISIBLE_DEVICES')
        # self._original_num_gpu = os.environ.get('OLLAMA_NUM_GPU')
        # os.environ['CUDA_VISIBLE_DEVICES'] = '-1'
        # os.environ['OLLAMA_NUM_GPU'] = '0'

        self.client = Client(host=self.host)

        # Não precisa restaurar nada
        # if self._original_cuda is not None:
        #     os.environ['CUDA_VISIBLE_DEVICES'] = self._original_cuda
        # else:
        #     os.environ.pop('CUDA_VISIBLE_DEVICES', None)
        # etc.

        self._test_connection()

    def _test_connection(self) -> None:
        try:
            test_result = self.client.embeddings(model=self.model, prompt="test")
            if 'embedding' in test_result:
                self.dimension = len(test_result['embedding'])
                print(f"✅ Conectado a {self.model} (GPU) - dimensão: {self.dimension}")
        except Exception as e:
            print(f"⚠️ {self.model} não disponível: {e}")
            self.dimension = 1024

    def compute_embedding(self, text: str) -> np.ndarray:
        if not text or not text.strip():
            text = " "

        try:
            result = self.client.embeddings(model=self.model, prompt=text)
            embedding = np.array(result['embedding'], dtype=np.float32)
            # Verifica se há NaN no embedding
            if np.isnan(embedding).any():
                print(f"⚠️ NaN detectado no embedding para texto: '{text[:50]}...'")
                # Retorna vetor de zeros da dimensão correta
                dim = self.dimension if self.dimension else 1024
                return np.zeros(dim, dtype=np.float32)
            return embedding
        except Exception as e:
            # Captura qualquer erro do Ollama, incluindo ResponseError com NaN
            print(f"⚠️ Erro ao gerar embedding: {e}. Usando vetor zero.")
            dim = self.dimension if self.dimension else 1024
            return np.zeros(dim, dtype=np.float32)

    def compute_embeddings_batch(self, texts: list) -> np.ndarray:
        embeddings = [self.compute_embedding(t) for t in texts]
        return np.array(embeddings)

# ----------------------------------------------------------------------
# FAISSManager
# ----------------------------------------------------------------------
class FAISSManager:
    """Gerencia índice FAISS para busca vetorial."""

    def __init__(self, dimension: int = 1024):
        self.dimension = dimension
        self.index: Optional[faiss.IndexFlatL2] = None
        self.stats = {
            "total_vectors": 0,
            "last_search_time": 0,
            "searches_performed": 0
        }

    def build_index(self, documents: List[Dict]) -> None:
        if not documents:
            print("⚠️ Nenhum documento para indexar")
            return

        vectors = self._extract_vectors(documents)
        if vectors is None or len(vectors) == 0:
            print("⚠️ Nenhum vetor válido encontrado")
            return

        self.index = faiss.IndexFlatL2(self.dimension)
        self.index.add(vectors)
        self.stats["total_vectors"] = self.index.ntotal
        print(f"✅ Índice FAISS criado com {self.index.ntotal} vetores (dimensão {self.dimension})")

    def _extract_vectors(self, documents: List[Dict]) -> Optional[np.ndarray]:
        vectors = []
        for doc in documents:
            if 'vector' in doc:
                vec = np.array(doc['vector'], dtype=np.float32)
                if len(vec) == self.dimension:
                    vectors.append(vec)
                else:
                    print(f"⚠️ Dimensão inválida: {len(vec)} (esperado {self.dimension})")
        return np.array(vectors).astype('float32') if vectors else None

    def search(self, query_vector: np.ndarray, k: int = 20) -> List[Tuple[int, float]]:
        if self.index is None:
            print("❌ Índice FAISS não inicializado")
            return []

        start = time.time()
        if query_vector.ndim == 1:
            query_vector = query_vector.reshape(1, -1)

        distances, indices = self.index.search(query_vector, k)
        results = [(idx, float(distances[0][i])) for i, idx in enumerate(indices[0]) if idx != -1]

        self.stats["searches_performed"] += 1
        self.stats["last_search_time"] = time.time() - start
        return results

    def get_nearest_neighbors(self, query_vector: np.ndarray, threshold: Optional[float] = None) -> List[Tuple[int, float]]:
        results = self.search(query_vector, k=50)
        if threshold is not None:
            results = [(idx, d) for idx, d in results if d <= threshold]
        return results

    def get_index_stats(self) -> Dict:
        stats = self.stats.copy()
        if self.index:
            stats.update({
                "index_size": self.index.ntotal,
                "dimension": self.index.d,
                "memory_usage_mb": self.index.ntotal * self.index.d * 4 / (1024 * 1024)
            })
        return stats

    def save_index(self, path: str) -> None:
        if self.index:
            faiss.write_index(self.index, path)
            print(f"✅ Índice salvo em: {path}")

    def load_index(self, path: str) -> None:
        try:
            self.index = faiss.read_index(path)
            self.stats["total_vectors"] = self.index.ntotal
            print(f"✅ Índice carregado: {self.index.ntotal} vetores")
        except Exception as e:
            print(f"❌ Erro ao carregar índice: {e}")

# ----------------------------------------------------------------------
# VanillaRAG (Baseline)
# ----------------------------------------------------------------------
class VanillaRAG:
    """
    Versão Baseline: Similaridade pura, sem penalidade temporal.
    """

    def __init__(self, json_path: Union[str, Path],
                 variant_name: str = "V1_VANILLA_MIXED_EQUITABLE",
                 embedding_cache=None, use_expansion: bool = True):
        self.use_expansion = use_expansion
        self.embedding_cache = embedding_cache
        self.cache_manager = CacheManager(external_cache=embedding_cache)

        self.embedding_manager = EmbeddingManager(model="bge-m3:latest")
        self.data_loader = DataLoader()
        self.data_loader.load_documents(json_path)
        self.base_dados = self.data_loader.documents

        self.faiss_manager = FAISSManager(dimension=1024)
        if self.base_dados:
            self.faiss_manager.build_index(self.base_dados)
        self.index = self.faiss_manager.index

        if use_expansion:
            self.flat_dict = self._load_flat_dictionary()
        else:
            self.flat_dict = None

        self.caminho_prompts = VALIDACAO_CONFIG / 'prompt_rag_vanilla_V1.json'
        self.prompts = self._load_prompts()
        self.variant_name = variant_name

        print(f"✅ VanillaRAG inicializado - BGE-M3 na CPU")
        print(f"   Documentos: {len(self.base_dados)}")
        print(f"   Expansão: {'✅ ATIVADA' if use_expansion else '❌ DESATIVADA'}")

    def _load_flat_dictionary(self) -> Dict:
        dict_path = VALIDACAO_CONFIG / 'dictionary_synonyms_flat_v3.json'
        try:
            with open(dict_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"⚠️ Dicionário não encontrado: {dict_path}")
            return {}

    def _load_prompts(self) -> Dict:
        try:
            with open(self.caminho_prompts, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"⚠️ Prompt não encontrado: {self.caminho_prompts}")
            return {
                self.variant_name: {
                    "system_role": "You are a technical specialist assistant.",
                    "constraints": ["Answer only based on the provided context"],
                    "prompt_template": "CONTEXT:\n{context}\n\nUSER_QUERY:\n{query}\n\nRESPONSE:"
                }
            }

    async def _get_embedding(self, query: str) -> np.ndarray:
        return await self.cache_manager.get_embedding(
            query,
            self.embedding_manager.compute_embedding
        )

    def _expand_query(self, query: str, max_terms: int = 5) -> str:
        if not self.use_expansion or not self.flat_dict:
            return query

        query_lower = query.lower()
        best_key = None
        best_match_len = 0
        for key in self.flat_dict.keys():
            if key in query_lower and len(key) > best_match_len:
                best_match_len = len(key)
                best_key = key

        if not best_key:
            return query

        synonyms = self.flat_dict[best_key]
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

    async def search(self, query: str, ref_date: str = "2026-03-23") -> Dict:
        expanded_query = self._expand_query(query)
        query_vector_1d = await self._get_embedding(expanded_query)
        query_vector = query_vector_1d.reshape(1, -1)

        distances, indices = self.index.search(query_vector, k=20)

        scored_results = []
        for i, idx in enumerate(indices[0]):
            if idx == -1:
                continue
            dist_score = distances[0][i]
            if dist_score < 1.2:
                doc = self.base_dados[idx]
                scored_results.append({'doc': doc, 'score': dist_score})

        if len(scored_results) == 0:
            distances, indices = self.index.search(query_vector, k=5)
            for i, idx in enumerate(indices[0]):
                if idx != -1:
                    doc = self.base_dados[idx]
                    scored_results.append({'doc': doc, 'score': distances[0][i]})

        context_parts = []
        for i, r in enumerate(scored_results[:5]):
            text = r['doc']['original_text']
            if len(text) > 2000:
                text = text[:2000] + "..."
            context_parts.append(f"[[SOURCE_{i}]]\n{text}")
        context_str = "\n\n".join(context_parts)

        variant = self.prompts.get(self.variant_name, self.prompts.get("V1_VANILLA_MIXED_EQUITABLE", {}))
        sys_prompt = variant.get('system_role', 'You are a technical specialist assistant.')
        constraints = variant.get('constraints', [])
        if constraints:
            sys_prompt += "\n\nRULES:\n" + "\n".join(f"- {c}" for c in constraints)

        template = variant.get('prompt_template',
                               "CONTEXT:\n{context}\n\nUSER_QUERY:\n{query}\n\nRESPONSE:")
        user_content = template.format(context=context_str, query=query, ref_date=None)

        response = await asyncio.to_thread(
            ollama.chat,
            model="phi3.5:latest",
            messages=[
                {'role': 'system', 'content': sys_prompt},
                {'role': 'user', 'content': user_content}
            ],
            options={"temperature": 0.0, "top_p": 0.9},
            keep_alive=0
        )

        return {
            "answer": response['message']['content'],
            "sources": [r['doc']['original_text'] for r in scored_results],
            "titles": [r['doc'].get('metadata', {}).get('title', 'Unknown') for r in scored_results],
            "normalized_query": expanded_query,
            "diagnostic": {
                "num_documents_retrieved": len(scored_results),
                "cpu_embeddings": True,
                "cache_used": self.embedding_cache is not None,
                "expansion_used": self.use_expansion,
                "expanded_query": expanded_query if self.use_expansion else None
            }
        }

# ----------------------------------------------------------------------
# Example usage (commented)
# ----------------------------------------------------------------------
if __name__ == "__main__":
    # Example: initialize and run a query
    async def main():
        rag = VanillaRAG("path_to_your_documents.json", use_expansion=True)
        result = await rag.search("What is the battery life of the new laptop?")
        print(result["answer"])
        print("\nSources:", result["titles"])

    # asyncio.run(main())
    print("Unified VanillaRAG class is ready. Import and use as needed.")