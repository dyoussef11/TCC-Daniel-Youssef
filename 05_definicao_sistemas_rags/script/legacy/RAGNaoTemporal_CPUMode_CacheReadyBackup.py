import faiss
import numpy as np
import ollama
import asyncio
from typing import Dict, Optional
from RAG_Temporal_V8_CPUMode_CacheReady import SpecialistTimeAwareRAG


class VanillaRAG(SpecialistTimeAwareRAG):
    """
    Versão Baseline: Similaridade pura, sem penalidade temporal.
    Herda o cache de embeddings da classe pai.
    """
    def __init__(self, json_path, variant_name="V1_VANILLA_BASE", embedding_cache=None):
        # ⭐ Passa o cache para a classe pai
        super().__init__(json_path, variant_name, embedding_cache=embedding_cache)
        
        from core.paths import VALIDACAO_CONFIG
        self.caminho_prompts = VALIDACAO_CONFIG / 'prompt_rag_vanilla_V1.json'
        try:
            with open(self.caminho_prompts, 'r', encoding='utf-8') as f:
                import json
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

    async def search(self, query, ref_date=None):
        """Busca sem penalidade temporal."""
        # ⭐ Usa o método da classe pai (que usa cache!)
        query_vector_1d = await self._get_embedding(query)
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
                "cache_used": self.external_cache is not None
            }
        }