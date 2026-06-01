import os
import json

from core.paths import EXTRACAO_DATA

def limpar_json_por_modelo(diretorio, dry_run=True):
    """
    Percorre o diretório e remove arquivos JSON onde o campo 'modelo_generico'
    possui apenas 1 palavra, A MENOS que essa palavra contenha um caractere '_'.
    
    :param diretorio: Caminho da pasta com os arquivos JSON
    :param dry_run: Se True, apenas simula e mostra o que seria apagado.
    """
    if not os.path.exists(diretorio):
        print(f"Erro: O diretório '{diretorio}' não foi encontrado.")
        return

    arquivos_processados = 0
    arquivos_removidos = 0

    print(f"{"[SIMULAÇÃO] " if dry_run else ""}Iniciando varredura em: {diretorio}\n")

    for nome_arquivo in os.listdir(diretorio):
        if nome_arquivo.endswith('.json'):
            caminho_arquivo = os.path.join(diretorio, nome_arquivo)
            arquivos_processados += 1
            
            try:
                with open(caminho_arquivo, 'r', encoding='utf-8') as f:
                    dados = json.load(f)
                
                modelo = dados.get("modelo_generico", "")
                
                if isinstance(modelo, str):
                    texto_limpo = modelo.strip()
                    palavras = texto_limpo.split()
                    quantidade_palavras = len(palavras)
                    
                    # Verifica se o texto contém o caractere de underline
                    contem_underline = "_" in texto_limpo
                else:
                    quantidade_palavras = 0
                    contem_underline = False

                # Critério de exclusão: 
                # Deve ter 1 ou nenhuma palavra E NÃO pode conter "_"
                if quantidade_palavras <= 1 and not contem_underline:
                    arquivos_removidos += 1
                    if dry_run:
                        print(f"Seria removido: {nome_arquivo} -> 'modelo_generico': \"{modelo}\"")
                    else:
                        os.remove(caminho_arquivo)
                        print(f"REMOVIDO: {nome_arquivo}")
                
                # Apenas para feedback visual na simulação se ele pulou por causa do "_"
                elif quantidade_palavras == 1 and contem_underline and dry_run:
                    print(f"Mantido (contém '_'): {nome_arquivo} -> 'modelo_generico': \"{modelo}\"")
                        
            except (json.JSONDecodeError, OSError) as e:
                print(f"Erro ao processar o arquivo {nome_arquivo}: {e}")

    print("\n--- Resumo ---")
    print(f"Total de arquivos JSON encontrados: {arquivos_processados}")
    print(f"Total de arquivos {"que seriam " if dry_run else ""}removidos: {arquivos_removidos}")
    if dry_run and arquivos_removidos > 0:
        print("\n[AVISO] Para efetivar a remoção física, mude 'dry_run=True' para 'dry_run=False'.")

# --- Execução ---
caminho_pasta = EXTRACAO_DATA/ "brutoV6"

# Rode primeiro como True para validar se os termos com "_" estão sendo mantidos!
limpar_json_por_modelo(caminho_pasta, dry_run=False)