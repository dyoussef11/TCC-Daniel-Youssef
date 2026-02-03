import json
import numpy as np
import torch
import sys
from pathlib import Path
from datetime import datetime
from sentence_transformers import SentenceTransformer

# --- CONFIGURAÇÃO ---
caminho_script = Path(__file__).resolve().parent
caminho_raiz_projeto = caminho_script.parent.parent 
sys.path.append(str(caminho_raiz_projeto))

try:
    from config import DIRETORIO_DADOS_RESUMO_CONVERSAS, DIRETORIO_DADOS_SIST_TIMERAG
except ImportError:
    DIRETORIO_DADOS_SIST_TIMERAG = caminho_script / 'dados_saida'
    DIRETORIO_DADOS_RESUMO_CONVERSAS = caminho_script / 'dados_saida'

CAMINHO_ENTRADA = DIRETORIO_DADOS_RESUMO_CONVERSAS / 'reddit_dados_com_resumo_llama_aprimorado_ingles.json'
CAMINHO_SAIDA = DIRETORIO_DADOS_SIST_TIMERAG / 'base_conhecimento_multilingue.json'

print("--- INICIANDO VETORIZAÇÃO MULTILÍNGUE ---")

# 1. Carregar Modelo Multilíngue (O Segredo!)
# Este modelo mapeia "Overheating" (EN) e "Superaquecimento" (PT) para o MESMO lugar.
device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Carregando modelo 'paraphrase-multilingual-MiniLM-L12-v2' no {device}...")
model = SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2', device=device)

# 2. Carregar Dados
with open(CAMINHO_ENTRADA, 'r', encoding='utf-8') as f:
    dados_reddit = json.load(f)

base_conhecimento = []

# 3. Processar
print("Processando posts...")
count = 0
for grupo in dados_reddit:
    for post in grupo.get('posts', []):
        
        # Extrair dados
        analise = post.get('analise_ia', {})
        titulo = post.get('titulo_limpo', '')
        resumo = analise.get('resumo', post.get('conteudo_texto_limpo', ''))
        
        # Construir Texto Rico (Mistura PT/EN não é problema para este modelo)
        texto_final = f"Título: {titulo}. Resumo: {resumo}"
        
        # Timestamp
        ts = post.get('timestamp')
        if not ts: continue
        dt = datetime.fromtimestamp(ts)
        
        # --- TRUQUE DO EMBEDDING TEMPORAL MANUAL ---
        # Como mudamos o modelo, vamos fazer um embedding simples de texto primeiro
        # A parte temporal será tratada apenas na busca (Reranking) para simplificar
        vector = model.encode(texto_final)
        
        base_conhecimento.append({
            'id': post.get('id_post'),
            'vector': vector.tolist(), # Converter numpy para lista
            'original_text': texto_final,
            'date': dt.isoformat()
        })
        count += 1

print(f"Salvando {count} vetores em {CAMINHO_SAIDA}...")
with open(CAMINHO_SAIDA, 'w', encoding='utf-8') as f:
    json.dump(base_conhecimento, f, ensure_ascii=False)

print("✅ SUCESSO! Base Multilíngue Criada.")