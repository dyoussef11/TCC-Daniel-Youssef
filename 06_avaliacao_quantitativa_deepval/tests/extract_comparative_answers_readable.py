#!/usr/bin/env python3
"""
Extrai respostas V1 e V9 dos CSVs, consolida repetições idênticas,
calcula médias das métricas (incluindo Answer_Relevancy), e gera relatórios legíveis.
"""
import sys
import re
import pandas as pd
import numpy as np
from pathlib import Path

from core.paths import AVALIACAO_DATA

# Import do dataset original
try:
    from core.paths import VALIDACAO_SCRIPT, AVALIACAO_SCRIPT
    for p in [VALIDACAO_SCRIPT, AVALIACAO_SCRIPT]:
        if str(p) not in sys.path:
            sys.path.append(str(p))
    from dataset_avaliacaoV4 import TEST_SUITE
except ImportError:
    sys.path.append(str(Path(__file__).parent))
    from dataset_avaliacaoV4 import TEST_SUITE

# =============================================================================
# CONFIGURAÇÃO
# =============================================================================
PASTA_CSVS = Path(AVALIACAO_DATA / "06_avaliacao_quantitativa_deepval/data/testes_com_modelos_diferentes_sem_fallback/com_repeticaoV7")
OUTPUT_EXCEL = PASTA_CSVS / "consolidado_respostas_formatado.xlsx"
OUTPUT_MD = PASTA_CSVS / "consolidado_respostas_visao_geral.md"
OUTPUT_TXT = PASTA_CSVS / "consolidado_respostas_visao_geral.txt"

# =============================================================================
# CARREGAR METADADOS DO DATASET ORIGINAL
# =============================================================================
metadata = {}
for tc in TEST_SUITE:
    original_id = tc.get("id")
    if not original_id:
        continue
    metadata[original_id] = {
        "query": tc.get("input", ""),
        "reference_date": tc.get("reference_date", ""),
        "expected_output": tc.get("expected_output", ""),
        "test_type": tc.get("test_type", "traditional"),
        "required_patterns": tc.get("required_patterns", []),
        "forbidden_patterns": tc.get("forbidden_patterns", []),
        "description": tc.get("description", ""),
        "expected_behavior": tc.get("expected_behavior", ""),
        "min_required_matches": tc.get("min_required_matches", 1),
    }

print(f"📚 Carregados {len(metadata)} casos do dataset original.")

# =============================================================================
# PERCORRER TODOS OS CSVs
# =============================================================================
csv_files = list(PASTA_CSVS.glob("DEEPEVAL_MIXED_NATIVE_COMPARATIVE_COM_REPETICAO_*.csv"))
if not csv_files:
    print(f"⚠️ Nenhum arquivo CSV encontrado em {PASTA_CSVS}")
    sys.exit(1)

print(f"📂 Encontrados {len(csv_files)} arquivos CSV.")

all_rows = []
metric_score_cols = set()

for csv_path in csv_files:
    print(f"  Processando: {csv_path.name}...")
    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        print(f"    ❌ Erro: {e}")
        continue

    # Nome da combinação
    match = re.search(r"J_(.*?)_G_(.*?)_\d{8}_\d{4}", csv_path.name)
    combinacao = f"J={match.group(1)} | G={match.group(2)}" if match else csv_path.stem

    # Colunas obrigatórias
    base_cols = ["ID", "Original_ID", "Repetition", "Query", "Test_Type",
                 "V1_Answer", "V9_Answer", "V1_Retrieval_Context", "V9_Retrieval_Context"]
    available_base = [c for c in base_cols if c in df.columns]
    df_sub = df[available_base].copy()
    df_sub["Arquivo_origem"] = combinacao

    # Identificar todas as colunas de score (V1_*_Score, V9_*_Score)
    score_pattern = re.compile(r"^(V1|V9)_.+_Score$")
    score_cols = [c for c in df.columns if score_pattern.match(c)]
    for col in score_cols:
        metric_score_cols.add(col)
    if score_cols:
        df_sub = df_sub.join(df[score_cols])

    # Enriquecer com metadados
    enriched = []
    for _, row in df_sub.iterrows():
        orig_id = row.get("Original_ID")
        meta = metadata.get(orig_id, {})
        d = row.to_dict()
        d["Reference_Date"] = meta.get("reference_date", "")
        d["Expected_Output"] = meta.get("expected_output", "")
        d["Required_Patterns"] = "; ".join(meta.get("required_patterns", []))
        d["Forbidden_Patterns"] = "; ".join(meta.get("forbidden_patterns", []))
        d["Description"] = meta.get("description", "")
        d["Expected_Behavior"] = meta.get("expected_behavior", "")
        d["Min_Required_Matches"] = meta.get("min_required_matches", 1)

        def check_patterns(answer, patterns, min_matches=1):
            if not patterns or pd.isna(answer):
                return "N/A"
            count = sum(1 for p in patterns if p.lower() in str(answer).lower())
            return f"{count}/{len(patterns)}" if patterns else "N/A"

        d["V1_Required_Hits"] = check_patterns(d.get("V1_Answer"), meta.get("required_patterns", []), meta.get("min_required_matches", 1))
        d["V9_Required_Hits"] = check_patterns(d.get("V9_Answer"), meta.get("required_patterns", []), meta.get("min_required_matches", 1))

        enriched.append(d)

    all_rows.extend(enriched)

if not all_rows:
    print("❌ Nenhum dado processado.")
    sys.exit(1)

df_all = pd.DataFrame(all_rows)
df_all.sort_values(["Arquivo_origem", "Original_ID", "Repetition"], inplace=True)

# =============================================================================
# 1. DATAFRAME DETALHADO (todas as repetições)
# =============================================================================
df_detailed = df_all.copy()

# =============================================================================
# 2. DATAFRAME CONSOLIDADO (médias e respostas únicas)
# =============================================================================
group_cols = ["Arquivo_origem", "Original_ID"]

# Função para consolidar respostas
def consolidate_responses(series):
    unique = series.dropna().unique()
    if len(unique) == 1:
        return unique[0], False
    else:
        return series.iloc[0], True

# Agrupar
df_consolidated = df_all.groupby(group_cols).apply(lambda g: pd.Series({
    "Query": g["Query"].iloc[0],
    "Test_Type": g["Test_Type"].iloc[0],
    "Reference_Date": g["Reference_Date"].iloc[0],
    "Expected_Output": g["Expected_Output"].iloc[0],
    "Required_Patterns": g["Required_Patterns"].iloc[0],
    "Forbidden_Patterns": g["Forbidden_Patterns"].iloc[0],
    "Description": g["Description"].iloc[0],
    "Expected_Behavior": g["Expected_Behavior"].iloc[0],
    "Min_Required_Matches": g["Min_Required_Matches"].iloc[0],
    "V1_Answer_Consolidated": consolidate_responses(g["V1_Answer"])[0],
    "V1_Answer_Varies": consolidate_responses(g["V1_Answer"])[1],
    "V9_Answer_Consolidated": consolidate_responses(g["V9_Answer"])[0],
    "V9_Answer_Varies": consolidate_responses(g["V9_Answer"])[1],
    "V1_Required_Hits": g["V1_Required_Hits"].iloc[0],
    "V9_Required_Hits": g["V9_Required_Hits"].iloc[0],
    # Médias das métricas de score
    **{col: g[col].mean() for col in metric_score_cols if col in g.columns}
})).reset_index()

# Renomear colunas de média
rename_dict = {}
for col in metric_score_cols:
    if col in df_consolidated.columns:
        rename_dict[col] = col + "_Mean"
df_consolidated.rename(columns=rename_dict, inplace=True)

# Número de repetições
rep_count = df_all.groupby(group_cols).size().reset_index(name="Num_Repeticoes")
df_consolidated = df_consolidated.merge(rep_count, on=group_cols, how="left")
df_consolidated.sort_values(["Arquivo_origem", "Original_ID"], inplace=True)

# =============================================================================
# 3. EXPORTAR EXCEL
# =============================================================================
with pd.ExcelWriter(OUTPUT_EXCEL, engine="openpyxl") as writer:
    df_consolidated.to_excel(writer, sheet_name="Consolidado", index=False)
    df_detailed.to_excel(writer, sheet_name="Detalhado", index=False)

    from openpyxl.utils import get_column_letter
    from openpyxl.styles import Alignment
    for sheet_name in writer.sheets:
        ws = writer.sheets[sheet_name]
        for col in ws.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                try:
                    if cell.value:
                        max_len = max(max_len, len(str(cell.value)))
                except:
                    pass
            adjusted_width = min(max_len + 2, 50)
            ws.column_dimensions[col_letter].width = adjusted_width
            for cell in col:
                cell.alignment = Alignment(wrap_text=True, vertical="top")

print(f"✅ Excel salvo em: {OUTPUT_EXCEL}")

# =============================================================================
# 4. GERAR MARKDOWN
# =============================================================================
# Extrair nomes das métricas a partir das colunas de score
metric_names = sorted(set([re.sub(r"^(V1|V9)_(.*)_Score$", r"\2", col) for col in metric_score_cols]))

with open(OUTPUT_MD, "w", encoding="utf-8") as f:
    f.write("# 📊 Comparação Consolidada V1 vs V9\n\n")
    f.write(f"- **Total de combinações × casos:** {len(df_consolidated)}\n")
    f.write(f"- **Arquivos processados:** {len(csv_files)}\n")
    f.write(f"- **Métricas incluídas:** {', '.join(metric_names)}\n\n")

    f.write("## 🔍 Navegação rápida\n\n")
    f.write("- [Casos Tradicionais](#casos-tradicionais)\n")
    f.write("- [Casos Comportamentais](#casos-comportamentais)\n")
    f.write("- [Casos Temporais](#casos-temporais)\n\n")

    for test_type, label in [("traditional", "Casos Tradicionais"),
                             ("behavioral", "Casos Comportamentais"),
                             ("temporal", "Casos Temporais")]:
        subset = df_consolidated[df_consolidated["Test_Type"] == test_type]
        if subset.empty:
            continue
        f.write(f"## {label}\n\n")
        for _, row in subset.iterrows():
            f.write(f"### {row['Original_ID']} (combinação: {row['Arquivo_origem']})\n")
            f.write(f"- **Repetições:** {row['Num_Repeticoes']}\n")
            f.write(f"- **Data referência:** {row['Reference_Date']}\n")
            f.write(f"- **Pergunta:**\n  > {row['Query']}\n")
            if row['Expected_Output']:
                f.write(f"- **Gabarito esperado:**\n  ```\n  {row['Expected_Output']}\n  ```\n")
            if row['Required_Patterns']:
                f.write(f"- **Padrões exigidos:** `{row['Required_Patterns']}`\n")
                f.write(f"  - V1 acertos: {row['V1_Required_Hits']}\n")
                f.write(f"  - V9 acertos: {row['V9_Required_Hits']}\n")
            if row['Description']:
                f.write(f"- **Descrição:** {row['Description']}\n")

            f.write("\n**Médias das métricas:**\n\n")
            f.write("| Métrica | V1 (média) | V9 (média) | Diferença |\n")
            f.write("|---------|------------|------------|-----------|\n")
            for metric in metric_names:
                v1_key = f"V1_{metric}_Score_Mean"
                v9_key = f"V9_{metric}_Score_Mean"
                v1_val = row.get(v1_key, np.nan)
                v9_val = row.get(v9_key, np.nan)
                if pd.isna(v1_val) and pd.isna(v9_val):
                    continue
                if pd.isna(v1_val) or pd.isna(v9_val):
                    diff = np.nan
                    arrow = "⚪"
                else:
                    diff = v9_val - v1_val
                    arrow = "🟢" if diff > 0.02 else "🔴" if diff < -0.02 else "⚪"
                f.write(f"| {metric} | {v1_val:.3f} | {v9_val:.3f} | {arrow} {diff:+.3f} |\n")

            f.write("\n**Respostas consolidadas:**\n\n")
            f.write("| Versão | Resposta | Variação |\n")
            f.write("|--------|----------|----------|\n")
            v1_ans = str(row['V1_Answer_Consolidated']).replace("\n", "<br>")
            v9_ans = str(row['V9_Answer_Consolidated']).replace("\n", "<br>")
            f.write(f"| **V1** | {v1_ans} | {'Sim' if row['V1_Answer_Varies'] else 'Não'} |\n")
            f.write(f"| **V9** | {v9_ans} | {'Sim' if row['V9_Answer_Varies'] else 'Não'} |\n")
            f.write("\n---\n\n")

print(f"✅ Markdown salvo em: {OUTPUT_MD}")

# =============================================================================
# 5. GERAR TXT
# =============================================================================
with open(OUTPUT_TXT, "w", encoding="utf-8") as f:
    f.write("=" * 100 + "\n")
    f.write("COMPARAÇÃO CONSOLIDADA V1 vs V9 (MÉDIAS E RESPOSTAS ÚNICAS)\n")
    f.write("=" * 100 + "\n\n")

    for _, row in df_consolidated.iterrows():
        f.write(f"\n▶️ {row['Original_ID']}  |  Combinação: {row['Arquivo_origem']}\n")
        f.write(f"   Repetições: {row['Num_Repeticoes']}\n")
        f.write(f"   Data ref: {row['Reference_Date']}\n")
        f.write(f"   Pergunta: {row['Query']}\n")
        if row['Expected_Output']:
            f.write(f"   Gabarito: {row['Expected_Output']}\n")
        if row['Required_Patterns']:
            f.write(f"   Padrões: {row['Required_Patterns']}  |  V1: {row['V1_Required_Hits']}  |  V9: {row['V9_Required_Hits']}\n")
        f.write("   Médias das métricas:\n")
        for metric in metric_names:
            v1_key = f"V1_{metric}_Score_Mean"
            v9_key = f"V9_{metric}_Score_Mean"
            v1_val = row.get(v1_key, np.nan)
            v9_val = row.get(v9_key, np.nan)
            if not (pd.isna(v1_val) or pd.isna(v9_val)):
                diff = v9_val - v1_val
                f.write(f"      {metric}: V1={v1_val:.3f} | V9={v9_val:.3f} (Δ {diff:+.3f})\n")
            elif not pd.isna(v1_val):
                f.write(f"      {metric}: V1={v1_val:.3f} | V9= indisponível\n")
            elif not pd.isna(v9_val):
                f.write(f"      {metric}: V1= indisponível | V9={v9_val:.3f}\n")
        f.write("-" * 80 + "\n")
        f.write("V1 (consolidada):\n" + str(row['V1_Answer_Consolidated'])[:2000] + "\n")
        if row['V1_Answer_Varies']:
            f.write("   (⚠️ Houve variação entre repetições)\n")
        f.write("-" * 40 + "\n")
        f.write("V9 (consolidada):\n" + str(row['V9_Answer_Consolidated'])[:2000] + "\n")
        if row['V9_Answer_Varies']:
            f.write("   (⚠️ Houve variação entre repetições)\n")
        f.write("=" * 100 + "\n")

print(f"✅ TXT salvo em: {OUTPUT_TXT}")

print("\n🎉 Processamento concluído!")
print(f"   📊 Excel (Consolidado + Detalhado): {OUTPUT_EXCEL}")
print(f"   📝 Markdown (Consolidado):          {OUTPUT_MD}")
print(f"   📄 TXT (Consolidado):               {OUTPUT_TXT}")