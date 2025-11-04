import sys
from pathlib import Path
import pandas as pd
from sklearn.model_selection import train_test_split
import os


# Obtém o caminho absoluto da pasta do script atual.
# Exemplo: 'C:\...\Buscar_Web\1- WebScrapping\script'
caminho_script = Path(__file__).resolve().parent

# Acessa a pasta raiz do projeto subindo dois níveis.
# Exemplo: 'C:\...\Buscar_Web'
caminho_raiz_projeto = caminho_script.parent.parent

# Adiciona o caminho da raiz ao caminho de busca do Python.
sys.path.append(str(caminho_raiz_projeto))

# Agora a importação do módulo 'config' deve funcionar.
from config import DIRETORIO_DADOS_SEPARACAO_TESTE,DIRETORIO_DADOS_LINGUAGENS, DIRETORIO_DADOS_LIMPEZA, DIRETORIO_DADOS_AMOSTRAGEM




# caminhos_arquivos = [
#     DIRETORIO_DADOS_LIMPEZA / 'dataset_respostas_en_limpo.csv',
#     DIRETORIO_DADOS_LIMPEZA/ 'dataset_respostas_pt_limpo.csv'
# ]

caminhos_arquivos = [
    DIRETORIO_DADOS_AMOSTRAGEM / 'dataset_rotulado_respostas_en.csv',
    DIRETORIO_DADOS_AMOSTRAGEM / 'dataset_rotulado_respostas_pt_br.csv'
]


caminho_saida = DIRETORIO_DADOS_SEPARACAO_TESTE 
os.makedirs(caminho_saida, exist_ok=True)

# --- Loop para processar e salvar o conjunto de teste ---
for caminho_arquivo in caminhos_arquivos:
    try:
        df = pd.read_csv(caminho_arquivo)
        # df.dropna(subset=['Conteudo_Processado', 'sentiment'], inplace=True)
        df.dropna(subset=['texto', 'label_predito'], inplace=True)
        print(f"✔ Arquivo '{caminho_arquivo}' carregado e limpo.")
    except FileNotFoundError:
        print(f"❌ Erro: Arquivo '{caminho_arquivo}' não encontrado. Pulando.")
        continue
    
    # Extrai o nome do arquivo para usar nos nomes de saída
    nome_base = os.path.basename(caminho_arquivo).replace('.csv', '')

    # Separa 20% do dataset para teste, mantendo a estratificação
    X = df['texto']
    y = df['label_predito']
    
    # X = df['Conteudo_Processado']
    # y = df['sentiment']
   
    # Stratify=y garante que a distribuição das classes de 'sentiment' seja a mesma
    # no conjunto de treino e de teste.
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    # Cria DataFrames separados para treino e teste
    df_train = pd.DataFrame({'Conteudo_Processado': X_train, 'sentiment': y_train})
    df_test = pd.DataFrame({'Conteudo_Processado': X_test, 'sentiment': y_test})

    # Salva os datasets em arquivos CSV
    caminho_saida_train = os.path.join(caminho_saida, f'{nome_base}_train.csv')
    caminho_saida_test = os.path.join(caminho_saida, f'{nome_base}_test.csv')

    df_train.to_csv(caminho_saida_train, index=False)
    df_test.to_csv(caminho_saida_test, index=False)
    
    print(f"✔ Conjunto de treino salvo em '{caminho_saida_train}'")
    print(f"✔ Conjunto de teste desbalanceado salvo em '{caminho_saida_test}'")