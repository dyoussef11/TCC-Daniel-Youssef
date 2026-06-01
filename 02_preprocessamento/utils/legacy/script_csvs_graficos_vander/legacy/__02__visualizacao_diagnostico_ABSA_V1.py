import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from core.paths import PREPROCESSAMENTO_DATA

# --- CONFIGURAÇÕES DE CAMINHO ---
CAMINHO_ENTRADA = PREPROCESSAMENTO_DATA / "Analise_RoBERTa_ABSA_ESTRATIFICADA_V5" / "metricas_absa_estratificada.csv"
CAMINHO_SAIDA = PREPROCESSAMENTO_DATA / "Graficos_Diagnostico_ABSA"
CAMINHO_SAIDA.mkdir(parents=True, exist_ok=True)

def preparar_dados(df):
    """Calcula métricas de suporte se não estiverem no CSV"""
    temas = ['performance', 'thermal', 'energy', 'display', 'stability']
    
    # Gravidade % baseada no limite de 300 sentenças
    if 'gravidade_percentual' not in df.columns:
        df['gravidade_percentual'] = (df['total_validas'] / 300 * 100).round(2)
        
    # Entropia de Shannon (Diversidade Temática)
    def calc_entropy(row):
        counts = np.array([row[t] for t in temas if t in row])
        total = counts.sum()
        if total == 0: return 0.0
        probs = counts[counts > 0] / total
        return -np.sum(probs * np.log(probs))
    
    if 'entropia_tematica' not in df.columns:
        df['entropia_tematica'] = df.apply(calc_entropy, axis=1)
    
    df['temas_cobertos'] = (df[temas] > 0).sum(axis=1)
    return df

def plotar_diagnostico(df):
    sns.set_theme(style="whitegrid")
    
    # 1. Gráfico de Bolhas: Gravidade vs Entropia
    # Mostra onde os notebooks estão no espaço de qualidade
    plt.figure(figsize=(12, 7))
    scatter = plt.scatter(
        df['entropia_tematica'], 
        df['gravidade_percentual'],
        s=df['n_posts'] * 1.5, 
        c=df['gravidade_percentual'], 
        cmap='YlOrRd', 
        alpha=0.6, 
        edgecolors="w"
    )
    
    # Linhas de Corte (Thresholds atuais que resultaram em 9 modelos)
    plt.axvline(1.01, color='blue', linestyle='--', alpha=0.5, label='Threshold Entropia (1.01)')
    plt.axhline(4.67, color='red', linestyle='--', alpha=0.5, label='Threshold Gravidade (4.67%)')
    
    plt.title('Diagnóstico ABSA: Gravidade vs Diversidade Temática\n(O tamanho da bolha indica volume de posts)', fontsize=14)
    plt.xlabel('Entropia Temática (Shannon Index)', fontsize=12)
    plt.ylabel('Gravidade Ponderada (%)', fontsize=12)
    plt.legend()
    plt.colorbar(scatter, label='Intensidade (%)')
    plt.savefig(CAMINHO_SAIDA / "01_bolhas_gravidade_vs_diversidade.png", dpi=300)
    
    # 2. Histograma de Temas Cobertos
    plt.figure(figsize=(10, 6))
    sns.countplot(data=df[df['n_posts'] >= 50], x='temas_cobertos', palette='viridis')
    plt.title('Distribuição de Quantidade de Temas por Modelo (n >= 50)', fontsize=14)
    plt.xlabel('Número de Temas com Reclamações', fontsize=12)
    plt.ylabel('Quantidade de Modelos', fontsize=12)
    plt.savefig(CAMINHO_SAIDA / "02_histograma_temas_cobertos.png", dpi=300)

    # 3. Correlação de Pearson: Volume vs Gravidade
    plt.figure(figsize=(8, 6))
    sns.regplot(data=df, x='n_posts', y='gravidade_percentual', scatter_kws={'alpha':0.3}, line_kws={'color':'red'})
    plt.title('Correlação: Volume de Posts vs Gravidade Detectada', fontsize=14)
    plt.savefig(CAMINHO_SAIDA / "03_correlacao_volume_gravidade.png", dpi=300)

def main():
    print("📊 Gerando gráficos de diagnóstico ABSA...")
    df = pd.read_csv(CAMINHO_ENTRADA, sep=';')
    df = preparar_dados(df)
    plotar_diagnostico(df)
    print(f"✅ Gráficos salvos com sucesso em: {CAMINHO_SAIDA}")

if __name__ == "__main__":
    main()