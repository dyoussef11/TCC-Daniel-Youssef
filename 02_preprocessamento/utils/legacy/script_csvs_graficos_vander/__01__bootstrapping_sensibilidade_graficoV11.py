"""
Bootstrapping CIENTÍFICO V11 - Fidelidade Visual Total
Replicação exata dos estilos, cores e anotações das imagens de referência.
"""
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from scipy import stats
from core.paths import PREPROCESSAMENTO_DATA

CAMINHO_ENTRADA = PREPROCESSAMENTO_DATA / "Contagem_Analise_VaderV7_CALIBRADO" / "prevalencia_com_diversidade.csv"
CAMINHO_SAIDA = PREPROCESSAMENTO_DATA / "Validacao_CientificaV12"
CAMINHO_SAIDA.mkdir(parents=True, exist_ok=True)

def bootstrap_estratificado(df, n_bootstrap=1000):
    df['faixa_tamanho'] = pd.cut(df['posts_unicos'], 
                                   bins=[0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85, 90, 95, 100, 1000],
                                   labels=['<5', '5-10', '10-15', '15-20', '20-25', '25-30', '30-35', '35-40', '40-45', '45-50', '50-55', '55-60', '60-65', '65-70', '70-75', '75-80', '80-85', '85-90', '90-95', '95-100', '>100'])
    
    resultados = []
    for faixa in df['faixa_tamanho'].unique():
        df_faixa = df[df['faixa_tamanho'] == faixa]
        if len(df_faixa) < 3: continue
        taxa_media = df_faixa['total_mencoes'].sum() / df_faixa['posts_unicos'].sum() if df_faixa['posts_unicos'].sum() > 0 else 0
        if taxa_media == 0: continue
        
        cv_list = []
        for _ in range(n_bootstrap):
            sample = df_faixa.sample(n=min(30, len(df_faixa)), replace=True)
            mencoes_boot = np.random.poisson(taxa_media, len(sample))
            cv = (np.std(mencoes_boot) / (np.mean(mencoes_boot) + 0.001)) * 100
            cv_list.append(cv)
        resultados.append({'faixa': faixa, 'cv_mean': np.mean(cv_list)})
    return pd.DataFrame(resultados)

def power_analysis(effect_size=0.5, alpha=0.05):
    from statsmodels.stats.power import TTestIndPower
    analysis = TTestIndPower()
    resultados = []
    # Incremento de 2 em 2 para precisão, mas com pontos de 5 em 5 para as anotações
    for n in range(20, 105, 5):
        power = analysis.power(effect_size=effect_size, nobs1=n, alpha=alpha, ratio=1.0)
        resultados.append({'n_posts': n, 'power': power})
    return pd.DataFrame(resultados)

def gerar_graficos_validacao(df, df_bootstrap, df_power):
    col_densidade = 'densidade_tecnica'
    if col_densidade not in df.columns:
        df[col_densidade] = df['total_mencoes'] / df['palavras'] * 1000

    # 1. Distribuição de Posts (Fiel à imagem 01)
    plt.figure(figsize=(12, 7))
    sns.histplot(df['posts_unicos'], bins=50, color='#729ece', edgecolor='black')
    colors = ['red', 'orange', 'orange', 'green', 'blue', 'purple']
    labels = ['n=20', 'n=30', 'n=40', 'n=50', 'n=75', 'n=100']
    vals = [20, 30, 40, 50, 75, 100]
    for v, c, l in zip(vals, colors, labels):
        plt.axvline(x=v, color=c, linestyle='--', label=l)
    plt.title('Distribuição de Posts por Modelo', fontsize=14)
    plt.xlabel('Número de Posts', fontsize=12)
    plt.ylabel('Count', fontsize=12)
    plt.legend()
    plt.savefig(CAMINHO_SAIDA / "01_distribuicao_posts.png", dpi=300)
    plt.close()

    # 2. CV Estratificado (Fiel à imagem 02 - Paleta Viridis)
    plt.figure(figsize=(14, 8))
    faixas_ordem = ['<5', '5-10', '10-15', '15-20', '20-25', '25-30', '30-35', '35-40', '40-45', '45-50', '50-55', '55-60', '60-65', '65-70', '70-75', '75-80', '80-85', '85-90', '90-95', '95-100', '>100']
    df_bootstrap['faixa'] = pd.Categorical(df_bootstrap['faixa'], categories=faixas_ordem, ordered=True)
    df_bs = df_bootstrap.sort_values('faixa')
    sns.barplot(data=df_bs, x='faixa', y='cv_mean', palette='viridis', hue='faixa', legend=False)
    plt.axhline(y=15, color='green', linestyle='--', label=r'CV $\leq$ 15% (aceitável)')
    plt.axhline(y=30, color='orange', linestyle='--', label=r'CV $\leq$ 30% (tolerável)')
    plt.xticks(rotation=45)
    plt.ylabel('CV (%)', fontsize=12)
    plt.title('Coeficiente de Variação por Faixa (Estratificado)', fontsize=14)
    plt.legend(loc='upper right')
    plt.savefig(CAMINHO_SAIDA / "02_cv_estratificado.png", dpi=300)
    plt.close()

    # 3. Poder Estatístico (Fiel à imagem 03 - Anotações em cada ponto)
    plt.figure(figsize=(12, 7))
    plt.plot(df_power['n_posts'], df_power['power'], marker='o', color='darkred', linewidth=2, markersize=5)
    plt.axhline(y=0.80, color='green', linestyle='--', label=r'Poder $\geq$ 80%')
    plt.axhline(y=0.70, color='orange', linestyle='--', label=r'Poder $\geq$ 70%')
    for x, y in zip(df_power['n_posts'], df_power['power']):
        plt.annotate(f'n={x}: {y:.2f}', xy=(x, y), xytext=(5, -5), textcoords='offset points', fontsize=9)
    plt.title('Poder Estatístico vs Tamanho da Amostra', fontsize=14)
    plt.xlabel('Número de Posts (n)', fontsize=12)
    plt.ylabel(r'Poder (1 - $\beta$)', fontsize=12)
    plt.legend(loc='upper left')
    plt.savefig(CAMINHO_SAIDA / "03_poder_estatistico.png", dpi=300)
    plt.close()

    # 4. Densidade vs Posts (Fiel à imagem 04 - Regressão com Red Line)
    plt.figure(figsize=(12, 7))
    sns.scatterplot(data=df, x='posts_unicos', y=col_densidade, alpha=0.5, color='#729ece')
    sns.regplot(data=df, x='posts_unicos', y=col_densidade, scatter=False, color='red', label='Tendência')
    plt.axvline(x=20, color='gray', linestyle='--')
    plt.title(f'Densidade ({col_densidade}) vs Número de Posts', fontsize=14)
    plt.xlabel('Posts Únicos', fontsize=12)
    plt.ylabel('Menções negativas / 1000 palavras', fontsize=12)
    plt.legend()
    plt.savefig(CAMINHO_SAIDA / "04_densidade_vs_posts.png", dpi=300)
    plt.close()

    # 5. Entropia Temática (Fiel à imagem 05 - Boxplot Teal)
    plt.figure(figsize=(10, 7))
    sns.boxplot(data=df, y='entropia_tematica', color='#126d6d', width=0.7)
    plt.axhline(y=df['entropia_tematica'].median(), color='orange', linestyle='--', label=f"Mediana={df['entropia_tematica'].median():.2f}")
    plt.title('Distribuição da Entropia Temática', fontsize=14)
    plt.ylabel('Entropia de Shannon', fontsize=12)
    plt.legend()
    plt.savefig(CAMINHO_SAIDA / "05_entropia_tematica.png", dpi=300)
    plt.close()

    # 6. Matriz de Correlação (Fiel à imagem 06)
    plt.figure(figsize=(12, 10))
    cols = ['posts_unicos', col_densidade, 'temas_cobertos', 'entropia_tematica', 'engajamento']
    # Filtrar apenas colunas que existem
    cols_present = [c for c in cols if c in df.columns]
    corr = df[cols_present].corr()
    sns.heatmap(corr, annot=True, fmt='.2f', cmap='RdBu_r', center=0)
    plt.title('Matriz de Correlação', fontsize=14)
    plt.savefig(CAMINHO_SAIDA / "06_matriz_correlacao.png", dpi=300)
    plt.close()

def main():
    print("🚀 Gerando gráficos com fidelidade visual total...")
    df = pd.read_csv(CAMINHO_ENTRADA, sep=';')
    
    # Cálculos auxiliares
    temas = ['performance', 'thermal', 'energy', 'display', 'stability']
    if 'temas_cobertos' not in df.columns:
        df['temas_cobertos'] = (df[temas] > 0).sum(axis=1)
    if 'entropia_tematica' not in df.columns:
        def calc_entropy(row):
            counts = np.array([row[t] for t in temas if t in df.columns])
            p = counts[counts > 0] / counts.sum() if counts.sum() > 0 else []
            return -np.sum(p * np.log(p)) if len(p) > 0 else 0
        df['entropia_tematica'] = df.apply(calc_entropy, axis=1)

    df_bs = bootstrap_estratificado(df)
    df_pw = power_analysis()
    
    gerar_graficos_validacao(df, df_bs, df_pw)
    print(f"✅ Gráficos salvos com sucesso em: {CAMINHO_SAIDA}")

if __name__ == "__main__":
    main()