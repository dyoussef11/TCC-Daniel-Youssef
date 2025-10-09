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
from config import DIRETORIO_DADOS_EXTRACAO_QA, DIRETORIO_DADOS_UNIFICACAO


import pandas as pd
import os
import re

# Define os caminhos base
caminho_entrada_perguntas = DIRETORIO_DADOS_EXTRACAO_QA / 'perguntas'
caminho_entrada_respostas = DIRETORIO_DADOS_EXTRACAO_QA / 'respostas'
arquivo_final_perguntas = DIRETORIO_DADOS_UNIFICACAO / 'perguntas_combinadas_final.csv'
arquivo_final_respostas = DIRETORIO_DADOS_UNIFICACAO /'respostas_combinadas_final.csv'

# Certifica-se de que o diretório de saída existe
os.makedirs(os.path.dirname(arquivo_final_perguntas), exist_ok=True)

# Dicionário para armazenar o mapeamento de IDs
id_mapa = {}
df_perguntas_combinado = pd.DataFrame()
id_counter = 0

print("--- Unificando Perguntas ---")

# 1. Lê todos os arquivos de perguntas, cria o ID único e o mapa
for arquivo_pergunta in os.listdir(caminho_entrada_perguntas):
    if not arquivo_pergunta.endswith('.csv'):
        continue
    
    caminho_completo = os.path.join(caminho_entrada_perguntas, arquivo_pergunta)
    print(f"Lendo perguntas de: {caminho_completo}")
    
    try:
        df_temp = pd.read_csv(caminho_completo, on_bad_lines='skip', dtype={'ID_Post': str})
    except pd.errors.ParserError as e:
        print(f"Erro ao ler o arquivo {arquivo_pergunta}: {e}. Pulando este arquivo.")
        continue
    
    if 'ID_Post' not in df_temp.columns:
        print(f"Aviso: Coluna 'ID_Post' não encontrada em {arquivo_pergunta}. Pulando este arquivo.")
        continue
    
    fonte = arquivo_pergunta.replace('.csv', '').replace('posts_', '')
    df_temp['Fonte'] = fonte
    df_temp['ID_Unico'] = range(id_counter, id_counter + len(df_temp))
    
    # Preenche o mapa com a chave 'fonte_ID_Post' e o valor 'ID_Unico'
    for original_id, novo_id in zip(df_temp['ID_Post'], df_temp['ID_Unico']):
        chave_mapa = f"{fonte}_{original_id}"
        id_mapa[chave_mapa] = novo_id
        
    id_counter += len(df_temp)
    df_perguntas_combinado = pd.concat([df_perguntas_combinado, df_temp], ignore_index=True)

# Reorganiza e salva as perguntas
if not df_perguntas_combinado.empty:
    colunas_perguntas = ['ID_Unico', 'ID_Post', 'Fonte', 'Titulo_Post', 'URL_Post', 'Conteudo_Post']
    df_perguntas_combinado = df_perguntas_combinado[colunas_perguntas]
    df_perguntas_combinado.to_csv(arquivo_final_perguntas, index=False, encoding='utf-8')
    print(f"\nTodas as perguntas foram salvas em: '{arquivo_final_perguntas}'")
else:
    print("\nNenhum arquivo de perguntas foi processado. O arquivo de perguntas final não será criado.")


# DataFrame para armazenar todas as respostas
df_respostas_combinado = pd.DataFrame()

print("\n--- Unificando e Atualizando Respostas ---")

# 2. Lê todos os arquivos de respostas e os combina
for arquivo_resposta in os.listdir(caminho_entrada_respostas):
    if not arquivo_resposta.endswith('.csv'):
        continue
        
    caminho_completo = os.path.join(caminho_entrada_respostas, arquivo_resposta)
    print(f"Lendo respostas de: {caminho_completo}")

    try:
        # Tenta ler a coluna ID_Post do arquivo de respostas
        df_temp = pd.read_csv(caminho_completo, on_bad_lines='skip', dtype={'ID_Post': str})
    except Exception as e:
        print(f"Ocorreu um erro ao ler {arquivo_resposta}: {e}. Pulando este arquivo.")
        continue

    # Verifica se o arquivo tem a coluna 'ID_Post' para fazer o mapeamento
    if 'ID_Post' not in df_temp.columns:
        print(f"Aviso: Coluna 'ID_Post' não encontrada em {arquivo_resposta}. Pulando o mapeamento de IDs.")
        continue
        
    fonte = arquivo_resposta.replace('.csv', '').replace('comentarios_', '')
    df_temp['Fonte'] = fonte

    # Mapeia e cria a coluna 'ID_Unico' usando o mapa criado das perguntas
    df_temp['ID_Unico'] = df_temp['ID_Post'].apply(lambda x: id_mapa.get(f"{fonte}_{x}"))
    
    # Remove as linhas onde não foi possível encontrar um ID_Unico válido
    df_temp.dropna(subset=['ID_Unico'], inplace=True)
    
    # Converte 'ID_Unico' para o tipo inteiro após a limpeza
    df_temp['ID_Unico'] = df_temp['ID_Unico'].astype(int)
    
    # Adiciona ao DataFrame combinado
    df_respostas_combinado = pd.concat([df_respostas_combinado, df_temp], ignore_index=True)

# Reorganiza e salva as respostas
if not df_respostas_combinado.empty:
    # Garante que a coluna de conteúdo tenha o nome correto
    if 'Conteudo_Comentario' not in df_respostas_combinado.columns and 'Conteudo_Resposta' in df_respostas_combinado.columns:
        df_respostas_combinado.rename(columns={'Conteudo_Resposta': 'Conteudo_Comentario'}, inplace=True)
        
    colunas_respostas = ['ID_Unico', 'Fonte', 'Conteudo_Comentario']
    df_respostas_combinado = df_respostas_combinado[colunas_respostas]
    df_respostas_combinado.to_csv(arquivo_final_respostas, index=False, encoding='utf-8')
    print(f"Todas as respostas foram salvas em: '{arquivo_final_respostas}'")
else:
    print("Nenhum arquivo de respostas foi processado ou nenhuma resposta com ID_Unico válido foi encontrada. O arquivo de respostas final não será criado.")

print("\nProcesso concluído! Perguntas e respostas unificadas e vinculadas por 'ID_Unico'.")