import json
import faiss
import ijson
import numpy as np
import ollama
import asyncio
import re
from pathlib import Path
from datetime import datetime
from typing import  Dict,  Union
import gc

from core.paths import VALIDACAO_CONFIG, VETORIZATION_DATA

class SpecialistTimeAwareRAG:
    """
    Engine RAG com Auditoria Silenciosa e Normalização por Sinônimos.
    Aplica penalidade temporal e expansão de SKU para maior precisão técnica.
    """
    
    # def __init__(self, json_path: Union[str, Path], variant_name: str = "V8_HYBRID_AUDITOR") -> None:
    def __init__(self, json_path: Union[str, Path], variant_name: str = "V9_HYBRID_AUDITOR") -> None:
        self.dimension: int = 1024  # Dimensão do BGE-M3
        # self.caminho_prompts: Path = VALIDACAO_CONFIG / 'prompt_rag_temporal_hybrid_V8.json'
        # self.caminho_prompts: Path = VALIDACAO_CONFIG / 'prompt_rag_temporal_hybrid_V8Backup.json'
        self.caminho_prompts: Path = VALIDACAO_CONFIG / 'prompt_rag_temporal_hybrid_V9.json'
        self.variant_name = variant_name
        
        print(f"--- 🧠 RAG ENGINE ATIVADA (Variante: {variant_name}) ---")
        
        # 1. Carregar a base de conhecimento
        self.base_dados = []
        try:
            with open(json_path, 'rb') as f:
                for item in ijson.items(f, 'item'):
                    self.base_dados.append(item)
            print(f"✅ Base carregada: {len(self.base_dados)} documentos.")
        except Exception as e:
            print(f"❌ Erro ao carregar base: {e}")
            self.base_dados = []

        # 3. Inicializar Index FAISS
        self.index = faiss.IndexFlatL2(self.dimension)
        if self.base_dados:
            vectors = np.array([d['vector'] for d in self.base_dados]).astype('float32')
            self.index.add(vectors)

        # 4. Carregar Prompts
        with open(self.caminho_prompts, 'r', encoding='utf-8') as f:
            self.prompts = json.load(f)

    def _extrair_auditoria(self, full_response: str) -> Dict[str, str]:
        audit_match = re.search(r"AUDIT:(.*?)(?=ANSWER:|$)", full_response, re.DOTALL | re.IGNORECASE)
        answer_match = re.search(r"ANSWER:(.*)", full_response, re.DOTALL | re.IGNORECASE)
        
        return {
            "audit_log": audit_match.group(1).strip() if audit_match else "No audit log provided.",
            "clean_answer": answer_match.group(1).strip() if answer_match else full_response.strip()
        }

    async def search(self, query: str, ref_date: str = "2026-03-23"):
        ref_dt = datetime.strptime(ref_date, "%Y-%m-%d")
        
        # 1. Embedding
        res_embed = await asyncio.to_thread(
            ollama.embeddings, model="bge-m3:latest", prompt=query
        )
        query_vector = np.array([res_embed['embedding']]).astype('float32')

        # 2. Busca (k=20)
        distances, indices = self.index.search(query_vector, k=20)
        
        scored_results = []
        for i, idx in enumerate(indices[0]):
            if idx == -1: 
                continue
            
            doc = self.base_dados[idx]
            dist_score = distances[0][i]
            
            # Threshold de relevância
            if dist_score > 1.2:  # Aumentei de 0.9 para 1.2 (mais permissivo)
                continue
                
            # Penalidade Temporal
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

        # 3. Top 10
        scored_results = sorted(scored_results, key=lambda x: x['score'])[:10]
        
        # Se não encontrou nada, afrouxa o threshold
        if len(scored_results) == 0:
            print(f"⚠️ Nenhum resultado com threshold 1.2. Buscando top 5 direto...")
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
        
        # 4. Contexto SEM INDENTAÇÃO!
        context_parts = []
        for i, r in enumerate(scored_results):
            meta = r['doc'].get('metadata', {})
            titulo = meta.get('title') or meta.get('model') or f"Source_{i}"
            
            context_parts.append(
                f"[[ID_{i} | DATE: {r['date']} | TITLE: {titulo}]]\n"
                f"{r['doc']['original_text']}"
            )
        
        context_str = "\n\n".join(context_parts)

        # 5. Prompt CORRETO (sem indentação no user_content)
        variant = self.prompts.get(self.variant_name, {})
        
        constraints_text = "\n".join(f"- {c}" for c in variant.get('constraints', []))
        
        sys_prompt = f"""{variant.get('system_role', '')}

    CRITICAL RULES:
    {constraints_text}

    MANDATORY OUTPUT FORMAT:
    AUDIT: [List source IDs used with dates. If internal knowledge needed, state 'Internal knowledge (2024 training) compatible with {ref_date}']
    ANSWER: [Clean technical response without any tags or meta-commentary]"""

        # SEM INDENTAÇÃO AQUI!
        user_content = f"""CONTEXT:
    {context_str}

    QUERY: {query}

    REFERENCE DATE: {ref_date}

    Generate your response following the exact format specified."""

        # 6. Usar modelo que funciona
        response = await asyncio.to_thread(
            ollama.chat,
            model="phi3.5:latest",  # Ou "llama3.2:3b"
            messages=[
                {'role': 'system', 'content': sys_prompt},
                {'role': 'user', 'content': user_content}
            ],
            options={"temperature": 0.1, "top_p": 0.9},
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
            "normalized_query": query
        }

if __name__ == "__main__":
    async def main():
        engine = SpecialistTimeAwareRAG(
            # VETORIZATION_DATA / 'base_conhecimento_multilingueV2.json'
            # VETORIZATION_DATA / 'base_conhecimento_multilingueV5.json'
            VETORIZATION_DATA / 'base_conhecimento_multilingueV6_OTIMIZADO.json'
        )
        
        # Teste com termo curto presente no dicionário (ex: "helios")
        pergunta = "Qual a RAM máxima do Helios 300 ?"
        res = await engine.search(pergunta)
        
        print(f"\n📝 QUERY ORIGINAL: {pergunta}")
        print(f"🔍 QUERY EXPANDIDA: {res['normalized_query']}")
        print(f"\n🤖 RESPOSTA FINAL:\n{res['answer']}")
        print(f"\n📜 AUDIT TRAIL:\n{res['audit_trail']}")

    asyncio.run(main())