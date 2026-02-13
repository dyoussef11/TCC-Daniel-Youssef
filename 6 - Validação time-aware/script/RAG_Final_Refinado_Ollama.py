import json
import faiss
import numpy as np
import torch
import sys
import re
import asyncio
from pathlib import Path
from datetime import datetime
from sentence_transformers import SentenceTransformer
from openai import AsyncOpenAI 

# --- BOOTSTRAP DE CAMINHO DO PROJETO ---
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.paths import (
VALIDACAO_CONFIG

)



class SpecialistTimeAwareRAG:
    def __init__(self, json_path, variant_name="V3_ENGINEER"): # CORREÇÃO: Nome da chave
        # --- 1. CONFIGURAÇÃO DE CAMINHOS ---
    
        self.caminho_sinonimos = VALIDACAO_CONFIG / 'dictionary_synonyms.json'
        self.caminho_prompts = VALIDACAO_CONFIG / 'prompt_variants.json'
        
        # --- 2. CARREGAR MODELOS ---
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"--- RAG V42 (Ollama-Powered Synthesis) ---")
        
        # Embedding local (leve)
        self.embed_model = SentenceTransformer(
            'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2', 
            device=self.device
        )
        
        # Conexão Ollama (Removemos o T5 daqui para liberar a GTX 1050 Ti)
        self.client = AsyncOpenAI(
            base_url='http://localhost:11434/v1', 
            api_key='ollama',
            timeout=120.0
        )
        self.model_name = "qwen2.5:3b"
        
        # --- 3. CARREGAR CONFIGURAÇÕES ---
        self.sinonimos = self.load_json_config(self.caminho_sinonimos, "Synonyms")
        self.prompt_library = self.load_json_config(self.caminho_prompts, "Prompt Variants")
        
        # Define a persona ativa com Fallback CORRETO
        self.set_variant(variant_name)

        # --- 4. CARREGAR BASE DE DADOS ---
        self.documents = []
        self.load_index(json_path)

    def load_json_config(self, path, name):
        if path.exists():
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def load_index(self, json_path):
        with open(json_path, 'r', encoding='utf-8') as f:
            self.documents = json.load(f)
        vectors = [doc['vector'] for doc in self.documents]
        self.index = faiss.IndexFlatL2(len(vectors[0]))
        self.index.add(np.array(vectors).astype('float32'))
        print(f"✅ Knowledge base ready with {len(self.documents)} docs.")

    def set_variant(self, variant_name):
        # CORREÇÃO: Fallback para V1_RESEARCHER (nome exato do seu JSON)
        self.current_variant = self.prompt_library.get(variant_name, self.prompt_library.get("V1_RESEARCHER"))
        print(f"🔄 Active Persona: {variant_name}")

    def identify_model(self, text):
        text_lower = text.lower()
        for modelo_oficial, apelidos in self.sinonimos.items():
            if modelo_oficial.lower() in text_lower or any(a.lower() in text_lower for a in apelidos):
                return modelo_oficial
        return None

    async def search(self, query, current_date_str, top_k=3):
        # 1. Temporal & Model Detection
        modelo_alvo = self.identify_model(query)
        try:
            current_date = datetime.fromisoformat(current_date_str)
        except ValueError:
            current_date = datetime.strptime(current_date_str, "%Y-%m-%d")
        q_year = current_date.year
        
        # 2. Vector Search
        query_vector = self.embed_model.encode([query])
        distances, indices = self.index.search(np.array(query_vector).astype('float32'), k=top_k * 5)
        
        scored_results = []
        for dist, idx in zip(distances[0], indices[0]):
            doc = self.documents[idx]
            doc_date = datetime.fromisoformat(doc['date'])
            if doc_date > current_date: continue 
            
            score = dist
            if modelo_alvo and modelo_alvo.lower() in doc['original_text'].lower():
                score *= 0.6
            
            scored_results.append({'doc': doc, 'score': score})

        scored_results = sorted(scored_results, key=lambda x: x['score'])[:top_k]
        
        if not scored_results:
            return "STATUS: No records found.\nTECHNICAL DETAILS: No history available up to this date."

        # 3. Context
        context_items = [f"- {r['doc']['original_text']}" for r in scored_results]
        context_str = "\n".join(context_items)
        
        # 4. Generation via Ollama
        # Agora acessamos ['task'] com segurança porque as chaves foram corrigidas
        task_f = self.current_variant['task'].format(query=query, q_year=q_year)
        prefix_f = self.current_variant['prefix'].format(query=query, q_year=q_year)
        
        prompt_sistema = f"You are a technical specialist. {task_f}. Use ONLY the evidence provided."
        user_content = f"EVIDENCE:\n{context_str}\n\nQUESTION: {query}\n\nStart with: {prefix_f}"

        try:
            response = await self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": prompt_sistema},
                    {"role": "user", "content": user_content}
                ],
                temperature=0.1
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            return f"IA_FAIL: {str(e)}"