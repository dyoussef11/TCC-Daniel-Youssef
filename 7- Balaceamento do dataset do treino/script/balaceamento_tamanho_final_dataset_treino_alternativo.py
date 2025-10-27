import sys
from pathlib import Path
import pandas as pd
import os
import random
import re
import numpy as np

# --- Configurações de Caminhos ---
caminho_script = Path(__file__).resolve().parent
caminho_raiz_projeto = caminho_script.parent.parent
sys.path.append(str(caminho_raiz_projeto))

# Tentar importar as variáveis de configuração
try:
    from config import DIRETORIO_DADOS_BALANCEAMENTO, DIRETORIO_DADOS_SEPARACAO_TESTE
except ImportError:
    print("ERRO: Módulo 'config' não encontrado. Defina caminhos de fallback.")
    # Fallback para execução
    DIRETORIO_DADOS_BALANCEAMENTO = Path('./dados_balanceados_saida')
    DIRETORIO_DADOS_LIMPEZA = Path('./dados_limpos_simplified')


# --- Constantes dos Arquivos LIMPOS e de SAÍDA ---
PT_INPUT_FILE = "dataset_respostas_pt_limpo_train.csv"
EN_INPUT_FILE = "dataset_respostas_en_limpo_train.csv"

PT_EQUAL_FILE = "dataset_respostas_pt_limpo_train_balanced.csv" # Novo nome mais claro
EN_EQUAL_FILE = "dataset_respostas_en_limpo_train_balanced.csv" # Novo nome mais claro

# Nome da coluna que contém o texto LIMPO
COLUNA_TEXTO = "Conteudo_Processado" 

# --- Dicionários de sinônimos (Permanecem inalterados) ---
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
    # Usamos o regex \b\w+\b para capturar palavras em texto pré-processado (sem pontuação)
    tokens = re.split(r'(\b\w+\b)', texto)

    # Nota: O texto já deve estar em minúsculas se veio da limpeza. 
    indices_candidatos = [i for i, t in enumerate(tokens) if t.lower() in sinonimos]
    if not indices_candidatos:
        return texto

    num_subs = min(len(indices_candidatos), random.randint(1, max_substituicoes))
    indices_a_substituir = random.sample(indices_candidatos, num_subs)

    for idx in indices_a_substituir:
        palavra_original = tokens[idx].lower()
        sinonimo = random.choice(sinonimos[palavra_original])
        
        # Como o texto está limpo (sem pontuação e em minúsculas), simplificamos a capitalização
        tokens[idx] = sinonimo

    return "".join(tokens)


# --- 1. Carregar datasets LIMPOS ---
print("Configurando diretórios...")
DIRETORIO_DADOS_BALANCEAMENTO.mkdir(parents=True, exist_ok=True)

try:
    df_pt = pd.read_csv(DIRETORIO_DADOS_SEPARACAO_TESTE/ PT_INPUT_FILE)
    df_en = pd.read_csv(DIRETORIO_DADOS_SEPARACAO_TESTE/ EN_INPUT_FILE)
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

# --- 3. Estratégia híbrida: duplicar e aumentar parcialmente ---
print("Iniciando aumento de dados com foco na diversidade na coluna tratada...")

# Passo 1: duplicar (garante o mesmo tamanho)
df_menor_expandido = df_menor.sample(len(df_maior), replace=True, random_state=42).reset_index(drop=True)

# Passo 2: aumentar parte dos exemplos (ex: 70%)
taxa_aumento = 0.7
num_aumentar = int(len(df_menor_expandido) * taxa_aumento)
indices_aumentar = np.random.choice(df_menor_expandido.index, size=num_aumentar, replace=False)

alterados = 0
for idx in indices_aumentar:
    # ATENÇÃO: Mudança da coluna de trabalho para a versão processada
    texto_original = df_menor_expandido.loc[idx, COLUNA_TEXTO]
    texto_aumentado = aumentar_texto(texto_original, idioma_menor)
    
    if texto_aumentado != texto_original:
        # APLICA A ALTERAÇÃO na coluna de trabalho
        df_menor_expandido.loc[idx, COLUNA_TEXTO] = texto_aumentado
        alterados += 1

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