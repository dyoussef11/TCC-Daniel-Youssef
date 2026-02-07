import json
import numpy as np
import torch
import sys
from pathlib import Path
from datetime import datetime
from sentence_transformers import SentenceTransformer

# --- CONFIGURAÇÃO DE CAMINHOS ---
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

print("--- INICIANDO VETORIZAÇÃO MULTILÍNGUE (V27 COMPATIBLE) ---")

# 1. Carregar Modelo Multilíngue
device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Carregando modelo no {device}...")
model = SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2', device=device)

# 2. Carregar Dados do Llama
with open(CAMINHO_ENTRADA, 'r', encoding='utf-8') as f:
    dados_reddit = json.load(f)

base_conhecimento = []
count = 0

# 3. Processamento com Enriquecimento de Metadados
print("Processando posts e gerando embeddings...")
for grupo in dados_reddit:
    for post in grupo.get('posts', []):
        
        # Extração de dados da análise da IA
        analise = post.get('analise_ia', {})
        summary = analise.get('summary', '')
        components = analise.get('components', {})
        intent = analise.get('intent', 'General')
        
        # Identificação do Modelo (Crucial para o RAG V27)
        # Se o Llama não identificou, usamos um valor padrão
        laptop_model = components.get('MODEL') if components.get('MODEL') else "Unknown Model"
        
        # Criar string de Hardware (CPU, GPU, RAM)
        hw_details = [f"{k}: {v}" for k, v in components.items() if v and k != 'MODEL']
        hw_str = " | ".join(hw_details)
        
        # --- CONSTRUÇÃO DO TEXTO RICO (METADATA-ENRICHED) ---
        # Adicionamos a tag MODEL: de forma explícita para o RAG dinâmico encontrar
        texto_final = (
            f"MODEL: {laptop_model}. "
            f"Title: {post.get('titulo_limpo')}. "
            f"Technical Summary: {summary if summary else post.get('conteudo_texto_limpo', '')[:200]}. "
            f"Hardware Specs: {hw_str}. "
            f"Intent: {intent}."
        )
        
        # Timestamp para filtro temporal
        ts = post.get('timestamp')
        if not ts: continue
        dt = datetime.fromtimestamp(ts)
        
        # Gerar o vetor (Embedding)
        vector = model.encode(texto_final)
        
        base_conhecimento.append({
            'id': post.get('id_post'),
            'vector': vector.tolist(),
            'original_text': texto_final, # O RAG lerá este texto rico
            'date': dt.isoformat(),
            'model_tag': laptop_model # Campo extra para facilitar filtros futuros
        })
        count += 1

# 4. Salvar Base de Conhecimento
print(f"Salvando {count} vetores em {CAMINHO_SAIDA}...")
with open(CAMINHO_SAIDA, 'w', encoding='utf-8') as f:
    json.dump(base_conhecimento, f, ensure_ascii=False)

print("✅ SUCESSO! Base Multilíngue Pronta para Descoberta Dinâmica.")