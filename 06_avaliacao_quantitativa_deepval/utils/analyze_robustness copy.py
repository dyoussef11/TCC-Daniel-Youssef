#!/usr/bin/env python3
"""
Análise de Robustez (versão compacta para TCC)
- Ignora combinações com N==0 (dados ausentes)
- Gera heatmap de deltas (V9 - V1) para métricas G-Eval
- Produz tabela LaTeX resumida (apenas combinações com dados)
- Inclui resumo estatístico global
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

# Tipo de teste para cada métrica
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
    """Extrai juiz e gerador do nome do arquivo."""
    pattern = r"J_(.+?)_G_(.+?)_\d{8}_\d{4}\.csv$"
    match = re.search(pattern, filename)
    if match:
        judge = match.group(1).replace("_", ":")
        generator = match.group(2).replace("_", ":")
        return judge, generator
    return None, None

def load_csv_safe(filepath: Path) -> pd.DataFrame:
    """Carrega CSV, retorna DataFrame vazio se falhar."""
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
    Calcula estatísticas para uma métrica/versão.
    Retorna dicionário com mean, std_mean, high_var_pct, count.
    Se não houver dados suficientes (N < 2), retorna NaN.
    """
    score_col = f"{version}_{metric}_Score"
    if score_col not in df.columns:
        return {"mean": np.nan, "std_mean": np.nan, "high_var_pct": np.nan, "count": 0}
    
    # Remove linhas com NaN
    df_clean = df[[score_col, "Original_ID"]].dropna()
    if df_clean.empty:
        return {"mean": np.nan, "std_mean": np.nan, "high_var_pct": np.nan, "count": 0}
    
    # Contagem total de casos (não repetições)
    n_cases = df_clean["Original_ID"].nunique()
    if n_cases < 2:  # Precisamos de pelo menos 2 casos para calcular std
        return {"mean": df_clean[score_col].mean(), "std_mean": np.nan, "high_var_pct": np.nan, "count": n_cases}
    
    # Desvio padrão por Original_ID (repetições)
    std_per_case = df_clean.groupby("Original_ID")[score_col].std()
    
    # Remove NaNs do std (casos com apenas uma repetição)
    std_per_case = std_per_case.dropna()
    if std_per_case.empty:
        return {"mean": df_clean[score_col].mean(), "std_mean": np.nan, "high_var_pct": np.nan, "count": n_cases}
    
    mean_score = df_clean[score_col].mean()
    std_mean = std_per_case.mean()
    high_var_count = (std_per_case > 0.15).sum()
    high_var_pct = high_var_count / len(std_per_case) if len(std_per_case) > 0 else np.nan
    
    return {
        "mean": mean_score,
        "std_mean": std_mean,
        "high_var_pct": high_var_pct,
        "count": n_cases
    }

# ============================================================================
# PROCESSAMENTO PRINCIPAL
# ============================================================================

def main():
    # Lista todos os CSVs
    csv_files = list(PASTA_CSVS.glob("DEEPEVAL_MIXED_NATIVE_COMPARATIVE_COM_REPETICAO_*.csv"))
    if not csv_files:
        print(f"Nenhum CSV encontrado em {PASTA_CSVS}")
        return
    
    print(f"Encontrados {len(csv_files)} arquivos CSV.")
    
    results = []
    skipped_files = []
    
    for filepath in csv_files:
        judge, generator = parse_combination_from_filename(filepath.name)
        if judge is None or generator is None:
            skipped_files.append(filepath.name)
            continue
        
        print(f"Processando: {judge} x {generator}")
        
        df = load_csv_safe(filepath)
        if df.empty:
            print(f"  -> Arquivo vazio ou com erro. Pulando.")
            skipped_files.append(filepath.name)
            continue
        
        # Para cada métrica, calcula estatísticas para V1 e V9
        for metric in METRICS:
            for version in ["V1", "V9"]:
                stats = compute_robustness_stats(df, metric, version)
                # Só adiciona se count > 0
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
        print("Nenhum dado válido foi extraído. Verifique os CSVs.")
        return
    
    df_results = pd.DataFrame(results)
    
    # Salva consolidado completo
    csv_out = OUTPUT_DIR / "consolidado_robustez.csv"
    df_results.to_csv(csv_out, index=False)
    print(f"\n✅ Consolidado salvo em {csv_out}")
    
    # ========================================================================
    # TABELA LATEX RESUMIDA (apenas G-Eval com N > 0)
    # ========================================================================
    geval_metrics = [m for m in METRICS if m in METRIC_TYPE and METRIC_TYPE[m] in ["behavioral", "temporal"]]
    
    # Filtra apenas métricas G-Eval e com N > 0 (já garantido)
    df_geval = df_results[df_results['Metric'].isin(geval_metrics)]
    
    # Pivot para ter V1 e V9 em colunas separadas
    pivot = df_geval.pivot_table(
        index=["Judge", "Generator", "Metric"],
        columns="Version",
        values=["Mean", "Std_Mean"]
    ).reset_index()
    
    # Achata colunas
    pivot.columns = ['Judge', 'Generator', 'Metric', 'V1_Mean', 'V9_Mean', 'V1_Std', 'V9_Std']
    
    # Remove linhas com NaN em V1_Mean ou V9_Mean (dados faltantes)
    pivot = pivot.dropna(subset=['V1_Mean', 'V9_Mean'])
    
    # Calcula delta
    pivot['Delta'] = pivot['V9_Mean'] - pivot['V1_Mean']
    
    # Ordena por métrica e depois por delta decrescente (destacar ganhos)
    pivot = pivot.sort_values(['Metric', 'Delta'], ascending=[True, False])
    
    # Formata para LaTeX (apenas 3 casas decimais)
    def fmt(x):
        return f"{x:.3f}" if pd.notna(x) else "---"
    
    latex_df = pivot.copy()
    latex_df['V1_Mean'] = latex_df['V1_Mean'].apply(fmt)
    latex_df['V9_Mean'] = latex_df['V9_Mean'].apply(fmt)
    latex_df['V1_Std'] = latex_df['V1_Std'].apply(fmt)
    latex_df['V9_Std'] = latex_df['V9_Std'].apply(fmt)
    latex_df['Delta'] = latex_df['Delta'].apply(lambda x: f"{x:+.3f}" if pd.notna(x) else "---")
    
    # Gera tabela LaTeX (usando longtable se houver muitas linhas)
    use_longtable = len(latex_df) > 20
    latex_table = latex_df.to_latex(
        index=False,
        columns=['Judge', 'Generator', 'Metric', 'V1_Mean', 'V1_Std', 'V9_Mean', 'V9_Std', 'Delta'],
        caption="Análise de Robustez para Métricas G-Eval (Média ± Desvio Padrão entre Repetições)",
        label="tab:robustez_geval",
        longtable=use_longtable,
        escape=False
    )
    
    with open(OUTPUT_DIR / "tabela_robustez_geval.tex", "w", encoding="utf-8") as f:
        f.write(latex_table)
    print(f"✅ Tabela LaTeX (G-Eval) salva em {OUTPUT_DIR / 'tabela_robustez_geval.tex'}")
    
    # ========================================================================
    # HEATMAP DE DELTAS (V9 - V1) para cada métrica G-Eval
    # ========================================================================
    sns.set_theme(style="whitegrid")
    
    # Para cada métrica G-Eval, criar um heatmap
    for metric in geval_metrics:
        df_metric = pivot[pivot['Metric'] == metric]
        if df_metric.empty:
            continue
        
        # Pivot para ter juiz nas linhas, gerador nas colunas, delta como valor
        heatmap_data = df_metric.pivot_table(
            index='Judge', 
            columns='Generator', 
            values='Delta'
        )
        
        # Se só tiver uma linha ou coluna, não faz heatmap (usar barplot)
        if heatmap_data.shape[0] < 2 or heatmap_data.shape[1] < 2:
            print(f"  -> Métrica {metric} tem poucas combinações para heatmap. Pulando.")
            continue
        
        # Remove linhas/colunas com todos NaN
        heatmap_data = heatmap_data.dropna(how='all').dropna(axis=1, how='all')
        
        if heatmap_data.empty:
            continue
        
        # Cria figura
        fig, ax = plt.subplots(figsize=(10, 8))
        
        # Heatmap com divergência (centro em 0)
        sns.heatmap(
            heatmap_data, 
            annot=True, 
            fmt='.3f', 
            cmap='RdBu_r', 
            center=0,
            linewidths=0.5,
            cbar_kws={'label': 'Δ (V9 - V1)'},
            ax=ax
        )
        
        ax.set_title(f'Delta (V9 - V1) - {metric}')
        ax.set_xlabel('Gerador')
        ax.set_ylabel('Juiz')
        
        plt.tight_layout()
        plt.savefig(OUTPUT_DIR / f"heatmap_{metric}.png", dpi=150)
        plt.close()
    
    print(f"✅ Heatmaps salvos em {OUTPUT_DIR}")
    
    # ========================================================================
    # RESULTADO GLOBAL: MÉDIAS DE ROBUSTEZ (STD médio) por métrica
    # ========================================================================
    # Filtra apenas métricas G-Eval e versão V9 (mais relevante)
    df_robust = df_results[
        (df_results['Metric'].isin(geval_metrics)) & 
        (df_results['Version'] == 'V9') &
        (df_results['N'] > 1)  # precisa de pelo menos 2 casos para std
    ]
    
    if not df_robust.empty:
        summary = df_robust.groupby('Metric')['Std_Mean'].agg(['mean', 'std', 'count']).reset_index()
        summary.columns = ['Metric', 'Std_Mean_Avg', 'Std_Mean_Std', 'Num_Combinations']
        
        # Salva resumo
        summary_csv = OUTPUT_DIR / "resumo_robustez_geval.csv"
        summary.to_csv(summary_csv, index=False)
        print(f"\n✅ Resumo de Robustez (G-Eval V9) salvo em {summary_csv}")
        
        # Exibe
        print("\n📊 Resumo de Robustez (G-Eval, V9):")
        print(summary.to_string(index=False))
    
    # ========================================================================
    # RELATÓRIO DE ARQUIVOS IGNORADOS
    # ========================================================================
    if skipped_files:
        print(f"\n⚠️ Arquivos ignorados (vazios ou nomes inválidos): {len(skipped_files)}")
        for fname in skipped_files:
            print(f"  - {fname}")

if __name__ == "__main__":
    main()