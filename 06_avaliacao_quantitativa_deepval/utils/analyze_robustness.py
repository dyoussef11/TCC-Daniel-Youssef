#!/usr/bin/env python3
"""
Análise de Robustez a partir dos CSVs com repetições (com_repeticaoV7)
Calcula médias e desvios padrão por combinação (juiz, gerador) e por métrica.
Gera tabela LaTeX compacta e gráficos apenas para métricas com dados.
"""

import os
import re
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from typing import Dict, List, Tuple
from core.paths import AVALIACAO_DATA

# ============================================================================
# CONFIGURAÇÃO
# ============================================================================
PASTA_CSVS = Path(AVALIACAO_DATA / "06_avaliacao_quantitativa_deepval/data/testes_com_modelos_diferentes_sem_fallback/com_repeticaoV7")
OUTPUT_DIR = Path("06_avaliacao_quantitativa_deepval/utils/analise_robustez")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Métricas que queremos analisar (colunas com _Score)
METRICS = [
    "Faithfulness",
    "Answer_Relevancy",
    "Contextual_Relevancy",
    "Contextual_Precision",
    "Contextual_Recall",
    "Behavioral_Guardrails",
    "Temporal_Reranking",
    "Intelligent_Fallback",
    "Temporal_Consistency"
]

# Tipo de teste para cada métrica (para separar nos gráficos)
METRIC_TYPE = {
    "Faithfulness": "traditional",
    "Answer_Relevancy": "traditional",
    "Contextual_Relevancy": "traditional",
    "Contextual_Precision": "traditional",
    "Contextual_Recall": "traditional",
    "Behavioral_Guardrails": "behavioral",
    "Temporal_Reranking": "behavioral",
    "Intelligent_Fallback": "behavioral",
    "Temporal_Consistency": "temporal"
}

# ============================================================================
# FUNÇÕES AUXILIARES
# ============================================================================

def parse_combination_from_filename(filename: str) -> Tuple[str, str]:
    """
    Extrai juiz e gerador do nome do arquivo.
    Exemplo: DEEPEVAL_MIXED_NATIVE_COMPARATIVE_COM_REPETICAO_J_granite3.2_8b_G_mistral_7b-instruct_20260803_1838.csv
    """
    pattern = r"J_(.+?)_G_(.+?)_\d{8}_\d{4}\.csv$"
    match = re.search(pattern, filename)
    if match:
        judge = match.group(1).replace("_", ":")  # granite3.2:8b
        generator = match.group(2).replace("_", ":")  # mistral:7b-instruct
        return judge, generator
    else:
        return None, None

def load_csv_safe(filepath: Path) -> pd.DataFrame:
    """Carrega CSV, retorna DataFrame vazio se falhar ou estiver vazio."""
    try:
        df = pd.read_csv(filepath)
        if df.empty:
            return pd.DataFrame()
        return df
    except Exception as e:
        print(f"Erro ao ler {filepath}: {e}")
        return pd.DataFrame()

def compute_robustness_stats(df: pd.DataFrame, metric: str, version: str) -> Dict:
    """
    Para uma métrica e versão (V1 ou V9), calcula:
    - Média geral da métrica (todos os casos)
    - Desvio padrão entre repetições (agrupado por Original_ID)
    - Média do desvio padrão (robustez)
    - Percentual de casos com desvio padrão > 0.15 (alta variabilidade)
    - Número de casos válidos
    """
    score_col = f"{version}_{metric}_Score"
    if score_col not in df.columns:
        return {
            "mean": np.nan,
            "std_mean": np.nan,
            "high_var_pct": np.nan,
            "count": 0
        }
    
    # Remove linhas com NaN no score
    df_clean = df[[score_col, "Original_ID"]].dropna()
    if df_clean.empty:
        return {"mean": np.nan, "std_mean": np.nan, "high_var_pct": np.nan, "count": 0}
    
    # Calcula o desvio padrão por Original_ID (repetições)
    std_per_case = df_clean.groupby("Original_ID")[score_col].std()
    
    # Estatísticas
    mean_score = df_clean[score_col].mean()
    std_mean = std_per_case.mean() if not std_per_case.empty else np.nan
    high_var_count = (std_per_case > 0.15).sum() if not std_per_case.empty else 0
    high_var_pct = high_var_count / len(std_per_case) if len(std_per_case) > 0 else np.nan
    
    return {
        "mean": mean_score,
        "std_mean": std_mean,
        "high_var_pct": high_var_pct,
        "count": len(df_clean)
    }

# ============================================================================
# PROCESSAMENTO PRINCIPAL
# ============================================================================

def main():
    # Lista todos os CSVs na pasta
    csv_files = list(PASTA_CSVS.glob("DEEPEVAL_MIXED_NATIVE_COMPARATIVE_COM_REPETICAO_*.csv"))
    if not csv_files:
        print(f"Nenhum CSV encontrado em {PASTA_CSVS}")
        return
    
    print(f"Encontrados {len(csv_files)} arquivos CSV.")
    
    # Lista para armazenar resultados consolidados por combinação
    results = []
    
    for filepath in csv_files:
        judge, generator = parse_combination_from_filename(filepath.name)
        if judge is None or generator is None:
            print(f"Pulando arquivo com nome inesperado: {filepath.name}")
            continue
        
        print(f"Processando: {judge} x {generator}")
        
        df = load_csv_safe(filepath)
        if df.empty:
            print(f"  -> Arquivo vazio ou com erro. Pulando.")
            continue
        
        # Para cada métrica, calcula estatísticas para V1 e V9
        for metric in METRICS:
            for version in ["V1", "V9"]:
                stats = compute_robustness_stats(df, metric, version)
                # Só adiciona se houver pelo menos 1 caso válido (N > 0)
                if stats["count"] > 0:
                    results.append({
                        "Judge": judge,
                        "Generator": generator,
                        "Metric": metric,
                        "Version": version,
                        "Mean": stats["mean"],
                        "Std_Mean": stats["std_mean"],
                        "High_Var_Pct": stats["high_var_pct"],
                        "N": stats["count"]
                    })
    
    if not results:
        print("Nenhum dado válido foi extraído (todos os N=0).")
        return
    
    # Converte para DataFrame
    df_results = pd.DataFrame(results)
    
    # Salva o consolidado (já sem N=0)
    csv_out = OUTPUT_DIR / "consolidado_robustez.csv"
    df_results.to_csv(csv_out, index=False)
    print(f"\n✅ Consolidado salvo em {csv_out} (apenas combinações com dados).")
    
    # ========================================================================
    # CRIA TABELA RESUMO PARA LATEX (média e std médio) - APENAS G-EVAL
    # ========================================================================
    # Filtra apenas as métricas G-Eval (comportamentais e temporais)
    geval_metrics = [m for m in METRICS if m in METRIC_TYPE and METRIC_TYPE[m] in ["behavioral", "temporal"]]
    
    # Pivot para ter colunas V1_mean, V1_std, V9_mean, V9_std
    # Importante: o pivot só inclui as combinações que têm dados para ambas as versões?
    # Para garantir, podemos fazer um pivot e depois eliminar linhas com NaN em V1 ou V9
    pivot = df_results.pivot_table(
        index=["Judge", "Generator", "Metric"],
        columns="Version",
        values=["Mean", "Std_Mean"]
    ).reset_index()
    
    # Achata os multi-index
    pivot.columns = ['Judge', 'Generator', 'Metric', 'V1_Mean', 'V9_Mean', 'V1_Std', 'V9_Std']
    
    # Remove linhas onde V1_Mean ou V9_Mean são NaN (dados faltando para uma das versões)
    pivot = pivot.dropna(subset=['V1_Mean', 'V9_Mean'])
    
    # Calcula delta (V9 - V1)
    pivot['Delta'] = pivot['V9_Mean'] - pivot['V1_Mean']
    
    # Salva tabela para LaTeX (apenas G-Eval)
    latex_df = pivot[pivot['Metric'].isin(geval_metrics)]
    latex_df = latex_df.sort_values(['Metric', 'Judge'])
    
    if latex_df.empty:
        print("⚠️ Nenhuma métrica G-Eval com dados suficientes para a tabela LaTeX.")
    else:
        # Formata valores para LaTeX
        def fmt(x):
            return f"{x:.3f}" if pd.notna(x) else "---"
        
        latex_df['V1_Mean'] = latex_df['V1_Mean'].apply(fmt)
        latex_df['V9_Mean'] = latex_df['V9_Mean'].apply(fmt)
        latex_df['V1_Std'] = latex_df['V1_Std'].apply(fmt)
        latex_df['V9_Std'] = latex_df['V9_Std'].apply(fmt)
        latex_df['Delta'] = latex_df['Delta'].apply(lambda x: f"{x:+.3f}" if pd.notna(x) else "---")
        
        # Gera tabela LaTeX
        latex_table = latex_df.to_latex(
            index=False,
            columns=['Judge', 'Generator', 'Metric', 'V1_Mean', 'V1_Std', 'V9_Mean', 'V9_Std', 'Delta'],
            caption="Análise de Robustez por Combinação (Média ± Desvio Padrão entre Repetições)",
            label="tab:robustez_completa",
            longtable=False,
            escape=False
        )
        
        with open(OUTPUT_DIR / "tabela_robustez.tex", "w", encoding="utf-8") as f:
            f.write(latex_table)
        print(f"✅ Tabela LaTeX salva em {OUTPUT_DIR / 'tabela_robustez.tex'}")
    
    # ========================================================================
    # GRÁFICOS DE BARRAS COM BARRAS DE ERRO (para G-Eval)
    # ========================================================================
    sns.set_theme(style="whitegrid")
    
    for metric in geval_metrics:
        # Filtra dados da métrica
        df_metric = df_results[df_results['Metric'] == metric]
        if df_metric.empty:
            print(f"⚠️ Sem dados para métrica {metric}, pulando gráfico.")
            continue
        
        # Pivot para ter V1 e V9 em colunas separadas
        df_plot = df_metric.pivot_table(
            index=["Judge", "Generator"],
            columns="Version",
            values=["Mean", "Std_Mean"]
        ).reset_index()
        df_plot.columns = ['Judge', 'Generator', 'V1_Mean', 'V9_Mean', 'V1_Std', 'V9_Std']
        
        # Remove combinações sem dados para ambas as versões
        df_plot = df_plot.dropna(subset=['V1_Mean', 'V9_Mean'])
        if df_plot.empty:
            print(f"⚠️ Nenhuma combinação com dados completos para {metric}, pulando gráfico.")
            continue
        
        # Ordena por V9_Mean decrescente para melhor visualização
        df_plot = df_plot.sort_values('V9_Mean', ascending=False)
        
        # Cria identificador combinado para o eixo x
        df_plot['Combination'] = df_plot['Judge'] + "\n" + df_plot['Generator']
        
        # Define posições das barras
        x = np.arange(len(df_plot))
        width = 0.35
        
        fig, ax = plt.subplots(figsize=(14, 8))
        
        # Barras V1
        ax.bar(x - width/2, df_plot['V1_Mean'], width, 
               label='V1 (Vanilla)', color='skyblue', 
               yerr=df_plot['V1_Std'], capsize=3)
        
        # Barras V9
        ax.bar(x + width/2, df_plot['V9_Mean'], width, 
               label='V9 (Temporal)', color='salmon',
               yerr=df_plot['V9_Std'], capsize=3)
        
        # Linha de referência em 0.8 (threshold comum)
        ax.axhline(y=0.8, color='gray', linestyle='--', linewidth=1, label='Threshold 0.8')
        
        ax.set_xlabel('Combinação (Juiz / Gerador)')
        ax.set_ylabel('Score Médio')
        ax.set_title(f'Comparação V1 vs V9 - {metric}')
        ax.set_xticks(x)
        ax.set_xticklabels(df_plot['Combination'], rotation=45, ha='right')
        ax.legend()
        
        plt.tight_layout()
        plt.savefig(OUTPUT_DIR / f"grafico_{metric}.png", dpi=150)
        plt.close()
        print(f"✅ Gráfico salvo: grafico_{metric}.png")
    
    # ========================================================================
    # ESTATÍSTICAS GERAIS DE ROBUSTEZ (resumo)
    # ========================================================================
    # Calcula média geral do desvio padrão por combinação e métrica
    robustez_summary = df_results.groupby(['Metric', 'Version'])['Std_Mean'].agg(['mean', 'std']).reset_index()
    print("\n📊 Resumo de Robustez (média do desvio padrão entre repetições):")
    print(robustez_summary.to_string(index=False))
    robustez_summary.to_csv(OUTPUT_DIR / "resumo_robustez_global.csv", index=False)
    print(f"✅ Resumo salvo em {OUTPUT_DIR / 'resumo_robustez_global.csv'}")

if __name__ == "__main__":
    main()