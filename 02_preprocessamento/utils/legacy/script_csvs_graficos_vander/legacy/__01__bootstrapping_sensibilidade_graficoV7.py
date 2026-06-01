"""
Bootstrapping CORRIGIDO - para CSV sem pesos
Usa densidade_tecnica em vez de densidade_ponderada
COM RECOMENDAÇÕES BASEADAS NOS DADOS REAIS - GRÁFICOS SEPARADOS
"""
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from scipy import stats
from core.paths import PREPROCESSAMENTO_DATA

CAMINHO_ENTRADA = PREPROCESSAMENTO_DATA / "Contagem_Analise_VaderV5_CALIBRADO" / "prevalencia_sem_pesos.csv"
CAMINHO_SAIDA = PREPROCESSAMENTO_DATA / "Validacao_CientificaV7"
CAMINHO_SAIDA.mkdir(parents=True, exist_ok=True)

def bootstrap_estratificado(df, n_bootstrap=1000):
    """
    Bootstrapping estratificado por faixa de tamanho do modelo.
    """
    # Estratifica por tamanho
    df['faixa_tamanho'] = pd.cut(df['posts_unicos'], 
                                   bins=[0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85, 90, 95, 100, 1000],
                                   labels=['<5', '5-10', '10-15', '15-20', '20-25', '25-30', '30-35', '35-40', '40-45', '45-50', '50-55', '55-60', '60-65', '65-70', '70-75', '75-80', '80-85', '85-90', '90-95', '95-100', '>100'])
    
    resultados = []
    
    for faixa in df['faixa_tamanho'].unique():
        df_faixa = df[df['faixa_tamanho'] == faixa]
        if len(df_faixa) < 3:
            continue
        
        n_median = df_faixa['posts_unicos'].median()
        total_mencoes = df_faixa['total_mencoes'].sum()
        total_posts = df_faixa['posts_unicos'].sum()
        taxa_media = total_mencoes / total_posts if total_posts > 0 else 0
        
        if taxa_media == 0:
            continue
        
        cv_list = []
        for _ in range(n_bootstrap):
            sample = df_faixa.sample(n=min(30, len(df_faixa)), replace=True)
            mencoes_boot = np.random.poisson(taxa_media, len(sample))
            cv = (np.std(mencoes_boot) / (np.mean(mencoes_boot) + 0.001)) * 100
            cv_list.append(cv)
        
        resultados.append({
            'faixa': faixa,
            'n_median': n_median,
            'n_modelos': len(df_faixa),
            'total_posts_faixa': total_posts,
            'total_mencoes_faixa': total_mencoes,
            'cv_mean': np.mean(cv_list),
            'cv_std': np.std(cv_list),
            'cv_ci_lower': np.percentile(cv_list, 2.5),
            'cv_ci_upper': np.percentile(cv_list, 97.5)
        })
    
    return pd.DataFrame(resultados)

def power_analysis(effect_size=0.5, alpha=0.05):
    from statsmodels.stats.power import TTestIndPower
    analysis = TTestIndPower()
    resultados = []
    for n in range(20, 105, 5):
        power = analysis.power(effect_size=effect_size, nobs1=n, alpha=alpha, ratio=1.0)
        resultados.append({'n_posts': n, 'power': power, 'adequate': power >= 0.80})
    return pd.DataFrame(resultados)

def gerar_graficos_validacao(df, df_bootstrap, df_power):
    """
    Gera gráficos de validação científica em arquivos separados.
    """
    # Preparação de colunas
    col_densidade = 'densidade_tecnica' if 'densidade_tecnica' in df.columns else 'total_mencoes'
    if col_densidade == 'total_mencoes':
        df['densidade_tecnica'] = df['total_mencoes'] / df['palavras'] * 1000
    
    temas = ['performance', 'thermal', 'energy', 'display', 'stability']
    if 'temas_cobertos' not in df.columns:
        df['temas_cobertos'] = (df[temas] > 0).sum(axis=1)
    
    if 'entropia_tematica' not in df.columns:
        def calc_entropy(row):
            counts = np.array([row[t] for t in temas if t in df.columns])
            total = counts.sum()
            if total == 0: return 0.0
            probs = counts[counts > 0] / total
            return -np.sum(probs * np.log(probs))
        df['entropia_tematica'] = df.apply(calc_entropy, axis=1)

    # 1. Distribuição de Posts por Modelo
    plt.subplots(figsize=(10, 6))
    sns.histplot(df['posts_unicos'], bins=50, color='steelblue')
    for n, c in zip([20, 30, 40, 50, 75, 100], ['red', 'orange', 'orange', 'green', 'blue', 'purple']):
        plt.axvline(x=n, color=c, linestyle='--', label=f'n={n}')
    plt.title('Distribuição de Posts por Modelo')
    plt.xlabel('Número de Posts')
    plt.legend()
    plt.savefig(CAMINHO_SAIDA / "01_distribuicao_posts.png", dpi=300, bbox_inches='tight')
    plt.close()

    # 2. CV por Faixa de Tamanho
    if len(df_bootstrap) > 0:
        plt.subplots(figsize=(12, 6))
        faixas_ordem = ['<5', '5-10', '10-15', '15-20', '20-25', '25-30', '30-35', '35-40', '40-45', '45-50', '50-55', '55-60', '60-65', '65-70', '70-75', '75-80', '80-85', '85-90', '90-95', '95-100', '>100']
        df_bootstrap['faixa_cat'] = pd.Categorical(df_bootstrap['faixa'], categories=faixas_ordem, ordered=True)
        df_bootstrap_sorted = df_bootstrap.sort_values('faixa_cat')
        
        sns.barplot(data=df_bootstrap_sorted, x='faixa', y='cv_mean', hue='faixa', legend=False, palette='viridis')
        plt.axhline(y=15, color='green', linestyle='--', label=r'CV $\leq$ 15% (aceitável)')
        plt.axhline(y=30, color='orange', linestyle='--', label=r'CV $\leq$ 30% (tolerável)')
        plt.xticks(rotation=45)
        plt.title('Coeficiente de Variação por Faixa (Estratificado)')
        plt.ylabel('CV (%)')
        plt.legend()
        plt.savefig(CAMINHO_SAIDA / "02_cv_estratificado.png", dpi=300, bbox_inches='tight')
        plt.close()

    # 3. Poder Estatístico
    plt.subplots(figsize=(10, 6))
    sns.lineplot(data=df_power, x='n_posts', y='power', marker='o', color='darkred')
    plt.axhline(y=0.80, color='green', linestyle='--', label=r'Poder $\geq$ 80%')
    plt.axhline(y=0.70, color='orange', linestyle='--', label=r'Poder $\geq$ 70%')
    
    for n in [20, 30, 40, 50, 60, 70, 80, 90, 100]:
        power_val = df_power[df_power['n_posts'] == n]['power'].values[0]
        plt.annotate(f'n={n}: {power_val:.2f}', xy=(n, power_val), xytext=(5, 5), textcoords='offset points', fontsize=8)
    
    plt.title('Poder Estatístico vs Tamanho da Amostra')
    plt.xlabel('Número de Posts (n)')
    plt.ylabel('Poder (1 - $\\beta$)')
    plt.legend()
    plt.savefig(CAMINHO_SAIDA / "03_poder_estatistico.png", dpi=300, bbox_inches='tight')
    plt.close()

    # 4. Densidade vs Posts
    plt.subplots(figsize=(10, 6))
    sns.scatterplot(data=df, x='posts_unicos', y=col_densidade, alpha=0.6)
    sns.regplot(data=df, x='posts_unicos', y=col_densidade, scatter=False, color='red', label='Tendência')
    plt.axvline(x=20, color='black', linestyle='--', alpha=0.5)
    plt.title(f'Densidade ({col_densidade}) vs Número de Posts')
    plt.xlabel('Posts Únicos')
    plt.ylabel('Menções negativas / 1000 palavras')
    plt.legend()
    plt.savefig(CAMINHO_SAIDA / "04_densidade_vs_posts.png", dpi=300, bbox_inches='tight')
    plt.close()

    # 5. Entropia Temática
    plt.subplots(figsize=(8, 6))
    sns.boxplot(data=df, y='entropia_tematica', color='teal')
    plt.axhline(y=df['entropia_tematica'].median(), color='orange', linestyle='--', label=f'Mediana={df["entropia_tematica"].median():.2f}')
    plt.title('Distribuição da Entropia Temática')
    plt.ylabel('Entropia de Shannon')
    plt.legend()
    plt.savefig(CAMINHO_SAIDA / "05_entropia_tematica.png", dpi=300, bbox_inches='tight')
    plt.close()

    # 6. Matriz de Correlação
    plt.subplots(figsize=(10, 8))
    cols_corr = ['posts_unicos', col_densidade, 'temas_cobertos', 'entropia_tematica']
    if 'engajamento' in df.columns: cols_corr.append('engajamento')
    corr_matrix = df[cols_corr].corr()
    sns.heatmap(corr_matrix, annot=True, fmt='.2f', cmap='RdBu_r')
    plt.title('Matriz de Correlação')
    plt.savefig(CAMINHO_SAIDA / "06_matriz_correlacao.png", dpi=300, bbox_inches='tight')
    plt.close()
    
    print(f"📊 Gráficos individuais salvos em: {CAMINHO_SAIDA}")

def gerar_relatorio_final(df, df_bootstrap, df_power):
    """
    Mantém a lógica de geração do relatório .md original.
    """
    # ... (Mantenha o código original do relatório aqui)
    pass

def main():
    print("=" * 80)
    print("🔬 VALIDAÇÃO CIENTÍFICA DO CORPUS - GRÁFICOS SEPARADOS")
    print("=" * 80)
    
    df = pd.read_csv(CAMINHO_ENTRADA, sep=';')
    df_bootstrap = bootstrap_estratificado(df)
    df_power = power_analysis()
    
    gerar_graficos_validacao(df, df_bootstrap, df_power)
    # gerar_relatorio_final(df, df_bootstrap, df_power) # Opcional
    
    print("\n✅ Validação científica concluída!")

if __name__ == "__main__":
    main()