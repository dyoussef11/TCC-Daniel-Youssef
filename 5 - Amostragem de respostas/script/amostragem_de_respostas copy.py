import sys
from pathlib import Path
import pandas as pd
import os
import numpy as np
import re
from sklearn.model_selection import train_test_split
# --- Configuração de Caminho ---
# Navegação para a raiz do projeto para importar 'config'
caminho_script = Path(__file__).resolve().parent
caminho_raiz_projeto = caminho_script.parent.parent
sys.path.append(str(caminho_raiz_projeto))

# Importa os diretórios
from config import DIRETORIO_DADOS_UNIFICACAO,DIRETORIO_DADOS_AMOSTRAGEM,DIRETORIO_DADOS_LINGUAGENS

# Define as PASTAS de entrada
caminho_entrada_respostas_pt_br_dir = DIRETORIO_DADOS_LINGUAGENS / 'dataset_respostas_pt.csv'
caminho_entrada_respostas_en_dir = DIRETORIO_DADOS_LINGUAGENS / 'dataset_respostas_en.csv'

caminho_saida_resposta_amonstrada_pt_br = DIRETORIO_DADOS_AMOSTRAGEM / 'seed_set_para_rotulagem_manual_pt_br.csv' 
caminho_saida_resposta_amonstrada_en = DIRETORIO_DADOS_AMOSTRAGEM / 'seed_set_para_rotulagem_manual_en.csv' 

# Seus dados já foram carregados, usaremos o DataFrame 'df_pt_br'
df_pt_br = pd.read_csv(caminho_entrada_respostas_pt_br_dir) 

# Definindo as categorias para rotulagem
CATEGORIES = [
    "SOLUÇÃO (EFETIVA ou POTENCIAL)",
    "INFORMATIVA/DIAGNÓSTICO",
    "ESPECULATIVA/INVÁLIDA",
    "IRRELEVANTE/FORA DE TÓPICO",
    "FEEDBACK DE FECHAMENTO"
]

# Limpeza básica (preencher NaNs no campo de comentários, se houver)
df_pt_br['Conteudo_Comentario'] = df_pt_br['Conteudo_Comentario'].fillna('')

print(f"Total de comentários no dataset: {len(df_pt_br)}")

# ----------------------------------------------------------------------
# 1. Amostragem (Seed Set)
# ----------------------------------------------------------------------

# Tamanho da amostra que será rotulada manualmente
SAMPLE_SIZE = 1000 

# Garantindo que o tamanho da amostra não exceda o tamanho do DataFrame
if SAMPLE_SIZE > len(df_pt_br):
    SAMPLE_SIZE = len(df_pt_br)

# Amostragem aleatória simples.
# Usamos 'random_state' para garantir a reprodutibilidade.
seed_set = df_pt_br.sample(n=SAMPLE_SIZE, random_state=42)

# Adiciona colunas para a rotulagem manual (uma coluna para cada categoria)
for category in CATEGORIES:
    seed_set[category] = 0 # Inicializado com 0 (Não Rotulado)

# Exemplo de como ficaria o DataFrame para rotulagem manual
print("\n--- Exemplo de DataFrame para Rotulagem Manual (Seed Set) ---")
print(seed_set[['Conteudo_Comentario'] + CATEGORIES].head())

# O próximo passo seria exportar 'seed_set' para um arquivo (e.g., CSV ou Excel)
# para que o(s) humano(s) possa(m) rotulá-lo.
seed_set.to_csv(caminho_saida_resposta_amonstrada_pt_br, index=False)

# Seus dados já foram carregados, usaremos o DataFrame 'df_pt_br'
df_en = pd.read_csv(caminho_entrada_respostas_en_dir) 

# Definindo as categorias para rotulagem
CATEGORIES = [
    "SOLUÇÃO (EFETIVA ou POTENCIAL)",
    "INFORMATIVA/DIAGNÓSTICO",
    "ESPECULATIVA/INVÁLIDA",
    "IRRELEVANTE/FORA DE TÓPICO",
    "FEEDBACK DE FECHAMENTO"
]

# Limpeza básica (preencher NaNs no campo de comentários, se houver)
df_en['Conteudo_Comentario'] = df_en['Conteudo_Comentario'].fillna('')

print(f"Total de comentários no dataset: {len(df_en)}")

# ----------------------------------------------------------------------
# 1. Amostragem (Seed Set)
# ----------------------------------------------------------------------

# Tamanho da amostra que será rotulada manualmente
SAMPLE_SIZE = 1000 

# Garantindo que o tamanho da amostra não exceda o tamanho do DataFrame
if SAMPLE_SIZE > len(df_en):
    SAMPLE_SIZE = len(df_en)

# Amostragem aleatória simples.
# Usamos 'random_state' para garantir a reprodutibilidade.
seed_set = df_en.sample(n=SAMPLE_SIZE, random_state=42)

# Adiciona colunas para a rotulagem manual (uma coluna para cada categoria)
for category in CATEGORIES:
    seed_set[category] = 0 # Inicializado com 0 (Não Rotulado)

# Exemplo de como ficaria o DataFrame para rotulagem manual
print("\n--- Exemplo de DataFrame para Rotulagem Manual (Seed Set) ---")
print(seed_set[['Conteudo_Comentario'] + CATEGORIES].head())

# O próximo passo seria exportar 'seed_set' para um arquivo (e.g., CSV ou Excel)
# para que o(s) humano(s) possa(m) rotulá-lo.
seed_set.to_csv(caminho_saida_resposta_amonstrada_en, index=False)


import pandas as pd
import numpy as np
import re
from pathlib import Path
from langdetect import detect, DetectorFactory

# Garante resultados consistentes na detecção de idioma
DetectorFactory.seed = 42

# --- Configuração de Caminho (Exemplo usando a estrutura que você mencionou) ---
# Substitua pelo seu caminho real para o arquivo original completo
caminho_entrada_respostas_dir = 'respostas_combinadas_final.csv' 

# Caminho de saída para o dataset completo rotulado programaticamente
caminho_saida_weak_labeled_dir = Path('./5 - Amostragem de respostas/data/dataset_weak_labeled_final.csv')

# Supondo que você já carregou o DataFrame df:
# df = pd.read_csv(caminho_entrada_respostas_dir)
# df['Conteudo_Comentario'] = df['Conteudo_Comentario'].fillna('')

# --- Rótulos (CATEGORIES) ---
CATEGORIES = [
    "SOLUÇÃO (EFETIVA ou POTENCIAL)",
    "INFORMATIVA/DIAGNÓSTICO",
    "ESPECULATIVA/INVÁLIDA",
    "IRRELEVANTE/FORA DE TÓPICO",
    "FEEDBACK DE FECHAMENTO"
]

print(f"Total de comentários: {len(df)}")
print("-" * 50)

# ----------------------------------------------------------------------
# PASSO 2.1: Divisão por Idioma (Language Split)
# ----------------------------------------------------------------------

def simple_detect_language(text):
    """Detecta o idioma do texto usando langdetect, com tratamento de erro."""
    try:
        # A detecção é mais confiável com textos mais longos
        if len(text.split()) < 3:
            return 'unknown'
        return detect(text)
    except:
        return 'unknown'

# Aplica a função de detecção no DataFrame completo (PODE DEMORAR um pouco)
print("Detectando idioma do dataset completo...")
df['language'] = df['Conteudo_Comentario'].apply(simple_detect_language)

# Separação dos DataFrames
df_pt = df[df['language'] == 'pt']
df_en = df[df['language'] == 'en']
df_rest = df[~df['language'].isin(['pt', 'en'])] # Textos muito curtos ou outros idiomas

print(f"Comentários PT: {len(df_pt)}")
print(f"Comentários EN: {len(df_en)}")
print(f"Comentários Outros/Não detectados: {len(df_rest)}")
print("-" * 50)

# ----------------------------------------------------------------------
# PASSO 2.2: Funções de Rotulagem (LFs) Específicas
# ----------------------------------------------------------------------

# --- LFs em Português ---
def create_pt_lfs(comment):
    # Dicionário para armazenar a saída multilabel
    labels = {cat: 0 for cat in CATEGORIES}

    # 1. SOLUÇÃO (EFETIVA ou POTENCIAL)
    keywords_solucao = r'\b(tentei|tenta|rodou|funcionou|resolvi|formatar|instala|deu certo)\b'
    if re.search(keywords_solucao, comment.lower()):
        labels["SOLUÇÃO (EFETIVA ou POTENCIAL)"] = 1

    # 2. INFORMATIVA/DIAGNÓSTICO
    keywords_diag = r'\b(erro|bug|versão|hardware|specs|temperatura|ghz|placa|configuraç[ãa]o|qual sua|verifica|driver)\b'
    if re.search(keywords_diag, comment.lower()):
        labels["INFORMATIVA/DIAGNÓSTICO"] = 1

    # 3. ESPECULATIVA/INVÁLIDA
    keywords_especulativa = r'\b(acho que|talvez seja|deve ser|n[ãa]o sei|chutaria|possivelmente|teoria|n[ãa]o entendo)\b'
    # Aplica só se for especulativa e não for uma solução clara
    if re.search(keywords_especulativa, comment.lower()) and labels["SOLUÇÃO (EFETIVA ou POTENCIAL)"] == 0:
        labels["ESPECULATIVA/INVÁLIDA"] = 1

    # 4. IRRELEVANTE/FORA DE TÓPICO
    keywords_irrelevante = r'\b(bom dia|boa tarde|rs|kkk|parab[é]ns|up|venda|compra)\b'
    if len(comment.split()) < 10 and re.search(keywords_irrelevante, comment.lower()):
        labels["IRRELEVANTE/FORA DE TÓPICO"] = 1

    # 5. FEEDBACK DE FECHAMENTO
    keywords_fechamento = r'\b(obrigado|muito obrigado|valeu|agrade[çc]o|fechou|finalizado|vou tentar|ajudou)\b'
    if re.search(keywords_fechamento, comment.lower()):
        labels["FEEDBACK DE FECHAMENTO"] = 1

    return pd.Series(labels)

# --- LFs em Inglês (Tradução da lógica PT) ---
def create_en_lfs(comment):
    labels = {cat: 0 for cat in CATEGORIES}

    # 1. SOLUÇÃO (EFETIVA ou POTENCIAL)
    keywords_solucao = r'\b(try|fixed|worked|reinstall|format|install|solved|did the trick|it worked)\b'
    if re.search(keywords_solucao, comment.lower()):
        labels["SOLUÇÃO (EFETIVA ou POTENCIAL)"] = 1

    # 2. INFORMATIVA/DIAGNÓSTICO
    keywords_diag = r'\b(error|bug|version|hardware|specs|temp|ghz|gpu|config|check your|driver)\b'
    if re.search(keywords_diag, comment.lower()):
        labels["INFORMATIVA/DIAGNÓSTICO"] = 1

    # 3. ESPECULATIVA/INVÁLIDA
    keywords_especulativa = r'\b(i think|maybe it is|could be|i don\'t know|i guess|theory|possibly)\b'
    if re.search(keywords_especulativa, comment.lower()) and labels["SOLUÇÃO (EFETIVA ou POTENCIAL)"] == 0:
        labels["ESPECULATIVA/INVÁLIDA"] = 1

    # 4. IRRELEVANTE/FORA DE TÓPICO
    keywords_irrelevante = r'\b(good morning|lol|haha|congrats|up|selling|buying)\b'
    if len(comment.split()) < 10 and re.search(keywords_irrelevante, comment.lower()):
        labels["IRRELEVANTE/FORA DE TÓPICO"] = 1

    # 5. FEEDBACK DE FECHAMENTO
    keywords_fechamento = r'\b(thanks|thank you|cheers|got it|will try|closed|solved)\b'
    if re.search(keywords_fechamento, comment.lower()):
        labels["FEEDBACK DE FECHAMENTO"] = 1

    return pd.Series(labels)

# ----------------------------------------------------------------------
# PASSO 2.3: Aplicação e Combinação
# ----------------------------------------------------------------------

# Aplica as LFs em Português
print("Aplicando LFs em Português...")
pt_weak_labels = df_pt['Conteudo_Comentario'].apply(create_pt_lfs)
df_pt = pd.concat([df_pt, pt_weak_labels], axis=1)

# Aplica as LFs em Inglês
print("Aplicando LFs em Inglês...")
en_weak_labels = df_en['Conteudo_Comentario'].apply(create_en_lfs)
df_en = pd.concat([df_en, en_weak_labels], axis=1)

# Trata o restante (Outros/Desconhecidos) - não rotulamos
rest_weak_labels = pd.DataFrame(0, index=df_rest.index, columns=CATEGORIES)
df_rest = pd.concat([df_rest, rest_weak_labels], axis=1)

# Combinação dos DataFrames
df_weak_labeled_final = pd.concat([df_pt, df_en, df_rest]).sort_index()

# Renomeando as colunas de rótulo para clareza
label_cols = {col: f"weak_label_{col}" for col in CATEGORIES}
df_weak_labeled_final.rename(columns=label_cols, inplace=True)

# Exportação do resultado
caminho_saida_weak_labeled_dir.parent.mkdir(parents=True, exist_ok=True)
df_weak_labeled_final.to_csv(caminho_saida_weak_labeled_dir, index=False)

print("-" * 50)
print(f"Rotulagem fraca concluída. Dataset salvo em: {caminho_saida_weak_labeled_dir}")
print(f"Total de amostras rotuladas: {len(df_weak_labeled_final)}")