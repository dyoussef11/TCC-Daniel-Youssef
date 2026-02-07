import json
import numpy as np
import faiss
import torch
import sys
import re
from datetime import datetime
from pathlib import Path
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
from sentence_transformers import SentenceTransformer

# --- CONFIGURAÇÃO DE AMBIENTE ---
script_path = Path(__file__).resolve().parent
project_root = script_path.parent.parent 
sys.path.append(str(project_root))

try:
    from config import DIRETORIO_DADOS_SIST_TIMERAG
except ImportError:
    DIRETORIO_DADOS_SIST_TIMERAG = script_path / 'dados_saida'

BASE_PATH = DIRETORIO_DADOS_SIST_TIMERAG / 'base_conhecimento_multilingue.json'

def clean_system_noise(text):
    """Limpeza agressiva de ruídos para o TCC (e-mails, saudações, lixo de sistema)."""
    noise_patterns = [
        r'(?i)summary:', r'(?i)intent:', r'(?i)components:', r'(?i)suggested_solution:',
        r'(?i)Ttulo:', r'(?i)Resumió', r'(?i)Post \d+:', r'\[Concise summation\]',
        r'[\w\.-]+@[\w\.-]+\.\w+', r'https?://\S+',
        r'(?i)(Happy New Year|Regards|Thank you|Sincerely|Best wishes|Disclaimer)'
    ]
    for pattern in noise_patterns:
        text = re.sub(pattern, '', text)
    return re.sub(r'\s+', ' ', text).strip()

class SpecialistTimeAwareRAG:
    def __init__(self, json_path):
        print("--- RAG V41 (Query-Driven & Source Title Linking) ---")
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.embedder = SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2', device=self.device)
        
        print("Carregando Flan-T5-Large...")
        self.tokenizer = AutoTokenizer.from_pretrained("google/flan-t5-large")
        self.model = AutoModelForSeq2SeqLM.from_pretrained(
            "google/flan-t5-large",
            torch_dtype=torch.float16,
            device_map="auto"
        )
        self.load_index(json_path)

    def load_index(self, path):
        with open(path, 'r', encoding='utf-8') as f:
            self.documents = json.load(f)
        vectors = [np.array(d['vector'], dtype='float32') for d in self.documents]
        self.index = faiss.IndexFlatL2(vectors[0].shape[0])
        self.index.add(np.vstack(vectors))
        print(f"Index carregado: {self.index.ntotal} docs.")

    def search(self, query, query_date_str, k=3):
        # 1. BARREIRA DE ESCOPO
        strict_keywords = ["g3", "g5", "g7", "7588", "3579", "5587", "dell", "legion", "nitro", "hp", "lenovo"]
        if not any(word in query.lower() for word in strict_keywords):
            return "ERROR: Missing hardware reference. Please specify the model for analysis."

        # 2. BUSCA VETORIAL E FILTRO TEMPORAL
        q_date = datetime.strptime(query_date_str, "%Y-%m-%d")
        q_year = q_date.year
        q_vec = self.embedder.encode(query)
        distances, indices = self.index.search(np.array([q_vec], dtype='float32'), 50)
        
        candidates = []
        for i, idx in enumerate(indices[0]):
            if idx == -1: continue
            doc = self.documents[idx]
            doc_dt = datetime.fromisoformat(doc['date'])
            if doc_dt > q_date: continue 
            
            dist = distances[0][i]
            days_diff = max((q_date - doc_dt).days, 1)
            score = ((1 / (1 + dist)) * 0.80) + ((1 / (1 + days_diff/365)) * 0.20)
            candidates.append({'doc': doc, 'score': score})
            
        candidates.sort(key=lambda x: x['score'], reverse=True)
        top_k = candidates[:k]
        
        if not top_k: return "ERROR: No technical records found."

        # 3. EXTRAÇÃO DE TÍTULOS E CONTEXTO
        context_str = ""
        source_titles = []
        for i, c in enumerate(top_k):
            yr = datetime.fromisoformat(c['doc']['date']).year
            full_txt = c['doc']['original_text']
            title_match = re.search(r'Title:\s*(.*?)\.\s*Technical Summary:', full_txt, re.I)
            title = title_match.group(1) if title_match else "Hardware Report"
            source_titles.append(f"'{title}' ({yr})")
            
            clean_txt = clean_system_noise(full_txt)
            context_str += f"[Source {i+1}]: {clean_txt[:350]}\n\n"

        # 4. PROMPT V41: FOCO NA RESPOSTA DA PERGUNTA
        # A pergunta agora vem DEPOIS do contexto para o modelo não esquecê-la
        prompt = f"""Hardware Evidence:
{context_str}

Task: Use the Evidence above to solve the question: "{query}"
Format the response exactly as follows:
STATUS: Brief mention of the titles {', '.join(source_titles[:1])}
TECHNICAL DETAILS: Currently ({q_year}), regarding {query}, the analysis of the records shows that"""

        inputs = self.tokenizer(prompt, return_tensors="pt", truncation=True, max_length=512).to(self.device)

        # 5. GERAÇÃO DETERMINÍSTICA (Ajustada para o gatilho final)
        outputs = self.model.generate(
            **inputs, 
            max_new_tokens=400, 
            min_new_tokens=150,
            num_beams=5,
            length_penalty=1.8,
            repetition_penalty=1.6, # Impede o modelo de copiar o prompt
            no_repeat_ngram_size=3
        )

        generated = self.tokenizer.decode(outputs[0], skip_special_tokens=True)

        # 6. RECONSTRUÇÃO DO RELATÓRIO
        res_status = source_titles[0] if source_titles else "General Analysis"
        res_details = generated

        if "TECHNICAL DETAILS:" in generated:
            res_details = generated.split("TECHNICAL DETAILS:")[1].strip()
        
        # Garante que o texto comece com a âncora se o modelo a ignorou
        if not res_details.lower().startswith(f"currently ({q_year})"):
            res_details = f"Currently ({q_year}), regarding {query}, the records indicate that " + res_details

        return (
            f"HARDWARE ANALYSIS: {query_date_str}\n" + "="*40 + "\n"
            f"STATUS (Sources): {res_status}\n\n"
            f"TECHNICAL DETAILS:\n{res_details}\n"
        )

