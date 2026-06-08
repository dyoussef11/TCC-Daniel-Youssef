# RAGNaoTemporal_Independent.py

import faiss
import numpy as np
import ollama
import asyncio
import json
from pathlib import Path
from typing import Dict, Optional

from core.paths import VALIDACAO_CONFIG
from modules.embeddings import EmbeddingManager
from modules.data_loader import DataLoader
from modules.faiss_manager import FAISSManager
from modules.cache_manager import CacheManager


class VanillaRAG:
    """
    Versão Baseline: Similaridade pura, sem penalidade temporal.
    Independente do Temporal RAG.
    """
    
    # def __init__(self, json_path, variant_name="V1_VANILLA_BASE", 
    def __init__(self, json_path, variant_name="V1_VANILLA_MIXED_EQUITABLE", 
                 embedding_cache=None, use_expansion: bool = True):
        
        self.use_expansion = use_expansion
        self.embedding_cache = embedding_cache
        
        # Cache manager
        self.cache_manager = CacheManager(external_cache=embedding_cache)
        
        # Embedding manager
        self.embedding_manager = EmbeddingManager(model="bge-m3:latest")
        
        # Data loader
        self.data_loader = DataLoader()
        self.data_loader.load_documents(json_path)
        self.base_dados = self.data_loader.documents
        
        # FAISS index
        self.faiss_manager = FAISSManager(dimension=1024)
        if self.base_dados:
            self.faiss_manager.build_index(self.base_dados)
        self.index = self.faiss_manager.index
        
        # Dicionário de expansão
        if use_expansion:
            self.flat_dict = self._load_flat_dictionary()
        else:
            self.flat_dict = None
        
        # Prompts
        self.caminho_prompts = VALIDACAO_CONFIG / 'prompt_rag_vanilla_V1.json'
        self.prompts = self._load_prompts()
        
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
                "V1_VANILLA_BASE": {
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
            if key in query_lower:
                if len(key) > best_match_len:
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
    
    async def search(self, query: str, ref_date: str ="2026-03-23") -> Dict:
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
        
        # variant = self.prompts.get("V1_VANILLA_BASE", {})
        variant = self.prompts.get("V1_VANILLA_MIXED_EQUITABLE", {})
        sys_prompt = variant.get('system_role', 'You are a technical specialist assistant.')
        constraints = variant.get('constraints', [])
        if constraints:
            sys_prompt += "\n\nRULES:\n" + "\n".join(f"- {c}" for c in constraints)
        
        template = variant.get('prompt_template', "CONTEXT:\n{context}\n\nUSER_QUERY:\n{query}\n\nRESPONSE:")
        user_content = template.format(
            context=context_str, 
            query=query, 
            ref_date=None
        )
        
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