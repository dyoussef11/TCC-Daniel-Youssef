import sys
from pathlib import Path
import pandas as pd
from sklearn.metrics import classification_report, accuracy_score, f1_score, precision_score, recall_score
from sklearn.model_selection import StratifiedKFold
from transformers import AutoTokenizer, AutoModelForSequenceClassification, Trainer, TrainingArguments
from datasets import Dataset
import numpy as np
import torch
import os
import matplotlib.pyplot as plt
import seaborn as sns

# --- Configurações de Caminhos (Ajustadas para o Ambiente da VM/Local) ---
# Usando o diretório atual para carregar os arquivos que você enviou.
caminho_script = Path(__file__).resolve().parent
caminho_raiz_projeto = caminho_script.parent.parent
sys.path.append(str(caminho_raiz_projeto))

from config import DIRETORIO_DADOS_BALANCEAMENTO, DIRETORIO_DADOS_SEPARACAO_TESTE


# --- CONSTANTES ---
TEXT_COLUMN = 'Conteudo_Comentario_Limpo'
LABEL_COLUMN =  'sentiment' # Usando o label_predito como 'ground truth' para o teste.
MODEL_NAME = 'neuralmind/bert-base-portuguese-cased' # Modelo BERT em PT. Para Inglês, use 'bert-base-uncased'.
N_SPLITS = 4 # Número de folds
MAX_LENGTH = 128 # Tamanho máximo da sequência para o Transformer

DIRETORIO_DADOS = Path('.')
caminho_saida = Path('./bart_cross_validation_results')
os.makedirs(caminho_saida, exist_ok=True)

# --- Função de Métricas ---
def compute_metrics(p):
    """Calcula as métricas de Precision, Recall e F1-Score."""
    predictions, labels = p
    predictions = np.argmax(predictions, axis=1)
    
    # As classes devem ser as mesmas usadas no mapeamento (id2label)
    report = classification_report(labels, predictions, output_dict=True, zero_division=0)
    
    return {
        'accuracy': report['accuracy'],
        'f1_macro': report['macro avg']['f1-score'],
        'precision_macro': report['macro avg']['precision'],
        'recall_macro': report['macro avg']['recall'],
        # Retorna o relatório completo se necessário, mas aqui só as médias
    }

# --- Função de Tokenização ---
def tokenize_function(examples, tokenizer, label_to_id):
    """Tokeniza os textos e mapeia rótulos para IDs."""
    # O BART/BERT espera um campo 'text'
    tokenized_inputs = tokenizer(examples[TEXT_COLUMN], truncation=True, padding='max_length', max_length=MAX_LENGTH)
    
    # Mapear strings de rótulo para IDs inteiros
    tokenized_inputs["labels"] = [label_to_id[label] for label in examples[LABEL_COLUMN]]
    return tokenized_inputs

# --- Loop para processar cada arquivo ---
caminhos_arquivos_treino = [
    DIRETORIO_DADOS_BALANCEAMENTO / 'dataset_rotulado_respostas_pt_br_train_balanced.csv',
    # Adicionar o dataset em inglês se quiser rodar, mudando o MODEL_NAME
    # DIRETORIO_DADOS / 'dataset_rotulado_respostas_en.csv',
]

for caminho_treino in caminhos_arquivos_treino:
    nome_base_arquivo = os.path.basename(caminho_treino).replace('.csv', '')
    pasta_saida = os.path.join(caminho_saida, f'cross_validation_{nome_base_arquivo}')
    os.makedirs(pasta_saida, exist_ok=True)
    
    if 'pt_br' in nome_base_arquivo:
        MODEL_NAME = 'neuralmind/bert-base-portuguese-cased'
    elif 'en' in nome_base_arquivo:
        MODEL_NAME = 'bert-base-uncased'

    print(f"\n{'='*70}")
    print(f"--- Validação cruzada BART/BERT com StratifiedKFold para '{nome_base_arquivo}' ---")
    print(f"Modelo: {MODEL_NAME}")

    try:
        df = pd.read_csv(caminho_treino)
        print(f"✔ Dataset '{caminho_treino}' carregado. Total de linhas: {len(df)}")
    except FileNotFoundError:
        print(f"❌ Erro: Arquivo não encontrado. Pulando.")
        continue

    # 1. Pré-processamento e Mapeamento de Rótulos
    df.dropna(subset=[TEXT_COLUMN, LABEL_COLUMN], inplace=True)
    if df.empty:
        print("Dataset vazio após a limpeza. Pulando.")
        continue
    
    # Mapeamento de rótulos para IDs (obrigatório para Transformers)
    label_list = sorted(df[LABEL_COLUMN].unique())
    id2label = {i: label for i, label in enumerate(label_list)}
    label2id = {label: i for i, label in enumerate(label_list)}
    num_labels = len(label_list)

    # Convertendo o DataFrame para o formato 'datasets'
    hf_dataset = Dataset.from_pandas(df[[TEXT_COLUMN, LABEL_COLUMN]])
    
    # --- 2. Configurar StratifiedKFold (em índices) ---
    X_indices = np.arange(len(df))
    y = df[LABEL_COLUMN]
    skf = StratifiedKFold(n_splits=N_SPLITS, shuffle=True, random_state=42)
    
    # --- Listas para armazenar as métricas de cada fold ---
    accuracy_scores = []
    
    print("\nIniciando validação cruzada...")
    
    # Rodar o tokenizer uma vez, pois ele é específico do modelo
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    
    for fold, (train_index, test_index) in enumerate(skf.split(X_indices, y), 1):
        print(f"--- Processando Fold {fold}/{N_SPLITS} ---")
        
        # Criar os subconjuntos de treinamento e teste do Hugging Face Dataset
        train_dataset = hf_dataset.select(train_index).map(
            lambda x: tokenize_function(x, tokenizer, label2id),
            batched=True,
            remove_columns=['__index_level_0', TEXT_COLUMN, LABEL_COLUMN]
        )
        test_dataset = hf_dataset.select(test_index).map(
            lambda x: tokenize_function(x, tokenizer, label2id),
            batched=True,
            remove_columns=['__index_level_0', TEXT_COLUMN, LABEL_COLUMN]
        )
        
        # --- 3. Inicializar Modelo e Configurações de Treinamento ---
        # ATENÇÃO: É necessário recarregar o modelo para cada fold para garantir um treinamento independente
        model = AutoModelForSequenceClassification.from_pretrained(
            MODEL_NAME, 
            num_labels=num_labels,
            id2label=id2label,
            label2id=label2id
        )

        training_args = TrainingArguments(
            output_dir=os.path.join(pasta_saida, f'fold_{fold}_output'),
            num_train_epochs=3,                     # Reduza para testar, aumente para precisão.
            per_device_train_batch_size=8,          # Ajuste de acordo com a memória da GPU (o padrão é 8).
            per_device_eval_batch_size=8,
            warmup_steps=500,                       
            weight_decay=0.01,
            logging_dir='./logs',
            logging_steps=100,
            # Configurações de avaliação (opcional)
            evaluation_strategy="epoch",
            save_strategy="epoch",
            load_best_model_at_end=True,
            metric_for_best_model="accuracy",
            # Desabilita o tokenizador para evitar avisos desnecessários (opcional)
            disable_tqdm=True
        )

        # --- 4. Inicializar o Trainer e Treinar ---
        trainer = Trainer(
            model=model,
            args=training_args,
            train_dataset=train_dataset,
            eval_dataset=test_dataset,
            compute_metrics=compute_metrics,
        )
        
        # Treinamento (ATENÇÃO: Este passo é demorado e exigente em recursos)
        # O BLOCO ABAIXO DEVE SER RODADO EM UM AMBIENTE COM ACELERAÇÃO
        # trainer.train() 

        # --- 5. Avaliação do Fold ---
        # Na ausência da GPU e treinamento completo, SIMULAMOS O RESULTADO
        
        # DESCOMENTAR AS DUAS LINHAS ABAIXO NO SEU AMBIENTE COM GPU:
        # metrics = trainer.evaluate()
        # acc = metrics['eval_accuracy']

        # Para fins de demonstração neste ambiente (sem GPU):
        # Acurácia de referência do TF-IDF: 0.82
        acc = np.random.uniform(0.75, 0.85) # Simulação de resultado
        
        print(f"Acurácia do Fold {fold}: {acc:.4f}")
        accuracy_scores.append(acc)

    # --- 6. Relatório final da Validação Cruzada (Simulação) ---
    
    print(f"\n{'='*70}")
    print("--- Relatório Final da Validação Cruzada BART/BERT (Simulado) ---")
    print(f"Acurácias por fold (Simulado): {[f'{score:.4f}' for score in accuracy_scores]}")
    print(f"Acurácia Média (Simulada): {np.mean(accuracy_scores):.4f} (+/- {np.std(accuracy_scores):.4f})")
    
    # --- Geração de Imagens de Comparação (Simulação) ---
    
    # Crie um gráfico simples para visualizar a variação dos folds
    plt.figure(figsize=(7, 5))
    plt.bar(range(1, N_SPLITS + 1), accuracy_scores, color='skyblue')
    plt.axhline(np.mean(accuracy_scores), color='red', linestyle='--', label=f'Média: {np.mean(accuracy_scores):.4f}')
    plt.title(f'Acurácia por Fold (BART/BERT - Simulado) - {nome_base_arquivo}')
    plt.xlabel('Fold')
    plt.ylabel('Acurácia')
    plt.ylim(min(accuracy_scores)*0.95, 1.0)
    plt.legend()
    plt.tight_layout()
    
    metrics_path = os.path.join(pasta_saida, f'{nome_base_arquivo}_bart_cv_accuracy_simulado.png')
    plt.savefig(metrics_path)
    plt.close()
    print(f"✔ Gráfico de acurácia por fold (Simulado) salvo em: {metrics_path}")

    print(f"{'='*70}\n")