# 03_filtro_qualidade_validado_cientificamente.py
import os
import json
import pandas as pd
import shutil
from pathlib import Path
from core.paths import PREPROCESSAMENTO_DATA

CAMINHO_METRICAS = PREPROCESSAMENTO_DATA / "Contagem_Analise_VaderV3_CALIBRADO" / "prevalencia_calibrada.csv"
# CAMINHO_INPUT_JSON = PREPROCESSAMENTO_DATA / "Dados_Consolidados_Por_ModeloV2"
CAMINHO_INPUT_JSON = PREPROCESSAMENTO_DATA / "Dados_Limpos_IniciaisV2"
CAMINHO_SAIDA_FINAL = PREPROCESSAMENTO_DATA / "Dados_Final_Threshold_V6"

# Thresholds baseados em evidência estatística
THRESHOLDS = {
    "posts_unicos": 30,           # CV < 50%, poder > 0.5
    "densidade_ponderada": 2.0,    # Percentil 30
    "temas_cobertos": 2,           # Mínimo para diversidade
    "entropia_tematica": 0.8,      # Distribuição balanceada
    "engajamento": 3.0             # Pelo menos 3 comentários/post
}

def aplicar_filtro_cientifico():
    if not CAMINHO_SAIDA_FINAL.exists():
        CAMINHO_SAIDA_FINAL.mkdir(parents=True)
    
    df = pd.read_csv(CAMINHO_METRICAS, sep=';')
    
    # Aplica thresholds
    mask = (
        (df['posts_unicos'] >= THRESHOLDS['posts_unicos']) &
        (df['densidade_ponderada'] >= THRESHOLDS['densidade_ponderada']) &
        (df['temas_cobertos'] >= THRESHOLDS['temas_cobertos']) &
        (df['entropia_tematica'] >= THRESHOLDS['entropia_tematica']) &
        (df['engajamento'] >= THRESHOLDS['engajamento'])
    )
    
    # Remove outliers extremos
    Q3 = df['densidade_ponderada'].quantile(0.99)
    mask = mask & (df['densidade_ponderada'] <= Q3)
    
    aprovados = df[mask]
    
    print(f"📊 Resultado do Filtro Científico:")
    print(f"   - Modelos analisados: {len(df)}")
    print(f"   - Modelos aprovados: {len(aprovados)} ({len(aprovados)/len(df)*100:.1f}%)")
    print(f"   - Posts totais: {aprovados['posts_unicos'].sum():,}")
    print(f"   - Densidade média: {aprovados['densidade_ponderada'].mean():.2f}")
    
    # Copia arquivos aprovados
    modelos_aprovados = set(aprovados['modelo'].unique())
    copiados = 0
    
    for arq in os.listdir(CAMINHO_INPUT_JSON):
        if not arq.endswith('.json'):
            continue
        
        with open(CAMINHO_INPUT_JSON / arq, 'r', encoding='utf-8') as f:
            dados = json.load(f)
        
        modelo = dados.get('modelo_busca_utilizado')
        if modelo in modelos_aprovados:
            shutil.copy2(CAMINHO_INPUT_JSON / arq, CAMINHO_SAIDA_FINAL / arq)
            copiados += 1
    
    print(f"   - Arquivos copiados: {copiados}")
    
    # Salva lista de aprovados para referência
    aprovados.to_csv(CAMINHO_SAIDA_FINAL / "modelos_aprovados_cientificamente.csv", 
                     index=False, sep=';', encoding='utf-8-sig')
    
    print(f"\n✅ Filtro concluído! Dados em: {CAMINHO_SAIDA_FINAL}")

if __name__ == "__main__":
    aplicar_filtro_cientifico()