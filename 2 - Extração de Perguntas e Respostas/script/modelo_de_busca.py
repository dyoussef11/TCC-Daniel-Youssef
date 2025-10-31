import csv 
import sys

from pathlib import Path

# ... (Código de Path e sys.path não alterado) ...

# --- VARIÁVEIS DE COLUNA (CORRETO) ---
nome_coluna_marca = 'Marca'
nome_coluna_modelo = 'Nome_Assinatura'
nome_coluna_tipo = 'Tipo_Notebook' # <-- VARIÁVEL JÁ EXISTENTE

def ler_e_filtrar_modelos(caminho_csv, marca_desejada=None, tipo_desejado=None):
    """
    Lê um arquivo CSV (com colunas 'Marca', 'Nome_Assinatura' e 'Tipo_Notebook'), 
    filtra pela marca e/ou tipo desejado (se especificados) e retorna uma lista 
    de termos de busca (Nome_Assinatura).
    
    Se marca_desejada ou tipo_desejado for None ou string vazia, não aplica o filtro correspondente.
    """
    modelos_filtrados = []
    
    # 1. Normaliza a marca desejada (Para UPPERCASE, compatível com o CSV final)
    if marca_desejada:
        marca_normalizada = marca_desejada.strip().upper()
    else:
        marca_normalizada = None 

    # 2. Normaliza o tipo desejado (Para UPPERCASE, compatível com o CSV final)
    if tipo_desejado:
        tipo_normalizado = tipo_desejado.strip().upper()
    else:
        tipo_normalizado = None

    try:
        # ATENÇÃO: Usamos 'latin1' como precaução de encoding.
        # Se seu CSV está salvo em UTF-8, mude de volta para encoding='utf-8'.
        with open(caminho_csv, 'r', newline='', encoding='latin1') as file: 
            reader = csv.DictReader(file)
            
            # Verificação do cabeçalho
            colunas_obrigatorias = [nome_coluna_marca, nome_coluna_modelo, nome_coluna_tipo]
            if not all(coluna in reader.fieldnames for coluna in colunas_obrigatorias):
                print(f"ERRO: O arquivo CSV deve conter as colunas: {', '.join(colunas_obrigatorias)}.")
                return []

            for row in reader:
                # 3. EXTRAÇÃO E NORMALIZAÇÃO DOS DADOS DO ARQUIVO
                # Normaliza para UPPER para bater com 'marca_normalizada' e 'tipo_normalizado'
                marca = row.get(nome_coluna_marca, '').strip().upper()
                modelo = row.get(nome_coluna_modelo, '').strip()
                tipo = row.get(nome_coluna_tipo, '').strip().upper() # <-- Novo: Tipo normalizado
                
                # 4. LÓGICA DE FILTRAGEM
                
                # Filtro de Marca: Deve incluir se: 1) Não há filtro OU 2) A marca na linha (UPPER) é IGUAL à marca desejada (UPPER).
                filtro_marca_passou = (marca_normalizada is None) or (marca == marca_normalizada)
                
                # Filtro de Tipo: Deve incluir se: 1) Não há filtro OU 2) O tipo na linha (UPPER) é IGUAL ao tipo desejado (UPPER).
                # Se você quer *apenas* "Gamer" e não aceita None, use: (tipo == tipo_normalizado)
                # Se você quer que o filtro só aplique se "tipo_desejado" foi fornecido, use a lógica abaixo:
                filtro_tipo_passou = (tipo_normalizado is None) or (tipo == tipo_normalizado)

                # A linha deve ser incluída se AMBOS os filtros passarem E o modelo for válido
                if filtro_marca_passou and filtro_tipo_passou and modelo and modelo != 'NOME BASE':
                    modelos_filtrados.append(modelo)
                    
    except FileNotFoundError:
        print(f"ERRO: Arquivo de modelos não encontrado em: {caminho_csv}")
        return [] 
    except Exception as e:
        print(f"Erro ao processar o arquivo CSV: {e}")
        return []
        
    return modelos_filtrados

# --- EXEMPLO DE USO ---
# Supondo que 'caminho_do_seu_csv' seja o caminho correto para o arquivo.
#
# Ex: Filtrar por marca "Dell" E tipo "Gamer"
# dell_gamers = ler_e_filtrar_modelos(caminho_do_seu_csv, marca_desejada="Dell", tipo_desejado="Gamer")
# print(f"Modelos Dell Gamer encontrados: {dell_gamers}")
#
# Ex: Filtrar APENAS por tipo "Gamer" (independente da marca)
# apenas_gamers = ler_e_filtrar_modelos(caminho_do_seu_csv, tipo_desejado="Gamer")
# print(f"Todos os modelos Gamer encontrados: {apenas_gamers}")