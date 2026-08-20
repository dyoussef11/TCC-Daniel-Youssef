import pandas as pd
import numpy as np
from pathlib import Path
from core.paths import PREPROCESSAMENTO_DATA

# --- CONFIGURAÇÕES DE CAMINHO ---
CAMINHO_METRICAS = PREPROCESSAMENTO_DATA / "Analise_RoBERTa_ABSA_ESTRATIFICADA_V5" / "metricas_absa_estratificada.csv"
CAMINHO_SAIDA = PREPROCESSAMENTO_DATA / "Dados_Final_Threshold_V11"
CAMINHO_SAIDA.mkdir(parents=True, exist_ok=True)

def calcular_entropia_shannon(row):
    """Calcula quão bem distribuídas estão as falhas nos 5 temas"""
    temas = ['performance', 'thermal', 'energy', 'display', 'stability']
    counts = np.array([row[t] for t in temas if t in row])
    total = counts.sum()
    if total == 0: return 0.0
    probs = counts[counts > 0] / total
    return -np.sum(probs * np.log(probs))

def executar_filtro_diversidade_cientifica():
    df = pd.read_csv(CAMINHO_METRICAS, sep=';')
    
    # Métricas de suporte baseadas no Passo 0
    df['gravidade_percentual'] = (df['total_validas'] / 500 * 100).round(2)
    df['entropia_tematica'] = df.apply(calcular_entropia_shannon, axis=1)
    df['temas_cobertos'] = (df[['performance', 'thermal', 'energy', 'display', 'stability']] > 0).sum(axis=1)

    # --- NOVOS THRESHOLDS CALIBRADOS (UFSM/SEMISH 2026) ---
    # Relaxamos para n >= 40 para capturar mais modelos com relevância estatística
    mask_rag = (
        (df['n_posts'] >= 40) &               # Poder estatístico ~0.65
        (df['gravidade_percentual'] >= 3.5) & # Acima do P25 de gravidade
        (df['entropia_tematica'] >= 0.55) &   # Garante que não é um problema único
        (df['temas_cobertos'] >= 2)           # Exige pelo menos dois tipos de falha
    )

    aprovados_rag = df[mask_rag].sort_values('score_prioridade', ascending=False)
    
    # Relatório de ganho de volume
    print(f"🚀 Modelos Aprovados para RAG (Novo Rigor): {len(aprovados_rag)}")
    # return aprovados_rag
    
    # 5. Relatório e Exportação
    print("="*60)
    print("🎯 SELEÇÃO ESTRATIFICADA PARA VETORIZAÇÃO (RAG)")
    print("="*60)
    print(f"✅ Modelos Analisados: {len(df)}")
    print(f"🚀 Modelos Aprovados para RAG: {len(aprovados_rag)}")
    
    if len(aprovados_rag) > 0:
        print("\n📈 Top 5 Modelos Selecionados para BGE-M3:")
        print(aprovados_rag[['modelo', 'n_posts', 'gravidade_percentual', 'temas_cobertos', 'score_prioridade']].head(5))

    # Salva a lista final que o BGE-M3 vai consumir
    aprovados_rag.to_csv(CAMINHO_SAIDA / "modelos_selecionados_final_rag.csv", sep=';', index=False, encoding='utf-8-sig')
    
    return aprovados_rag

if __name__ == "__main__":
    executar_filtro_diversidade_cientifica()