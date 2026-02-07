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

class ThresholdCalibratorRAG:
    def __init__(self, json_path):
        print("--- RAG V43 (Threshold Calibration Tool) ---")
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.embedder = SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2', device=self.device)
        self.tokenizer = AutoTokenizer.from_pretrained("google/flan-t5-large")
        self.model = AutoModelForSeq2SeqLM.from_pretrained("google/flan-t5-large", dtype=torch.float16, device_map="auto")
        
        with open(json_path, 'r', encoding='utf-8') as f:
            self.documents = json.load(f)
        vectors = [np.array(d['vector'], dtype='float32') for d in self.documents]
        self.index = faiss.IndexFlatL2(vectors[0].shape[0])
        self.index.add(np.vstack(vectors))

    def test_thresholds(self, query, query_date_str):
        q_date = datetime.strptime(query_date_str, "%Y-%m-%d")
        q_vec = self.embedder.encode(query)
        distances, indices = self.index.search(np.array([q_vec], dtype='float32'), 10)
        
        # Níveis de teste sugeridos
        thresholds = [1.1, 1.2, 1.3, 1.4, 1.5]
        results = {}

        print(f"\nQUERY: {query}")
        print("-" * 50)

        for t in thresholds:
            valid_docs = []
            for i, idx in enumerate(indices[0]):
                dist = distances[0][i]
                if dist <= t:
                    doc = self.documents[idx]
                    if datetime.fromisoformat(doc['date']) <= q_date:
                        valid_docs.append((doc, dist))
            
            results[t] = len(valid_docs)
            status = "✅ PASS" if len(valid_docs) > 0 else "❌ BLOCKED"
            print(f"Threshold {t}: {status} | Encontrou {len(valid_docs)} documentos relevantes.")

        return results

    def run_expert_analysis(self, query, query_date_str, threshold=1.35):
        """Versão final com a lógica de diagnóstico que você solicitou."""
        q_date = datetime.strptime(query_date_str, "%Y-%m-%d")
        q_vec = self.embedder.encode(query)
        distances, indices = self.index.search(np.array([q_vec], dtype='float32'), 5)
        
        candidates = []
        for i, idx in enumerate(indices[0]):
            dist = distances[0][i]
            if dist > threshold: continue # Filtro Dinâmico
            
            doc = self.documents[idx]
            if datetime.fromisoformat(doc['date']) > q_date: continue
            candidates.append((doc, dist))

        if not candidates:
            return "No specific technical data found for this query within safety thresholds."

        # Priorização Temporal (V32 Logic)
        candidates.sort(key=lambda x: x[0]['date'], reverse=True)
        latest_doc, best_dist = candidates[0]
        latest_year = datetime.fromisoformat(latest_doc['date']).year

        # Extração do Título (Sua solicitação)
        title_match = re.search(r'Title:\s*(.*?)\.', latest_doc['original_text'], re.I)
        res_title = title_match.group(1) if title_match else "General Report"

        # Prompt focado em esclarecimento e eficácia
        prompt = f"""Evidence: {latest_doc['original_text'][:500]}
Task: Explain accurately if the evidence solves: "{query}". 
If the evidence does not mention the specific version or fix, be honest.

TECHNICAL DETAILS:
Currently ({q_date.year}), based on {res_title} ({latest_year}), the records clarify that"""

        inputs = self.tokenizer(prompt, return_tensors="pt", truncation=True).to(self.device)
        outputs = self.model.generate(**inputs, max_new_tokens=250, min_new_tokens=100, num_beams=5, length_penalty=1.5)
        details = self.tokenizer.decode(outputs[0], skip_special_tokens=True)

        return (
            f"DIAGNOSTIC REPORT\n" + "="*40 + "\n"
            f"STATUS (Source): {res_title[:50]}...\n"
            f"MATCH DISTANCE: {best_dist:.4f}\n\n"
            f"TECHNICAL DETAILS:\n{details.strip()}"
        )

if __name__ == "__main__":
    calibrator = ThresholdCalibratorRAG(BASE_PATH)
    
    # 1. Teste de Sensibilidade (Para você achar o valor ideal)
    # Use uma pergunta que você sabe que deu "falso positivo"
    calibrator.test_thresholds("Does the G7 work well with Thunderbolt 3 eGPUs?", "2025-01-01")
    
    # 2. Execução com o melhor threshold encontrado (ex: 1.30)
    print("\n" + "="*50)
    print(calibrator.run_expert_analysis("Does the G7 work well with Thunderbolt 3 eGPUs?", "2025-01-01", threshold=1.30))