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
    
    

# class TimeAwareEmbeddingEnglish:
#     # 1. Mudança principal: O modelo padrão agora é o BERT em inglês (Uncased)
#     def __init__(self, model_name='bert-base-uncased'):
#         # 'all-MiniLM-L6-v2' é nativo em inglês, então funciona perfeitamente aqui
#         self.content_model = SentenceTransformer('all-MiniLM-L6-v2')
        
#         # Carregando tokenizadores/modelos de inglês
#         self.tokenizer = AutoTokenizer.from_pretrained(model_name)
#         self.model = AutoModel.from_pretrained(model_name)
        
#     # def create_temporal_embedding(self, text, timestamp):
#     #     # O encode agora processará o texto em inglês
#     #     content_embed = self.content_model.encode(text)
        
#     #     # A matemática do tempo é universal, não muda nada aqui
#     #     time_embed = self._normalize_time(timestamp)
        
#     #     combined_embed = np.concatenate([content_embed, time_embed])
#     #     return combined_embed

#     def create_temporal_embedding(self, text, timestamp):
#         # 1. Vetor de Conteúdo (384 dimensões)
#         content_embed = self.content_model.encode(text)
        
#         # 2. Vetor de Tempo
#         time_embed = self._normalize_time_cyclic(timestamp)
        
#         # --- A MÁGICA DO TCC (PESO TEMPORAL) ---
#         # Multiplicamos por 10 para que o tempo tenha peso na distância vetorial
#         # Se continuar errando a data, aumente para 20 ou 30.
#         PESO_TEMPORAL = 10.0 
#         time_embed = time_embed * PESO_TEMPORAL 
        
#         # 3. Fusão
#         combined_embed = np.concatenate([content_embed, time_embed])
#         return combined_embed
    
#     def _normalize_time(self, timestamp):
#         year_norm = timestamp.year / 2030
#         month_norm = timestamp.month / 12
#         return np.array([year_norm, month_norm])

class TimeAwareEmbeddingEnglish:
    def __init__(self, model_name='bert-base-uncased'):
        # Modelo eficiente para Inglês
        self.content_model = SentenceTransformer('all-MiniLM-L6-v2')
        
    def create_temporal_embedding(self, text, timestamp):
        # 1. Vetor de Conteúdo (384 dimensões)
        content_embed = self.content_model.encode(text)
        
        # 2. Vetor de Tempo (3 dimensões: Ano, Seno, Cosseno)
        time_embed = self._normalize_time_cyclic(timestamp)
        
        # --- A MÁGICA DO TCC (PESO TEMPORAL) ---
        # Multiplicamos o vetor de tempo para que ele tenha impacto matemático na busca.
        # Sem isso, o texto (384 dimensões) "engole" o tempo (3 dimensões).
        PESO_TEMPORAL = 10.0 
        time_embed = time_embed * PESO_TEMPORAL
        
        # 3. Fusão (387 dimensões)
        combined_embed = np.concatenate([content_embed, time_embed])
        return combined_embed
    
    def _normalize_time_cyclic(self, timestamp):
        """
        Transforma a data em uma representação matemática contínua.
        Isso corrige o erro que você estava vendo.
        """
        # Normalização Linear do Ano (escala suave)
        # Usamos 2018 como base (ano do lançamento do Dell G7)
        year_norm = (timestamp.year - 2018) / 10.0 
        
        # Normalização Cíclica do Mês (Seno e Cosseno)
        # Garante que Dezembro (12) e Janeiro (1) sejam matematicamente próximos
        month_angle = 2 * np.pi * (timestamp.month / 12)
        month_sin = np.sin(month_angle)
        month_cos = np.cos(month_angle)
        
        return np.array([year_norm, month_sin, month_cos], dtype='float32')