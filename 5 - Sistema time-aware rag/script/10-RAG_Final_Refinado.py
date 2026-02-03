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

# --- CONFIGURAÇÃO ---
caminho_script = Path(__file__).resolve().parent
caminho_raiz_projeto = caminho_script.parent.parent 
sys.path.append(str(caminho_raiz_projeto))
try:
    from config import DIRETORIO_DADOS_SIST_TIMERAG
except ImportError:
    DIRETORIO_DADOS_SIST_TIMERAG = caminho_script / 'dados_saida'

CAMINHO_BASE = DIRETORIO_DADOS_SIST_TIMERAG / 'base_conhecimento_multilingue.json'

class SpecialistTimeAwareRAG:
    def __init__(self, json_path):
        print("--- RAG V14 (Model Validation & Expert Output) ---")
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.embedder = SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2', device=self.device)
        
        # Carregamento em float16 (dtype) para economizar VRAM na GTX 1050 Ti
        print("Carregando Flan-T5-Large...")
        self.tokenizer = AutoTokenizer.from_pretrained("google/flan-t5-large")
        self.model = AutoModelForSeq2SeqLM.from_pretrained(
            "google/flan-t5-large",
            torch_dtype=torch.float16, # Mantendo float16 para performance
            device_map="auto"
        )
        self.load_index(json_path)

    def load_index(self, path):
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        vectors = [np.array(d['vector'], dtype='float32') for d in data]
        self.documents = data
        self.index = faiss.IndexFlatL2(vectors[0].shape[0])
        self.index.add(np.vstack(vectors))
        print(f"Índice: {self.index.ntotal} docs.")

    def search(self, query, query_date_str, k=3):
        # 1. Validação de Modelo (Essencial para o TCC)
        model_keywords = ["g7", "7588", "g3", "g5", "dell", "legion", "nitro", "7590", "laptop", "notebook"]
        if not any(word in query.lower() for word in model_keywords):
            return "ERROR: Please specify the laptop model for an accurate analysis."

        q_date = datetime.strptime(query_date_str, "%Y-%m-%d")
        q_vec = self.embedder.encode(query)
        distances, indices = self.index.search(np.array([q_vec], dtype='float32'), 100)
        
        candidates = []
        for i, idx in enumerate(indices[0]):
            if idx == -1: continue
            doc = self.documents[idx]
            try:
                doc_dt = datetime.fromisoformat(doc['date'])
                if doc_dt > q_date: continue
            except: continue
            
            dist = distances[0][i]
            days_diff = (q_date - doc_dt).days
            score = ((1 / (1 + dist)) * 0.85) + ((1 / (1 + days_diff/365)) * 0.15)
            candidates.append({'doc': doc, 'score': score})
            
        candidates.sort(key=lambda x: x['score'], reverse=True)
        top_k = candidates[:k]
        
        if not top_k: return "No records found for this period."

        context_str = ""
        for i, c in enumerate(top_k):
            # Limpeza radical de ruído para o T5-Large
            text = c['doc']['original_text'][:300].strip().replace('\n', ' ')
            context_str += f"Post {i+1}: {text}\n"

        # --- PROMPT V18: CLEAN LOGIC (SEM METALINGUAGEM) ---
        prompt = f"""Task: Analyze the laptop status based on user reviews.
        Question: {query}
        Date Context: {query_date_str}

        Reviews:
        {context_str}

        Structured Answer:
        STATUS: 
        DETAILS: 
        VERDICT: """

        inputs = self.tokenizer(prompt, return_tensors="pt", truncation=True, max_length=512).to(self.device)

        # Otimização de Geração para GTX 1050 Ti
        outputs = self.model.generate(
            **inputs, 
            max_new_tokens=150, 
            min_new_tokens=35,      # Força o modelo a desenvolver os detalhes
            num_beams=5, 
            repetition_penalty=1.3, # Permite termos técnicos repetidos sem "travar"
            no_repeat_ngram_size=3,
            early_stopping=True
        )

        generated = self.tokenizer.decode(outputs[0], skip_special_tokens=True)

        # --- PÓS-PROCESSAMENTO V20: RECONSTRUÇÃO POR PARTIÇÃO ---
        # 1. Limpeza de ruído e normalização
        raw_text = generated.replace("(Summarize in 3 words)", "").replace("(Final advice)", "")
        raw_text = re.sub(r'\[.*?\]', '', raw_text) # Remove qualquer coisa entre colchetes
        
        # 2. Extração de Conteúdo (Garante que pegamos o texto mesmo sem as tags certas)
        # Removemos as tags existentes para re-organizar
        clean_content = re.sub(r'(?i)(STATUS:|DETAILS:|VERDICT:)', '|||', raw_text)
        parts = [p.strip() for p in clean_content.split('|||') if p.strip()]

        # 3. Mapeamento Lógico
        # STATUS: Geralmente a primeira frase curta
        # DETAILS: O corpo técnico
        # VERDICT: A recomendação final
        status = "Issue Reported"
        details = "Technical details extracted from community discussions."
        verdict = "Monitoring and thermal maintenance recommended."

        if len(parts) >= 1:
            status = parts[0].split('.')[0] # Pega só a primeira frase curta para o Status
        if len(parts) >= 2:
            details = parts[1] if len(parts[1]) > 10 else parts[0]
        if len(parts) >= 3:
            verdict = parts[2]
        elif len(parts) == 1 and "." in parts[0]:
            # Fallback caso ele tenha gerado um blocão sem tags
            sub_parts = parts[0].split(". ", 1)
            status = sub_parts[0]
            details = sub_parts[1]

        # 4. Montagem Final (Garante a ordem G7 -> Status -> Details -> Verdict)
        final_report = (
            f"MODEL: DELL G7 7588\n"
            f"DATE: {query_date_str}\n"
            f"{'-'*30}\n"
            f"STATUS: {status.replace('STATUS:', '').strip()}\n"
            f"DETAILS: {details.replace('DETAILS:', '').strip()}\n"
            f"VERDICT: {verdict.replace('VERDICT:', '').strip()}"
        )

        return final_report

if __name__ == "__main__":
    # Certifique-se de que a base de dados aponta para o seu arquivo traduzido pelo Llama
    rag = SpecialistTimeAwareRAG(CAMINHO_BASE) 
    
    print("\n" + "="*50)
    print("ANÁLISE TÉCNICA (DELL G7 - 2018):")
    # Agora com o T5-Large, ele deve sintetizar os posts sobre o i7-8750H e McAfee
    print(rag.search("Does the Dell G7 7588 have overheating issues?", "2018-12-01"))