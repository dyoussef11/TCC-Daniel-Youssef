import sys
from pathlib import Path

# Obtém o caminho absoluto da pasta do script atual.
caminho_script = Path(__file__).resolve().parent
caminho_raiz_projeto = caminho_script.parent.parent
sys.path.append(str(caminho_raiz_projeto))

from config import DIRETORIO_DADOS_SEPARACAO_TESTE, DIRETORIO_DADOS_BALANCEAMENTO

import pandas as pd
import random
import re
import os
from langdetect import detect, DetectorFactory

# Garante que a detecção de idioma seja consistente
DetectorFactory.seed = 0

def get_language(text):
    """Detecta o idioma de um texto, retornando 'unknown' se falhar."""
    try:
        if pd.isna(text) or len(str(text).strip()) < 3:
            return 'unknown'
        return detect(text)
    except:
        return 'unknown'

# --- 1. Dicionários de sinônimos ---
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
        
        # escolhe até "max_substituicoes" palavras diferentes para trocar
        num_subs = min(len(palavras_disponiveis), random.randint(1, max_substituicoes))
        palavras_escolhidas = random.sample(palavras_disponiveis, num_subs)

        for p in palavras_escolhidas:
            indice = nova_frase.index(p)
            nova_frase[indice] = random.choice(sinonimos[p])

        frases_aumentadas.append(" ".join(nova_frase))

    return frases_aumentadas


# --- 2. Configurações e Caminhos ---
caminhos_arquivos_treino = [
    DIRETORIO_DADOS_SEPARACAO_TESTE / 'dataset_respostas_en_train.csv',
    DIRETORIO_DADOS_SEPARACAO_TESTE / 'dataset_respostas_pt_train.csv'
]

caminho_saida = DIRETORIO_DADOS_BALANCEAMENTO
os.makedirs(caminho_saida, exist_ok=True)

# --- 3. Loop para processar cada arquivo ---
for caminho_treino in caminhos_arquivos_treino:
    nome_base_arquivo = os.path.basename(caminho_treino).replace('_train.csv', '')
    
    print(f"\n{'='*50}")
    print(f"--- Balanceando o arquivo de treino: '{caminho_treino}' ---")
    
    # Carregar e limpar os dados de treino
    try:
        df_train = pd.read_csv(caminho_treino)
        df_train.dropna(subset=['Conteudo_Comentario', 'sentiment'], inplace=True)
        print(f"✔ Dataset de treino carregado e limpo. Total de registros: {len(df_train)}")
    except FileNotFoundError:
        print(f"❌ Erro: Arquivo de treino não encontrado para '{nome_base_arquivo}'. Pulando.")
        continue

    if df_train.empty:
        print("Dataset de treino vazio. Pulando.")
        continue

    # Adicionar a coluna de idioma
    df_train['language'] = df_train['Conteudo_Comentario'].astype(str).apply(get_language)
    
    contagem_classes_treino = df_train['sentiment'].value_counts()
    print("Distribuição original do treino:")
    print(contagem_classes_treino)
    
    classe_majoritaria = contagem_classes_treino.idxmax()
    tamanho_majoritario = contagem_classes_treino.max()
    
    # Dataframe para os dados balanceados, começando com a classe majoritária
    df_balanceado = df_train[df_train['sentiment'] == classe_majoritaria].copy()
    
    for classe, contagem in contagem_classes_treino.items():
        if classe != classe_majoritaria:
            df_classe = df_train[df_train['sentiment'] == classe].copy()
            num_exemplos_aumentar = tamanho_majoritario - contagem
            
            if len(df_classe) == 0:
                print(f"Aviso: Classe '{classe}' não tem exemplos para aumento. Pulando.")
                continue

            num_gerar_por_exemplo = int(num_exemplos_aumentar / len(df_classe))
            num_restante = num_exemplos_aumentar % len(df_classe)
            
            novos_dados = []
            
            for index, row in df_classe.iterrows():
                novos_textos = aumentar_texto(row['Conteudo_Comentario'], num_gerar_por_exemplo, row['language'])
                for t in set(novos_textos):  # transforma em set para evitar duplicata do mesmo texto
                    if t.strip() and t != row['Conteudo_Comentario']:
                        novos_dados.append({'Conteudo_Comentario': t, 'sentiment': classe})

            # Aumenta os textos restantes aleatoriamente
            textos_restantes = random.sample(list(df_classe['Conteudo_Comentario']), num_restante)
            for texto in textos_restantes:
                 novos_dados.extend([{'Conteudo_Comentario': t, 'sentiment': classe} for t in aumentar_texto(texto, 1, df_classe[df_classe['Conteudo_Comentario'] == texto]['language'].iloc[0])])
            
            df_novos = pd.DataFrame(novos_dados)
            
            # Concatena os dados originais e os novos dados da classe minoritária
            df_classe_completo = pd.concat([df_classe, df_novos], ignore_index=True)
            
            # Adiciona ao dataframe final balanceado
            df_balanceado = pd.concat([df_balanceado, df_classe_completo], ignore_index=True)
            df_balanceado.drop_duplicates(subset=["Conteudo_Comentario", "sentiment"], inplace=True)
            
    print("\n✔ Conjunto de treino balanceado!")
    print("Nova distribuição do treino:")
    print(df_balanceado['sentiment'].value_counts())
    
    # Salvar o dataset de treino balanceado
    caminho_saida_balanceado = os.path.join(caminho_saida, f'{nome_base_arquivo}_train_balanced.csv')
    df_balanceado.to_csv(caminho_saida_balanceado, index=False)
    print(f"✔ Dataset de treino balanceado salvo em '{caminho_saida_balanceado}'")
    print(f"{'='*50}\n")