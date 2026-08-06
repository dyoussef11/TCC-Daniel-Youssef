import pandas as pd
from pathlib import Path
from core.paths import EXTRACAO_DATA

# 1. Define o caminho da pasta
pasta_csv = EXTRACAO_DATA / "logs5"

# 2. Lista todos os arquivos .csv dentro da pasta
arquivos = list(pasta_csv.glob("*.csv"))

if not arquivos:
    print("Nenhum arquivo CSV encontrado na pasta.")
else:
    # 3. Lê cada CSV e armazena em uma lista de DataFrames
    #    (ordena os arquivos por nome para manter consistência)
    arquivos_ordenados = sorted(arquivos)
    lista_dfs = []
    
    for arquivo in arquivos_ordenados:
        print(f"Lendo: {arquivo.name}")
        df = pd.read_csv(arquivo)
        lista_dfs.append(df)
    
    # 4. Concatena todos os DataFrames (ignorando os índices originais)
    df_combinado = pd.concat(lista_dfs, ignore_index=True)
    
    # 5. (Opcional) Salva o resultado em um novo CSV dentro da mesma pasta
    caminho_saida = pasta_csv / "Logs_unidos_falhas_vazios.csv"
    df_combinado.to_csv(caminho_saida, index=False, encoding='utf-8-sig')
    
    print(f"✅ Combinação concluída! Total de {len(df_combinado)} linhas.")
    print(f"Arquivo salvo em: {caminho_saida}")
    
    # Se quiser apenas trabalhar com o DataFrame sem salvar, use:
    df_combinado.head()