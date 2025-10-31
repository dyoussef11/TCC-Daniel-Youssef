# deduplicador.py

import pandas as pd
import csv 
import sys
from pathlib import Path
import re
import numpy as np

# --- CONFIGURAÇÃO INICIAL (LÓGICA FORNECIDA PELO USUÁRIO) ---

# Obtém o caminho absoluto da pasta do script atual.
# NOTA: Esta é a lógica que você forneceu para garantir a importação de paths/config
try:
    caminho_script = Path(__file__).resolve().parent
    caminho_raiz_projeto = caminho_script.parent.parent
    sys.path.append(str(caminho_raiz_projeto))
    
    # Importação do módulo 'config' (Assumindo que ele está na raiz do projeto)
    from config import DIRETORIO_CSV_DATASET_COLETADOS, DIRETORIO_CSV_DATASET_FINAL
    print("Paths de diretório lidos do config.py.")
except ImportError:
    # Fallback para execução local, se 'config' não for acessível
    print("Aviso: 'config.py' não encontrado. Usando Paths simulados.")
    class PathSimulado:
        def __init__(self, *args):
            self.parts = args
        def __truediv__(self, other):
            return PathSimulado(*self.parts, other)
        def __str__(self):
            return '/'.join(self.parts)
        @property
        def name(self):
            return self.parts[-1] if self.parts else ''

    DIRETORIO_CSV_DATASET_COLETADOS = PathSimulado('data', 'coletados')
    DIRETORIO_CSV_DATASET_FINAL = PathSimulado('data', 'final')
    Path = PathSimulado
except NameError:
     # Em ambientes de notebook onde __file__ não existe
     print("Aviso: Variável __file__ não definida. Usando Paths simulados.")
     class PathSimulado:
        def __init__(self, *args):
            self.parts = args
        def __truediv__(self, other):
            return PathSimulado(*self.parts, other)
        def __str__(self):
            return '/'.join(self.parts)
        @property
        def name(self):
            return self.parts[-1] if self.parts else ''

     DIRETORIO_CSV_DATASET_COLETADOS = PathSimulado('data', 'coletados')
     DIRETORIO_CSV_DATASET_FINAL = PathSimulado('data', 'final')


# --- NOMES DE ARQUIVO ---
# Utiliza o nome do arquivo que você especificou
ARQUIVO_ENTRADA = DIRETORIO_CSV_DATASET_FINAL / 'dataset_laptops.csv'
# Novo nome para a saída desduplicada
ARQUIVO_SAIDA = DIRETORIO_CSV_DATASET_FINAL / 'dataset_laptops_UNICOS.csv'


def deduplicar_por_nome_assinatura():
    """
    Carrega o dataset e mantém apenas uma linha para cada 'Nome_Assinatura' único.
    """
    print(f"\n--- Iniciando a Desduplicação de Nomes de Assinatura ---")
    print(f"Tentando ler o arquivo de entrada: {ARQUIVO_ENTRADA}")
    
    # Converte o Path para string para compatibilidade com pd.read_csv
    caminho_entrada_str = str(ARQUIVO_ENTRADA)
    caminho_saida_str = str(ARQUIVO_SAIDA)
    
    # Verificação simples de existência (assumindo que o Path simulado não suporta .exists())
    if 'Simulado' not in str(Path) and not Path(caminho_entrada_str).exists():
        print(f"ERRO: Arquivo de entrada não encontrado. Certifique-se de que '{ARQUIVO_ENTRADA.name}' foi gerado.")
        return

    try:
        # Carrega o DataFrame
        df = pd.read_csv(caminho_entrada_str)
        tamanho_original = len(df)
        print(f"Dataset lido com sucesso. Registros totais: {tamanho_original}")
        
        # 1. Limpeza e Conversão para Garantir Comparação Correta
        df['Marca'] = df['Marca'].astype(str).str.strip().str.upper()
        df['Nome_Assinatura'] = df['Nome_Assinatura'].astype(str).str.strip().str.upper()

        # 2. Desduplicação:
        # Mantém apenas o primeiro registro encontrado para cada combinação (Marca + Nome_Assinatura).
        df_unico = df.drop_duplicates(subset=['Marca', 'Nome_Assinatura'], keep='first')
        
        # Opcional: Remover linhas onde a Nome_Assinatura ficou vazia após o processamento
        df_unico.dropna(subset=['Nome_Assinatura'], inplace=True)
        
        tamanho_final = len(df_unico)
        
        print(f"Desduplicação concluída.")
        print(f"Registros ÚNICOS mantidos: {tamanho_final}")
        print(f"Total de linhas removidas (duplicadas): {tamanho_original - tamanho_final}")

        # 3. Salvar o resultado
        df_unico.to_csv(caminho_saida_str, index=False)
        
        print("\n--- Processo de Desduplicação COMPLETO ---")
        print(f"Dataset final para busca (nomes únicos) salvo em: {ARQUIVO_SAIDA.name}")

        # Demonstração do resultado (Exemplo de 'ROG STRIX' que deve aparecer apenas uma vez)
        print(f"\n--- Exemplo de Nomes de Assinatura Únicos (Primeiros 10) ---")
        print(df_unico['Nome_Assinatura'].unique().tolist()[:10])

    except Exception as e:
        print(f"ERRO durante a desduplicação: {e}")

if __name__ == "__main__":
    deduplicar_por_nome_assinatura()