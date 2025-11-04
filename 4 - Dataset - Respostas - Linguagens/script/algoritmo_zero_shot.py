

import sys
from pathlib import Path
import pandas as pd
# Importa o módulo de detecção
from langdetect import detect, DetectorFactory
import torch

# --- Configuração de Caminhos ---

# 1. Obtém o caminho absoluto da pasta do script atual.
caminho_script = Path(__file__).resolve().parent

# 2. Acessa a pasta raiz do projeto subindo dois níveis.
caminho_raiz_projeto = caminho_script.parent.parent

# 3. Adiciona o caminho da raiz ao caminho de busca do Python.
sys.path.append(str(caminho_raiz_projeto))

from config import DIRETORIO_DADOS_LINGUAGENS,DIRETORIO_DADOS_AMOSTRAGEM

# Importação correta do pipeline
from transformers import pipeline
import pandas as pd

caminho_entrada_resposta_pt_br = DIRETORIO_DADOS_LINGUAGENS / 'dataset_respostas_pt.csv'
caminho_entrada_resposta_en = DIRETORIO_DADOS_LINGUAGENS / 'dataset_respostas_en.csv'

caminho_saida_resposta_pt_br = DIRETORIO_DADOS_AMOSTRAGEM / 'dataset_rotulado_respostas_pt_br.csv'
caminho_saida_resposta_en = DIRETORIO_DADOS_AMOSTRAGEM / 'dataset_rotulado_respostas_en.csv'

# --- Configuração de Dispositivo GPU/CPU ---
if torch.cuda.is_available():
    DEVICE = 0
    print("GPU (CUDA) detectada e será utilizada.")
else:
    DEVICE = -1
    print("GPU não detectada. Utilizando a CPU.")

# Carrega os comentários
df_pt_br = pd.read_csv(caminho_entrada_resposta_pt_br)

# ----------------- PARTE 1: PORTUGUÊS -----------------

# NOVO MODELO ESTÁVEL: facebook/bart-large-mnli
classifier_pt = pipeline("zero-shot-classification",
                         model="facebook/bart-large-mnli", device=DEVICE)

# 🎯 NOVO: Rótulos Descritivos e Claros para o ciclo Problema/Solução
labels_pt_genericos = [
    "SUGESTÃO DE SOLUÇÃO",
    "ANÁLISE OU DIAGNÓSTICO",
    "ESPECULAÇÃO",
    "FORA DO TÓPICO",
    "STATUS E FECHAMENTO"
]

# Aplicar em uma amostra (exemplo: 100 frases)
subset = df_pt_br["Conteudo_Comentario"].dropna().sample(100, random_state=42)

resultados = []
for texto in subset:
    # 🎯 NOVO TEMPLATE: Focado no conteúdo
    res = classifier_pt(
        texto, 
        labels_pt_genericos, 
        multi_label=False, 
        hypothesis_template="O conteúdo desta resposta representa: {}."
    ) 
    resultados.append({
        "texto": texto,
        "label_predito": res["labels"][0],
        "confianca": res["scores"][0]
    })

df_pred = pd.DataFrame(resultados)
df_pred.to_csv(caminho_saida_resposta_pt_br, index=False) # Mudado index=True para False


# ----------------- PARTE 2: INGLÊS -----------------

# Carrega os comentários
df_en = pd.read_csv(caminho_entrada_resposta_en)

# NOVO MODELO ESTÁVEL: facebook/bart-large-mnli
classifier_en = pipeline("zero-shot-classification",
                         model="facebook/bart-large-mnli", device=DEVICE) # Adicionando device=DEVICE

# 🎯 NOVO: Rótulos Descritivos e Claros para o ciclo Problema/Solução
labels_en_genericos = [
    "SOLUTION SUGGESTION",
    "ANALYSIS OR DIAGNOSIS",
    "SPECULATION",
    "OFF-TOPIC",
    "STATUS AND CLOSURE"
]

# Aplicar em uma amostra (exemplo: 100 frases)
subset = df_en["Conteudo_Comentario"].dropna().sample(100, random_state=42)

resultados = []
for texto in subset:
    # 🎯 NOVO TEMPLATE: Focado no conteúdo
    res = classifier_en(
        texto, 
        labels_en_genericos, 
        multi_label=False, 
        hypothesis_template="The content of this reply is: {}."
    )
    resultados.append({
        "texto": texto,
        "label_predito": res["labels"][0],
        "confianca": res["scores"][0]
    })

df_pred = pd.DataFrame(resultados)
df_pred.to_csv(caminho_saida_resposta_en, index=False) # Mudado index=True para False