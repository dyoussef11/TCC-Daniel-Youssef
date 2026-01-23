import sys
import json
import re
from pathlib import Path
from openai import OpenAI
import numpy as np
import torch
from sentence_transformers import SentenceTransformer
from transformers import AutoModel, AutoTokenizer

# --- 1. CONFIGURAÇÕES E CAMINHOS ---
caminho_script = Path(__file__).resolve().parent
caminho_raiz_projeto = caminho_script.parent.parent 
sys.path.append(str(caminho_raiz_projeto))

try:
    from config import DIRETORIO_DADOS_RESUMO_CONVERSAS, DIRETORIO_DADOS_PRE_PROCESSAMENTO
except ImportError:
    print("Aviso: Módulos de configuração não encontrados. Usando caminhos locais.")
    DIRETORIO_DADOS_PRE_PROCESSAMENTO = caminho_script / 'dados_saida'
    DIRETORIO_DADOS_RESUMO_CONVERSAS = caminho_script / 'dados_saida'

CAMINHO_ENTRADA_JSON = DIRETORIO_DADOS_PRE_PROCESSAMENTO / 'reddit_dados_limpos_enriquecidos.json'
CAMINHO_SAIDA_JSON = DIRETORIO_DADOS_RESUMO_CONVERSAS / 'reddit_dados_com_resumo_llama_definitivo.json'

# class TimeAwareEmbedding:
#     def __init__(self, model_name='neuralmind/bert-base-portuguese-cased'):
#         self.content_model = SentenceTransformer('all-MiniLM-L6-v2')
#         self.tokenizer = AutoTokenizer.from_pretrained(model_name)
#         self.model = AutoModel.from_pretrained(model_name)
        
#     def create_temporal_embedding(self, text, timestamp):
#         # Embedding de conteúdo
#         content_embed = self.content_model.encode(text)
        
#         # Embedding temporal (normalizado)
#         time_embed = self._normalize_time(timestamp)
        
#         # Concatenar ou combinar
#         combined_embed = np.concatenate([content_embed, time_embed])
#         return combined_embed
    
#     def _normalize_time(self, timestamp):
#         # Normalizar timestamp para embedding
#         year_norm = timestamp.year / 2030
#         month_norm = timestamp.month / 12
#         return np.array([year_norm, month_norm])
    
    

class TimeAwareEmbeddingEnglish:
    # 1. Mudança principal: O modelo padrão agora é o BERT em inglês (Uncased)
    def __init__(self, model_name='bert-base-uncased'):
        # 'all-MiniLM-L6-v2' é nativo em inglês, então funciona perfeitamente aqui
        self.content_model = SentenceTransformer('all-MiniLM-L6-v2')
        
        # Carregando tokenizadores/modelos de inglês
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModel.from_pretrained(model_name)
        
    def create_temporal_embedding(self, text, timestamp):
        # O encode agora processará o texto em inglês
        content_embed = self.content_model.encode(text)
        
        # A matemática do tempo é universal, não muda nada aqui
        time_embed = self._normalize_time(timestamp)
        
        combined_embed = np.concatenate([content_embed, time_embed])
        return combined_embed
    
    def _normalize_time(self, timestamp):
        year_norm = timestamp.year / 2030
        month_norm = timestamp.month / 12
        return np.array([year_norm, month_norm])