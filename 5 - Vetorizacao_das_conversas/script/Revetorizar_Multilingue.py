import json
import numpy as np
import torch
import sys
from pathlib import Path
from datetime import datetime
from sentence_transformers import SentenceTransformer


# --- BOOTSTRAP DE CAMINHO DO PROJETO ---
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.paths import (
    NER_DATA,
    VETORIZATION_DATA,
)

# Certifique-se de que este arquivo foi gerado com o prompt rígido (summary, specs, intent)
CAMINHO_ENTRADA = NER_DATA / 'reddit_dados_com_resumo_llama_aprimorado_ingles.json'
CAMINHO_SAIDA = VETORIZATION_DATA / 'base_conhecimento_multilingue.json'

print("--- INICIANDO VETORIZAÇÃO MULTILÍNGUE (V27 COMPATIBLE) ---")

device = "cuda" if torch.cuda.is_available() else "cpu"
model = SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2', device=device)

with open(CAMINHO_ENTRADA, 'r', encoding='utf-8') as f:
    dados_reddit = json.load(f)

base_conhecimento = []
count = 0

print("Processando posts e gerando embeddings...")
for grupo in dados_reddit:
    # Captura o modelo de referência do grupo caso a IA falhe em detectar individualmente
    modelo_grupo = grupo.get('modelo_referencia', 'Unknown')
    
    for post in grupo.get('posts', []):
        analise = post.get('analise_ia', {})
        
        # Ajuste para o novo Schema Rígido
        summary = analise.get('summary', '')
        specs = analise.get('specs', {}) # Mudamos de components para specs
        intent = analise.get('intent', 'General')
        suggested_solution = analise.get('suggested_solution')
        
        # Detalhes de Hardware
        hw_details = [f"{k}: {v}" for k, v in specs.items() if v]
        hw_str = " | ".join(hw_details)
        
        # --- CONSTRUÇÃO DO TEXTO RICO ---
        # Usamos o modelo do grupo se a IA não for específica
        texto_final = (
            f"MODEL: {modelo_grupo}. "
            f"Title: {post.get('titulo', '')}. "
            f"Technical Summary: {summary if summary else post.get('conteudo_texto_limpo', '')[:200]}. "
            f"Hardware Specs: {hw_str}. "
            f"Intent: {intent}."
        )
        
        # TRATAMENTO DE DATA (String para ISO)
        data_str = post.get('data') # No seu JSON é 'data'
        if not data_str:
            continue
            
        try:
            # Converte '2026-01-23' para objeto datetime
            dt = datetime.strptime(data_str, "%Y-%m-%d")
        except:
            # Fallback caso o formato mude
            dt = datetime.now()
        
        # Gerar o vetor
        vector = model.encode(texto_final)
        
        base_conhecimento.append({
            'id': post.get('id'), # No seu JSON é 'id'
            'vector': vector.tolist(),
            'original_text': texto_final,
            'date': dt.isoformat(),
            'model_tag': modelo_grupo
        })
        count += 1

# 4. Salvar Base de Conhecimento
if count > 0:
    print(f"Salvando {count} vetores em {CAMINHO_SAIDA}...")
    with open(CAMINHO_SAIDA, 'w', encoding='utf-8') as f:
        json.dump(base_conhecimento, f, ensure_ascii=False, indent=4)
    print("✅ SUCESSO! Base Multilíngue Pronta.")
else:
    print("❌ ERRO: Nenhum post foi processado. Verifique os campos de 'data' no JSON.")