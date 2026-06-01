"""
Bootstrapping CIENTÍFICO V10 - Gráficos de Alta Performance
Detalhamento estatístico completo em todos os 6 eixos.
"""
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from scipy import stats
from core.paths import PREPROCESSAMENTO_DATA

CAMINHO_ENTRADA = PREPROCESSAMENTO_DATA / "Contagem_Analise_VaderV5_CALIBRADO" / "prevalencia_sem_pesos.csv"
CAMINHO_SAIDA = PREPROCESSAMENTO_DATA / "Validacao_CientificaV10"
CAMINHO_SAIDA.mkdir(parents=True, exist_ok=True)

def bootstrap_estratificado(df, n_bootstrap=1000):
    """
    Bootstrapping com cálculo de Intervalo de Confiança (CI) para as barras de erro.
    """
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
        
        resultados.append({
            'faixa': faixa, 
            'cv_mean': np.mean(cv_list),
            'cv_err': np.std(cv_list), # Para as barras de erro
            'n_modelos': len(df_faixa)
        })
    return pd.DataFrame(resultados)

def power_analysis_multidimensional(alpha=0.05):
    from statsmodels.stats.power import TTestIndPower
    analysis = TTestIndPower()
    resultados = []
    for es in [0.3, 0.5, 0.8]:
        for n in range(10, 152, 2):
            power = analysis.power(effect_size=es, nobs1=n, alpha=alpha, ratio=1.0)
            resultados.append({'n_posts': n, 'power': power, 'effect_size': es, 'cenario': f'Efeito {es}'})
    return pd.DataFrame(resultados)

def gerar_graficos_validacao(df, df_bootstrap, df_power):
    # Colunas calculadas
    col_densidade = 'densidade_tecnica'
    if col_densidade not in df.columns:
        df[col_densidade] = df['total_mencoes'] / df['palavras'] * 1000
    
    # 01. Distribuição com Anotações de Retenção
    plt.subplots(figsize=(10, 6))
    sns.histplot(df['posts_unicos'], bins=50, color='steelblue', kde=True)
    thresholds = [20, 50, 100]
    for n in thresholds:
        count = len(df[df['posts_unicos'] >= n])
        pct = (count / len(df)) * 100
        plt.axvline(x=n, color='red', linestyle='--', alpha=0.7)
        plt.text(n+1, plt.gca().get_ylim()[1]*0.8, f'n$\geq${n}\n{pct:.1f}%', color='red', fontweight='bold')
    plt.title('01. Histograma de Corpus: Retenção por Volume de Posts')
    plt.savefig(CAMINHO_SAIDA / "01_distribuicao_posts.png", dpi=300)
    plt.close()

    # 02. CV com Barras de Erro (Bootstrap Error)
    plt.subplots(figsize=(12, 6))
    df_bootstrap['faixa_cat'] = pd.Categorical(df_bootstrap['faixa'], categories=df_bootstrap['faixa'].unique(), ordered=True)
    df_bs = df_bootstrap.sort_values('faixa_cat')
    plt.bar(df_bs['faixa'], df_bs['cv_mean'], yerr=df_bs['cv_err'], capsize=5, color='teal', alpha=0.8)
    plt.axhline(y=15, color='green', linestyle='--', label=r'Rigor Científico ($\leq$15%)')
    plt.xticks(rotation=45)
    plt.ylabel('CV Médio (%)')
    plt.title('02. Estabilidade das Menções (Bootstrapping c/ Erro Padrão)')
    plt.legend()
    plt.savefig(CAMINHO_SAIDA / "02_cv_estratificado.png", dpi=300)
    plt.close()

    # 03. Poder Multidimensional (Mantido o avanço da V9)
    plt.subplots(figsize=(12, 7))
    sns.lineplot(data=df_power, x='n_posts', y='power', hue='cenario', palette='Set1')
    plt.axhline(y=0.80, color='black', linestyle=':', label='Target 0.80')
    plt.title(r'03. Sensibilidade do Poder Estatístico ($\Delta n=2$)')
    plt.savefig(CAMINHO_SAIDA / "03_poder_estatistico.png", dpi=300)
    plt.close()

    # 04. Densidade vs Posts com Quadrantes Médios
    plt.subplots(figsize=(10, 6))
    sns.scatterplot(data=df, x='posts_unicos', y=col_densidade, alpha=0.5, size='palavras', sizes=(20, 200))
    plt.axvline(x=df['posts_unicos'].median(), color='gray', linestyle='--', alpha=0.5)
    plt.axhline(y=df[col_densidade].median(), color='gray', linestyle='--', alpha=0.5)
    sns.regplot(data=df, x='posts_unicos', y=col_densidade, scatter=False, color='darkred')
    plt.title('04. Análise de Quadrantes: Densidade vs. Volume')
    plt.savefig(CAMINHO_SAIDA / "04_densidade_vs_posts.png", dpi=300)
    plt.close()

    # 05. Entropia com Jitter (Distribuição Real)
    plt.subplots(figsize=(8, 6))
    sns.boxplot(data=df, y='entropia_tematica', color='lightgrey', showfliers=False)
    sns.stripplot(data=df, y='entropia_tematica', color='orange', alpha=0.3, jitter=True)
    plt.title('05. Variedade de Problemas (Entropia com Distribuição)')
    plt.savefig(CAMINHO_SAIDA / "05_entropia_tematica.png", dpi=300)
    plt.close()

    # 06. Heatmap de Correlação com Máscara
    plt.subplots(figsize=(10, 8))
    corr = df[['posts_unicos', col_densidade, 'temas_cobertos', 'entropia_tematica']].corr()
    mask = np.triu(np.ones_like(corr, dtype=bool))
    sns.heatmap(corr, mask=mask, annot=True, cmap='coolwarm', center=0, fmt='.2f')
    plt.title('06. Matriz de Dependência das Variáveis (Lower Triangle)')
    plt.savefig(CAMINHO_SAIDA / "06_matriz_correlacao.png", dpi=300)
    plt.close()

def main():
    print("🔬 INICIANDO VALIDAÇÃO CIENTÍFICA V10...")
    df = pd.read_csv(CAMINHO_ENTRADA, sep=';')
    
    # Garantir que temos entropia e temas
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
    df_pw = power_analysis_multidimensional()
    
    gerar_graficos_validacao(df, df_bs, df_pw)
    print(f"✅ Processo concluído. Arquivos salvos em: {CAMINHO_SAIDA}")

if __name__ == "__main__":
    main()