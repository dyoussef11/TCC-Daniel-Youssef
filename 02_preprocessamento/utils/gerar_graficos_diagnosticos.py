import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
from pathlib import Path
from core.paths import PREPROCESSAMENTO_DATA

# ============ CONFIGURAÇÕES ============
CAMINHO_CSV = PREPROCESSAMENTO_DATA / 'analises_dados' /"Analise_Temporal"
PASTA_IMAGENS = PREPROCESSAMENTO_DATA / 'analises_dados' /"graficos_diagnosticos"
PASTA_IMAGENS.mkdir(parents=True, exist_ok=True)

sns.set_theme(style="whitegrid")
plt.rcParams['figure.dpi'] = 150

def gerar_graficos_analiticos():
    # Carregar CSVs
    df_global = pd.read_csv(CAMINHO_CSV / "distribuicao_temporal_global.csv", sep=';', encoding='utf-8-sig')
    df_modelo = pd.read_csv(CAMINHO_CSV / "distribuicao_temporal_por_modelo.csv", sep=';', encoding='utf-8-sig')
    df_duracao = pd.read_csv(CAMINHO_CSV / "dimensao_temporal_por_modelo.csv", sep=';', encoding='utf-8-sig')

    # ---- GRÁFICO 1: Dispersão Volume x Duração com Destaque de Modelos Problemáticos ----
    # Calcular percentis para identificar outliers
    df_duracao['rank_volume'] = df_duracao['total_posts'].rank(pct=True)
    df_duracao['rank_duracao'] = df_duracao['duracao_dias'].rank(pct=True)
    # Modelos problemáticos: top 20% em ambos
    df_duracao['alerta'] = ((df_duracao['rank_volume'] >= 0.8) & (df_duracao['rank_duracao'] >= 0.8))
    
    plt.figure(figsize=(14, 10))
    # Plotar todos os pontos
    sns.scatterplot(data=df_duracao, x='duracao_dias', y='total_posts', 
                    hue='alerta', palette={True: 'red', False: 'lightgray'}, 
                    alpha=0.6, s=60)
    # Destacar modelos em alerta com anotações
    alertas = df_duracao[df_duracao['alerta']].nlargest(10, 'total_posts')
    for _, row in alertas.iterrows():
        plt.annotate(row['modelo'], (row['duracao_dias'], row['total_posts']),
                     xytext=(5,5), textcoords='offset points', fontsize=8, alpha=0.8)
    plt.title("Modelos Problemáticos: Alto Volume e Longa Duração", fontsize=15, pad=20)
    plt.xlabel("Duração (dias)", fontsize=12)
    plt.ylabel("Total de Posts", fontsize=12)
    plt.legend(['Potencialmente Problemático', 'Outros'], loc='upper left')
    plt.tight_layout()
    plt.savefig(PASTA_IMAGENS / "01_dispersao_alerta.png", dpi=300)
    print("✅ Gráfico 1: Dispersão com alerta gerado.")

    # ---- GRÁFICO 2: Top 20 em Duração com Cor por Volume ----
    top_duracao = df_duracao.nlargest(20, 'duracao_dias')
    plt.figure(figsize=(12, 10))
    sns.barplot(data=top_duracao, y='modelo', x='duracao_dias', hue= 'modelo',
                palette='Reds_r', edgecolor='black')
    # Adicionar rótulo de total de posts
    for i, row in enumerate(top_duracao.itertuples()):
        plt.text(row.duracao_dias + 10, i, f"Posts: {row.total_posts}", 
                 va='center', fontsize=8)
    plt.title("Modelos com Maior Duração (e respectivo volume de posts)", fontsize=15, pad=20)
    plt.xlabel("Duração (dias)", fontsize=12)
    plt.ylabel("Modelo", fontsize=12)
    plt.tight_layout()
    plt.savefig(PASTA_IMAGENS / "02_top_duracao_com_volume.png", dpi=300)
    print("✅ Gráfico 2: Duração com volume gerado.")

    # ---- GRÁFICO 3: Picos Anômalos (Ano com maior crescimento) ----
    # Para cada modelo, calcular o desvio padrão da quantidade anual e identificar anos com pico
    df_modelo['ano'] = df_modelo['ano'].astype(int)
    # Calcular média e desvio por modelo
    stats = df_modelo.groupby('modelo')['quantidade'].agg(['mean', 'std']).reset_index()
    stats.columns = ['modelo', 'media', 'std']
    df_modelo = df_modelo.merge(stats, on='modelo')
    df_modelo['zscore'] = (df_modelo['quantidade'] - df_modelo['media']) / df_modelo['std'].replace(0, 1)
    # Pegar os maiores picos (zscore > 2)
    picos = df_modelo[df_modelo['zscore'] > 2].nlargest(20, 'zscore')
    # Para visualização, pegar modelos com mais de um pico
    plt.figure(figsize=(14, 8))
    # Selecionar alguns modelos para exibir (top 5 em zscore)
    top_picos = picos.nlargest(5, 'zscore')['modelo'].unique()
    df_picos = df_modelo[df_modelo['modelo'].isin(top_picos)]
    sns.lineplot(data=df_picos, x='ano', y='quantidade', hue='modelo', marker='o', linewidth=2)
    # Destacar os pontos que são picos
    for modelo in top_picos:
        subset = picos[picos['modelo'] == modelo]
        plt.scatter(subset['ano'], subset['quantidade'], color='red', s=100, edgecolor='black', zorder=5)
    plt.title("Modelos com Picos Anômalos de Posts (possíveis falhas ou eventos)", fontsize=15, pad=20)
    plt.xlabel("Ano", fontsize=12)
    plt.ylabel("Quantidade de Posts", fontsize=12)
    plt.legend(title='Modelo', bbox_to_anchor=(1.05, 1), loc='upper left')
    plt.tight_layout()
    plt.savefig(PASTA_IMAGENS / "03_picos_anomalos.png", dpi=300)
    print("✅ Gráfico 3: Picos anômalos gerado.")

    # ---- GRÁFICO 4: Heatmap com escala log (para realçar padrões) ----
    top20_modelos = df_modelo.groupby('modelo')['quantidade'].sum().nlargest(20).index
    df_heat = df_modelo[df_modelo['modelo'].isin(top20_modelos)].pivot(index='modelo', columns='ano', values='quantidade').fillna(0)
    # Aplicar log(1+x) para melhor visualização
    df_heat_log = np.log1p(df_heat)
    plt.figure(figsize=(16, 10))
    sns.heatmap(df_heat_log, annot=False, cmap='YlOrRd', cbar_kws={'label': 'log(1+Posts)'})
    plt.title("Heatmap (Escala Log) - Atividade dos Top 20 Modelos", fontsize=15, pad=20)
    plt.xlabel("Ano", fontsize=12)
    plt.ylabel("Modelo", fontsize=12)
    plt.tight_layout()
    plt.savefig(PASTA_IMAGENS / "04_heatmap_log.png", dpi=300)
    print("✅ Gráfico 4: Heatmap log gerado.")

    # ---- GRÁFICO 5: Ranking Combinado (Alerta) ----
    # Criar um score combinado: média dos percentis de volume e duração
    df_duracao['score'] = (df_duracao['rank_volume'] + df_duracao['rank_duracao']) / 2
    top_alerta = df_duracao.nlargest(15, 'score')[['modelo', 'total_posts', 'duracao_dias', 'score']]
    plt.figure(figsize=(12, 8))
    sns.barplot(data=top_alerta, y='modelo', x='score', hue = 'modelo',palette='coolwarm', edgecolor='black')
    plt.title("Ranking de Modelos com Maior Pontuação Combinada\n(Volume + Duração)", fontsize=15, pad=20)
    plt.xlabel("Score Combinado (0 a 1)", fontsize=12)
    plt.ylabel("Modelo", fontsize=12)
    # Adicionar anotações com total de posts
    for i, row in enumerate(top_alerta.itertuples()):
        plt.text(row.score + 0.01, i, f"Posts: {row.total_posts} | Dias: {row.duracao_dias:.0f}", 
                va='center', fontsize=8)
    plt.tight_layout()
    plt.savefig(PASTA_IMAGENS / "05_ranking_combinado.png", dpi=300)
    print("✅ Gráfico 5: Ranking combinado gerado.")

    print(f"\n🚀 Todos os gráficos analíticos salvos em: {PASTA_IMAGENS}")

if __name__ == "__main__":
    gerar_graficos_analiticos()