import json
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
from pathlib import Path

from core.paths import PREPROCESSAMENTO_DATA

# Configurações de Caminho
# CAMINHO_JSON = PREPROCESSAMENTO_DATA / "analise_estatisticaV2" / "analise_diversidade_resultado.json"
CAMINHO_JSON = PREPROCESSAMENTO_DATA / "analise_estatisticaV4" / "analise_diversidade_resultado.json"
# PASTA_IMAGENS = PREPROCESSAMENTO_DATA / "graficos" 
PASTA_IMAGENS = PREPROCESSAMENTO_DATA / "graficos3" 

def gerar_dashboards():
    # Criar pasta para os gráficos
    PASTA_IMAGENS.mkdir(parents=True, exist_ok=True)
    
    # 1. Carregar os dados
    try:
        with open(CAMINHO_JSON, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Erro: O arquivo {CAMINHO_JSON} não foi encontrado.")
        return

    sns.set_theme(style="whitegrid")
    
    # --- GRÁFICO 1: DISTRIBUIÇÃO DE MARCAS ---
    if 'distribuicao_marcas' in data:
        marcas = pd.Series(data['distribuicao_marcas']).sort_values(ascending=False)
        plt.figure(figsize=(12, 6))
        sns.barplot(x=marcas.index, y=marcas.values, color='skyblue')
        plt.title("Representatividade por Marca Principal", fontsize=15, pad=20)
        plt.xlabel("Marca", fontsize=12)
        plt.ylabel("Quantidade de Arquivos (Modelos)", fontsize=12)
        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.savefig(PASTA_IMAGENS / "01_distribuicao_marcas.png", dpi=300)
        print("✅ Gráfico de Marcas gerado.")

    # --- GRÁFICO 2: VOLUME POR CATEGORIA ---
    if 'distribuicao_categorias' in data:
        categorias = pd.Series(data['distribuicao_categorias']).sort_values(ascending=False)
        plt.figure(figsize=(12, 6))
        sns.barplot(x=categorias.index, y=categorias.values, color='salmon')
        plt.title("Volume Total de Posts por Categoria de Problema", fontsize=15, pad=20)
        plt.xlabel("Categoria", fontsize=12)
        plt.ylabel("Total de Posts", fontsize=12)
        plt.xticks(rotation=30, ha='right')
        plt.tight_layout()
        plt.savefig(PASTA_IMAGENS / "02_volume_categorias.png", dpi=300)
        print("✅ Gráfico de Categorias gerado.")

    # --- GRÁFICO 3: TERMOS GERAIS ---
    if 'problemas_mais_comuns' in data:
        problemas = pd.Series(data['problemas_mais_comuns']).sort_values(ascending=False).head(20)
        plt.figure(figsize=(12, 8))
        sns.barplot(x=problemas.values, y=problemas.index, color='teal')
        plt.title("Top 20 Indicadores Técnicos Mais Frequentes (Geral)", fontsize=15, pad=20)
        plt.xlabel("Frequência Absoluta", fontsize=12)
        plt.ylabel("Termo Detectado", fontsize=12)
        plt.tight_layout()
        plt.savefig(PASTA_IMAGENS / "03_termos_gerais.png", dpi=300)
        print("✅ Gráfico de Termos Gerais gerado.")

    # --- GRÁFICO 4: TERMOS POR GRUPO (NOVO) ---
    if 'termos_por_grupo' in data:
        # Pegamos as 4 categorias principais para visualização
        categorias_com_dados = list(data['termos_por_grupo'].keys())[:4]
        fig, axes = plt.subplots(2, 2, figsize=(16, 12))
        axes = axes.flatten()
        
        for i, cat in enumerate(categorias_com_dados):
            termos = pd.Series(data['termos_por_grupo'][cat]).sort_values(ascending=False).head(8)
            sns.barplot(x=termos.values, y=termos.index, ax=axes[i], color='indigo', alpha=0.7)
            axes[i].set_title(f"Principais Termos: {cat.replace('_', ' ').title()}", fontsize=12)
            axes[i].set_xlabel("Frequência")

        plt.suptitle("Detalhamento de Termos Específicos por Categoria", fontsize=18)
        plt.tight_layout(rect=[0, 0.03, 1, 0.95])
        plt.savefig(PASTA_IMAGENS / "04_detalhe_por_grupo.png", dpi=300)
        print("✅ Gráfico de Detalhamento por Grupo gerado.")

    print(f"\n🚀 Todos os gráficos foram salvos em: {PASTA_IMAGENS}")

if __name__ == "__main__":
    gerar_dashboards()