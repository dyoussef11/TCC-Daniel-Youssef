import sys
from pathlib import Path
import re
import pandas as pd
from collections import Counter
import os # Importar para simulação de caminho
# import torch # Mantido, mas não usado na limpeza
# from transformers import pipeline # Mantido, mas não usado na limpeza
# from langdetect import detect, DetectorFactory # Mantido, mas não usado neste ambiente

# --- Configuração de Caminhos ---
# ... (O bloco try/except da Pathlib foi mantido como estava)
try:
    # 1. Obtém o caminho absoluto da pasta do script atual.
    caminho_script = Path(__file__).resolve().parent

    # 2. Acessa a pasta raiz do projeto subindo dois níveis.
    caminho_raiz_projeto = caminho_script.parent.parent

    # 3. Adiciona o caminho da raiz ao caminho de busca do Python.
    sys.path.append(str(caminho_raiz_projeto))

    # 4. Importa o diretório base para unificação (Definido no seu arquivo config.py)
    from config import DIRETORIO_DADOS_LIMPEZA_DATASETS

except NameError:
    # Fallback caso a execução ocorra fora do seu script
    # DIRETORIO_DADOS_LINGUAGENS = Path('./')
    DIRETORIO_DADOS_UNIFICACAO = Path('./')


# Caminhos de Entrada
caminho_entrada_pt = DIRETORIO_DADOS_LIMPEZA_DATASETS / 'dataset_respostas_pt_limpo.csv'
caminho_entrada_en = DIRETORIO_DADOS_LIMPEZA_DATASETS / 'dataset_respostas_en_limpo.csv'

# Caminhos de Saída
caminho_saida_pt_limpo = DIRETORIO_DADOS_LIMPEZA_DATASETS / 'dataset_respostas_pt_limpo_v2.csv'
caminho_saida_en_limpo = DIRETORIO_DADOS_LIMPEZA_DATASETS / 'dataset_respostas_en_limpo_v2.csv'


# --- Função de Limpeza de Texto (clean_text) ---
# Função aprimorada para remover ruído estrutural de fóruns
def clean_text(text):
    if pd.isna(text):
        return text

    text = str(text)

    # 1. REMOÇÃO DE ENTIDADES (Mentions, URLs, Zero-Width Space)
    text = re.sub(r'@\S+|http\S+|www\S+|&#x200B;', ' ', text)

    # 2. REMOÇÃO DE CABEÇALHOS DE CITAÇÃO
    text = re.sub(r'Em\s+\d{2}/\d{2}/\d{4}\s+às\s+\d{2}:\d{2}.+?disse:\s*', ' ', text, flags=re.IGNORECASE)

    # 3. CONSOLIDAÇÃO DE RUÍDO DE FORMATAÇÃO (Quebras de Linha, Tabs, Non-breaking Spaces)
    text = re.sub(r'[\r\n\t\xa0]+', ' ', text)
    text = re.sub(r'\s+ \s*', ' ', text) # Remove o bloco de formatação de fórum

    # 4. NORMALIZAÇÃO DE CAIXA
    text = text.lower()
    
    # 5. REMOÇÃO DO RUÍDO NUMÉRICO ISOLADO (como o '1' de pontuação/score no final)
    text = re.sub(r'\s\d+\s*$', '', text)

    # 6. CONSOLIDAÇÃO DE ESPAÇOS E FINALIZAÇÃO
    text = re.sub(r'\s+', ' ', text).strip()

    return text

# --- Função de Processamento por Arquivo ---
def process_and_save(input_file_name, output_path):
    
    # Carrega o arquivo usando o objeto Path
    df = pd.read_csv(input_file_name) 
    
    # CORREÇÃO AQUI: Usa .name para obter a string do nome do arquivo antes de .lower()
    language = "PT-BR" if "pt" in input_file_name.name.lower() else "EN" 
    
    print(f"\n--- Processando {language} ---")
    print(f"DataFrame carregado de: {input_file_name}. Total de linhas: {len(df)}")
    
    # Aplicar a limpeza
    df['Conteudo_Comentario_Limpo'] = df['Conteudo_Comentario'].apply(clean_text)
    
    print("Amostra do resultado (Conteudo_Comentario_Limpo):")
    print(df[['Conteudo_Comentario', 'Conteudo_Comentario_Limpo']].head(2))

    # Salvar o DataFrame processado no caminho de saída (objeto Path)
    df.to_csv(output_path, index=False)
    print(f"DataFrame limpo salvo em: {output_path}")
    
    return output_path.name

# --- Processamento Principal ---
files_generated = []

# 1. Processar e salvar o Dataset PT
files_generated.append(process_and_save(caminho_entrada_pt, caminho_saida_pt_limpo))

# 2. Processar e salvar o Dataset EN
files_generated.append(process_and_save(caminho_entrada_en, caminho_saida_en_limpo))