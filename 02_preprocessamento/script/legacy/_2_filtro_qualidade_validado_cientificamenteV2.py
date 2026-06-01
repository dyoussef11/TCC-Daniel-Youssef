# 03_filtro_qualidade_validado_cientificamente.py (VERSÃO ATUALIZADA)
import os
import json
import numpy as np
import pandas as pd
import shutil
from pathlib import Path
from core.paths import PREPROCESSAMENTO_DATA

CAMINHO_METRICAS = PREPROCESSAMENTO_DATA / "Contagem_Analise_VaderV4_CALIBRADO" / "prevalencia_sem_pesos.csv"
CAMINHO_INPUT_JSON = PREPROCESSAMENTO_DATA / "Dados_Limpos_IniciaisV2"
CAMINHO_SAIDA_FINAL = PREPROCESSAMENTO_DATA / "Dados_Final_Threshold_V7"  # Nova versão

# NOVOS THRESHOLDS - Baseados na validação científica
THRESHOLDS = {
    # Estatísticos (da power analysis)
    "posts_unicos": 20,              # Poder estatístico ≥ 0.80, CV ≤ 15%
    
    # Conteúdo (da distribuição de densidade)
    "densidade_tecnica": 1.5,        # Ajustado para versão sem pesos (era 2.0 com pesos)
    
    # Diversidade temática
    "temas_cobertos": 2,             # Mínimo para diversidade (mantido)
    "entropia_tematica": 0.6,        # Reduzido pois sem pesos a entropia é menor
    
    # Engajamento
    "engajamento": 2.0               # Reduzido para capturar mais modelos válidos
}

def aplicar_filtro_cientifico():
    if not CAMINHO_SAIDA_FINAL.exists():
        CAMINHO_SAIDA_FINAL.mkdir(parents=True)
    
    df = pd.read_csv(CAMINHO_METRICAS, sep=';')
    
    print(f"📊 Colunas disponíveis: {list(df.columns)}")
    
    # Verifica quais colunas existem e ajusta dinamicamente
    col_densidade = 'densidade_tecnica' if 'densidade_tecnica' in df.columns else 'densidade_ponderada'
    col_posts = 'posts_unicos'
    col_temas = 'temas_cobertos'
    col_entropia = 'entropia_tematica' if 'entropia_tematica' in df.columns else None
    col_engajamento = 'engajamento' if 'engajamento' in df.columns else None
    
    # Se não tem entropia, calcula
    if col_entropia is None:
        temas = ['performance', 'thermal', 'energy', 'display', 'stability']
        def calc_entropy(row):
            counts = np.array([row[t] for t in temas if t in df.columns])
            total = counts.sum()
            if total == 0:
                return 0.0
            probs = counts[counts > 0] / total
            return -np.sum(probs * np.log(probs))
        df['entropia_tematica_calc'] = df.apply(calc_entropy, axis=1)
        col_entropia = 'entropia_tematica_calc'
    
    # Aplica thresholds
    mask = (df[col_posts] >= THRESHOLDS['posts_unicos'])
    mask = mask & (df[col_densidade] >= THRESHOLDS['densidade_tecnica'])
    mask = mask & (df[col_temas] >= THRESHOLDS['temas_cobertos'])
    mask = mask & (df[col_entropia] >= THRESHOLDS['entropia_tematica'])
    
    if col_engajamento and col_engajamento in df.columns:
        mask = mask & (df[col_engajamento] >= THRESHOLDS['engajamento'])
    
    # Remove outliers extremos (99º percentil) - ajustado para versão sem pesos
    Q99 = df[col_densidade].quantile(0.99)
    mask = mask & (df[col_densidade] <= Q99)
    
    aprovados = df[mask]
    
    print(f"\n" + "="*60)
    print(f"📊 RESULTADO DO FILTRO CIENTÍFICO")
    print(f"="*60)
    print(f"   - Modelos analisados: {len(df)}")
    print(f"   - Modelos aprovados: {len(aprovados)} ({len(aprovados)/len(df)*100:.1f}%)")
    print(f"\n📈 ESTATÍSTICAS DOS APROVADOS:")
    print(f"   - Posts totais: {aprovados[col_posts].sum():,}")
    print(f"   - Média posts/modelo: {aprovados[col_posts].mean():.1f}")
    print(f"   - Densidade média: {aprovados[col_densidade].mean():.2f}")
    print(f"   - Temas médios: {aprovados[col_temas].mean():.1f}")
    
    # Salva lista de aprovados
    aprovados.to_csv(CAMINHO_SAIDA_FINAL / "modelos_aprovados_cientificamente.csv", 
                     index=False, sep=';', encoding='utf-8-sig')
    
    # Copia arquivos JSON
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
    
    print(f"   - Arquivos JSON copiados: {copiados}")
    
    print(f"\n✅ Filtro concluído! Dados em: {CAMINHO_SAIDA_FINAL}")

if __name__ == "__main__":
    aplicar_filtro_cientifico()