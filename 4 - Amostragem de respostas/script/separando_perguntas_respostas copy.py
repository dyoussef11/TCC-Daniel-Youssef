import sys
from pathlib import Path
import pandas as pd
import os
import numpy as np
import re
from sklearn.model_selection import train_test_split
# --- Configuração de Caminho ---
# Navegação para a raiz do projeto para importar 'config'
caminho_script = Path(__file__).resolve().parent
caminho_raiz_projeto = caminho_script.parent.parent
sys.path.append(str(caminho_raiz_projeto))

# Importa os diretórios
from config import DIRETORIO_DADOS_EXTRACAO_QA,  DIRETORIO_DADOS_UNIFICACAO 

# Define as PASTAS de entrada
caminho_entrada_respostas_dir = DIRETORIO_DADOS_UNIFICACAO / 'respostas_combinadas_final.csv'

# Seus dados já foram carregados, usaremos o DataFrame 'df'
df = pd.read_csv(caminho_entrada_respostas_dir) 

# Definindo as categorias para rotulagem
CATEGORIES = [
    "SOLUÇÃO (EFETIVA ou POTENCIAL)",
    "INFORMATIVA/DIAGNÓSTICO",
    "ESPECULATIVA/INVÁLIDA",
    "IRRELEVANTE/FORA DE TÓPICO",
    "FEEDBACK DE FECHAMENTO"
]

# Limpeza básica (preencher NaNs no campo de comentários, se houver)
df['Conteudo_Comentario'] = df['Conteudo_Comentario'].fillna('')

print(f"Total de comentários no dataset: {len(df)}")