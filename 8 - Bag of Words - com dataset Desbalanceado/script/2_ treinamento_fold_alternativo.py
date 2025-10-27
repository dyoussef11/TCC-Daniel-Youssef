import sys
from pathlib import Path
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, accuracy_score, confusion_matrix
from sklearn.model_selection import StratifiedKFold
import matplotlib.pyplot as plt
import seaborn as sns
import os
import numpy as np

# --- Configurações de Caminhos ---
caminho_script = Path(__file__).resolve().parent
caminho_raiz_projeto = caminho_script.parent.parent
sys.path.append(str(caminho_raiz_projeto))

try:
    from config import DIRETORIO_DADOS_BALANCEAMENTO, DIRETORIO_IMAGENS_MODELO_BAG_OF_WORDS
except ImportError:
    print("ERRO: Módulo 'config' não encontrado. Usando caminhos de fallback.")
    DIRETORIO_DADOS_BALANCEAMENTO = Path('./data')
    DIRETORIO_IMAGENS_MODELO_BAG_OF_WORDS = Path('./images_bag_of_words')
    
# --- CONSTANTES ---
# Coluna onde o texto limpo e aumentado está armazenado.
# ATENÇÃO: Verifique se o nome desta coluna está correto nos seus CSVs finais.
TEXT_COLUMN = 'Conteudo_Processado' 

caminhos_arquivos_treino = [
    DIRETORIO_DADOS_BALANCEAMENTO / 'dataset_respostas_en_limpo_train_balanced.csv',
    DIRETORIO_DADOS_BALANCEAMENTO / 'dataset_respostas_pt_limpo_train_balanced.csv'
]

caminho_saida = DIRETORIO_IMAGENS_MODELO_BAG_OF_WORDS
os.makedirs(caminho_saida, exist_ok=True)

# --- Loop para processar cada arquivo ---
for caminho_treino in caminhos_arquivos_treino:
    # Ajustado para extrair o nome base sem o caminho completo e extensão
    nome_base_arquivo = os.path.basename(caminho_treino).replace('.csv', '')
    pasta_saida = os.path.join(caminho_saida, f'cross_validation_{nome_base_arquivo}')
    os.makedirs(pasta_saida, exist_ok=True)

    print(f"\n{'='*50}")
    print(f"--- Validação cruzada com StratifiedKFold para '{nome_base_arquivo}' ---")

    # --- LÓGICA PARA DEFINIR A REGULARIZAÇÃO (C) ---
    # CORREÇÃO: Usando a substring correta para identificar o arquivo EN
    # if 'en_limpo_train_balanced' in nome_base_arquivo:
    #     C_VALUE = 0.3 # Novo valor intermediário
    #     print(f"ATENÇÃO: Usando Regularização C={C_VALUE} para ajustar o modelo EN.")
    # else:
    #     C_VALUE = 1.0 # Mantendo o padrão para o dataset PT
        
    # --- 1. Carregar o dataset completo para CV ---
    try:
        df = pd.read_csv(caminho_treino)
        print(f"✔ Dataset '{caminho_treino}' carregado.")
    except FileNotFoundError:
        print(f"❌ Erro: Arquivo de treino não encontrado para '{nome_base_arquivo}'. Pulando.")
        continue

    # ATENÇÃO: Usando a constante TEXT_COLUMN
    df.dropna(subset=[TEXT_COLUMN, 'sentiment'], inplace=True)
    if df.empty:
        print("Dataset vazio após a limpeza. Pulando.")
        continue

    # ATENÇÃO: Usando a constante TEXT_COLUMN
    X = df[TEXT_COLUMN] 
    y = df['sentiment']
    
    # --- 2. Configurar StratifiedKFold ---
    n_splits = 3 # Você pode ajustar o número de splits
    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
    
    # --- Listas para armazenar as métricas de cada fold ---
    accuracy_scores = []
    all_reports = []
    all_cms = []
    
    # --- 3. Loop de Validação Cruzada ---
    
    print("\nIniciando validação cruzada...")
    for fold, (train_index, test_index) in enumerate(skf.split(X, y), 1):
        print(f"--- Processando Fold {fold}/{n_splits} ---")
        
        # Subconjuntos de treino e teste para o fold atual
        X_train, X_test = X.iloc[train_index], X.iloc[test_index]
        y_train, y_test = y.iloc[train_index], y.iloc[test_index]

        # --- 4. Vetorização TF-IDF (dentro do loop) ---
        
        # vectorizer = TfidfVectorizer(max_features=5000)
        vectorizer = TfidfVectorizer()
        X_train_tfidf = vectorizer.fit_transform(X_train)
        X_test_tfidf = vectorizer.transform(X_test)
        
        # --- 5. Treinamento e Avaliação (APLICANDO C_VALUE) ---
        
        # A ALTERAÇÃO É AQUI: O C_VALUE definido condicionalmente é aplicado
        model = LogisticRegression(random_state=42, max_iter=1000, )
        
        model.fit(X_train_tfidf, y_train)
        y_pred = model.predict(X_test_tfidf)
        
        # Coletar a acurácia
        acc = accuracy_score(y_test, y_pred)
        accuracy_scores.append(acc)
        
        # Coletar relatório de classificação e matrizes de confusão para o fold atual
        report = classification_report(y_test, y_pred, output_dict=True, zero_division=0)
        all_reports.append(report)
        
        cm = confusion_matrix(y_test, y_pred)
        all_cms.append(cm)
        
        print(f"Acurácia do Fold {fold}: {acc:.4f}")
    
    # --- 6. Relatório final da Validação Cruzada ---
    
    print(f"\n{'='*50}")
    print("--- Relatório Final da Validação Cruzada ---")
    print(f"Acurácias por fold: {[f'{score:.4f}' for score in accuracy_scores]}")
    print(f"Acurácia Média: {np.mean(accuracy_scores):.4f} (+/- {np.std(accuracy_scores):.4f})")
    
    # --- Geração de Imagens para o Último Fold como Exemplo Representativo ---
    
    # Matriz de Confusão do Último Fold
    last_cm = all_cms[-1]
    classes = sorted(y.unique())
    plt.figure(figsize=(8, 6))
    sns.heatmap(last_cm, annot=True, fmt='d', cmap='Blues',
                xticklabels=classes, yticklabels=classes)
    
    # Nome do arquivo e título da imagem atualizados para incluir o C_VALUE
    plt.title(f'Matriz de Confusão - {nome_base_arquivo} (Último Fold)')
    plt.ylabel('Rótulo Real')
    plt.xlabel('Rótulo Previsto')
    plt.tight_layout()
    cm_path = os.path.join(pasta_saida, f'{nome_base_arquivo}_matriz_confusao_C__n_splits_{n_splits}.png')
    plt.savefig(cm_path)
    plt.close()
    print(f"✔ Matriz de confusão salva em: {cm_path}")

    # Gráfico de Métricas de Desempenho do Último Fold
    last_report_df = pd.DataFrame(all_reports[-1]).transpose().round(2)
    df_plot = last_report_df.drop(index=['accuracy', 'macro avg', 'weighted avg'], errors='ignore')
    df_plot = df_plot.drop(columns=['support'], errors='ignore')
    
    ax = df_plot.plot(kind='bar', figsize=(10, 6), width=0.8)
    
    # Nome do arquivo e título da imagem atualizados para incluir o C_VALUE
    ax.set_title(f'Métricas de Desempenho por Classe - {nome_base_arquivo} (Último Fold)')
    ax.set_xlabel('Classe')
    ax.set_ylabel('Score')
    plt.xticks(rotation=45)
    plt.ylim(0, 1.1)
    plt.legend(loc='lower left')
    plt.tight_layout()
    metrics_path = os.path.join(pasta_saida, f'{nome_base_arquivo}_performance_metrics_C_n_splits_{n_splits}.png')
    plt.savefig(metrics_path)
    plt.close()
    print(f"✔ Gráfico de métricas salvo em: {metrics_path}")

    print(f"{'='*50}\n")