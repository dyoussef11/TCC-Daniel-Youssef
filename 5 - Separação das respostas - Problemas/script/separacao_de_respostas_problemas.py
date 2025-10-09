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
from config import DIRETORIO_DADOS_CLASSIFICACAO,DIRETORIO_DADOS_UNIFICACAO,DIRETORIO_DADOS_CLASSIFICACAO

import pandas as pd
import os

# Define os nomes dos arquivos de entrada e saída
caminho_entrada_perguntas = DIRETORIO_DADOS_CLASSIFICACAO/ 'perguntas_Classificadas_Contagem_final.csv'
caminho_entrada_respostas = DIRETORIO_DADOS_UNIFICACAO/ 'respostas_combinadas_final.csv'
caminho_saida_respostas = DIRETORIO_DADOS_CLASSIFICACAO/ 'respostas_problema.csv'
try:
    # 1. Carrega o arquivo de perguntas
    df_perguntas = pd.read_csv(caminho_entrada_perguntas)
    print(f"Arquivo de perguntas '{caminho_entrada_perguntas}' carregado com sucesso.")

    # Exibe informações sobre o DataFrame de perguntas para verificação
    print("\nInformações sobre o arquivo de perguntas:")
    df_perguntas.info()
    print("\nPrimeiras linhas do arquivo de perguntas:")
    print(df_perguntas.head())

    # 2. Filtra as perguntas do tipo 'Problema' e extrai os IDs únicos
    perguntas_problema_df = df_perguntas[df_perguntas['Tipo_de_Post_Contagem'] == 'Problema']
    ids_problema = perguntas_problema_df['ID_Unico'].unique()
    
    print(f"\nTotal de perguntas do tipo 'Problema' encontradas: {len(ids_problema)}")

except FileNotFoundError:
    print(f"Erro: Arquivo '{caminho_entrada_perguntas}' não encontrado. Verifique o caminho e o nome do arquivo.")
    exit()

try:
    # 3. Carrega o arquivo de respostas
    df_respostas = pd.read_csv(caminho_entrada_respostas)
    print(f"Arquivo de respostas '{caminho_entrada_respostas}' carregado com sucesso.")

    # Exibe informações sobre o DataFrame de respostas para verificação
    print("\nInformações sobre o arquivo de respostas:")
    df_respostas.info()
    print("\nPrimeiras linhas do arquivo de respostas:")
    print(df_respostas.head())
    
    # --- CORREÇÃO AQUI ---
    # Converte a coluna 'ID_Unico' para numérico, tratando erros
    df_respostas['ID_Unico'] = pd.to_numeric(df_respostas['ID_Unico'], errors='coerce')
    print("\nColuna 'ID_Unico' do arquivo de respostas convertida para numérico, com valores inválidos substituídos por NaN.")
    
    # Remove as linhas com IDs inválidos (NaN)
    df_respostas.dropna(subset=['ID_Unico'], inplace=True)
    df_respostas['ID_Unico'] = df_respostas['ID_Unico'].astype(int)
    print("Linhas com IDs inválidos removidas e a coluna convertida para inteiro.")
    # --- FIM DA CORREÇÃO ---

    # 4. Filtra as respostas usando os IDs únicos das perguntas de 'Problema'
    respostas_problema_df = df_respostas[df_respostas['ID_Unico'].isin(ids_problema)]
    
    print(f"Total de respostas encontradas para as perguntas de 'Problema': {len(respostas_problema_df)}")
    
    # 5. Salva o resultado em um novo arquivo CSV
    if not respostas_problema_df.empty:
        respostas_problema_df.to_csv(caminho_saida_respostas, index=False, encoding='utf-8')
        print(f"\nAs respostas correspondentes foram salvas em '{caminho_saida_respostas}'.")
    else:
        print("\nNenhuma resposta correspondente foi encontrada para salvar.")

except FileNotFoundError:
    print(f"Erro: Arquivo '{caminho_entrada_respostas}' não encontrado. Verifique o caminho e o nome do arquivo.")

print("\nProcesso concluído.")