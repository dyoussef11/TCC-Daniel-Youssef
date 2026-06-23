import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from core.paths import PREPROCESSAMENTO_DATA

# ============ CONFIGURAÇÕES ============
CAMINHO_CSV = PREPROCESSAMENTO_DATA / "Analise_Temporal"
PASTA_IMAGENS = PREPROCESSAMENTO_DATA / "graficos_temporais"
PASTA_IMAGENS.mkdir(parents=True, exist_ok=True)

sns.set_theme(style="whitegrid")

def gerar_graficos_temporais():
    # Carregar os CSVs
    try:
        df_global = pd.read_csv(CAMINHO_CSV / "distribuicao_temporal_global.csv", sep=';', encoding='utf-8-sig')
        df_modelo = pd.read_csv(CAMINHO_CSV / "distribuicao_temporal_por_modelo.csv", sep=';', encoding='utf-8-sig')
        df_duracao = pd.read_csv(CAMINHO_CSV / "dimensao_temporal_por_modelo.csv", sep=';', encoding='utf-8-sig')
    except FileNotFoundError as e:
        print(f"Erro: {e}. Verifique se os CSVs estão em {CAMINHO_CSV}")
        return

    # ---- GRÁFICO 1: Distribuição Global por Ano ----
    plt.figure(figsize=(12, 6))
    ax = sns.barplot(data=df_global, x='ano', y='quantidade', palette='Blues_d', hue='ano')
    plt.title("Distribuição Global de Posts por Ano", fontsize=15, pad=20)
    plt.xlabel("Ano", fontsize=12)
    plt.ylabel("Quantidade de Posts", fontsize=12)
    # Adicionar rótulos de percentual
    for p in ax.patches:
        ax.annotate(f"{p.get_height():,}", (p.get_x() + p.get_width() / 2., p.get_height()),
                    ha='center', va='bottom', fontsize=9)
    plt.tight_layout()
    plt.savefig(PASTA_IMAGENS / "01_distribuicao_global_por_ano.png", dpi=300)
    print("✅ Gráfico 1: Distribuição global por ano gerado.")

    # ---- GRÁFICO 2: Top 10 Modelos por Duração ----
    top_duracao = df_duracao.dropna(subset=['duracao_dias']).nlargest(10, 'duracao_dias')
    plt.figure(figsize=(12, 8))
    sns.barplot(data=top_duracao, y='modelo', x='duracao_dias', palette='Reds_r', hue='modelo')
    plt.title("Top 10 Modelos com Maior Duração (dias entre 1º post e último comentário)", fontsize=15, pad=20)
    plt.xlabel("Duração (dias)", fontsize=12)
    plt.ylabel("Modelo", fontsize=12)
    plt.tight_layout()
    plt.savefig(PASTA_IMAGENS / "02_top10_duracao.png", dpi=300)
    print("✅ Gráfico 2: Top 10 duração gerado.")

    # ---- GRÁFICO 3: Evolução Anual dos 10 Modelos Mais Produtivos ----
    top_modelos = df_modelo.groupby('modelo')['quantidade'].sum().nlargest(10).index
    df_top = df_modelo[df_modelo['modelo'].isin(top_modelos)]
    plt.figure(figsize=(14, 8))
    sns.lineplot(data=df_top, x='ano', y='quantidade', hue='modelo', marker='o', linewidth=2.5)
    plt.title("Evolução Anual dos 10 Modelos com Mais Posts", fontsize=15, pad=20)
    plt.xlabel("Ano", fontsize=12)
    plt.ylabel("Quantidade de Posts", fontsize=12)
    plt.legend(loc='upper left', bbox_to_anchor=(1, 1), title='Modelo')
    plt.tight_layout()
    plt.savefig(PASTA_IMAGENS / "03_evolucao_top10_modelos.png", dpi=300)
    print("✅ Gráfico 3: Evolução dos top 10 modelos gerado.")

    # ---- GRÁFICO 4: Relação Duração x Total de Posts ----
    plt.figure(figsize=(12, 8))
    # Selecionar alguns modelos para destacar (os mais longos)
    top_longevos = df_duracao.nlargest(10, 'duracao_dias')['modelo'].tolist()
    df_duracao['destaque'] = df_duracao['modelo'].apply(lambda x: x if x in top_longevos else 'Outros')
    cores = {'Outros': 'lightgray'}
    for modelo in top_longevos:
        cores[modelo] = sns.color_palette("tab10")[top_longevos.index(modelo) % 10]
    sns.scatterplot(data=df_duracao, x='duracao_dias', y='total_posts', hue='destaque',
                    palette=cores, alpha=0.7, s=80)
    plt.title("Relação entre Duração e Volume de Posts", fontsize=15, pad=20)
    plt.xlabel("Duração (dias)", fontsize=12)
    plt.ylabel("Total de Posts", fontsize=12)
    plt.legend(title='Modelo', bbox_to_anchor=(1.05, 1), loc='upper left')
    plt.tight_layout()
    plt.savefig(PASTA_IMAGENS / "04_duracao_vs_volume.png", dpi=300)
    print("✅ Gráfico 4: Relação duração x volume gerado.")

    # ---- GRÁFICO 5: Heatmap de Atividade (Top 20 Modelos × Anos) ----
    top20_modelos = df_modelo.groupby('modelo')['quantidade'].sum().nlargest(20).index
    df_heatmap = df_modelo[df_modelo['modelo'].isin(top20_modelos)].pivot(index='modelo', columns='ano', values='quantidade').fillna(0)
    plt.figure(figsize=(14, 10))
    sns.heatmap(df_heatmap, annot=True, fmt='.0f', cmap='YlOrRd', cbar_kws={'label': 'Posts'})
    plt.title("Mapa de Calor: Atividade dos 20 Modelos com Mais Posts por Ano", fontsize=15, pad=20)
    plt.xlabel("Ano", fontsize=12)
    plt.ylabel("Modelo", fontsize=12)
    plt.tight_layout()
    plt.savefig(PASTA_IMAGENS / "05_heatmap_top20_modelos_anos.png", dpi=300)
    print("✅ Gráfico 5: Heatmap de atividade gerado.")

    print(f"\n🚀 Todos os gráficos foram salvos em: {PASTA_IMAGENS}")

if __name__ == "__main__":
    gerar_graficos_temporais()