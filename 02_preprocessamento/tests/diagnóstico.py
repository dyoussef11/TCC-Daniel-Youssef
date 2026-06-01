import pandas as pd
from core.paths import PREPROCESSAMENTO_DATA
import os

# Verifica se o arquivo V5 existe
caminho_v5 = PREPROCESSAMENTO_DATA / "Contagem_Analise_VaderV5_CALIBRADO" / "prevalencia_sem_pesos.csv"
print(f"Arquivo V5 existe? {caminho_v5.exists()}")
print(f"Tamanho do arquivo: {caminho_v5.stat().st_size if caminho_v5.exists() else 'N/A'} bytes")

if caminho_v5.exists():
    # Tenta ler com diferentes separadores
    for sep in [';', ',']:
        try:
            df = pd.read_csv(caminho_v5, sep=sep)
            print(f"\n--- Separador '{sep}' ---")
            print(f"Colunas: {list(df.columns)[:5]}...")
            print(f"Total menções: {df['total_mencoes'].sum():,}")
            print(f"Densidade média: {df['densidade_tecnica'].mean():.2f}")
        except Exception as e:
            print(f"Erro com sep='{sep}': {e}")