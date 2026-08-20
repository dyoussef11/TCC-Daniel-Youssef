# mapeamento_modelos.py
import pandas as pd
from pathlib import Path

def carregar_mapeamento_por_modelo_limpo(csv_path: Path) -> dict:
    """
    Carrega CSV e retorna dicionário: modelo_limpo (limpo, sem underlines) -> nome completo.
    Exemplo: 'g15_5530' -> 'Dell G15 5530'
    """
    if not csv_path.exists():
        print(f"⚠️ CSV não encontrado em {csv_path}")
        return {}
    df = pd.read_csv(csv_path)
    mapa = {}
    for _, row in df.iterrows():
        modelo_limpo = str(row['modelo_limpo']).strip()
        marca = str(row['marca']).strip()
        if not modelo_limpo or modelo_limpo == 'nan':
            continue
        # Monta nome completo: marca + modelo_limpo (se marca não estiver presente)
        if marca.lower() in modelo_limpo.lower():
            nome_completo = modelo_limpo
        else:
            nome_completo = f"{marca} {modelo_limpo}"
        # Remove underlines e capitaliza
        nome_completo = ' '.join(nome_completo.split()).replace('_', ' ').title()
        mapa[modelo_limpo] = nome_completo
    print(f"✅ Mapeamento carregado: {len(mapa)} modelos")
    return mapa

def obter_nome_modelo(modelo_original: str, marca_arquivo: str, mapa_por_modelo_limpo: dict) -> str:
    """
    Retorna nome do modelo pronto para embedding.
    Estratégia:
      1. Tenta match exato com modelo_original (igual ao modelo_limpo do CSV)
      2. Se não, tenta a parte antes do primeiro '_' (ex: 'proart_p16' a partir de 'proart_p16_h7606...')
      3. Fallback: marca + modelo_original limpo (sem underlines)
    """
    if not modelo_original:
        return "Unknown Model"

    # Passo 1: match exato
    if modelo_original in mapa_por_modelo_limpo:
        return mapa_por_modelo_limpo[modelo_original]

    # Passo 2: tenta usar a parte principal (até o primeiro underline)
    partes = modelo_original.split('_')
    if len(partes) > 1:
        chave_curta = '_'.join(partes[:2])  # ex: 'proart_p16'
        if chave_curta in mapa_por_modelo_limpo:
            return mapa_por_modelo_limpo[chave_curta]

    # Passo 3: fallback
    nome_base = modelo_original.replace('_', ' ').title()
    if marca_arquivo and marca_arquivo.lower() not in nome_base.lower():
        nome_base = f"{marca_arquivo.title()} {nome_base}"
    return nome_base