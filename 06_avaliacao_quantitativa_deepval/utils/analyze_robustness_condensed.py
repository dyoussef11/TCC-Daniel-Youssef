#!/usr/bin/env python3
"""
Análise de Robustez Condensada para TCC.
Agrega resultados por juiz (média sobre todos os geradores) e gera:
- Tabela LaTeX com média ± desvio padrão para métricas G-Eval.
- Gráficos para Behavioral_Guardrails e Temporal_Consistency.
"""

import os
import re
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from typing import Tuple

from core.paths import AVALIACAO_DATA

# ============================================================================
# CONFIGURAÇÃO
# ============================================================================
PASTA_CSVS = Path(AVALIACAO_DATA / "06_avaliacao_quantitativa_deepval/data/testes_com_modelos_diferentes_sem_fallback/com_repeticaoV7")
OUTPUT_DIR = Path("06_avaliacao_quantitativa_deepval/utils/analise_robustez_condensada")
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

# Métricas G-Eval (para a tabela principal)
GEVAL_METRICS = ["Behavioral_Guardrails", "Temporal_Reranking", "Intelligent_Fallback", "Temporal_Consistency"]

# ============================================================================
# FUNÇÕES AUXILIARES
# ============================================================================

def parse_combination_from_filename(filename: str) -> Tuple[str, str]:
    pattern = r"J_(.+?)_G_(.+?)_\d{8}_\d{4}\.csv$"
    match = re.search(pattern, filename)
    if match:
        judge = match.group(1).replace("_", ":")
        generator = match.group(2).replace("_", ":")
        return judge, generator
    return None, None

def load_csv_safe(filepath: Path) -> pd.DataFrame:
    try:
        df = pd.read_csv(filepath)
        if df.empty:
            return pd.DataFrame()
        return df
    except Exception:
        return pd.DataFrame()

def compute_stats_by_case(df: pd.DataFrame, metric: str, version: str) -> dict:
    """Calcula média geral e desvio padrão entre repetições (por caso) para uma métrica."""
    score_col = f"{version}_{metric}_Score"
    if score_col not in df.columns:
        return {"mean": np.nan, "std_mean": np.nan, "count": 0}
    df_clean = df[[score_col, "Original_ID"]].dropna()
    if df_clean.empty:
        return {"mean": np.nan, "std_mean": np.nan, "count": 0}
    # Desvio padrão entre repetições por caso
    std_per_case = df_clean.groupby("Original_ID")[score_col].std()
    return {
        "mean": df_clean[score_col].mean(),
        "std_mean": std_per_case.mean() if not std_per_case.empty else np.nan,
        "count": len(df_clean)
    }

# ============================================================================
# PROCESSAMENTO PRINCIPAL
# ============================================================================

def main():
    csv_files = list(PASTA_CSVS.glob("DEEPEVAL_MIXED_NATIVE_COMPARATIVE_COM_REPETICAO_*.csv"))
    if not csv_files:
        print(f"Nenhum CSV encontrado em {PASTA_CSVS}")
        return

    print(f"Encontrados {len(csv_files)} arquivos CSV.")
    
    # Armazena dados brutos por combinação
    all_data = []

    for filepath in csv_files:
        judge, generator = parse_combination_from_filename(filepath.name)
        if judge is None or generator is None:
            print(f"Pulando arquivo com nome inesperado: {filepath.name}")
            continue
        
        df = load_csv_safe(filepath)
        if df.empty:
            print(f"Arquivo vazio ou com erro: {filepath.name}")
            continue

        for metric in METRICS:
            for version in ["V1", "V9"]:
                stats = compute_stats_by_case(df, metric, version)
                all_data.append({
                    "Judge": judge,
                    "Generator": generator,
                    "Metric": metric,
                    "Version": version,
                    "Mean": stats["mean"],
                    "Std_Repetitions": stats["std_mean"],  # desvio entre repetições
                    "N": stats["count"]
                })

    if not all_data:
        print("Nenhum dado válido extraído.")
        return

    df_all = pd.DataFrame(all_data)
    
    # ========================================================================
    # 1. TABELA CONDENSADA POR JUIZ (média e desvio sobre geradores)
    # ========================================================================
    # Agrupa por Judge, Version, Metric: média e desvio padrão das médias (entre geradores)
    df_judge_agg = df_all.groupby(['Judge', 'Version', 'Metric']).agg({
        'Mean': ['mean', 'std'],          # média das médias e desvio entre geradores
        'Std_Repetitions': 'mean'         # média do desvio entre repetições
    }).reset_index()
    
    # Achata colunas multi-index
    df_judge_agg.columns = ['Judge', 'Version', 'Metric', 'Mean_avg', 'Mean_std', 'StdRep_avg']
    
    # Pivot para ter V1 e V9 lado a lado
    pivot = df_judge_agg.pivot_table(
        index=['Judge', 'Metric'],
        columns='Version',
        values=['Mean_avg', 'Mean_std', 'StdRep_avg']
    ).reset_index()
    pivot.columns = ['Judge', 'Metric', 'V1_Mean', 'V9_Mean', 'V1_Std', 'V9_Std', 'V1_RepStd', 'V9_RepStd']
    
    # Calcula delta
    pivot['Delta'] = pivot['V9_Mean'] - pivot['V1_Mean']
    
    # Filtra apenas métricas G-Eval para a tabela principal
    pivot_geval = pivot[pivot['Metric'].isin(GEVAL_METRICS)]
    
    # Ordena por juiz e métrica
    pivot_geval = pivot_geval.sort_values(['Judge', 'Metric'])
    
    # Formata para LaTeX: "média ± desvio"
    def fmt_mean_std(row, version):
        mean = row[f'{version}_Mean']
        std = row[f'{version}_Std']
        if pd.isna(mean) or pd.isna(std):
            return "---"
        return f"{mean:.3f} $\pm$ {std:.3f}"
    
    pivot_geval['V1_Display'] = pivot_geval.apply(lambda r: fmt_mean_std(r, 'V1'), axis=1)
    pivot_geval['V9_Display'] = pivot_geval.apply(lambda r: fmt_mean_std(r, 'V9'), axis=1)
    pivot_geval['Delta_Display'] = pivot_geval['Delta'].apply(lambda x: f"{x:+.3f}" if pd.notna(x) else "---")
    
    # Cria tabela LaTeX
    latex_table = pivot_geval[['Judge', 'Metric', 'V1_Display', 'V9_Display', 'Delta_Display']].to_latex(
        index=False,
        columns=['Judge', 'Metric', 'V1_Display', 'V9_Display', 'Delta_Display'],
        caption="Análise de Robustez por Juiz (Média $\pm$ Desvio Padrão entre Geradores)",
        label="tab:robustez_por_juiz",
        escape=False,
        column_format="llccc"
    )
    
    with open(OUTPUT_DIR / "tabela_robustez_por_juiz.tex", "w", encoding="utf-8") as f:
        f.write(latex_table)
    print(f"✅ Tabela LaTeX salva em {OUTPUT_DIR / 'tabela_robustez_por_juiz.tex'}")

    # ========================================================================
    # 2. GRÁFICOS APENAS PARA BEHAVIORAL E TEMPORAL CONSISTENCY
    # ========================================================================
    sns.set_theme(style="whitegrid")
    plot_metrics = ['Behavioral_Guardrails', 'Temporal_Consistency']
    
    for metric in plot_metrics:
        # Filtra a métrica
        df_plot = df_judge_agg[df_judge_agg['Metric'] == metric].copy()
        # Pivot para ter V1 e V9 em colunas
        df_plot_pivot = df_plot.pivot_table(
            index='Judge',
            columns='Version',
            values=['Mean_avg', 'Mean_std']
        ).reset_index()
        df_plot_pivot.columns = ['Judge', 'V1_Mean', 'V9_Mean', 'V1_Std', 'V9_Std']
        
        # Ordena por V9_Mean decrescente
        df_plot_pivot = df_plot_pivot.sort_values('V9_Mean', ascending=False)
        
        # Configura gráfico
        x = np.arange(len(df_plot_pivot))
        width = 0.35
        
        fig, ax = plt.subplots(figsize=(10, 6))
        
        # Barras V1
        bars1 = ax.bar(x - width/2, df_plot_pivot['V1_Mean'], width, 
                       label='V1 (Vanilla)', color='skyblue', 
                       yerr=df_plot_pivot['V1_Std'], capsize=3, error_kw={'ecolor': 'gray'})
        
        # Barras V9
        bars2 = ax.bar(x + width/2, df_plot_pivot['V9_Mean'], width, 
                       label='V9 (Temporal)', color='salmon',
                       yerr=df_plot_pivot['V9_Std'], capsize=3, error_kw={'ecolor': 'gray'})
        
        # Linha de threshold 0.8
        ax.axhline(y=0.8, color='gray', linestyle='--', linewidth=1, label='Threshold 0.8')
        
        ax.set_xlabel('Modelo Juiz')
        ax.set_ylabel('Score Médio')
        ax.set_title(f'Comparação V1 vs V9 - {metric}')
        ax.set_xticks(x)
        ax.set_xticklabels(df_plot_pivot['Judge'], rotation=45, ha='right')
        ax.legend(loc='lower right')
        ax.set_ylim(0, 1.05)
        
        plt.tight_layout()
        plt.savefig(OUTPUT_DIR / f"grafico_condensado_{metric}.png", dpi=150)
        plt.close()
        print(f"✅ Gráfico salvo: grafico_condensado_{metric}.png")
    
    # ========================================================================
    # 3. RESUMO NUMÉRICO (para referência)
    # ========================================================================
    # Tabela com médias e desvios gerais por juiz e métrica
    summary = df_judge_agg[['Judge', 'Metric', 'Mean_avg', 'Mean_std', 'StdRep_avg']].copy()
    summary.to_csv(OUTPUT_DIR / "resumo_robustez_por_juiz.csv", index=False)
    print(f"✅ Resumo CSV salvo em {OUTPUT_DIR / 'resumo_robustez_por_juiz.csv'}")

if __name__ == "__main__":
    main()