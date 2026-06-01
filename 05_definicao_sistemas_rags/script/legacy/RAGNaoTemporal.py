import faiss
import numpy as np
import ollama
import asyncio
import re
from typing import Dict
from RAG_Temporal_V8 import SpecialistTimeAwareRAG

class VanillaRAG(SpecialistTimeAwareRAG):
    """
    Versão Baseline: Similaridade pura, sem penalidade temporal.
    """
    def __init__(self, json_path, variant_name="V1_VANILLA_BASE"):
        super().__init__(json_path, variant_name)
        # Força o caminho correto do prompt Vanilla
        from core.paths import VALIDACAO_CONFIG
        self.caminho_prompts = VALIDACAO_CONFIG / 'prompt_rag_vanilla_V1.json'
        with open(self.caminho_prompts, 'r', encoding='utf-8') as f:
            import json
            self.prompts = json.load(f)

    async def search(self, query, ref_date=None):
        # Embedding
        res_embed = await asyncio.to_thread(
            ollama.embeddings, model="bge-m3:latest", prompt=query
        )
        query_vector = np.array([res_embed['embedding']]).astype('float32')
        
        # Busca (k=10)
        distances, indices = self.index.search(query_vector, k=10)
        
        scored_results = []
        for i, idx in enumerate(indices[0]):
            if idx != -1 and distances[0][i] < 1.2:  # Threshold 1.2
                doc = self.base_dados[idx]
                scored_results.append({'doc': doc})

        # Se não encontrou, pega os top 5 sem threshold
        if len(scored_results) == 0:
            print(f"⚠️ Vanilla: Nenhum resultado. Pegando top 5...")
            distances, indices = self.index.search(query_vector, k=5)
            for i, idx in enumerate(indices[0]):
                if idx != -1:
                    doc = self.base_dados[idx]
                    scored_results.append({'doc': doc})

        # Contexto sem indentação
        context_parts = []
        for i, r in enumerate(scored_results[:5]):
            context_parts.append(
                f"[[SOURCE_{i}]]\n{r['doc']['original_text']}"
            )
        context_str = "\n\n".join(context_parts)

        # Prompt Vanilla
        variant = self.prompts.get("V1_VANILLA_BASE", {})
        
        sys_prompt = variant.get('system_role', '')
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
            options={"temperature": 0.1, "top_p": 0.9},
            keep_alive=0
        )

        return {
            "answer": response['message']['content'],
            "sources": [r['doc']['original_text'] for r in scored_results],
            "titles": [r['doc'].get('metadata', {}).get('title', 'Unknown') for r in scored_results]
        }