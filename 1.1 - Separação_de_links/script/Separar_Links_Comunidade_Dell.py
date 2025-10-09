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
from config import DIRETORIO_DADOS_WEBSCRAPPING, DIRETORIO_DADOS_LINKS

import pandas as pd

def extrair_e_salvar_links_com_numero(caminho_arquivo_csv, termo_busca="-7588", caminho_arquivo_saida="links_filtrados.csv"):
    """
    Lê um arquivo CSV, extrai links que contêm um termo específico em seus nomes,
    e salva esses links em um novo arquivo CSV.

    Args:
        caminho_arquivo_csv (str): O caminho para o arquivo CSV de entrada.
        termo_busca (str): O termo que os links devem conter (padrão é "-7588").
        caminho_arquivo_saida (str): O caminho para o arquivo CSV de saída onde os links
                                     encontrados serão salvos.

    Returns:
        list: Uma lista de links que correspondem ao critério de busca.
    """
    try:
        # Tenta ler o CSV. Se houver um erro de codificação, tenta com 'latin-1'
        try:
            df = pd.read_csv(caminho_arquivo_csv)
        except UnicodeDecodeError:
            df = pd.read_csv(caminho_arquivo_csv, encoding='latin-1')

        links_encontrados = []

        # Itera sobre todas as colunas do DataFrame
        for coluna in df.columns:
            # Verifica se a coluna é do tipo string/objeto e se contém o termo de busca
            # na=False garante que valores NaN (Not a Number) não causem erro
            if df[coluna].dtype == 'object' and df[coluna].astype(str).str.contains(termo_busca, na=False).any():
                # Filtra os links que contêm o termo de busca
                links_na_coluna = df[coluna][df[coluna].astype(str).str.contains(termo_busca, na=False)]
                # Adiciona os links encontrados à lista
                links_encontrados.extend(links_na_coluna.tolist())

        # Remove duplicatas e converte para uma lista
        links_unicos = list(set(links_encontrados))

        # Cria um DataFrame com os links encontrados
        df_links_filtrados = pd.DataFrame(links_unicos, columns=['Links'])

        # Salva os links em um novo arquivo CSV
        df_links_filtrados.to_csv(caminho_arquivo_saida, index=False, encoding='utf-8')
        print(f"Links filtrados salvos com sucesso em '{caminho_arquivo_saida}'")

        return links_unicos

    except FileNotFoundError:
        print(f"Erro: O arquivo '{caminho_arquivo_csv}' não foi encontrado.")
        return []
    except Exception as e:
        print(f"Ocorreu um erro: {e}")
        return []

# --- Exemplo de uso ---
# Substitua 'seu_arquivo.csv' pelo caminho real do seu arquivo CSV
caminho_do_seu_arquivo = DIRETORIO_DADOS_WEBSCRAPPING / 'links_ComunidadeDell_Brasil_7588.csv'
nome_arquivo_saida = DIRETORIO_DADOS_LINKS / 'links_ComunidadeDell_Brasil_7588.csv'

links_filtrados = extrair_e_salvar_links_com_numero(caminho_do_seu_arquivo, caminho_arquivo_saida=nome_arquivo_saida)

if links_filtrados:
    print(f"\nLinks encontrados contendo '-7588':")
    for link in links_filtrados:
        print(link)
else:
    print("\nNenhum link contendo '-7588' foi encontrado ou ocorreu um erro.")