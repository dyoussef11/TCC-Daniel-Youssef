
import json
import numpy as np
import torch
import sys
import re
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
    VETORIZATION_CONFIG
)

# Arquivos de Entrada e Saída
CAMINHO_ENTRADA = NER_DATA / 'reddit_dados_com_resumo_llama_aprimorado_ingles.json'
CAMINHO_SAIDA = VETORIZATION_DATA / 'base_conhecimento_multilingue.json'
CAMINHO_SINONIMOS = VETORIZATION_CONFIG/ 'dictionary_synonyms.json'

print("--- INICIANDO VETORIZAÇÃO MULTILÍNGUE COM SINÔNIMOS (V28) ---")

# 1. Carregar Modelo e Dicionário
device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Carregando modelo no {device}...")
model = SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2', device=device)

if CAMINHO_SINONIMOS.exists():
    with open(CAMINHO_SINONIMOS, 'r', encoding='utf-8') as f:
        DICIONARIO_SINONIMOS = json.load(f)
    print(f"✅ Dicionário de sinônimos carregado: {len(DICIONARIO_SINONIMOS)} modelos.")
else:
    print("⚠️ Aviso: Arquivo de sinônimos não encontrado. Usando busca padrão.")
    DICIONARIO_SINONIMOS = {}

# 2. Carregar Dados do Llama
with open(CAMINHO_ENTRADA, 'r', encoding='utf-8') as f:
    dados_reddit = json.load(f)

base_conhecimento = []
count = 0

# 3. Processamento e Enriquecimento

print("Processando posts e gerando embeddings...")
for grupo in dados_reddit:
    modelo_ref = grupo.get('modelo_referencia', 'Unknown')
    # Recupera apelidos do dicionário para injetar no contexto
    apelidos = DICIONARIO_SINONIMOS.get(modelo_ref, [])
    apelidos_str = ", ".join(apelidos) if apelidos else ""

    for post in grupo.get('posts', []):
        analise = post.get('analise_ia', {})
        
        # Ajuste para o schema: summary, specs (ou components), intent
        summary = analise.get('summary', '')
        specs = analise.get('specs', analise.get('components', {}))
        intent = analise.get('intent', 'General')
        
        # Hardware string
        hw_details = [f"{k}: {v}" for k, v in specs.items() if v]
        hw_str = " | ".join(hw_details)
        
        # CONSTRUÇÃO DO TEXTO RICO (Essencial para o FAISS encontrar apelidos como "G7")
        texto_final = (
            f"MODEL: {modelo_ref}. ALIASES: {apelidos_str}. "
            f"Title: {post.get('titulo', '')}. "
            f"Summary: {summary if summary else post.get('conteudo_texto_limpo', '')[:200]}. "
            f"Specs: {hw_str}. "
            f"Intent: {intent}."
        )
        
        # Tratamento de Data
        data_str = post.get('data')
        if not data_str: continue
        try:
            dt = datetime.strptime(data_str, "%Y-%m-%d")
        except:
            dt = datetime.now()
        
        # Gerar o vetor
        vector = model.encode(texto_final)
        
        base_conhecimento.append({
            'id': post.get('id'),
            'vector': vector.tolist(),
            'original_text': texto_final,
            'date': dt.isoformat(),
            'model_tag': modelo_ref
        })
        count += 1

# 4. Salvar Base de Conhecimento
print(f"Salvando {count} vetores em {CAMINHO_SAIDA}...")
with open(CAMINHO_SAIDA, 'w', encoding='utf-8') as f:
    json.dump(base_conhecimento, f, ensure_ascii=False, indent=4)

print("✅ SUCESSO! Base Multilíngue pronta para o RAG Final.")