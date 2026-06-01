"""
Bootstrapping CORRIGIDO - sem viés de seleção
Inclui: estratificação por tamanho de modelo e power analysis
"""
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from scipy import stats
from core.paths import PREPROCESSAMENTO_DATA

CAMINHO_ENTRADA = PREPROCESSAMENTO_DATA / "Contagem_Analise_VaderV3_CALIBRADO" / "prevalencia_calibrada.csv"
CAMINHO_SAIDA = PREPROCESSAMENTO_DATA / "Validacao_Cientifica"
CAMINHO_SAIDA.mkdir(parents=True, exist_ok=True)

def bootstrap_estratificado(df, n_bootstrap=1000):
    """
    Bootstrapping estratificado por faixa de tamanho do modelo.
    EVITA o viés de usar só modelos grandes para estimar erro dos pequenos.
    """
    # Estratifica por tamanho
    df['faixa_tamanho'] = pd.cut(df['posts_unicos'], 
                                   bins=[0, 15, 30, 50, 100, 1000],
                                   labels=['<15', '15-30', '30-50', '50-100', '>100'])
    
    resultados = []
    
    for faixa in df['faixa_tamanho'].unique():
        df_faixa = df[df['faixa_tamanho'] == faixa]
        if len(df_faixa) < 5:
            continue
        
        n_posts = df_faixa['posts_unicos'].median()
        taxa_media = df_faixa['total_mencoes'].sum() / df_faixa['posts_unicos'].sum()
        
        if taxa_media == 0:
            continue
        
        cv_list = []
        for _ in range(n_bootstrap):
            # Amostra COM REPOSIÇÃO dentro da faixa
            sample = df_faixa.sample(n=min(30, len(df_faixa)), replace=True)
            mencoes_boot = np.random.poisson(taxa_media, len(sample))
            cv = (np.std(mencoes_boot) / np.mean(mencoes_boot)) * 100 if np.mean(mencoes_boot) > 0 else 100
            cv_list.append(cv)
        
        resultados.append({
            'faixa': faixa,
            'n_median': n_posts,
            'n_modelos': len(df_faixa),
            'cv_mean': np.mean(cv_list),
            'cv_std': np.std(cv_list),
            'cv_ci_lower': np.percentile(cv_list, 2.5),
            'cv_ci_upper': np.percentile(cv_list, 97.5)
        })
    
    return pd.DataFrame(resultados)

def power_analysis(df, effect_size=0.5, alpha=0.05):
    """
    Calcula o poder estatístico para detectar diferenças entre grupos.
    """
    from statsmodels.stats.power import TTestIndPower
    
    analysis = TTestIndPower()
    
    resultados = []
    for n in [10, 15, 20, 25, 30, 40, 50, 100]:
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
    fig, axes = plt.subplots(2, 3, figsize=(18, 12))
    
    # 1. Distribuição de Posts por Modelo
    sns.histplot(df['posts_unicos'], bins=50, ax=axes[0,0], color='steelblue')
    axes[0,0].axvline(x=20, color='red', linestyle='--', label='n=20')
    axes[0,0].set_title('Distribuição de Posts por Modelo')
    axes[0,0].set_xlabel('Número de Posts')
    axes[0,0].legend()
    
    # 2. CV por Faixa de Tamanho (BOOTSTRAP CORRIGIDO)
    sns.barplot(data=df_bootstrap, x='faixa', y='cv_mean', ax=axes[0,1], palette='viridis')
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
    sns.scatterplot(data=df, x='posts_unicos', y='densidade_ponderada', ax=axes[1,0], alpha=0.6)
    sns.regplot(data=df, x='posts_unicos', y='densidade_ponderada', ax=axes[1,0], 
                scatter=False, color='red', label='Tendência')
    axes[1,0].axvline(x=20, color='black', linestyle='--')
    axes[1,0].axhline(y=3.0, color='green', linestyle='--')
    axes[1,0].set_title('Densidade Ponderada vs Número de Posts')
    axes[1,0].set_xlabel('Posts Únicos')
    axes[1,0].set_ylabel('Densidade Ponderada (menções/1000 palavras)')
    axes[1,0].legend()
    
    # 5. Entropia Temática
    sns.boxplot(data=df, y='entropia_tematica', ax=axes[1,1], color='teal')
    axes[1,1].axhline(y=1.0, color='orange', linestyle='--', label='Diversidade mínima')
    axes[1,1].set_title('Distribuição da Entropia Temática')
    axes[1,1].set_ylabel('Entropia de Shannon')
    axes[1,1].legend()
    
    # 6. Matriz de Correlação
    corr_cols = ['posts_unicos', 'densidade_ponderada', 'temas_cobertos', 'entropia_tematica', 'engajamento']
    corr_matrix = df[corr_cols].corr()
    sns.heatmap(corr_matrix, annot=True, fmt='.2f', cmap='RdBu_r', ax=axes[1,2])
    axes[1,2].set_title('Matriz de Correlação')
    
    plt.tight_layout()
    plt.savefig(CAMINHO_SAIDA / "validacao_cientifica_completa.png", dpi=400, bbox_inches='tight')
    plt.close()
    
    print(f"📊 Gráficos salvos em: {CAMINHO_SAIDA}")

def gerar_relatorio_final(df, df_bootstrap, df_power):
    """
    Gera relatório executivo com recomendações baseadas em evidências.
    """
    report = []
    report.append("# Relatório de Validação Científica do Corpus\n")
    
    # 1. Estatísticas descritivas
    report.append("## 1. Estatísticas Descritivas\n")
    report.append(f"- Total de modelos: {len(df)}")
    report.append(f"- Total de posts: {df['posts_unicos'].sum():,}")
    report.append(f"- Média de posts/modelo: {df['posts_unicos'].mean():.1f} (±{df['posts_unicos'].std():.1f})")
    report.append(f"- Densidade média: {df['densidade_ponderada'].mean():.2f}")
    report.append(f"- Modelos com n ≥ 20: {len(df[df['posts_unicos'] >= 20])} ({len(df[df['posts_unicos'] >= 20])/len(df)*100:.1f}%)")
    
    # 2. Validação do Threshold n=20
    report.append("\n## 2. Validação do Threshold n=20\n")
    cv_n20 = df_bootstrap[df_bootstrap['n_median'] <= 25]['cv_mean'].mean()
    report.append(f"- CV médio para n≈20: {cv_n20:.1f}%")
    report.append(f"- Status: {'✅ ACEITÁVEL' if cv_n20 <= 15 else '⚠️ ELEVADO'}")
    
    power_n20 = df_power[df_power['n_posts'] == 20]['power'].values[0]
    report.append(f"- Poder estatístico para n=20: {power_n20:.2f}")
    report.append(f"- Status: {'✅ ADEQUADO' if power_n20 >= 0.8 else '⚠️ BAIXO'}")
    
    # 3. Recomendações
    report.append("\n## 3. Recomendações para Thresholds\n")
    
    if cv_n20 <= 15 and power_n20 >= 0.8:
        report.append("✅ **n ≥ 20** é estatisticamente válido.")
    elif cv_n20 <= 20 and power_n20 >= 0.7:
        report.append("⚠️ **n ≥ 25** recomendado para maior robustez.")
    else:
        report.append("❌ **n ≥ 30** necessário para validade estatística.")
    
    # Densidade
    p25_dens = df['densidade_ponderada'].quantile(0.25)
    report.append(f"\n- Percentil 25 da densidade: {p25_dens:.2f}")
    report.append(f"- Recomendação: **densidade ≥ {max(2.5, round(p25_dens, 1))}**")
    
    # Temas
    p25_temas = df['temas_cobertos'].quantile(0.25)
    report.append(f"- Percentil 25 de temas: {p25_temas:.0f}")
    report.append(f"- Recomendação: **temas ≥ {max(2, int(p25_temas))}**")
    
    with open(CAMINHO_SAIDA / "relatorio_final.md", 'w', encoding='utf-8') as f:
        f.write('\n'.join(report))
    
    print(f"📄 Relatório final: {CAMINHO_SAIDA / 'relatorio_final.md'}")

def main():
    print("=" * 80)
    print("🔬 VALIDAÇÃO CIENTÍFICA COMPLETA DO CORPUS")
    print("=" * 80)
    
    df = pd.read_csv(CAMINHO_ENTRADA, sep=';')
    print(f"\n📊 Dados carregados: {len(df)} modelos")
    
    # Remove outliers para análise de threshold
    df_clean = df[~df['is_outlier']] if 'is_outlier' in df.columns else df
    print(f"📊 Após remoção de outliers: {len(df_clean)} modelos")
    
    # Bootstrapping corrigido
    print("\n🔄 Executando Bootstrapping Estratificado...")
    df_bootstrap = bootstrap_estratificado(df_clean)
    
    # Power analysis
    print("⚡ Executando Power Analysis...")
    df_power = power_analysis(df_clean)
    
    # Gráficos
    print("📈 Gerando gráficos...")
    gerar_graficos_validacao(df_clean, df_bootstrap, df_power)
    
    # Relatório
    gerar_relatorio_final(df_clean, df_bootstrap, df_power)
    
    print("\n✅ Validação científica concluída!")

if __name__ == "__main__":
    main()