import json
import faiss
import numpy as np
import torch
import sys
import re
from pathlib import Path
from datetime import datetime
from sentence_transformers import SentenceTransformer
from transformers import T5Tokenizer, T5ForConditionalGeneration


# --- BOOTSTRAP DE CAMINHO DO PROJETO ---
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.paths import (
VALIDACAO_CONFIG
)

class SpecialistTimeAwareRAG:
    def __init__(self, json_path, variant_name="V3_LEAD_DIAGNOSTICIAN"):
        # --- 1. CONFIGURAÇÃO DE CAMINHOS ---
        self.caminho_sinonimos = VALIDACAO_CONFIG / 'dictionary_synonyms.json'
        self.caminho_prompts = VALIDACAO_CONFIG / 'prompt_variants.json'
        
        # --- 2. CARREGAR MODELOS ---
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"--- RAG V41 (Persona-Driven & Time-Aware) ---")
        
        self.embed_model = SentenceTransformer(
            'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2', 
            device=self.device
        )
        
        self.tokenizer = T5Tokenizer.from_pretrained("google/flan-t5-large")
        self.llm = T5ForConditionalGeneration.from_pretrained(
            "google/flan-t5-large", 
            device_map="auto"
        )
        
        # --- 3. CARREGAR CONFIGURAÇÕES ---
        self.sinonimos = self.load_json_config(self.caminho_sinonimos, "Synonyms")
        self.prompt_library = self.load_json_config(self.caminho_prompts, "Prompt Variants")
        
        # Define a persona ativa
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
        """Switches Persona without reloading model weights."""
        self.current_variant = self.prompt_library.get(variant_name, self.prompt_library.get("V1_SCIENTIFIC_RESEARCHER"))
        print(f"🔄 Active Persona: {variant_name}")

    def identify_model(self, text):
        text_lower = text.lower()
        for modelo_oficial, apelidos in self.sinonimos.items():
            if modelo_oficial.lower() in text_lower or any(a.lower() in text_lower for a in apelidos):
                return modelo_oficial
        return None

    def search(self, query, current_date_str, top_k=4):
        # 1. Temporal & Model Detection
        modelo_alvo = self.identify_model(query)
        try:
            current_date = datetime.fromisoformat(current_date_str)
        except ValueError:
            current_date = datetime.strptime(current_date_str, "%Y-%m-%d")
        q_year = current_date.year
        
        # 2. Vector Search
        query_vector = self.embed_model.encode([query])
        distances, indices = self.index.search(np.array(query_vector).astype('float32'), k=top_k * 4)
        
        scored_results = []
        source_titles = []
        
        for dist, idx in zip(distances[0], indices[0]):
            doc = self.documents[idx]
            doc_date = datetime.fromisoformat(doc['date'])
            if doc_date > current_date: continue # Time-Aware Filter
            
            score = dist
            if modelo_alvo and modelo_alvo.lower() in doc['original_text'].lower():
                score *= 0.7 # Synonym Boost
            
            scored_results.append({'doc': doc, 'score': score})
            title_match = re.search(r"Title: (.*?)\.", doc['original_text'])
            if title_match: source_titles.append(title_match.group(1))

        scored_results = sorted(scored_results, key=lambda x: x['score'])[:top_k]
        
        if not scored_results:
            return "STATUS: No records found.\nTECHNICAL DETAILS: No history available up to this date."

        # 3. CONTEXT TRUNCATION (Preventing > 512 tokens error)
       # Remova os rótulos que poluem o contexto
        context_items = []
        for r in scored_results:
            clean_text = r['doc']['original_text'].replace("Summary:", "").replace("Specs:", "").replace("Intent:", "")
            context_items.append(f"- {clean_text[:200]}")
        context_str = "\n".join(context_items)
        
        # 4. PROMPT INJECTION (Persona-Aware)
        task_f = self.current_variant['task'].format(query=query, q_year=q_year)
        prefix_f = self.current_variant['prefix'].format(query=query, q_year=q_year)
        
        prompt = f"""
        SYSTEM: You are a technical support specialist.
        CONTEXT FROM DATABASE:
        {context_str}

        USER QUESTION: {query}
        INSTRUCTION: Based ONLY on the context above, provide a diagnostic. 
        If the information is not present, say it was not found in the records.

        {prefix_f}"""

        inputs = self.tokenizer(prompt, return_tensors="pt", truncation=True, max_length=512).to(self.device)
        outputs = self.llm.generate(
            **inputs, 
            max_new_tokens=350,      # Espaço suficiente para a resposta [cite: 1]
            min_new_tokens=40,       # Força o modelo a desenvolver o texto [cite: 1]
            temperature=0.1,         # Mantém o foco técnico e determinístico [cite: 1]
            repetition_penalty=1.1,  # REDUZIDO: Valores altos causam texto ilegível 
            no_repeat_ngram_size=2,  # Evita repetição de frases sem quebrar termos técnicos 
            do_sample=True
        )
        
        resposta = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
        if "TECHNICAL DETAILS:" not in resposta:
            return f"STATUS: {source_titles[0] if source_titles else 'N/A'}\nTECHNICAL DETAILS: {resposta}"
        return resposta