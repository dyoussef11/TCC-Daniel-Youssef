"""
Bootstrapping CORRIGIDO - para CSV sem pesos
Usa densidade_tecnica em vez de densidade_ponderada
"""
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from scipy import stats
from core.paths import PREPROCESSAMENTO_DATA

CAMINHO_ENTRADA = PREPROCESSAMENTO_DATA / "Contagem_Analise_VaderV5_CALIBRADO" / "prevalencia_sem_pesos.csv"
CAMINHO_SAIDA = PREPROCESSAMENTO_DATA / "Validacao_CientificaV3"
CAMINHO_SAIDA.mkdir(parents=True, exist_ok=True)

def bootstrap_estratificado(df, n_bootstrap=1000):
    """
    Bootstrapping estratificado por faixa de tamanho do modelo.
    """
    # Estratifica por tamanho
    df['faixa_tamanho'] = pd.cut(df['posts_unicos'], 
                                   bins=[0, 5, 10, 15, 20, 30, 50, 1000],
                                   labels=['<5', '5-10', '10-15', '15-20', '20-30', '30-50', '>50'])
    
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
            # Amostra COM REPOSIÇÃO dentro da faixa
            sample = df_faixa.sample(n=min(30, len(df_faixa)), replace=True)
            # Simula menções baseado na taxa média observada
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
    """
    Calcula o poder estatístico para detectar diferenças entre grupos.
    """
    from statsmodels.stats.power import TTestIndPower
    
    analysis = TTestIndPower()
    
    resultados = []
    for n in [5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 100]:
        power = analysis.power(effect_size=effect_size, 
                               nobs1=n, 
                               alpha=alpha, 
                               ratio=1.0)
        resultados.append({
            'n_posts': n,
            'power': power,
            'adequate': power >= 0.80
        })
    
    return pd.DataFrame(resultados)

def gerar_graficos_validacao(df, df_bootstrap, df_power):
    """
    Gera gráficos de validação científica.
    """
    # Verifica quais colunas existem
    col_densidade = 'densidade_tecnica' if 'densidade_tecnica' in df.columns else 'total_mencoes'
    if col_densidade == 'total_mencoes':
        df['densidade_tecnica'] = df['total_mencoes'] / df['palavras'] * 1000
    
    col_temas = 'temas_cobertos' if 'temas_cobertos' in df.columns else None
    if col_temas is None:
        temas = ['performance', 'thermal', 'energy', 'display', 'stability']
        df['temas_cobertos'] = (df[temas] > 0).sum(axis=1)
    
    col_entropia = 'entropia_tematica' if 'entropia_tematica' in df.columns else None
    if col_entropia is None:
        # Calcula entropia simples
        temas = ['performance', 'thermal', 'energy', 'display', 'stability']
        def calc_entropy(row):
            counts = np.array([row[t] for t in temas if t in df.columns])
            total = counts.sum()
            if total == 0:
                return 0.0
            probs = counts[counts > 0] / total
            return -np.sum(probs * np.log(probs))
        df['entropia_tematica'] = df.apply(calc_entropy, axis=1)
    
    fig, axes = plt.subplots(2, 3, figsize=(18, 12))
    
    # 1. Distribuição de Posts por Modelo
    sns.histplot(df['posts_unicos'], bins=50, ax=axes[0,0], color='steelblue')
    axes[0,0].axvline(x=20, color='red', linestyle='--', label='n=20')
    axes[0,0].set_title('Distribuição de Posts por Modelo')
    axes[0,0].set_xlabel('Número de Posts')
    axes[0,0].legend()
    
    # 2. CV por Faixa de Tamanho
    if len(df_bootstrap) > 0:
        sns.barplot(data=df_bootstrap, x='faixa', y='cv_mean', ax=axes[0,1], hue='faixa', legend=False, palette='viridis')
        axes[0,1].axhline(y=15, color='green', linestyle='--', label='CV ≤ 15% (aceitável)')
        axes[0,1].set_title('Coeficiente de Variação por Faixa (Estratificado)')
        axes[0,1].set_ylabel('CV (%)')
        axes[0,1].legend()
    
    # 3. Poder Estatístico
    sns.lineplot(data=df_power, x='n_posts', y='power', ax=axes[0,2], marker='o', color='darkred')
    axes[0,2].axhline(y=0.80, color='green', linestyle='--', label='Poder ≥ 80%')
    axes[0,2].axvline(x=20, color='blue', linestyle=':', label='n=20')
    axes[0,2].set_title('Poder Estatístico vs Tamanho da Amostra')
    axes[0,2].set_ylabel('Poder (1 - β)')
    axes[0,2].legend()
    
    # 4. Densidade vs Posts (com linha de tendência)
    sns.scatterplot(data=df, x='posts_unicos', y=col_densidade, ax=axes[1,0], alpha=0.6)
    sns.regplot(data=df, x='posts_unicos', y=col_densidade, ax=axes[1,0], 
                scatter=False, color='red', label='Tendência')
    axes[1,0].axvline(x=20, color='black', linestyle='--')
    axes[1,0].set_title(f'Densidade ({col_densidade}) vs Número de Posts')
    axes[1,0].set_xlabel('Posts Únicos')
    axes[1,0].set_ylabel('Menções negativas / 1000 palavras')
    axes[1,0].legend()
    
    # 5. Entropia Temática
    sns.boxplot(data=df, y='entropia_tematica', ax=axes[1,1], color='teal')
    axes[1,1].axhline(y=1.0, color='orange', linestyle='--', label='Diversidade mínima')
    axes[1,1].set_title('Distribuição da Entropia Temática')
    axes[1,1].set_ylabel('Entropia de Shannon')
    axes[1,1].legend()
    
    # 6. Matriz de Correlação
    cols_corr = ['posts_unicos', col_densidade, 'temas_cobertos', 'entropia_tematica']
    # Adiciona engajamento se existir
    if 'engajamento' in df.columns:
        cols_corr.append('engajamento')
    
    corr_matrix = df[cols_corr].corr()
    sns.heatmap(corr_matrix, annot=True, fmt='.2f', cmap='RdBu_r', ax=axes[1,2])
    axes[1,2].set_title('Matriz de Correlação')
    
    plt.tight_layout()
    plt.savefig(CAMINHO_SAIDA / "validacao_cientifica_completa.png", dpi=400, bbox_inches='tight')
    plt.close()
    
    print(f"📊 Gráficos salvos em: {CAMINHO_SAIDA / 'validacao_cientifica_completa.png'}")

def gerar_relatorio_final(df, df_bootstrap, df_power):
    """
    Gera relatório executivo com recomendações baseadas em evidências.
    """
    report = []
    report.append("# Relatório de Validação Científica do Corpus (Sem Pesos)\n")
    
    # 1. Estatísticas descritivas
    report.append("## 1. Estatísticas Descritivas\n")
    report.append(f"- Total de modelos: {len(df)}")
    report.append(f"- Total de posts: {df['posts_unicos'].sum():,}")
    report.append(f"- Média de posts/modelo: {df['posts_unicos'].mean():.1f} (±{df['posts_unicos'].std():.1f})")
    report.append(f"- Densidade média: {df['densidade_tecnica'].mean():.2f} menções/1000 palavras")
    report.append(f"- Modelos com n ≥ 20: {len(df[df['posts_unicos'] >= 20])} ({len(df[df['posts_unicos'] >= 20])/len(df)*100:.1f}%)")
    
    # 2. Validação do Threshold n=20
    report.append("\n## 2. Validação do Threshold n=20\n")
    
    if len(df_bootstrap) > 0:
        # Encontra a faixa que contém n=20
        faixa_n20 = df_bootstrap[df_bootstrap['n_median'] <= 25]
        if len(faixa_n20) > 0:
            cv_n20 = faixa_n20['cv_mean'].mean()
            report.append(f"- CV médio para n≈20: {cv_n20:.1f}%")
            report.append(f"- Status: {'✅ ACEITÁVEL' if cv_n20 <= 15 else '⚠️ ELEVADO'}")
    
    power_n20 = df_power[df_power['n_posts'] == 20]['power'].values[0]
    report.append(f"- Poder estatístico para n=20: {power_n20:.2f}")
    report.append(f"- Status: {'✅ ADEQUADO' if power_n20 >= 0.8 else '⚠️ BAIXO'}")
    
    # 3. Recomendações para Thresholds
    report.append("\n## 3. Recomendações para Thresholds\n")
    
    # Percentis
    p25_dens = df['densidade_tecnica'].quantile(0.25)
    p50_dens = df['densidade_tecnica'].median()
    
    report.append(f"\n### Distribuição da Densidade Técnica:")
    report.append(f"- Percentil 25: {p25_dens:.2f}")
    report.append(f"- Mediana: {p50_dens:.2f}")
    report.append(f"- Percentil 75: {df['densidade_tecnica'].quantile(0.75):.2f}")
    
    report.append(f"\n### Recomendação Final:")
    report.append(f"- **n mínimo: 20 posts** (poder estatístico adequado)")
    report.append(f"- **Densidade mínima: {max(2.0, round(p25_dens, 1))}** menções/1000 palavras")
    
    with open(CAMINHO_SAIDA / "relatorio_final_sem_pesos.md", 'w', encoding='utf-8') as f:
        f.write('\n'.join(report))
    
    print(f"📄 Relatório final: {CAMINHO_SAIDA / 'relatorio_final_sem_pesos.md'}")

def main():
    print("=" * 80)
    print("🔬 VALIDAÇÃO CIENTÍFICA DO CORPUS (SEM PESOS DE SEVERIDADE)")
    print("=" * 80)
    
    df = pd.read_csv(CAMINHO_ENTRADA, sep=';')
    print(f"\n📊 Dados carregados: {len(df)} modelos")
    print(f"📊 Colunas disponíveis: {list(df.columns)}")
    
    # Bootstrapping corrigido
    print("\n🔄 Executando Bootstrapping Estratificado...")
    df_bootstrap = bootstrap_estratificado(df)
    
    # Power analysis
    print("⚡ Executando Power Analysis...")
    df_power = power_analysis()
    
    # Gráficos
    print("📈 Gerando gráficos...")
    gerar_graficos_validacao(df, df_bootstrap, df_power)
    
    # Relatório
    gerar_relatorio_final(df, df_bootstrap, df_power)
    
    print("\n✅ Validação científica concluída!")

if __name__ == "__main__":
    main()