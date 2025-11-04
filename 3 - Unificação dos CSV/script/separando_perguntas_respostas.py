import sys
from pathlib import Path
import pandas as pd
import os

# --- Configuração de Caminho ---
# Navegação para a raiz do projeto para importar 'config'
caminho_script = Path(__file__).resolve().parent
caminho_raiz_projeto = caminho_script.parent.parent
sys.path.append(str(caminho_raiz_projeto))

# Importa os diretórios
from config import DIRETORIO_DADOS_EXTRACAO_QA, DIRETORIO_DADOS_SEPARACAO_PROBLEMAS, DIRETORIO_DADOS_UNIFICACAO 

# Define as PASTAS de entrada
caminho_entrada_perguntas_dir = DIRETORIO_DADOS_EXTRACAO_QA / 'perguntas'
caminho_entrada_respostas_dir = DIRETORIO_DADOS_EXTRACAO_QA / 'respostas'

# Define os nomes dos arquivos de saída (consolidação)
# Eles serão salvos no diretório DIRETORIO_DADOS_UNIFICACAO
caminho_saida_perguntas = DIRETORIO_DADOS_UNIFICACAO / 'perguntas_combinadas_final.csv'
caminho_saida_respostas = DIRETORIO_DADOS_UNIFICACAO / 'respostas_combinadas_final.csv'


def carregar_e_combinar_csvs(diretorio: Path, nome_tipo: str):
    """Lê todos os arquivos CSV em um diretório e os combina em um único DataFrame, com tratamento de erros."""
    
    arquivos_csv = list(diretorio.glob('*.csv'))
    
    if not arquivos_csv:
        raise FileNotFoundError(f"ERRO: Nenhum arquivo CSV encontrado em '{diretorio}'. Verifique o caminho.")
    
    print(f"\n✅ Encontrados {len(arquivos_csv)} arquivos para {nome_tipo} no diretório: {diretorio.name}")
    
    lista_dataframes = []
    
    for f in arquivos_csv:
        try:
            # Solução robusta para lidar com erros de tokenização:
            # engine='python', on_bad_lines='warn', e delimiter=','
            df = pd.read_csv(f, 
                              engine='python', 
                              on_bad_lines='warn', # Avisa sobre linhas malformadas em vez de travar
                              delimiter=',',
                              encoding='utf-8')
            lista_dataframes.append(df)
        except Exception as e:
            print(f"ERRO: Falha ao ler o arquivo {f.name}. Detalhes: {e}")
            
    if not lista_dataframes:
        raise Exception(f"ERRO: Nenhum DataFrame válido foi carregado do diretório {diretorio.name}.")
            
    df_combinado = pd.concat(lista_dataframes, ignore_index=True)
    
    return df_combinado


try:
    # 1. Carrega e Consolidada as Perguntas
    df_perguntas_combinado = carregar_e_combinar_csvs(caminho_entrada_perguntas_dir, 'perguntas')
    print(f"Dataframe de Perguntas consolidado com {len(df_perguntas_combinado)} linhas.")
    
    # 2. Salva o resultado das Perguntas
    # Garantindo que o diretório de saída exista
    os.makedirs(caminho_saida_perguntas.parent, exist_ok=True)
    df_perguntas_combinado.to_csv(caminho_saida_perguntas, index=False, encoding='utf-8')
    print(f"\nConsolidação de perguntas salva em: '{caminho_saida_perguntas}'.")
    
    # 3. Carrega e Consolidada as Respostas
    df_respostas_combinado = carregar_e_combinar_csvs(caminho_entrada_respostas_dir, 'respostas')
    print(f"Dataframe de Respostas consolidado com {len(df_respostas_combinado)} linhas.")

    # 4. Salva o resultado das Respostas
    df_respostas_combinado.to_csv(caminho_saida_respostas, index=False, encoding='utf-8')
    print(f"\nConsolidação de respostas salva em: '{caminho_saida_respostas}'.")


except FileNotFoundError as e:
    print(f"ERRO CRÍTICO: Falha ao encontrar diretórios ou arquivos. Verifique se DIRETORIO_DADOS_EXTRACAO_QA está correto. Detalhes: {e}")
except Exception as e:
    print(f"Ocorreu um erro inesperado: {e}")

print("\nProcesso de consolidação concluído. Dois arquivos CSV consolidados foram criados.")