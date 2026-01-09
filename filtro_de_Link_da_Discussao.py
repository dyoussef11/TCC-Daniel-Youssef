import pandas as pd

# Carrega o arquivo original
df = pd.read_csv('saida_scrapy_dell.csv')

# Filtra as linhas onde a coluna 'Titulo' contém a string '15 7588'
# O parâmetro case=False garante que pegue variações de maiúsculas/minúsculas
df_filtrado = df[df['Link_da_Discussao'].str.contains('-7588', case=False, na=False)]

# Salva o resultado em um novo arquivo
df_filtrado.to_csv('saida_filtrada_dell_7588.csv', index=False)

print(f"Filtragem concluída. De {len(df)} linhas, restaram {len(df_filtrado)}.")