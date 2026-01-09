# Garante que as bibliotecas necessárias para o pipeline estejam importadas
import pandas as pd
from transformers import pipeline, AutoTokenizer, AutoModelForSeq2SeqLM
from pathlib import Path
import sys
import re 
from langdetect import detect, DetectorFactory
from tqdm import tqdm 
import torch
import warnings
import time

# Suprime avisos
warnings.filterwarnings("ignore", "Your max_length is set to")
warnings.filterwarnings("ignore", category=FutureWarning)

# --- Configuração de Caminhos ---
caminho_script = Path(__file__).resolve().parent
caminho_raiz_projeto = caminho_script.parent.parent
sys.path.append(str(caminho_raiz_projeto))


def preparar_texto_para_sumarizacao(texto, max_tokens=512):
    """
    Prepara o texto para sumarização:
    - Remove ruído
    - Garante tamanho mínimo
    - Trunca se necessário
    """
    if not texto or pd.isna(texto):
        return ""
    
    texto = str(texto).strip()
    
    # Remove múltiplas quebras de linha
    texto = re.sub(r'\n+', ' ', texto)
    
    # Remove espaços múltiplos
    texto = re.sub(r'\s+', ' ', texto)
    
    # Remove marcadores residuais
    texto = re.sub(r'\[USUARIO\]|\[URL\]|\[EMAIL\]', '', texto)
    
    # Tamanho mínimo para sumarização (muito curto = copia)
    if len(texto.split()) < 15:
        return ""  # Ignora textos muito curtos
    
    return texto.strip()



def validar_resumo(resumo, texto_original, min_ratio=0.3, max_ratio=0.9):
    """
    Valida se o resumo é realmente um resumo e não uma cópia.
    """
    if not resumo or not texto_original:
        return False
    
    len_resumo = len(resumo.split())
    len_original = len(texto_original.split())
    
    # Ratio de tamanho
    ratio = len_resumo / len_original if len_original > 0 else 0
    
    # Verifica se não é apenas uma cópia truncada
    if ratio < min_ratio or ratio > max_ratio:
        return True
    
    # Verifica se tem palavras suficientes
    if len_resumo < 10:
        return False
    
    return True
