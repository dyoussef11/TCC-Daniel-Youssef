import sys
from pathlib import Path
import pandas as pd
import os
import random
import re
import numpy as np
from sklearn.utils import resample # Importação Adicionada para Oversampling Estratificado

# --- Configurações de Caminhos SIMPLIFICADAS ---
# Simplificação: Assumindo que os arquivos de entrada estão no diretório de execução,
# e definindo o diretório de saída.
# --- Configuração de Caminhos ---
caminho_script = Path(__file__).resolve().parent
caminho_raiz_projeto = caminho_script.parent.parent
sys.path.append(str(caminho_raiz_projeto))

from config import DIRETORIO_DADOS_BALANCEAMENTO, DIRETORIO_DADOS_SEPARACAO_TESTE


# --- Constantes dos Arquivos LIMPOS e de SAÍDA (NOMES CORRIGIDOS) ---
# ATENÇÃO: Corrigi a confusão nos nomes de arquivo originais.
PT_INPUT_FILE = "dataset_rotulado_respostas_pt_br_train.csv"
EN_INPUT_FILE = "dataset_rotulado_respostas_en_train.csv"

PT_EQUAL_FILE = "dataset_rotulado_respostas_pt_br_train_balanced.csv"
EN_EQUAL_FILE = "dataset_rotulado_respostas_en_train_balanced.csv"

# Nome da coluna que contém o texto LIMPO e a coluna de rótulo
COLUNA_TEXTO = "Conteudo_Comentario_Limpo"
# COLUNA_LABEL = "label_predito" # Assumindo este nome de coluna
COLUNA_LABEL = "sentiment" # Assumindo este nome de coluna

# --- Dicionários de sinônimos (Inalterados) ---
# ... (sinonimos_pt, sinonimos_en, mapeamento_sinonimos permanecem aqui) ...
sinonimos_pt = {
    'ajuda': ['apoio', 'auxílio', 'suporte', 'socorro', 'assistência', 'amparo', 'colaboração', 'contribuição', 'cooperação', 'mão', 'favor', 'benefício'],
    'obrigado': ['agradecido', 'valeu', 'grato', 'obrigada', 'reconhecido', 'satisfação', 'prazer', 'muito obrigado'],
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

# --- Função de aumento de dados (Inalterada) ---
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
        tokens[idx] = sinonimo

    return "".join(tokens)


# --- 1. Carregar datasets LIMPOS ---
print("Configurando diretórios...")
DIRETORIO_DADOS_BALANCEAMENTO.mkdir(parents=True, exist_ok=True)

try:
    df_pt = pd.read_csv(DIRETORIO_DADOS_SEPARACAO_TESTE / PT_INPUT_FILE)
    df_en = pd.read_csv(DIRETORIO_DADOS_SEPARACAO_TESTE / EN_INPUT_FILE)
except FileNotFoundError as e:
    print(f"Erro ao carregar arquivo LIMPO. Verifique os caminhos e nomes: {e}")
    sys.exit(1)

print("\nTamanhos originais dos datasets LIMPOS:")
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
    df_pt.to_csv(DIRETORIO_DADOS_BALANCEAMENTO / PT_EQUAL_FILE, index=False)
    df_en.to_csv(DIRETORIO_DADOS_BALANCEAMENTO / EN_EQUAL_FILE, index=False)
    sys.exit(0)

print(f"\nPrecisamos aumentar {diferenca} exemplos em {idioma_menor.upper()} para igualar {len(df_maior)}.")

# --- 3. Estratégia melhorada: Oversampling Estratificado + Augmentação ---
print("Iniciando aumento de dados com Estratificação Interna...")

# Passo 1: Oversampling Estratificado no DF menor para melhor balanceamento de classes
print(f"Oversampling das classes minoritárias em {idioma_menor.upper()}...")
df_menor_list = []
# Define o tamanho da classe majoritária no DF minoritário como o novo target
max_class_size = df_menor[COLUNA_LABEL].value_counts().max()

for label in df_menor[COLUNA_LABEL].unique():
    df_label = df_menor[df_menor[COLUNA_LABEL] == label]
    
    # Faz o upsampling (duplicação) da classe para o tamanho da classe majoritária
    # Se já for a maior, resample_size = len(df_label), então não muda (ou duplica o tamanho, mas o target é max_class_size)
    if len(df_label) < max_class_size:
        df_label_resampled = resample(df_label, 
                                      replace=True, 
                                      n_samples=max_class_size, # Aumenta até o tamanho da maior classe
                                      random_state=42)
        df_menor_list.append(df_label_resampled)
    else:
        # Mantém a maior classe como está
        df_menor_list.append(df_label)

df_menor_balanceado = pd.concat(df_menor_list).sample(frac=1, random_state=42).reset_index(drop=True)
print(f"Tamanho do DF menor após estratificação interna: {len(df_menor_balanceado)}")

# Passo 2: Redução/Oversampling do novo DF menor para igualar o tamanho do DF maior
if len(df_menor_balanceado) > len(df_maior):
    # Se o balanceamento interno fez o DF menor ultrapassar o maior, faz o downsampling (amostragem)
    df_menor_expandido = df_menor_balanceado.sample(len(df_maior), replace=False, random_state=42).reset_index(drop=True)
    print(f"Downsampling para igualar o tamanho: {len(df_menor_expandido)}")
else:
    # Caso contrário (mais provável), usa replace=True para Oversampling até o tamanho do DF maior
    df_menor_expandido = df_menor_balanceado.sample(len(df_maior), replace=True, random_state=42).reset_index(drop=True)
    print(f"Oversampling final para igualar o tamanho: {len(df_menor_expandido)}")


# Passo 3: Aumentar parte dos exemplos (ex: 70%) usando a função vetorizada
taxa_aumento = 0.7
num_aumentar = int(len(df_menor_expandido) * taxa_aumento)
indices_aumentar = np.random.choice(df_menor_expandido.index, size=num_aumentar, replace=False)

# Cria uma cópia do DF apenas com os dados a serem aumentados
df_sub = df_menor_expandido.loc[indices_aumentar, :].copy()

# Aplica a função de aumento vetorizada na coluna COLUNA_TEXTO
def aplicar_aumento(row):
    return aumentar_texto(row[COLUNA_TEXTO], idioma_menor)

# Usa .apply() para vetorizar, mas apenas na sub-seleção
df_sub[COLUNA_TEXTO + '_AUMENTADO'] = df_sub.apply(aplicar_aumento, axis=1)

# Atualiza a coluna original apenas onde a augmentação resultou em uma mudança
df_sub['MUDOU'] = (df_sub[COLUNA_TEXTO] != df_sub[COLUNA_TEXTO + '_AUMENTADO'])
alterados = df_sub['MUDOU'].sum()

# Aplica as mudanças de volta ao DF expandido principal
df_menor_expandido.loc[df_sub.index, COLUNA_TEXTO] = np.where(
    df_sub['MUDOU'], 
    df_sub[COLUNA_TEXTO + '_AUMENTADO'], 
    df_sub[COLUNA_TEXTO]
)

print(f"Textos aumentados na coluna '{COLUNA_TEXTO}': {alterados}/{num_aumentar}")


# --- 4. Salvar datasets nivelados ---
if idioma_menor == "pt":
    df_pt_balanced = df_menor_expandido
    df_en_balanced = df_maior
else:
    df_en_balanced = df_menor_expandido
    df_pt_balanced = df_maior

print("\nTamanhos finais:")
print(f"PT: {len(df_pt_balanced)}")
print(f"EN: {len(df_en_balanced)}")

# Salvar os resultados no DIRETORIO_DADOS_BALANCEAMENTO
df_pt_balanced.to_csv(DIRETORIO_DADOS_BALANCEAMENTO / PT_EQUAL_FILE, index=False)
df_en_balanced.to_csv(DIRETORIO_DADOS_BALANCEAMENTO / EN_EQUAL_FILE, index=False)

print(f"\n✔ Datasets salvos com tamanhos iguais em: {DIRETORIO_DADOS_BALANCEAMENTO}")