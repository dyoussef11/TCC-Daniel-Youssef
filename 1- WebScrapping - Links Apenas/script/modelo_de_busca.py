import csv 
import sys

from pathlib import Path

# ... (Código de Path e sys.path não alterado) ...

# --- VARIÁVEIS DE COLUNA (CORRETO) ---
nome_coluna_marca = 'Marca'
nome_coluna_modelo = 'Nome_Assinatura'

def ler_e_filtrar_modelos(caminho_csv, marca_desejada=None):
    """
    Lê um arquivo CSV (com colunas 'Marca' e 'Nome_Assinatura'), filtra pela marca desejada 
    (se especificada) e retorna uma lista de termos de busca (Nome_Assinatura).
    
    Se marca_desejada for None ou string vazia, retorna todos os modelos.
    """
    modelos_filtrados = []
    
    # 1. Normaliza a marca desejada (Para UPPERCASE, compatível com o CSV final)
    if marca_desejada:
        marca_normalizada = marca_desejada.strip().upper()
    else:
        marca_normalizada = None 

    try:
        # ATENÇÃO: Usamos 'latin1' como precaução de encoding.
        # Se seu CSV está salvo em UTF-8, mude de volta para encoding='utf-8'.
        with open(caminho_csv, 'r', newline='', encoding='latin1') as file: 
            reader = csv.DictReader(file)
            
            # Verificação do cabeçalho
            if nome_coluna_marca not in reader.fieldnames or nome_coluna_modelo not in reader.fieldnames:
                print(f"ERRO: O arquivo CSV deve conter as colunas '{nome_coluna_marca}' e '{nome_coluna_modelo}'.")
                return []

            for row in reader:
                # 2. EXTRAÇÃO E NORMALIZAÇÃO CORRIGIDA DA MARCA DO ARQUIVO
                # Normaliza para UPPER para bater com 'marca_normalizada'
                marca = row.get(nome_coluna_marca, '').strip().upper()
                modelo = row.get(nome_coluna_modelo, '').strip()
                
                # 3. LÓGICA DE FILTRAGEM
                # Deve incluir se: 1) Não há filtro OU 2) A marca na linha (UPPER) é IGUAL à marca desejada (UPPER).
                deve_incluir = (marca_normalizada is None) or (marca == marca_normalizada)

                # Verifica se deve incluir, se o modelo não está vazio e não é o fallback
                if deve_incluir and modelo and modelo != 'NOME BASE':
                    modelos_filtrados.append(modelo)
                     
    except FileNotFoundError:
        print(f"ERRO: Arquivo de modelos não encontrado em: {caminho_csv}")
        return [] 
    except Exception as e:
        print(f"Erro ao processar o arquivo CSV: {e}")
        return []
        
    return modelos_filtrados

# --- O código agora deve funcionar corretamente ao ser chamado ---
# Ex: dell_modelos = ler_e_filtrar_modelos(caminho_do_seu_csv, marca_desejada="Dell")
# 'Dell' -> 'DELL' (Marca desejada)
# 'Dell' -> 'DELL' (Marca lida do CSV)
# A comparação ('DELL' == 'DELL') é bem-sucedida.