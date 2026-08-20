# mapeamento_modelos.py
import pandas as pd
from pathlib import Path

def carregar_mapeamento(csv_path: Path) -> dict:
    """
    Carrega o dataset de laptops e retorna um dicionário:
    chave: id_unico (ex: dell_g15_5530_13thgen_16gb_1tb)
    valor: nome completo com marca (ex: Dell G15 5530)
    """
    df = pd.read_csv(csv_path)
    mapa = {}
    for _, row in df.iterrows():
        key = row['id_unico']
        nome = f"{row['marca']} {row['modelo_limpo']}"
        mapa[key] = nome
    return mapa

def carregar_mapeamento_por_modelo_limpo(csv_path: Path) -> dict:
    """
    Alternativa: mapeia pelo modelo_limpo (sem marca) para o nome completo.
    Exemplo: 'g15_5530' -> 'Dell G15 5530'
    """
    df = pd.read_csv(csv_path)
    mapa = {}
    for _, row in df.iterrows():
        modelo_limpo = row['modelo_limpo']
        marca = row['marca']
        # Verifica se a marca já está presente no modelo_limpo
        if marca.lower() in modelo_limpo.lower():
            # Se já estiver, usa o modelo_limpo como está
            nome_completo = modelo_limpo
        else:
            # Senão, adiciona a marca
            nome_completo = f"{marca} {modelo_limpo}"
        mapa[modelo_limpo] = nome_completo
    return mapa

def obter_nome_modelo(modelo_original: str, modelo_generico: str, marca: str, 
                       mapa_por_modelo_limpo: dict) -> str:
    """
    Função auxiliar para obter o nome do modelo a ser usado no embedding.
    Prioridades:
      1. modelo_generico (já pode ter a marca)
      2. mapa por modelo_limpo (usa a chave = modelo_original)
      3. modelo_original com marca adicionada
    """
    # # Se modelo_generico existe e não é 'na', usa ele
    # if modelo_generico and modelo_generico.lower() != 'na':
    #     nome = modelo_generico.replace('_', ' ').title()
    #     return nome
    
    # Tenta mapear pelo modelo_original (que geralmente é igual ao modelo_limpo)
    if modelo_original in mapa_por_modelo_limpo:
        return mapa_por_modelo_limpo[modelo_original]
    
    # Fallback: usa o modelo_original e adiciona a marca se necessário
    if marca and marca.lower() not in modelo_original.lower():
        return f"{marca.title()} {modelo_original.replace('_', ' ').title()}"
    else:
        return modelo_original.replace('_', ' ').title()