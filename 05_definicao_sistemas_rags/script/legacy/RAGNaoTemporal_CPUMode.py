# RAGNaoTemporal_CPUMode.py
import faiss
import numpy as np
import ollama
import asyncio
import re
from typing import Dict
from datetime import datetime
from RAG_Temporal_V8_CPUMode import SpecialistTimeAwareRAG


class VanillaRAG(SpecialistTimeAwareRAG):
    """
    Versão Baseline: Similaridade pura, sem penalidade temporal.
    MODIFICADO: BGE-M3 forçado a rodar na CPU (herdado da classe pai)
    """
    def __init__(self, json_path, variant_name="V1_VANILLA_BASE", embedding_cache=None):
        super().__init__(json_path, variant_name)
        # Força o caminho correto do prompt Vanilla
        self.external_cache = embedding_cache
        from core.paths import VALIDACAO_CONFIG
        self.caminho_prompts = VALIDACAO_CONFIG / 'prompt_rag_vanilla_V1.json'
        try:
            with open(self.caminho_prompts, 'r', encoding='utf-8') as f:
                import json
                self.prompts = json.load(f)
        except FileNotFoundError:
            print(f"⚠️ Arquivo de prompt não encontrado: {self.caminho_prompts}")
            print("   Usando prompts padrão...")
            self.prompts = {
                "V1_VANILLA_BASE": {
                    "system_role": "You are a technical specialist assistant.",
                    "constraints": [
                        "Answer only based on the provided context",
                        "Be concise and technical",
                        "Do not mention the context in your answer"
                    ],
                    "prompt_template": "CONTEXT:\n{context}\n\nUSER_QUERY:\n{query}\n\nRESPONSE:"
                }
            }
        
        print(f"✅ VanillaRAG inicializado - BGE-M3 na CPU (herdado)")

    async def search(self, query, ref_date=None):
        """
        Busca sem penalidade temporal.
        Usa o cliente CPU da classe pai para embeddings.
        """
        # ⭐ EMBEDDING NA CPU (usando o método da classe pai)
        print(f"🔄 [Vanilla] Gerando embedding para: {query[:50]}...")
        
        # Usa o mesmo método da classe pai (que força CPU e tem cache)
        query_vector_1d = await self._get_embedding(query)
        
        # Converte para 2D para o FAISS
        query_vector = query_vector_1d.reshape(1, -1)
        print(f"✅ [Vanilla] Embedding gerado (dimensão: {query_vector.shape[1]})")

        # Busca (k=10)
        distances, indices = self.index.search(query_vector, k=10)
        
        scored_results = []
        for i, idx in enumerate(indices[0]):
            if idx == -1:
                continue
            
            dist_score = distances[0][i]
            
            # Threshold 1.2
            if dist_score < 1.2:
                doc = self.base_dados[idx]
                scored_results.append({'doc': doc, 'score': dist_score})

        # Se não encontrou, pega os top 5 sem threshold
        if len(scored_results) == 0:
            print(f"⚠️ [Vanilla] Nenhum resultado com threshold 1.2. Pegando top 5...")
            distances, indices = self.index.search(query_vector, k=5)
            for i, idx in enumerate(indices[0]):
                if idx != -1:
                    doc = self.base_dados[idx]
                    scored_results.append({'doc': doc, 'score': distances[0][i]})
        
        print(f"📄 [Vanilla] Recuperados {len(scored_results)} documentos")

        # Contexto sem indentação
        context_parts = []
        for i, r in enumerate(scored_results[:5]):
            # Trunca texto muito longo
            text = r['doc']['original_text']
            if len(text) > 2000:
                text = text[:2000] + "..."
            
            context_parts.append(
                f"[[SOURCE_{i}]]\n{text}"
            )
        context_str = "\n\n".join(context_parts)

        # Prompt Vanilla
        variant = self.prompts.get("V1_VANILLA_BASE", {})
        
        sys_prompt = variant.get('system_role', 'You are a technical specialist assistant.')
        constraints = variant.get('constraints', [])
        if constraints:
            sys_prompt += "\n\nRULES:\n" + "\n".join(f"- {c}" for c in constraints)

        template = variant.get('prompt_template', "CONTEXT:\n{context}\n\nUSER_QUERY:\n{query}\n\nRESPONSE:")
        user_content = template.format(context=context_str, query=query)

        print("🤖 [Vanilla] Gerando resposta...")
        
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
            "titles": [r['doc'].get('metadata', {}).get('title', 'Unknown') for r in scored_results],
            "diagnostic": {
                "num_documents_retrieved": len(scored_results),
                "cpu_embeddings": True
            }
        }