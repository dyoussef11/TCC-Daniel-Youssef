

import sys
from pathlib import Path
import pandas as pd
# Importa o módulo de detecção
from langdetect import detect, DetectorFactory
import torch
import re
from transformers import pipeline
import pandas as pd
from transformers import XLMRobertaTokenizer, XLMRobertaForSequenceClassification

# --- Configuração de Caminhos ---

# 1. Obtém o caminho absoluto da pasta do script atual.
caminho_script = Path(__file__).resolve().parent

# 2. Acessa a pasta raiz do projeto subindo dois níveis.
caminho_raiz_projeto = caminho_script.parent.parent

# 3. Adiciona o caminho da raiz ao caminho de busca do Python.
sys.path.append(str(caminho_raiz_projeto))

from config import DIRETORIO_DADOS_MODELO_ZERO_SHOT,DIRETORIO_DADOS_LIMPEZA_DATASETS


caminho_entrada_resposta_pt_br = DIRETORIO_DADOS_LIMPEZA_DATASETS / 'dataset_respostas_pt.csv'
caminho_entrada_resposta_en = DIRETORIO_DADOS_LIMPEZA_DATASETS / 'dataset_respostas_en.csv'

caminho_saida_resposta_pt_br = DIRETORIO_DADOS_MODELO_ZERO_SHOT / 'dataset_rotulado_respostas_pt_br.csv'
caminho_saida_resposta_en = DIRETORIO_DADOS_MODELO_ZERO_SHOT / 'dataset_rotulado_respostas_en.csv'

tokenizer = XLMRobertaTokenizer.from_pretrained("joeddav/xlm-roberta-large-xnli")
model = XLMRobertaForSequenceClassification.from_pretrained("joeddav/xlm-roberta-large-xnli")

def dividir_texto(texto, tamanho_max=300):
    frases = re.split(r'(?<=[.!?]) +', texto)
    blocos, bloco_atual = [], ""
    for frase in frases:
        if len(bloco_atual) + len(frase) < tamanho_max:
            bloco_atual += " " + frase
        else:
            blocos.append(bloco_atual.strip())
            bloco_atual = frase
    if bloco_atual:
        blocos.append(bloco_atual.strip())
    return blocos

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
df_pt_br_no_dupl = df_pt_br.drop_duplicates(subset=['Conteudo_Comentario_Limpo'])
# NOVO MODELO ESTÁVEL: facebook/bart-large-mnli
classifier_pt = pipeline(
    "zero-shot-classification",
    model="joeddav/xlm-roberta-large-xnli",
    device=DEVICE,
    tokenizer=tokenizer,
    # use_fast=False
)



# 🎯 NOVO: Rótulos Descritivos e Claros para o ciclo Problema/Solução
# labels_pt_genericos = [
#     "PROPOSTA DE SOLUÇÃO",
#     "DIAGNÓSTICO",
#     "INFORMATIVA",
#     "ESPECULATIVA",
#     "INVÁLIDA",
#     "IRRELEVANTE",
#     "FORA DE TÓPICO",
#     "FEEDBACK DE FECHAMENTO"
# ]

labels_pt_genericos = [
    "PROPOSTA DE SOLUÇÃO/AÇÃO",
    "DIAGNÓSTICO DE PROBLEMA TÉCNICO",
    "INFORMAÇÃO DE CONTEXTO/TUTORIAL",
    "PERGUNTA/DUVIDA SOBRE COMPATIBILIDADE",
    "COMENTÁRIO INVÁLIDO/PLACEHOLDER",
    "COMENTÁRIO DE OPINIÃO/DESABAFO",
    "MENSAGEM NÃO RELACIONADA AO TEMA",
    "FECHAMENTO DE TÓPICO/STATUS DE RESOLUÇÃO"
]

# Aplicar em uma amostra (exemplo: 100 frases)
# subset = df_pt_br_no_dupl["Conteudo_Comentario_Limpo"].dropna().sample(100, random_state=42)
subset = df_pt_br_no_dupl["Conteudo_Comentario_Limpo"]

# subset = df_pt_br["Conteudo_Comentario_Limpo"].dropna().sample(100, random_state=42)

resultados = []

for texto in subset:
    if not isinstance(texto, str) or not texto.strip():
        continue  # pula entradas vazias ou não textuais

    blocos = dividir_texto(str(texto))
    blocos = [b.strip() for b in blocos if b.strip()]  # remove blocos vazios

    if not blocos:
        continue  # pula se o texto ficou sem conteúdo

    predicoes = []
    for bloco in blocos:
        res = classifier_pt(
            bloco,
            labels_pt_genericos,
            multi_label=False,
            hypothesis_template="O conteúdo desta resposta é melhor descrito como uma {}."
        )
        predicoes.append(res)

    
    # --- Combina os resultados dos blocos ---
    # Pega o rótulo mais frequente entre os blocos
    labels_mais_comuns = pd.Series([p["labels"][0] for p in predicoes]).value_counts()
    label_final = labels_mais_comuns.index[0]
    
    # Média das pontuações do rótulo vencedor
    confiancas_label = [
        p["scores"][0]
        for p in predicoes
        if p["labels"][0] == label_final
    ]
    confianca_final = sum(confiancas_label) / len(confiancas_label)
    
    resultados.append({
        "Conteudo_Comentario_Limpo": texto,
        "label_predito": label_final,
        "confianca": round(confianca_final, 3),
        "num_blocos": len(blocos)
    })

df_pred = pd.DataFrame(resultados)
df_pred.to_csv(caminho_saida_resposta_pt_br, index=False)



# ----------------- PARTE 2: INGLÊS -----------------

# Carrega os comentários
df_en = pd.read_csv(caminho_entrada_resposta_en)
df_en_no_dupl = df_en.drop_duplicates(subset=['Conteudo_Comentario_Limpo'])

# NOVO MODELO ESTÁVEL: joeddav/xlm-roberta-large-xnli
# 🛑 CORREÇÃO: Adicionando 'use_fast=False' para evitar o erro de conversão/tiktoken

classifier_en = pipeline("zero-shot-classification",
                         model="facebook/bart-large-mnli", 
                         device=DEVICE)

# 🎯 NOVO: Rótulos Descritivos e Claros para o ciclo Problema/Solução
labels_en_genericos = [
    "SOLUTION PROPOSAL",
    "DIAGNOSIS",

    "INFORMATIVE",

    "SPECULATIVE",

    "INVALID",

    "IRRELEVANT",

    "OFF-TOPIC",

    "CLOSING FEEDBACK"
]

# Aplicar em uma amostra (exemplo: 100 frases)
# subset = df_en["Conteudo_Comentario"].dropna().sample(100, random_state=42)
# subset = df_en["Conteudo_Comentario_Limpo"].dropna().sample(100, random_state=42)
# subset = df_en_no_dupl["Conteudo_Comentario_Limpo"].dropna().sample(100, random_state=42)
subset = df_en_no_dupl["Conteudo_Comentario_Limpo"]
# subset = df_en["Conteudo_Comentario_Limpo"]

resultados = []

for texto in subset:
    if not isinstance(texto, str) or not texto.strip():
        continue  # pula entradas vazias

    blocos = dividir_texto(str(texto))
    blocos = [b.strip() for b in blocos if b.strip()]  # limpa blocos vazios
    if not blocos:
        continue  # se o texto não gerar blocos válidos, pula

    predicoes = []
    for bloco in blocos:
        res = classifier_en(
            bloco,
            labels_en_genericos,
            multi_label=False,
            hypothesis_template="The content of this response is best described as a {}."
        )
        predicoes.append(res)

    
    labels_mais_comuns = pd.Series([p["labels"][0] for p in predicoes]).value_counts()
    label_final = labels_mais_comuns.index[0]
    
    confiancas_label = [
        p["scores"][0]
        for p in predicoes
        if p["labels"][0] == label_final
    ]
    confianca_final = sum(confiancas_label) / len(confiancas_label)
    
    resultados.append({
        "Conteudo_Comentario_Limpo": texto,
        "label_predito": label_final,
        "confianca": round(confianca_final, 3),
        "num_blocos": len(blocos)
    })

df_pred = pd.DataFrame(resultados)
df_pred.to_csv(caminho_saida_resposta_en, index=False)
