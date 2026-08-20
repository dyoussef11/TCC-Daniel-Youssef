# 03_filtro_qualidade_validado_cientificamente.py (VERSÃO FINAL - ALINHADA)
import os
import json
import numpy as np
import pandas as pd
import shutil
from pathlib import Path
from core.paths import PREPROCESSAMENTO_DATA

# ATENÇÃO: Agora usando V5 (alinhado com busca Reddit)
CAMINHO_METRICAS = PREPROCESSAMENTO_DATA / "Contagem_Analise_VaderV5_CALIBRADO" / "prevalencia_sem_pesos.csv"
CAMINHO_INPUT_JSON = PREPROCESSAMENTO_DATA / "Dados_Limpos_IniciaisV3"
CAMINHO_SAIDA_FINAL = PREPROCESSAMENTO_DATA / "Dados_Final_Threshold_V10_ALINHADO"

# NOVOS THRESHOLDS - Baseados na validação com 23 termos (alinhado com busca Reddit)
# Distribuição real da densidade_tecnica: p25=0.46, p50=0.85, p75=1.30

# NOVOS THRESHOLDS - Baseados na distribuição real do V5
# Distribuição da densidade_tecnica:
# p25=0.46, p50=0.85, p75=1.30

THRESHOLDS_BY_RIGOR = {
    "exploratorio": {
        "posts_unicos": 20,
        "densidade_tecnica": 0.4,    # Abaixo do p25
        "temas_cobertos": 1,
        "entropia_tematica": 0.4,
        "engajamento": 2.0
    },
    "padrao": {
        "posts_unicos": 30,
        "densidade_tecnica": 0.5,    # Logo acima do p25 (0.46)
        "temas_cobertos": 2,
        "entropia_tematica": 0.5,
        "engajamento": 3.0
    },
    "conservador": {
        "posts_unicos": 50,
        "densidade_tecnica": 0.9,    # Próximo da mediana (0.85)
        "temas_cobertos": 2,
        "entropia_tematica": 0.6,
        "engajamento": 3.0
    },
    "rigoroso": {
        "posts_unicos": 100,
        "densidade_tecnica": 1.3,    # Percentil 75 (1.30)
        "temas_cobertos": 3,
        "entropia_tematica": 0.7,
        "engajamento": 4.0
    }
}

def aplicar_filtro_cientifico(rigor="conservador"):  # Mudado para conservador como padrão
    """
    Aplica filtro com diferentes níveis de rigor.
    
    rigor: 'exploratorio', 'padrao', 'conservador', 'rigoroso'
    
    Recomendação: usar 'conservador' (n=50, densidade=0.9)
    """
    if not CAMINHO_SAIDA_FINAL.exists():
        CAMINHO_SAIDA_FINAL.mkdir(parents=True)
    
    thresholds = THRESHOLDS_BY_RIGOR.get(rigor, THRESHOLDS_BY_RIGOR["conservador"])
    
    df = pd.read_csv(CAMINHO_METRICAS, sep=';')
    
    print("="*70)
    print("📊 FILTRO DE QUALIDADE CIENTÍFICA (VERSÃO ALINHADA COM BUSCA REDDIT)")
    print("="*70)
    print(f"📁 Arquivo de métricas: {CAMINHO_METRICAS}")
    print(f"🎯 Rigor: {rigor.upper()}")
    print(f"📏 Thresholds: {thresholds}")
    
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
    
    # Estatísticas descritivas da densidade
    print(f"\n📊 Distribuição da Densidade Técnica (n={len(df)}):")
    print(f"   - Percentil 25: {df[col_densidade].quantile(0.25):.2f}")
    print(f"   - Mediana: {df[col_densidade].median():.2f}")
    print(f"   - Percentil 75: {df[col_densidade].quantile(0.75):.2f}")
    print(f"   - Média: {df[col_densidade].mean():.2f}")
    
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
    print(f"   - Engajamento médio: {aprovados['engajamento'].mean():.1f}")
    
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
    relatorio.append("# Relatório de Validação de Thresholds (Versão Alinhada)\n")
    relatorio.append(f"## Rigor utilizado: {rigor_used.upper()}\n")
    
    relatorio.append("## Estatísticas da Densidade Técnica\n")
    relatorio.append(f"- Percentil 25: {df['densidade_tecnica'].quantile(0.25):.2f}")
    relatorio.append(f"- Mediana: {df['densidade_tecnica'].median():.2f}")
    relatorio.append(f"- Percentil 75: {df['densidade_tecnica'].quantile(0.75):.2f}")
    relatorio.append(f"- Média: {df['densidade_tecnica'].mean():.2f}")
    
    relatorio.append("\n## Comparação de Cenários\n")
    relatorio.append("| Rigor | n mínimo | Densidade mínima | Entropia | Modelos aprovados | % do total |")
    relatorio.append("|-------|----------|------------------|----------|-------------------|------------|")
    
    for rigor, th in THRESHOLDS_BY_RIGOR.items():
        mask = (df['posts_unicos'] >= th['posts_unicos'])
        mask = mask & (df['densidade_tecnica'] >= th['densidade_tecnica'])
        mask = mask & (df['entropia_tematica'] >= th['entropia_tematica'])
        
        n_aprovados = mask.sum()
        pct = n_aprovados / len(df) * 100
        
        relatorio.append(f"| {rigor} | {th['posts_unicos']} | {th['densidade_tecnica']} | {th['entropia_tematica']} | {n_aprovados} | {pct:.1f}% |")
    
    with open(CAMINHO_SAIDA_FINAL / "relatorio_thresholds.md", 'w', encoding='utf-8') as f:
        f.write('\n'.join(relatorio))
    
    print(f"\n📄 Relatório: {CAMINHO_SAIDA_FINAL / 'relatorio_thresholds.md'}")

if __name__ == "__main__":
    # Recomendado para seu trabalho:
    # aplicar_filtro_cientifico("conservador")  # n=50, densidade=0.9
    
    # Opções alternativas:
    aplicar_filtro_cientifico("padrao")       # n=30, densidade=0.5
    # aplicar_filtro_cientifico("rigoroso")     # n=100, densidade=1.3