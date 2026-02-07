
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
    """Limpeza profunda para evitar que o modelo use lixo de sistema na resposta."""
    noise_patterns = [
        r'(?i)summary:', r'(?i)intent:', r'(?i)components:', r'(?i)suggested_solution:',
        r'(?i)Ttulo:', r'(?i)Resumió', r'(?i)Post \d+:', r'\[Concise summation\]',
        r'[\w\.-]+@[\w\.-]+\.\w+', r'https?://\S+',
        r'(?i)(Happy New Year|Best wishes|Regards|Thank you|Sincerely|Disclaimer)'
    ]
    for pattern in noise_patterns:
        text = re.sub(pattern, '', text)
    return re.sub(r'\s+', ' ', text).strip()

class SpecialistTimeAwareRAG:
    def __init__(self, json_path):
        print("--- RAG V42 (Context Grounding & Safety Threshold) ---")
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.embedder = SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2', device=self.device)
        
        print("Carregando Flan-T5-Large em float16...")
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
        # 1. BARREIRA DE ESCOPO (HARDWARE CHECK)
        strict_keywords = ["g3", "g5", "g7", "7588", "3579", "5587", "dell", "legion", "nitro", "hp", "lenovo"]
        if not any(word in query.lower() for word in strict_keywords):
            return "ERROR: Missing hardware reference. Specify the model (e.g., G7 7588)."

        # 2. BUSCA VETORIAL E FILTRO TEMPORAL
        q_date = datetime.strptime(query_date_str, "%Y-%m-%d")
        q_vec = self.embedder.encode(query)
        distances, indices = self.index.search(np.array([q_vec], dtype='float32'), 50)
        
        candidates = []
        for i, idx in enumerate(indices[0]):
            if idx == -1: continue
            
            # --- NOVIDADE V42: THRESHOLD DE SEGURANÇA ---
            # Distância L2 menor que 1.1 costuma ser um bom match semântico.
            # Se for maior que 1.4, o post é provavelmente irrelevante.
            if distances[0][i] > 1.15: continue 
            
            doc = self.documents[idx]
            doc_dt = datetime.fromisoformat(doc['date'])
            if doc_dt > q_date: continue 
            
            dist = distances[0][i]
            days_diff = max((q_date - doc_dt).days, 1)
            score = ((1 / (1 + dist)) * 0.80) + ((1 / (1 + days_diff/365)) * 0.20)
            candidates.append({'doc': doc, 'score': score, 'dist': dist})
            
        candidates.sort(key=lambda x: x['score'], reverse=True)
        top_k = candidates[:k]
        
        if not top_k:
            return "ERROR: No relevant technical information was found in the database for this specific query."

        # 3. CONSTRUÇÃO DO CONTEXTO E TÍTULOS
        context_str = ""
        source_titles = []
        for i, c in enumerate(top_k):
            yr = datetime.fromisoformat(c['doc']['date']).year
            full_txt = c['doc']['original_text']
            title_match = re.search(r'Title:\s*(.*?)\.\s*Technical Summary:', full_txt, re.I)
            title = title_match.group(1) if title_match else "Hardware Report"
            source_titles.append(f"'{title}' ({yr})")
            context_str += f"[Evidence {i+1}]: {clean_system_noise(full_txt)[:400]}\n\n"

        # 4. PROMPT V42: STRICT GROUNDING (Fidelidade aos Dados)
        # O prompt agora proíbe o modelo de usar conhecimento externo.
        prompt = f"""Target: Technical Hardware Analysis
Reference Date: {query_date_str}

TECHNICAL EVIDENCE:
{context_str}

STRICT INSTRUCTIONS:
- Use ONLY the evidence provided above. 
- If the evidence does not mention the BIOS version or specific component asked in "{query}", state exactly: "No specific information regarding this component was found in the records."
- Focus on technical facts (fixes, temperatures, parts).

REPORT:
STATUS: Brief summary of the source: {source_titles[0]}
TECHNICAL DETAILS: Currently ({q_date.year}), after analyzing the technical records regarding '{query}', I found that"""

        inputs = self.tokenizer(prompt, return_tensors="pt", truncation=True, max_length=1024).to(self.device)

        # 5. GERAÇÃO DETERMINÍSTICA (Alta Penalidade de Repetição)
        outputs = self.model.generate(
            **inputs, 
            max_new_tokens=450, 
            min_new_tokens=150,      # Força o detalhamento técnico
            num_beams=8,
            length_penalty=2.0, 
            repetition_penalty=1.8,  # Bloqueia a repetição do prompt e alucinações
            no_repeat_ngram_size=3,
            early_stopping=True
        )

        generated = self.tokenizer.decode(outputs[0], skip_special_tokens=True)

        # 6. RECONSTRUÇÃO FINAL
        res_details = generated
        if "TECHNICAL DETAILS:" in generated:
            res_details = generated.split("TECHNICAL DETAILS:")[1].strip()
        
        # Garante a âncora narrativa
        if not res_details.lower().startswith(f"currently ({q_date.year})"):
            res_details = f"Currently ({q_date.year}), regarding {query}, the records indicate that " + res_details

        return (
            f"HARDWARE ANALYSIS REPORT\n" + "="*40 + "\n"
            f"QUERY: {query}\n"
            f"SOURCES: {', '.join(source_titles)}\n\n"
            f"STATUS: {source_titles[0]}\n\n"
            f"TECHNICAL DETAILS:\n{res_details}\n"
        )

if __name__ == "__main__":
    rag = SpecialistTimeAwareRAG(BASE_PATH)
    print("\n" + "="*50)
    # Teste de Grounding: Se o post não falar de BIOS, ele deve admitir.
    print(rag.search("Does BIOS 1.9.0 improve thermal limits on the G7 7588?", "2020-05-10"))