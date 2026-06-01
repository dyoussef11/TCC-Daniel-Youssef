# 03_filtro_qualidade_validado_cientificamente.py (VERSÃO FINAL)
import os
import json
import numpy as np
import pandas as pd
import shutil
from pathlib import Path
from core.paths import PREPROCESSAMENTO_DATA

CAMINHO_METRICAS = PREPROCESSAMENTO_DATA / "Contagem_Analise_VaderV4_CALIBRADO" / "prevalencia_sem_pesos.csv"
CAMINHO_INPUT_JSON = PREPROCESSAMENTO_DATA / "Dados_Limpos_IniciaisV2"
CAMINHO_SAIDA_FINAL = PREPROCESSAMENTO_DATA / "Dados_Final_Threshold_V8_FINAL"  # Nova versão

# NOVOS THRESHOLDS - Baseados na validação científica com poder estatístico
THRESHOLDS = {
    # ===== ESTATÍSTICOS (Power Analysis) =====
    # NOTA: n=20 tem poder 0.34 (inadequado)
    #       n=30 tem poder 0.46 (ainda baixo, mas melhor)
    #       n=50 tem poder 0.71 (aceitável para pesquisa exploratória)
    #       n=100 tem poder 0.94 (ideal)
    
    "posts_unicos": 30,              # Mínimo para poder estatístico > 0.45
    
    # ===== CONTEÚDO (Distribuição real) =====
    "densidade_tecnica": 1.0,        # Percentil 25 (1.01) arredondado para baixo
                                     # Modelos acima disso têm mais problemas que 75% dos outros
    
    # ===== DIVERSIDADE =====
    "temas_cobertos": 2,             # Mínimo para diversidade (mantido)
    "entropia_tematica": 0.6,        # Diversidade balanceada
    
    # ===== ENGAJAMENTO =====
    "engajamento": 3.0               # Média de comentários por post
}

# Thresholds alternativos por nível de rigor
THRESHOLDS_BY_RIGOR = {
    "exploratorio": {
        "posts_unicos": 20,          # Poder 0.34 - risco alto
        "densidade_tecnica": 0.8,
        "temas_cobertos": 1,
        "entropia_tematica": 0.4,
        "engajamento": 2.0
    },
    "padrao": {
        "posts_unicos": 30,          # Poder 0.46 - aceitável
        "densidade_tecnica": 1.0,
        "temas_cobertos": 2,
        "entropia_tematica": 0.6,
        "engajamento": 3.0
    },
    "conservador": {
        "posts_unicos": 50,          # Poder 0.71 - recomendado
        "densidade_tecnica": 1.5,
        "temas_cobertos": 2,
        "entropia_tematica": 0.7,
        "engajamento": 3.0
    },
    "rigoroso": {
        "posts_unicos": 100,         # Poder 0.94 - ideal para publicação
        "densidade_tecnica": 2.0,
        "temas_cobertos": 3,
        "entropia_tematica": 0.8,
        "engajamento": 4.0
    }
}

def aplicar_filtro_cientifico(rigor="padrao"):
    """
    Aplica filtro com diferentes níveis de rigor.
    
    rigor: 'exploratorio', 'padrao', 'conservador', 'rigoroso'
    """
    if not CAMINHO_SAIDA_FINAL.exists():
        CAMINHO_SAIDA_FINAL.mkdir(parents=True)
    
    # Seleciona thresholds baseado no rigor
    thresholds = THRESHOLDS_BY_RIGOR.get(rigor, THRESHOLDS_BY_RIGOR["conservador"])
    
    df = pd.read_csv(CAMINHO_METRICAS, sep=';')
    
    print(f"📊 Modo: {rigor.upper()}")
    print(f"   Thresholds: {thresholds}")
    
    # Verifica colunas
    col_densidade = 'densidade_tecnica' if 'densidade_tecnica' in df.columns else 'densidade_ponderada'
    col_posts = 'posts_unicos'
    col_temas = 'temas_cobertos' if 'temas_cobertos' in df.columns else None
    
    # Calcula entropia se não existir
    if 'entropia_tematica' not in df.columns:
        temas = ['performance', 'thermal', 'energy', 'display', 'stability']
        def calc_entropy(row):
            counts = np.array([row[t] for t in temas if t in df.columns])
            total = counts.sum()
            if total == 0:
                return 0.0
            probs = counts[counts > 0] / total
            return -np.sum(probs * np.log(probs))
        df['entropia_tematica'] = df.apply(calc_entropy, axis=1)
    
    # Aplica thresholds
    mask = (df[col_posts] >= thresholds['posts_unicos'])
    mask = mask & (df[col_densidade] >= thresholds['densidade_tecnica'])
    
    if col_temas:
        mask = mask & (df[col_temas] >= thresholds['temas_cobertos'])
    
    mask = mask & (df['entropia_tematica'] >= thresholds['entropia_tematica'])
    
    if 'engajamento' in df.columns:
        mask = mask & (df['engajamento'] >= thresholds['engajamento'])
    
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
    
    # Salva lista de aprovados
    aprovados.to_csv(CAMINHO_SAIDA_FINAL / f"modelos_aprovados_{rigor}.csv", 
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
            shutil.copy2(CAMINHO_INPUT_JSON / arq, CAMINHO_SAIDA_FINAL / f"{rigor}_{arq}")
            copiados += 1
    
    print(f"   - Arquivos JSON copiados: {copiados}")
    
    # Gera relatório comparativo
    gerar_relatorio_comparativo(df, rigor)
    
    return aprovados

def gerar_relatorio_comparativo(df, rigor_used):
    """Gera relatório comparativo dos thresholds"""
    
    relatorio = []
    relatorio.append("# Relatório de Validação de Thresholds\n")
    relatorio.append(f"## Rigor utilizado: {rigor_used.upper()}\n")
    
    relatorio.append("## Comparação de Cenários\n")
    relatorio.append("| Rigor | n mínimo | Densidade mínima | Modelos aprovados | % do total |")
    relatorio.append("|-------|----------|------------------|-------------------|------------|")
    
    for rigor, th in THRESHOLDS_BY_RIGOR.items():
        mask = (df['posts_unicos'] >= th['posts_unicos'])
        mask = mask & (df['densidade_tecnica'] >= th['densidade_tecnica'])
        
        n_aprovados = mask.sum()
        pct = n_aprovados / len(df) * 100
        
        relatorio.append(f"| {rigor} | {th['posts_unicos']} | {th['densidade_tecnica']} | {n_aprovados} | {pct:.1f}% |")
    
    with open(CAMINHO_SAIDA_FINAL / "relatorio_thresholds.md", 'w', encoding='utf-8') as f:
        f.write('\n'.join(relatorio))
    
    print(f"\n📄 Relatório: {CAMINHO_SAIDA_FINAL / 'relatorio_thresholds.md'}")

if __name__ == "__main__":
    # Para teste com diferentes níveis:
    # aplicar_filtro_cientifico("exploratorio")
    aplicar_filtro_cientifico("padrao")
    # aplicar_filtro_cientifico("conservador")
    # aplicar_filtro_cientifico("rigoroso")