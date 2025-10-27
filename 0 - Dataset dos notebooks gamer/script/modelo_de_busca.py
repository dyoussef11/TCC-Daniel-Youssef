
import csv 
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

def ler_e_filtrar_modelos(caminho_csv, marca_desejada):
    """
    Lê um arquivo CSV (com colunas 'modelo' e 'marca'), filtra pela marca desejada 
    e retorna uma lista de termos de busca.
    """
    modelos_filtrados = []
    
   
    marca_normalizada = marca_desejada.strip().lower()

    try:
        with open(caminho_csv, 'r', newline='', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            
            # Garante que as colunas 'modelo' e 'marca' existem no cabeçalho
            if 'modelo' not in reader.fieldnames or 'marca' not in reader.fieldnames:
                print("ERRO: O arquivo CSV deve conter as colunas 'modelo' e 'marca'.")
                # Retorna lista vazia para o script principal lidar com o erro
                return [] 

            for row in reader:
                # Extrai e normaliza os dados da linha
                marca = row.get('marca', '').strip().lower()
                modelo = row.get('modelo', '').strip()
                
                # Verifica se a marca corresponde e o modelo não está vazio
                if marca == marca_normalizada and modelo:
                    modelos_filtrados.append(modelo)
                    
    except FileNotFoundError:
        print(f"ERRO: Arquivo de modelos não encontrado em: {caminho_csv}")
        # Retorna lista vazia e permite que o script principal saia graciosamente
        return [] 
    except Exception as e:
        print(f"Erro ao processar o arquivo CSV: {e}")
        # Retorna lista vazia em caso de outros erros de processamento
        return []
        
    return modelos_filtrados
