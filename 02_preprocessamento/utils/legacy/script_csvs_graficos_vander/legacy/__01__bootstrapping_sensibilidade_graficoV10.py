"""
Bootstrapping CORRIGIDO - para CSV sem pesos
Usa densidade_tecnica em vez de densidade_ponderada
VALIDAÇÃO CIENTÍFICA V9 - ANÁLISE MULTIDIMENSIONAL (INCREMENTO N=2 + MÚLTIPLOS EFFECT SIZES)
"""
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from scipy import stats
from core.paths import PREPROCESSAMENTO_DATA

CAMINHO_ENTRADA = PREPROCESSAMENTO_DATA / "Contagem_Analise_VaderV5_CALIBRADO" / "prevalencia_sem_pesos.csv"
CAMINHO_SAIDA = PREPROCESSAMENTO_DATA / "Validacao_CientificaV9"
CAMINHO_SAIDA.mkdir(parents=True, exist_ok=True)

def bootstrap_estratificado(df, n_bootstrap=1000):
    """
    Bootstrapping estratificado por faixa de tamanho do modelo.
    """
    df['faixa_tamanho'] = pd.cut(df['posts_unicos'], 
                                   bins=[0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85, 90, 95, 100, 1000],
                                   labels=['<5', '5-10', '10-15', '15-20', '20-25', '25-30', '30-35', '35-40', '40-45', '45-50', '50-55', '55-60', '60-65', '65-70', '70-75', '75-80', '80-85', '85-90', '90-95', '95-100', '>100'])
    
    resultados = []
    for faixa in df['faixa_tamanho'].unique():
        df_faixa = df[df['faixa_tamanho'] == faixa]
        if len(df_faixa) < 3: continue
        
        n_median = df_faixa['posts_unicos'].median()
        total_mencoes = df_faixa['total_mencoes'].sum()
        total_posts = df_faixa['posts_unicos'].sum()
        taxa_media = total_mencoes / total_posts if total_posts > 0 else 0
        
        if taxa_media == 0: continue
        
        cv_list = []
        for _ in range(n_bootstrap):
            sample = df_faixa.sample(n=min(30, len(df_faixa)), replace=True)
            mencoes_boot = np.random.poisson(taxa_media, len(sample))
            cv = (np.std(mencoes_boot) / (np.mean(mencoes_boot) + 0.001)) * 100
            cv_list.append(cv)
        
        resultados.append({
            'faixa': faixa, 'n_median': n_median, 'n_modelos': len(df_faixa),
            'cv_mean': np.mean(cv_list), 'cv_std': np.std(cv_list)
        })
    return pd.DataFrame(resultados)

def power_analysis_multidimensional(alpha=0.05):
    """
    Calcula poder estatístico variando N (de 2 em 2) e Effect Size (0.3, 0.5, 0.8).
    """
    from statsmodels.stats.power import TTestIndPower
    analysis = TTestIndPower()
    resultados = []
    
    # Testamos diferentes cenários de "impacto" nos dados
    # 0.3 = Pequeno (difícil detectar), 0.5 = Médio, 0.8 = Grande (fácil detectar)
    effect_sizes = [0.3, 0.5, 0.8]
    
    for es in effect_sizes:
        for n in range(10, 152, 2):
            power = analysis.power(effect_size=es, nobs1=n, alpha=alpha, ratio=1.0)
            resultados.append({
                'n_posts': n, 
                'power': power, 
                'effect_size': es,
                'cenario': f'Efeito {es}'
            })
    return pd.DataFrame(resultados)

def gerar_graficos_validacao(df, df_bootstrap, df_power):
    # Processamento básico de colunas
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

    # Gráficos 1, 2, 4, 5, 6 (Mantidos como solicitado)
    
    # 01. Distribuição
    plt.subplots(figsize=(10, 6))
    sns.histplot(df['posts_unicos'], bins=50, color='steelblue')
    plt.title('01. Distribuição de Posts por Modelo')
    plt.savefig(CAMINHO_SAIDA / "01_distribuicao_posts.png", dpi=300, bbox_inches='tight')
    plt.close()

    # 02. CV
    plt.subplots(figsize=(12, 6))
    sns.barplot(data=df_bootstrap, x='faixa', y='cv_mean', hue='faixa', legend=False, palette='viridis')
    plt.title('02. Coeficiente de Variação por Faixa')
    plt.savefig(CAMINHO_SAIDA / "02_cv_estratificado.png", dpi=300, bbox_inches='tight')
    plt.close()

    # 03. PODER ESTATÍSTICO MULTIDIMENSIONAL
    plt.subplots(figsize=(12, 7))
    # Plotamos múltiplas linhas para diferentes tamanhos de efeito
    sns.lineplot(data=df_power, x='n_posts', y='power', hue='cenario', marker='o', markersize=3)
    
    plt.axhline(y=0.80, color='green', linestyle='--', alpha=0.6, label=r'Threshold 0.80')
    
    # Anotamos o ponto de cruzamento de 0.80 para cada cenário
    for es in [0.3, 0.5, 0.8]:
        cen = df_power[(df_power['effect_size'] == es) & (df_power['power'] >= 0.80)].head(1)
        if not cen.empty:
            n_target = cen['n_posts'].values[0]
            plt.annotate(f'n={n_target}\n(ES={es})', xy=(n_target, 0.80), xytext=(0, -25),
                         textcoords='offset points', ha='center', fontsize=8, 
                         bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="gray", alpha=0.8))

    plt.title(r'03. Sensibilidade do Poder Estatístico ($\alpha=0.05, n$ step=2)')
    plt.xlabel('Número de Posts (n)')
    plt.ylabel(r'Poder (1 - $\beta$)')
    plt.legend(title='Cenários de Efeito')
    plt.grid(True, alpha=0.3)
    plt.savefig(CAMINHO_SAIDA / "03_poder_estatistico_multidimensional.png", dpi=300, bbox_inches='tight')
    plt.close()

    # 04, 05, 06 (Mantidos)
    plt.subplots(figsize=(10, 6))
    sns.scatterplot(data=df, x='posts_unicos', y=col_densidade, alpha=0.6)
    plt.title('04. Densidade vs Número de Posts')
    plt.savefig(CAMINHO_SAIDA / "04_densidade_vs_posts.png", dpi=300, bbox_inches='tight')
    plt.close()

    plt.subplots(figsize=(8, 6))
    sns.boxplot(data=df, y='entropia_tematica', color='teal')
    plt.title('05. Distribuição da Entropia Temática')
    plt.savefig(CAMINHO_SAIDA / "05_entropia_tematica.png", dpi=300, bbox_inches='tight')
    plt.close()

    plt.subplots(figsize=(10, 8))
    sns.heatmap(df[['posts_unicos', col_densidade, 'temas_cobertos', 'entropia_tematica']].corr(), annot=True, cmap='RdBu_r')
    plt.title('06. Matriz de Correlação')
    plt.savefig(CAMINHO_SAIDA / "06_matriz_correlacao.png", dpi=300, bbox_inches='tight')
    plt.close()

def main():
    print("=" * 80)
    print("🔬 VALIDAÇÃO CIENTÍFICA V9 - ANÁLISE DE SENSIBILIDADE MULTIVARIADA")
    print("=" * 80)
    
    df = pd.read_csv(CAMINHO_ENTRADA, sep=';')
    df_bootstrap = bootstrap_estratificado(df)
    df_power = power_analysis_multidimensional()
    
    gerar_graficos_validacao(df, df_bootstrap, df_power)
    
    print("\n💡 RESUMO DE EQUILÍBRIO (Target Power 0.80):")
    for es in [0.8, 0.5, 0.3]:
        target = df_power[(df_power['effect_size'] == es) & (df_power['power'] >= 0.80)].head(1)
        if not target.empty:
            print(f"   - Para detectar efeito '{es}': mínimo de {target['n_posts'].values[0]} posts.")

    print(f"\n✅ Concluído! Resultados em: {CAMINHO_SAIDA}")

if __name__ == "__main__":
    main()