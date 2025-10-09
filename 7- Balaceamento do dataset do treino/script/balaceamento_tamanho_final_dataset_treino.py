import sys
from pathlib import Path

# Obtém o caminho absoluto da pasta do script atual.
caminho_script = Path(__file__).resolve().parent
caminho_raiz_projeto = caminho_script.parent.parent
sys.path.append(str(caminho_raiz_projeto))


import pandas as pd
import os
import random
import re
from langdetect import detect, DetectorFactory
from config import DIRETORIO_DADOS_BALANCEAMENTO

# Garante consistência na detecção de idioma
DetectorFactory.seed = 0

def get_language(text):
    try:
        if pd.isna(text) or len(str(text).strip()) < 3:
            return 'unknown'
        return detect(text)
    except:
        return 'unknown'

# Dicionários de sinônimos (mesmos do código anterior)
sinonimos_pt = {
    'ajuda': ['apoio', 'auxílio', 'suporte', 'socorro'],
    'obrigado': ['agradecido', 'valeu', 'grato', 'obrigada'],
    'bom': ['ótimo', 'excelente', 'positivo', 'fantástico'],
    'bem': ['muito', 'bastante', 'corretamente', 'satisfatoriamente'],
    'problema': ['falha', 'defeito', 'dificuldade', 'questão', 'erro'],
    'ruim': ['negativo', 'péssimo', 'lamentável', 'deficiente'],
    'lento': ['devagar', 'demorado', 'atrasado', 'vagoroso']
}

sinonimos_en = {
    'help': ['support', 'assistance', 'aid', 'succor'],
    'thanks': ['grateful', 'thankful', 'much obliged', 'appreciate'],
    'good': ['great', 'excellent', 'positive', 'fantastic'],
    'well': ['very', 'quite', 'correctly', 'satisfactorily'],
    'problem': ['issue', 'fault', 'difficulty', 'question', 'error'],
    'bad': ['negative', 'terrible', 'lamentable', 'poor']
}

mapeamento_sinonimos = {
    'pt': sinonimos_pt,
    'en': sinonimos_en
}

def aumentar_texto(texto, num_aumentacoes, language, max_substituicoes=2):
    if language not in mapeamento_sinonimos:
        return []
    
    sinonimos = mapeamento_sinonimos[language]
    frases_aumentadas = []
    palavras = re.findall(r'\b\w+\b', texto.lower())

    for _ in range(num_aumentacoes):
        nova_frase = list(palavras)
        palavras_disponiveis = [p for p in nova_frase if p in sinonimos]

        if not palavras_disponiveis:
            continue
        
        num_subs = min(len(palavras_disponiveis), random.randint(1, max_substituicoes))
        palavras_escolhidas = random.sample(palavras_disponiveis, num_subs)

        for p in palavras_escolhidas:
            indice = nova_frase.index(p)
            nova_frase[indice] = random.choice(sinonimos[p])

        frases_aumentadas.append(" ".join(nova_frase))

    return frases_aumentadas


# --- 1. Carregar datasets balanceados ---
df_pt = pd.read_csv(os.path.join(DIRETORIO_DADOS_BALANCEAMENTO, "dataset_respostas_pt_train_balanced.csv"))
df_en = pd.read_csv(os.path.join(DIRETORIO_DADOS_BALANCEAMENTO, "dataset_respostas_en_train_balanced.csv"))

print("Tamanhos originais:")
print("PT:", len(df_pt))
print("EN:", len(df_en))

# --- 2. Descobrir maior e menor ---
if len(df_pt) > len(df_en):
    df_maior, df_menor = df_pt, df_en
    idioma_menor = "en"
else:
    df_maior, df_menor = df_en, df_pt
    idioma_menor = "pt"

diferenca = len(df_maior) - len(df_menor)
print(f"\nPrecisamos aumentar {diferenca} exemplos em {idioma_menor.upper()}")

# --- 3. Aumentar o dataset menor ---
novos_dados = []
for i in range(diferenca):
    linha = df_menor.sample(1).iloc[0]
    idioma = idioma_menor
    novos_textos = aumentar_texto(linha["Conteudo_Comentario"], 1, idioma)
    if novos_textos:
        novos_dados.append({"Conteudo_Comentario": novos_textos[0], "sentiment": linha["sentiment"]})

df_menor_aumentado = pd.concat([df_menor, pd.DataFrame(novos_dados)], ignore_index=True)

# --- 4. Salvar os dois nivelados ---
if idioma_menor == "pt":
    df_pt = df_menor_aumentado
    df_en = df_maior
else:
    df_en = df_menor_aumentado
    df_pt = df_maior

print("\nTamanhos finais iguais:")
print("PT:", len(df_pt))
print("EN:", len(df_en))

df_pt.to_csv(os.path.join(DIRETORIO_DADOS_BALANCEAMENTO, "dataset_respostas_pt_train_equal.csv"), index=False)
df_en.to_csv(os.path.join(DIRETORIO_DADOS_BALANCEAMENTO, "dataset_respostas_en_train_equal.csv"), index=False)

print("\n✔ Datasets salvos com tamanhos iguais!")
