import csv 
import sys

from pathlib import Path

# ... (Código de Path e sys.path não alterado) ...

def ler_e_filtrar_modelos(caminho_csv, marca_desejada=None):
    """
    Lê um arquivo CSV (com colunas 'modelo' e 'marca'), filtra pela marca desejada 
    (se especificada) e retorna uma lista de termos de busca.
    
    Se marca_desejada for None ou string vazia, retorna todos os modelos.
    """
    modelos_filtrados = []
    
    # 1. Normaliza a marca desejada, se ela existir.
    # Se for None ou vazia, marca_normalizada será None (ou string vazia, depende da conversão).
    if marca_desejada:
        marca_normalizada = marca_desejada.strip().lower()
    else:
        # Se nenhuma marca for especificada, não usaremos o filtro de marca.
        marca_normalizada = None 

    try:
        with open(caminho_csv, 'r', newline='', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            
            # Garante que as colunas 'modelo' e 'marca' existem no cabeçalho
            if 'modelo' not in reader.fieldnames or 'marca' not in reader.fieldnames:
                print("ERRO: O arquivo CSV deve conter as colunas 'modelo' e 'marca'.")
                return [] 

            for row in reader:
                # Extrai e normaliza os dados da linha
                marca = row.get('marca', '').strip().lower()
                modelo = row.get('modelo', '').strip()
                
                # 2. LÓGICA DE FILTRAGEM MODIFICADA
                # A condição é VERDADEIRA se:
                # 1) Nenhuma marca foi especificada (marca_normalizada é None), OU
                # 2) A marca da linha (marca) corresponde à marca desejada (marca_normalizada).
                deve_incluir = (marca_normalizada is None) or (marca == marca_normalizada)

                # Verifica se deve incluir e se o modelo não está vazio
                if deve_incluir and modelo:
                    # Incluímos apenas o nome do modelo na lista de termos de busca
                    modelos_filtrados.append(modelo)
                    
    except FileNotFoundError:
        print(f"ERRO: Arquivo de modelos não encontrado em: {caminho_csv}")
        return [] 
    except Exception as e:
        print(f"Erro ao processar o arquivo CSV: {e}")
        return []
        
    return modelos_filtrados

# --- EXEMPLO DE USO ---
# Supondo que você tenha o caminho para o CSV:
# caminho_do_seu_csv = caminho_raiz_projeto / '0 - Dataset dos notebooks gamer\csv\modelos_de_busca.csv'

# USO 1: Filtrando apenas por Dell
# dell_modelos = ler_e_filtrar_modelos(caminho_do_seu_csv, marca_desejada="Dell")

# USO 2: Rodando a lista completa (não especificando a marca)
# todos_modelos = ler_e_filtrar_modelos(caminho_do_seu_csv)