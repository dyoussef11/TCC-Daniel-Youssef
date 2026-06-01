"""
Bootstrapping CORRIGIDO - para CSV sem pesos
Usa densidade_tecnica em vez de densidade_ponderada
COM RECOMENDAÇÕES BASEADAS NOS DADOS REAIS - GRÁFICOS SEPARADOS (INCREMENTO 2)
"""
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from scipy import stats
from core.paths import PREPROCESSAMENTO_DATA

CAMINHO_ENTRADA = PREPROCESSAMENTO_DATA / "Contagem_Analise_VaderV5_CALIBRADO" / "prevalencia_sem_pesos.csv"
CAMINHO_SAIDA = PREPROCESSAMENTO_DATA / "Validacao_CientificaV8"
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

def power_analysis(effect_size=0.5, alpha=0.05):
    """
    Calcula poder estatístico com incremento de 2 em 2 para maior precisão.
    """
    from statsmodels.stats.power import TTestIndPower
    analysis = TTestIndPower()
    resultados = []
    # Incremento de 2 em 2 para encontrar o "sweet spot"
    for n in range(10, 152, 2):
        power = analysis.power(effect_size=effect_size, nobs1=n, alpha=alpha, ratio=1.0)
        resultados.append({'n_posts': n, 'power': power, 'adequate': power >= 0.80})
    return pd.DataFrame(resultados)

def gerar_graficos_validacao(df, df_bootstrap, df_power):
    # Preparação de dados (mantida da V7)
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
    for n, c in zip([20, 30, 50, 80, 100], ['red', 'orange', 'green', 'blue', 'purple']):
        plt.axvline(x=n, color=c, linestyle='--', label=f'n={n}')
    plt.title('Distribuição de Posts por Modelo')
    plt.xlabel('Número de Posts')
    plt.legend()
    plt.savefig(CAMINHO_SAIDA / "01_distribuicao_posts.png", dpi=300, bbox_inches='tight')
    plt.close()

    # 2. CV por Faixa
    if len(df_bootstrap) > 0:
        plt.subplots(figsize=(12, 6))
        faixas_ordem = ['<5', '5-10', '10-15', '15-20', '20-25', '25-30', '30-35', '35-40', '40-45', '45-50', '50-55', '55-60', '60-65', '65-70', '70-75', '75-80', '80-85', '85-90', '90-95', '95-100', '>100']
        df_bootstrap['faixa_cat'] = pd.Categorical(df_bootstrap['faixa'], categories=faixas_ordem, ordered=True)
        sns.barplot(data=df_bootstrap.sort_values('faixa_cat'), x='faixa', y='cv_mean', hue='faixa', legend=False, palette='viridis')
        plt.axhline(y=15, color='green', linestyle='--', label=r'CV $\leq$ 15% (aceitável)')
        plt.axhline(y=30, color='orange', linestyle='--', label=r'CV $\leq$ 30% (tolerável)')
        plt.xticks(rotation=45)
        plt.title('Coeficiente de Variação por Faixa')
        plt.ylabel('CV (%)')
        plt.legend()
        plt.savefig(CAMINHO_SAIDA / "02_cv_estratificado.png", dpi=300, bbox_inches='tight')
        plt.close()

    # 3. Poder Estatístico (AGORA COM INCREMENTO DE 2)
    plt.subplots(figsize=(12, 7))
    sns.lineplot(data=df_power, x='n_posts', y='power', marker='o', color='darkred', markersize=4)
    plt.axhline(y=0.80, color='green', linestyle='--', label=r'Poder $\geq$ 80% (Padrão Ouro)')
    plt.axhline(y=0.70, color='orange', linestyle='--', label=r'Poder $\geq$ 70% (Aceitável)')
    
    # Anotações em pontos estratégicos para não poluir
    pontos_anotacao = [20, 30, 40, 50, 64, 80, 100, 128] # n=64 e n=128 são potências de 2 comuns
    for n in pontos_anotacao:
        val = df_power[df_power['n_posts'] == n]['power']
        if not val.empty:
            plt.annotate(f'n={n}\n{val.values[0]:.2f}', xy=(n, val.values[0]), xytext=(0, 10), 
                         textcoords='offset points', ha='center', fontsize=9, fontweight='bold')
    
    plt.title('Poder Estatístico vs Tamanho da Amostra (Granularidade n=2)')
    plt.xlabel('Número de Posts (n)')
    plt.ylabel(r'Poder (1 - $\beta$)')
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.savefig(CAMINHO_SAIDA / "03_poder_estatistico.png", dpi=300, bbox_inches='tight')
    plt.close()

    # 4. Densidade vs Posts
    plt.subplots(figsize=(10, 6))
    sns.scatterplot(data=df, x='posts_unicos', y=col_densidade, alpha=0.6)
    sns.regplot(data=df, x='posts_unicos', y=col_densidade, scatter=False, color='red', label='Tendência')
    plt.title(f'Densidade vs Número de Posts')
    plt.xlabel('Posts Únicos')
    plt.ylabel('Menções / 1000 palavras')
    plt.savefig(CAMINHO_SAIDA / "04_densidade_vs_posts.png", dpi=300, bbox_inches='tight')
    plt.close()

    # 5. Entropia Temática
    plt.subplots(figsize=(8, 6))
    sns.boxplot(data=df, y='entropia_tematica', color='teal')
    plt.title('Distribuição da Entropia Temática')
    plt.savefig(CAMINHO_SAIDA / "05_entropia_tematica.png", dpi=300, bbox_inches='tight')
    plt.close()

    # 6. Matriz de Correlação
    plt.subplots(figsize=(10, 8))
    cols_corr = ['posts_unicos', col_densidade, 'temas_cobertos', 'entropia_tematica']
    if 'engajamento' in df.columns: cols_corr.append('engajamento')
    sns.heatmap(df[cols_corr].corr(), annot=True, fmt='.2f', cmap='RdBu_r')
    plt.title('Matriz de Correlação')
    plt.savefig(CAMINHO_SAIDA / "06_matriz_correlacao.png", dpi=300, bbox_inches='tight')
    plt.close()
    
    print(f"📊 Gráficos salvos em: {CAMINHO_SAIDA}")

def main():
    print("=" * 80)
    print("🔬 VALIDAÇÃO CIENTÍFICA - ANÁLISE DE ALTA SENSIBILIDADE (STEP 2)")
    print("=" * 80)
    
    df = pd.read_csv(CAMINHO_ENTRADA, sep=';')
    df_bootstrap = bootstrap_estratificado(df)
    df_power = power_analysis()
    
    gerar_graficos_validacao(df, df_bootstrap, df_power)
    
    # Exibe o ponto onde cruza 0.80
    cruzamento = df_power[df_power['power'] >= 0.80].head(1)
    if not cruzamento.empty:
        print(f"\n💡 EQUILÍBRIO ENCONTRADO: O poder de 0.80 é atingido com n = {cruzamento['n_posts'].values[0]}")
    
    print("\n✅ Concluído!")

if __name__ == "__main__":
    main()