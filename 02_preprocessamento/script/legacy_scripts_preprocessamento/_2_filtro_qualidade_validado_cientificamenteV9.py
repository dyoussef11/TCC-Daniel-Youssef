import os
import json
import numpy as np
import pandas as pd
import shutil
from pathlib import Path
from core.paths import PREPROCESSAMENTO_DATA

# --- CONFIGURAÇÕES DE CAMINHO ---
CAMINHO_METRICAS = PREPROCESSAMENTO_DATA / "Analise_RoBERTa_V7_FINAL" / "metricas_completas_roberta.csv"
CAMINHO_INPUT_JSON = PREPROCESSAMENTO_DATA / "Dados_Limpos_IniciaisV3"
CAMINHO_SAIDA_FINAL = PREPROCESSAMENTO_DATA / "Dados_Final_RoBERTa_Threshold_V1"

# --- THRESHOLDS AJUSTADOS PARA GRAVIDADE RoBERTa ---
THRESHOLDS_BY_RIGOR = {
    "exploratorio": {
        "n_posts": 30,
        "gravidade_percentual": 0.5,
        "temas_cobertos": 1,
        "entropia_tematica": 0.3
    },
    "padrao": {
        "n_posts": 50,
        "gravidade_percentual": 0.8,
        "temas_cobertos": 2,
        "entropia_tematica": 0.5
    },
    "conservador": {
        "n_posts": 65,
        "gravidade_percentual": 5.67,
        "temas_cobertos": 4,
        "entropia_tematica": 1.01
    },
    "rigoroso": {
        "n_posts": 100,
        "gravidade_percentual": 1.5,
        "temas_cobertos": 4,
        "entropia_tematica": 1.2
    }
}

def verificar_colunas(df):
    colunas = {}
    colunas['posts'] = 'n_posts' if 'n_posts' in df.columns else 'posts_unicos'
    colunas['densidade'] = 'gravidade_percentual' if 'gravidade_percentual' in df.columns else 'densidade_roberta'
    colunas['modelo'] = 'modelo'
    return colunas

def calcular_entropia(df):
    temas = ['performance', 'thermal', 'energy', 'display', 'stability']
    temas_existentes = [t for t in temas if t in df.columns]
    
    def calc_entropy(row):
        counts = np.array([row[t] for t in temas_existentes])
        total = counts.sum()
        if total == 0: return 0.0
        probs = counts[counts > 0] / total
        return -np.sum(probs * np.log(probs))
    
    df['entropia_tematica'] = df.apply(calc_entropy, axis=1)
    return df

def aplicar_filtro_cientifico(rigor="conservador", dry_run=True):
    if not CAMINHO_SAIDA_FINAL.exists() and not dry_run:
        CAMINHO_SAIDA_FINAL.mkdir(parents=True)
    
    df = pd.read_csv(CAMINHO_METRICAS, sep=';')
    colunas = verificar_colunas(df)
    df = calcular_entropia(df)
    
    th = THRESHOLDS_BY_RIGOR[rigor]
    
    # Aplicação da Máscara de Filtro
    mask = (df[colunas['posts']] >= th['n_posts']) & \
           (df[colunas['densidade']] >= th['gravidade_percentual']) & \
           (df['entropia_tematica'] >= th['entropia_tematica'])
    
    aprovados = df[mask].copy()
    
    print(f"🎯 Rigor: {rigor.upper()} | Modelos Aprovados: {len(aprovados)}")
    
    if not dry_run and len(aprovados) > 0:
        output_file = CAMINHO_SAIDA_FINAL / f"modelos_aprovados_{rigor}.csv"
        aprovados.to_csv(output_file, index=False, sep=';', encoding='utf-8-sig')
        
        # Cópia dos JSONs originais para a pasta final
        for mod in aprovados[colunas['modelo']]:
            origem = CAMINHO_INPUT_JSON / f"{mod}.json" # Ajuste se o nome do arquivo for diferente
            if origem.exists():
                shutil.copy2(origem, CAMINHO_SAIDA_FINAL / f"{rigor}_{mod}.json")
    
    return aprovados

if __name__ == "__main__":
    aplicar_filtro_cientifico(rigor="conservador", dry_run=False)