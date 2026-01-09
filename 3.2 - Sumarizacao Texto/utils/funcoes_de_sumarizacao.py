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



