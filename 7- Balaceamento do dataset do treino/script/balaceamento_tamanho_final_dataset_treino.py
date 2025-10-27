import sys
from pathlib import Path
import pandas as pd
import os
import random
import re
import numpy as np  # Importa numpy para operações eficientes

# --- Configurações de Caminhos ---
caminho_script = Path(__file__).resolve().parent
caminho_raiz_projeto = caminho_script.parent.parent
sys.path.append(str(caminho_raiz_projeto))

from config import DIRETORIO_DADOS_BALANCEAMENTO

# --- Constantes ---
PT_BALANCED_FILE = "dataset_respostas_pt_train_balanced.csv"
EN_BALANCED_FILE = "dataset_respostas_en_train_balanced.csv"
PT_EQUAL_FILE = "dataset_respostas_pt_train_equal.csv"
EN_EQUAL_FILE = "dataset_respostas_en_train_equal.csv"

# --- Dicionários de sinônimos ---
sinonimos_pt = {
    'ajuda': ['apoio', 'auxílio', 'suporte', 'socorro', 'assistência', 'amparo', 'colaboração', 'contribuição', 'cooperação', 'mão', 'favor', 'benefício'],
    'obrigado': ['agradecido', 'valeu', 'grato', 'obrigada', 'reconhecido', 'satisfação', 'prazer', 'muito obrigado'], # 'valeu' é mais informal
    'bom': ['ótimo', 'excelente', 'positivo', 'fantástico', 'maravilhoso', 'agradável', 'favorável', 'proveitoso', 'benéfico', 'apropriado', 'conveniente'],
    'bem': ['muito', 'bastante', 'corretamente', 'satisfatoriamente', 'adequadamente', 'certo', 'apropriadamente', 'ótimo', 'perfeitamente'],
    'problema': ['falha', 'defeito', 'dificuldade', 'questão', 'erro', 'complicação', 'obstáculo', 'impedimento', 'transtorno', 'adversidade', 'dilema', 'assunto'],
    'ruim': ['negativo', 'péssimo', 'lamentável', 'deficiente', 'terrível', 'mau', 'prejudicial', 'desfavorável', 'fraco', 'detestável', 'nefasto'],
    'lento': ['devagar', 'demorado', 'atrasado', 'vagoroso', 'moroso', 'lerdo', 'arrastado', 'indolente', 'pausado', 'tardio']
}

sinonimos_en = {
    'help': ['support', 'assistance', 'aid', 'succor', 'cooperation', 'contribution', 'relief', 'back up', 'advise', 'facilitate', 'serve', 'lend a hand'],
    'thanks': ['grateful', 'thankful', 'much obliged', 'appreciate', 'gratitude', 'acknowledgement', 'recognition', 'cheers'], 
    'good': ['great', 'excellent', 'positive', 'fantastic', 'nice', 'fine', 'wonderful', 'favorable', 'beneficial', 'advantageous', 'pleasant', 'superb'],
    'well': ['very', 'quite', 'correctly', 'satisfactorily', 'properly', 'accurately', 'nicely', 'finely', 'perfectly'],
    'problem': ['issue', 'fault', 'difficulty', 'question', 'error', 'trouble', 'complication', 'obstacle', 'challenge', 'dilemma', 'puzzle', 'snag'],
    'bad': ['negative', 'terrible', 'lamentable', 'poor', 'awful', 'dreadful', 'unpleasant', 'harmful', 'wicked', 'inferior']
}
mapeamento_sinonimos = {
    'pt': sinonimos_pt,
    'en': sinonimos_en
}

# --- Função de aumento de dados ---
def aumentar_texto(texto: str, language: str, max_substituicoes: int = 2) -> str:
    """
    Substitui até 'max_substituicoes' palavras por sinônimos, se disponíveis.
    Retorna o texto aumentado ou o original se nada for substituído.
    """
    if language not in mapeamento_sinonimos:
        return texto
    
    sinonimos = mapeamento_sinonimos[language]
    tokens = re.split(r'(\b\w+\b)', texto)

    indices_candidatos = [i for i, t in enumerate(tokens) if t.lower() in sinonimos]
    if not indices_candidatos:
        return texto

    num_subs = min(len(indices_candidatos), random.randint(1, max_substituicoes))
    indices_a_substituir = random.sample(indices_candidatos, num_subs)

    for idx in indices_a_substituir:
        palavra_original = tokens[idx].lower()
        sinonimo = random.choice(sinonimos[palavra_original])

        if tokens[idx].istitle():
            tokens[idx] = sinonimo.capitalize()
        elif tokens[idx].isupper():
            tokens[idx] = sinonimo.upper()
        else:
            tokens[idx] = sinonimo

    return "".join(tokens)

# --- 1. Carregar datasets ---
try:
    df_pt = pd.read_csv(os.path.join(DIRETORIO_DADOS_BALANCEAMENTO, PT_BALANCED_FILE))
    df_en = pd.read_csv(os.path.join(DIRETORIO_DADOS_BALANCEAMENTO, EN_BALANCED_FILE))
except FileNotFoundError as e:
    print(f"Erro ao carregar arquivo: {e}")
    sys.exit(1)

print("Tamanhos originais:")
print(f"PT: {len(df_pt)}")
print(f"EN: {len(df_en)}")

# --- 2. Descobrir maior e menor ---
if len(df_pt) > len(df_en):
    df_maior, df_menor = df_pt, df_en
    idioma_menor = "en"
else:
    df_maior, df_menor = df_en, df_pt
    idioma_menor = "pt"

diferenca = len(df_maior) - len(df_menor)

if diferenca == 0:
    print("\nOs datasets já possuem o mesmo tamanho. Nenhuma alteração necessária.")
    df_pt.to_csv(os.path.join(DIRETORIO_DADOS_BALANCEAMENTO, PT_EQUAL_FILE), index=False)
    df_en.to_csv(os.path.join(DIRETORIO_DADOS_BALANCEAMENTO, EN_EQUAL_FILE), index=False)
    sys.exit(0)

print(f"\nPrecisamos aumentar {diferenca} exemplos em {idioma_menor.upper()} para igualar {len(df_maior)}.")

# --- 3. Estratégia híbrida: duplicar e aumentar parcialmente ---
print("Iniciando aumento de dados com foco na diversidade...")

# Passo 1: duplicar (garante o mesmo tamanho)
df_menor_expandido = df_menor.sample(len(df_maior), replace=True, random_state=42).reset_index(drop=True)

# Passo 2: aumentar parte dos exemplos (ex: 70%)
taxa_aumento = 0.7
num_aumentar = int(len(df_menor_expandido) * taxa_aumento)
indices_aumentar = np.random.choice(df_menor_expandido.index, size=num_aumentar, replace=False)

alterados = 0
for idx in indices_aumentar:
    texto_original = df_menor_expandido.loc[idx, "Conteudo_Comentario"]
    texto_aumentado = aumentar_texto(texto_original, idioma_menor)
    if texto_aumentado != texto_original:
        df_menor_expandido.loc[idx, "Conteudo_Comentario"] = texto_aumentado
        alterados += 1

print(f"Textos aumentados: {alterados}/{num_aumentar}")

# --- 4. Salvar datasets nivelados ---
if idioma_menor == "pt":
    df_pt = df_menor_expandido
    df_en = df_maior
else:
    df_en = df_menor_expandido
    df_pt = df_maior

print("\nTamanhos finais:")
print(f"PT: {len(df_pt)}")
print(f"EN: {len(df_en)}")

df_pt.to_csv(os.path.join(DIRETORIO_DADOS_BALANCEAMENTO, PT_EQUAL_FILE), index=False)
df_en.to_csv(os.path.join(DIRETORIO_DADOS_BALANCEAMENTO, EN_EQUAL_FILE), index=False)

print("\n✔ Datasets salvos com tamanhos iguais!")
