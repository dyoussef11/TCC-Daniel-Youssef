# RAG_BaseLine.py (ATUALIZADO)
import faiss
import numpy as np
import ollama
import asyncio
import json
from typing import Dict, Optional
from pathlib import Path
from RAG_Temporal_V9 import SpecialistTimeAwareRAG
from core.paths import VALIDACAO_CONFIG


class VanillaRAG(SpecialistTimeAwareRAG):
    """
    Versão Baseline: Similaridade pura, sem penalidade temporal.
    COM suporte a expansão de query via dicionário hierárquico.
    """
    def __init__(self, json_path, variant_name="V1_VANILLA_BASE", embedding_cache=None, use_expansion: bool = True):
        # ⭐ Passa o cache para a classe pai
        # super().__init__(json_path, variant_name, embedding_cache=embedding_cache)
        super().__init__(json_path, variant_name, embedding_cache=embedding_cache, 
                        use_expansion=use_expansion)

        # ⭐ NOVO: controle de expansão
        self.use_expansion = use_expansion
        
        # ⭐ Carrega o dicionário hierárquico flat (se usar expansão)
        if use_expansion:
            self.flat_dict = self._load_flat_dictionary()
        else:
            self.flat_dict = None
        
        self.caminho_prompts = VALIDACAO_CONFIG / 'prompt_rag_vanilla_V1.json'
        try:
            with open(self.caminho_prompts, 'r', encoding='utf-8') as f:
                self.prompts = json.load(f)
        except FileNotFoundError:
            print(f"⚠️ Arquivo de prompt não encontrado: {self.caminho_prompts}")
            self.prompts = {
                "V1_VANILLA_BASE": {
                    "system_role": "You are a technical specialist assistant.",
                    "constraints": ["Answer only based on the provided context"],
                    "prompt_template": "CONTEXT:\n{context}\n\nUSER_QUERY:\n{query}\n\nRESPONSE:"
                }
            }
        
        print(f"✅ VanillaRAG inicializado - BGE-M3 na CPU (com cache)")
        print(f"   Expansão de query: {'✅ ATIVADA' if use_expansion else '❌ DESATIVADA'}")
    
    def _load_flat_dictionary(self) -> Dict:
        """Carrega o dicionário flat hierárquico."""
        dict_path = VALIDACAO_CONFIG / 'dictionary_synonyms_flat_v3.json'
        try:
            with open(dict_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"⚠️ Dicionário flat não encontrado: {dict_path}")
            return {}
    
    def _expand_query(self, query: str, max_terms: int = 5) -> str:
        """
        Expande a query usando o dicionário flat hierárquico.
        Retorna a query expandida (ou original se não houver expansão).
        """
        if not self.use_expansion or not self.flat_dict:
            return query
        
        query_lower = query.lower()
        
        # Encontra a melhor chave correspondente
        best_key = None
        best_match_len = 0
        
        for key in self.flat_dict.keys():
            if key in query_lower:
                if len(key) > best_match_len: 
                    best_match_len = len(key)
                    best_key = key
        
        if not best_key:
            return query
        
        # Obtém os sinônimos
        synonyms = self.flat_dict[best_key]
        
        # Filtra termos que já estão na query
        new_terms = []
        for term in synonyms:
            term_lower = term.lower()
            if term_lower not in query_lower and len(term) >= 3:
                if term not in ['gaming', 'laptop', 'notebook', 'edition']:
                    new_terms.append(term)
        
        if not new_terms:
            return query
        
        # Limita número de termos
        new_terms = new_terms[:max_terms]
        
        return f"{query} {' '.join(new_terms)}"
    
    async def search(self, query, ref_date=None):
        """Busca sem penalidade temporal (com expansão opcional)."""
        
        # ⭐ NOVO: Expande a query se configurado
        expanded_query = self._expand_query(query)
        
        # Usa o embedding da query expandida
        query_vector_1d = await self._get_embedding(expanded_query)
        query_vector = query_vector_1d.reshape(1, -1)

        distances, indices = self.index.search(query_vector, k=10)
        
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

        variant = self.prompts.get("V1_VANILLA_BASE", {})
        sys_prompt = variant.get('system_role', 'You are a technical specialist assistant.')
        constraints = variant.get('constraints', [])
        if constraints:
            sys_prompt += "\n\nRULES:\n" + "\n".join(f"- {c}" for c in constraints)

        template = variant.get('prompt_template', "CONTEXT:\n{context}\n\nUSER_QUERY:\n{query}\n\nRESPONSE:")
        user_content = template.format(context=context_str, query=query)

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
            "diagnostic": {
                "num_documents_retrieved": len(scored_results),
                "cpu_embeddings": True,
                "cache_used": self.external_cache is not None,
                "expansion_used": self.use_expansion,
                "expanded_query": expanded_query if self.use_expansion else None
            }
        }