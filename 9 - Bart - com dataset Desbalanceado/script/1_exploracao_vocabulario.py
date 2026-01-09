import sys
from pathlib import Path

# Obtém o caminho absoluto da pasta do script atual.
# Exemplo: 'C:\...\Buscar_Web\1- WebScrapping\script'
caminho_script = Path(__file__).resolve().parent

# Acessa a pasta raiz do projeto subindo dois níveis.
# Exemplo: 'C:\...\Buscar_Web'
caminho_raiz_projeto = caminho_script.parent.parent

# Adiciona o caminho da raiz ao caminho de busca do Python.
sys.path.append(str(caminho_raiz_projeto))

# Agora a importação do módulo 'config' deve funcionar.
from config import DIRETORIO_DADOS_BALANCEAMENTO,DIRETORIO_DADOS_BAG_OF_WORDS


import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.feature_extraction.text import TfidfVectorizer
import os

# --- Configurações ---
# Lista com os caminhos dos arquivos balanceados
caminhos_arquivos = [
    DIRETORIO_DADOS_BALANCEAMENTO / 'dataset_respostas_en.csv',
    DIRETORIO_DADOS_BALANCEAMENTO / 'dataset_respostas_pt.csv'
]

# Pasta de saída para os resultados (agora com um nome mais genérico)
caminho_saida = DIRETORIO_DADOS_BAG_OF_WORDS
os.makedirs(caminho_saida, exist_ok=True)

# --- Loop para processar cada arquivo ---
for caminho_arquivo in caminhos_arquivos:
    # Extrai o nome do arquivo para usar nas pastas de saída
    nome_base_arquivo = os.path.basename(caminho_arquivo).replace('_Desbalanceado.csv', '')

    # Cria uma pasta específica para os resultados deste arquivo
    pasta_saida_especifica = os.path.join(caminho_saida, nome_base_arquivo)
    os.makedirs(pasta_saida_especifica, exist_ok=True)
    
    print(f"\n--- Processando o arquivo: '{caminho_arquivo}' ---")
    
    # --- 1. Carregar os dados ---
    try:
        df = pd.read_csv(caminho_arquivo)
        print(f"✔ Arquivo carregado com sucesso!")
    except FileNotFoundError:
        print(f"❌ Erro: Arquivo '{caminho_arquivo}' não encontrado. Pulando para o próximo.")
        continue

    # --- 2. Limpeza ---
    df.dropna(subset=['Conteudo_Comentario', 'sentiment'], inplace=True)
    print("\nInformações do dataset:")
    df.info()
    
    # --- 3. Separar dados ---
    X = df['Conteudo_Comentario']
    y = df['sentiment']

    # --- 4. Split ---
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    print(f"\nTreino: {len(X_train)} | Teste: {len(X_test)}")

    # --- 5. Vetorização TF-IDF ---
    # Instancia o vetorizador
    vectorizer = TfidfVectorizer()
    
    # Treina o vetorizador no conjunto de treino e transforma
    X_train_tfidf = vectorizer.fit_transform(X_train)
    # Apenas transforma o conjunto de teste (não treina novamente)
    X_test_tfidf = vectorizer.transform(X_test)

    # --- 6. Exploração ---
    vocabulario = vectorizer.get_feature_names_out()
    print("\nTamanho do vocabulário:", len(vocabulario))
    print("Primeiras 20 palavras:", vocabulario[:20])
    print("\nExemplo da matriz TF-IDF (5 primeiras linhas):")
    print(X_train_tfidf.toarray()[:5])

    # --- 7. Exportação ---
    # Salva o vocabulário
    pd.DataFrame(vocabulario, columns=["Palavra"]).to_csv(
        os.path.join(pasta_saida_especifica, f"{nome_base_arquivo}_vocabulario.csv"), index=False
    )
    # Salva a matriz TF-IDF de treino
    pd.DataFrame(X_train_tfidf.toarray(), columns=vocabulario).to_csv(
        os.path.join(pasta_saida_especifica, f"{nome_base_arquivo}_matriz_tfidf_treino.csv"), index=False
    )
    # Salva a matriz TF-IDF de teste
    pd.DataFrame(X_test_tfidf.toarray(), columns=vocabulario).to_csv(
        os.path.join(pasta_saida_especifica, f"{nome_base_arquivo}_matriz_tfidf_teste.csv"), index=False
    )
    
    print(f"\n✔ Arquivos exportados para a pasta '{pasta_saida_especifica}'.")