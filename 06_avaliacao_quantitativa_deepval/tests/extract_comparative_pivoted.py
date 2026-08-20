#!/usr/bin/env python3
"""
Extrai respostas V1 e V9 dos CSVs, pivoteia por combinação (juiz|gerador),
consolida repetições (médias, resposta única ou flag de variação),
e gera relatórios com uma linha por caso.
Inclui Answer Relevancy e todas as métricas disponíveis.
"""
import sys
import re
import pandas as pd
import numpy as np
from pathlib import Path
from collections import defaultdict

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
OUTPUT_EXCEL = PASTA_CSVS / "consolidado_pivotado.xlsx"
OUTPUT_MD = PASTA_CSVS / "consolidado_pivotado.md"
OUTPUT_TXT = PASTA_CSVS / "consolidado_pivotado.txt"

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
# PERCORRER TODOS OS CSVs E EXTRAIR DADOS POR COMBINAÇÃO
# =============================================================================
csv_files = list(PASTA_CSVS.glob("DEEPEVAL_MIXED_NATIVE_COMPARATIVE_COM_REPETICAO_*.csv"))
if not csv_files:
    print(f"⚠️ Nenhum arquivo CSV encontrado em {PASTA_CSVS}")
    sys.exit(1)

print(f"📂 Encontrados {len(csv_files)} arquivos CSV.")

# Estrutura: dict[original_id] = {
#     'fixed': {query, ref_date, expected, ...},
#     'combinations': {
#         'comb_id': {
#             'V1_Answer': str, 'V1_Answer_Varies': bool,
#             'V9_Answer': str, 'V9_Answer_Varies': bool,
#             'V1_Required_Hits': str, 'V9_Required_Hits': str,
#             'metrics': {'V1_Faithfulness_Mean': float, 'V9_Faithfulness_Mean': float, ...},
#             'num_repetitions': int
#         }
#     }
# }
data_store = defaultdict(lambda: {'fixed': {}, 'combinations': {}})

# Coleção de todas as métricas encontradas (nomes base, ex: 'Faithfulness')
all_metric_names = set()

for csv_path in csv_files:
    print(f"  Processando: {csv_path.name}...")
    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        print(f"    ❌ Erro: {e}")
        continue

    # Nome da combinação
    match = re.search(r"J_(.*?)_G_(.*?)_\d{8}_\d{4}", csv_path.name)
    if match:
        comb_id = f"J_{match.group(1)}_G_{match.group(2)}"
        comb_label = f"{match.group(1)} | {match.group(2)}"
    else:
        comb_id = csv_path.stem
        comb_label = comb_id

    # Colunas obrigatórias
    required_cols = ["Original_ID", "Repetition", "V1_Answer", "V9_Answer"]
    if not all(c in df.columns for c in required_cols):
        print(f"    ⚠️ CSV sem colunas necessárias, pulando.")
        continue

    # Identificar colunas de score (V1_*_Score, V9_*_Score)
    score_cols = [c for c in df.columns if re.match(r"^(V1|V9)_.+_Score$", c)]
    # Extrair nomes das métricas (ex: Faithfulness, Answer_Relevancy, ...)
    metric_names = set()
    for col in score_cols:
        # Ex: V1_Faithfulness_Score -> Faithfulness
        parts = col.split('_')
        if len(parts) >= 3:
            metric = '_'.join(parts[1:-1])  # junta partes do meio
            metric_names.add(metric)
    all_metric_names.update(metric_names)

    # Agrupar por Original_ID e consolidar repetições
    grouped = df.groupby("Original_ID")
    for orig_id, group in grouped:
        if orig_id not in metadata:
            continue  # ignorar casos que não estão no dataset original

        # Inicializar entrada se não existir
        if not data_store[orig_id]['fixed']:
            meta = metadata[orig_id]
            data_store[orig_id]['fixed'] = {
                "Query": meta.get("query", ""),
                "Reference_Date": meta.get("reference_date", ""),
                "Expected_Output": meta.get("expected_output", ""),
                "Test_Type": meta.get("test_type", "traditional"),
                "Required_Patterns": "; ".join(meta.get("required_patterns", [])),
                "Forbidden_Patterns": "; ".join(meta.get("forbidden_patterns", [])),
                "Description": meta.get("description", ""),
                "Expected_Behavior": meta.get("expected_behavior", ""),
                "Min_Required_Matches": meta.get("min_required_matches", 1),
            }

        # Processar respostas V1 e V9 (consolidar se idênticas)
        v1_answers = group["V1_Answer"].dropna()
        v9_answers = group["V9_Answer"].dropna()
        v1_unique = v1_answers.unique()
        v9_unique = v9_answers.unique()
        v1_consolidated = v1_unique[0] if len(v1_unique) > 0 else ""
        v9_consolidated = v9_unique[0] if len(v9_unique) > 0 else ""
        v1_varies = len(v1_unique) > 1
        v9_varies = len(v9_unique) > 1

        # Calcular médias das métricas
        metrics_means = {}
        for metric in metric_names:
            v1_score_col = f"V1_{metric}_Score"
            v9_score_col = f"V9_{metric}_Score"
            if v1_score_col in group.columns:
                metrics_means[f"V1_{metric}_Mean"] = group[v1_score_col].mean()
            else:
                metrics_means[f"V1_{metric}_Mean"] = np.nan
            if v9_score_col in group.columns:
                metrics_means[f"V9_{metric}_Mean"] = group[v9_score_col].mean()
            else:
                metrics_means[f"V9_{metric}_Mean"] = np.nan

        # Verificar padrões exigidos (usando a primeira resposta ou a consolidada)
        def check_patterns(answer, patterns, min_matches=1):
            if not patterns or pd.isna(answer):
                return "N/A"
            count = sum(1 for p in patterns if p.lower() in str(answer).lower())
            return f"{count}/{len(patterns)}" if patterns else "N/A"

        meta = metadata[orig_id]
        v1_hits = check_patterns(v1_consolidated, meta.get("required_patterns", []), meta.get("min_required_matches", 1))
        v9_hits = check_patterns(v9_consolidated, meta.get("required_patterns", []), meta.get("min_required_matches", 1))

        # Armazenar dados da combinação
        data_store[orig_id]['combinations'][comb_id] = {
            "comb_label": comb_label,
            "V1_Answer": v1_consolidated,
            "V1_Answer_Varies": v1_varies,
            "V9_Answer": v9_consolidated,
            "V9_Answer_Varies": v9_varies,
            "V1_Required_Hits": v1_hits,
            "V9_Required_Hits": v9_hits,
            "num_repetitions": len(group),
            **metrics_means
        }

print(f"✅ Processados {len(data_store)} casos únicos com {len(all_metric_names)} métricas.")

# =============================================================================
# CONSTRUIR DATAFRAME PIVOTADO
# =============================================================================
# Lista de colunas fixas
fixed_cols = ["Original_ID", "Test_Type", "Query", "Reference_Date",
              "Expected_Output", "Required_Patterns", "Forbidden_Patterns",
              "Description", "Expected_Behavior"]

# Coletar todas as combinações
all_combs = set()
for entry in data_store.values():
    all_combs.update(entry['combinations'].keys())
all_combs = sorted(all_combs)

# Construir lista de linhas
rows = []
for orig_id, entry in data_store.items():
    fixed = entry['fixed']
    row = {
        "Original_ID": orig_id,
        "Test_Type": fixed.get("Test_Type", ""),
        "Query": fixed.get("Query", ""),
        "Reference_Date": fixed.get("Reference_Date", ""),
        "Expected_Output": fixed.get("Expected_Output", ""),
        "Required_Patterns": fixed.get("Required_Patterns", ""),
        "Forbidden_Patterns": fixed.get("Forbidden_Patterns", ""),
        "Description": fixed.get("Description", ""),
        "Expected_Behavior": fixed.get("Expected_Behavior", ""),
    }
    # Para cada combinação, adicionar colunas
    for comb in all_combs:
        if comb in entry['combinations']:
            cdata = entry['combinations'][comb]
            # Respostas e flags
            row[f"{comb}_V1_Answer"] = cdata["V1_Answer"]
            row[f"{comb}_V1_Answer_Varies"] = cdata["V1_Answer_Varies"]
            row[f"{comb}_V9_Answer"] = cdata["V9_Answer"]
            row[f"{comb}_V9_Answer_Varies"] = cdata["V9_Answer_Varies"]
            row[f"{comb}_V1_Required_Hits"] = cdata["V1_Required_Hits"]
            row[f"{comb}_V9_Required_Hits"] = cdata["V9_Required_Hits"]
            row[f"{comb}_num_repetitions"] = cdata["num_repetitions"]
            # Métricas
            for metric in all_metric_names:
                v1_mean = cdata.get(f"V1_{metric}_Mean", np.nan)
                v9_mean = cdata.get(f"V9_{metric}_Mean", np.nan)
                row[f"{comb}_V1_{metric}_Mean"] = v1_mean
                row[f"{comb}_V9_{metric}_Mean"] = v9_mean
        else:
            # Sem dados para essa combinação (preencher com NaN)
            row[f"{comb}_V1_Answer"] = ""
            row[f"{comb}_V1_Answer_Varies"] = False
            row[f"{comb}_V9_Answer"] = ""
            row[f"{comb}_V9_Answer_Varies"] = False
            row[f"{comb}_V1_Required_Hits"] = "N/A"
            row[f"{comb}_V9_Required_Hits"] = "N/A"
            row[f"{comb}_num_repetitions"] = 0
            for metric in all_metric_names:
                row[f"{comb}_V1_{metric}_Mean"] = np.nan
                row[f"{comb}_V9_{metric}_Mean"] = np.nan
    rows.append(row)

df_pivot = pd.DataFrame(rows)
# Ordenar por tipo e ID
df_pivot.sort_values(["Test_Type", "Original_ID"], inplace=True)

# =============================================================================
# EXPORTAR PARA EXCEL
# =============================================================================
with pd.ExcelWriter(OUTPUT_EXCEL, engine="openpyxl") as writer:
    df_pivot.to_excel(writer, sheet_name="Pivot", index=False)

    # Formatação
    from openpyxl.utils import get_column_letter
    from openpyxl.styles import Alignment
    ws = writer.sheets["Pivot"]
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            try:
                if cell.value:
                    max_len = max(max_len, len(str(cell.value)))
            except:
                pass
        adjusted_width = min(max_len + 2, 40)
        ws.column_dimensions[col_letter].width = adjusted_width
        for cell in col:
            cell.alignment = Alignment(wrap_text=True, vertical="top")

print(f"✅ Excel salvo em: {OUTPUT_EXCEL}")

# =============================================================================
# GERAR MARKDOWN (AGRUPADO POR CASO)
# =============================================================================
with open(OUTPUT_MD, "w", encoding="utf-8") as f:
    f.write("# 📊 Comparação Pivotada V1 vs V9 por Combinação\n\n")
    f.write(f"- **Total de casos:** {len(df_pivot)}\n")
    f.write(f"- **Combinações (juiz|gerador):** {', '.join(all_combs)}\n")
    f.write(f"- **Métricas:** {', '.join(sorted(all_metric_names))}\n\n")

    for _, row in df_pivot.iterrows():
        f.write(f"## {row['Original_ID']}  |  {row['Test_Type']}\n\n")
        f.write(f"- **Pergunta:** {row['Query']}\n")
        if row['Reference_Date']:
            f.write(f"- **Data referência:** {row['Reference_Date']}\n")
        if row['Expected_Output']:
            f.write(f"- **Gabarito:**\n  ```\n  {row['Expected_Output']}\n  ```\n")
        if row['Required_Patterns']:
            f.write(f"- **Padrões exigidos:** `{row['Required_Patterns']}`\n")
        if row['Description']:
            f.write(f"- **Descrição:** {row['Description']}\n")
        f.write("\n### Respostas por Combinação\n\n")
        f.write("| Combinação | V1 Answer | V9 Answer | V1 Variação | V9 Variação | V1 Hits | V9 Hits | Repetições |\n")
        f.write("|------------|-----------|-----------|-------------|-------------|---------|---------|------------|\n")
        for comb in all_combs:
            v1_ans = str(row.get(f"{comb}_V1_Answer", ""))[:100] + "..." if len(str(row.get(f"{comb}_V1_Answer", ""))) > 100 else str(row.get(f"{comb}_V1_Answer", ""))
            v9_ans = str(row.get(f"{comb}_V9_Answer", ""))[:100] + "..." if len(str(row.get(f"{comb}_V9_Answer", ""))) > 100 else str(row.get(f"{comb}_V9_Answer", ""))
            v1_var = "Sim" if row.get(f"{comb}_V1_Answer_Varies", False) else "Não"
            v9_var = "Sim" if row.get(f"{comb}_V9_Answer_Varies", False) else "Não"
            v1_hits = row.get(f"{comb}_V1_Required_Hits", "N/A")
            v9_hits = row.get(f"{comb}_V9_Required_Hits", "N/A")
            reps = row.get(f"{comb}_num_repetitions", 0)
            f.write(f"| {comb} | {v1_ans} | {v9_ans} | {v1_var} | {v9_var} | {v1_hits} | {v9_hits} | {reps} |\n")
        f.write("\n### Médias das Métricas por Combinação\n\n")
        f.write("| Combinação | " + " | ".join([f"V1_{m}_Mean" for m in sorted(all_metric_names)]) + " | " + " | ".join([f"V9_{m}_Mean" for m in sorted(all_metric_names)]) + " |\n")
        f.write("|------------|" + "|".join(["---"] * (2 * len(all_metric_names) + 1)) + "|\n")
        for comb in all_combs:
            v1_means = [f"{row.get(f'{comb}_V1_{m}_Mean', np.nan):.3f}" if not pd.isna(row.get(f'{comb}_V1_{m}_Mean', np.nan)) else "—" for m in sorted(all_metric_names)]
            v9_means = [f"{row.get(f'{comb}_V9_{m}_Mean', np.nan):.3f}" if not pd.isna(row.get(f'{comb}_V9_{m}_Mean', np.nan)) else "—" for m in sorted(all_metric_names)]
            f.write(f"| {comb} | " + " | ".join(v1_means) + " | " + " | ".join(v9_means) + " |\n")
        f.write("\n---\n\n")

print(f"✅ Markdown salvo em: {OUTPUT_MD}")

# =============================================================================
# GERAR TXT (AGRUPADO POR CASO)
# =============================================================================
with open(OUTPUT_TXT, "w", encoding="utf-8") as f:
    f.write("=" * 120 + "\n")
    f.write("RELATÓRIO PIVOTADO POR CASO – TODAS AS COMBINAÇÕES\n")
    f.write("=" * 120 + "\n\n")

    for _, row in df_pivot.iterrows():
        f.write(f"\n▶️ {row['Original_ID']}  |  {row['Test_Type']}\n")
        f.write(f"   Pergunta: {row['Query']}\n")
        if row['Reference_Date']:
            f.write(f"   Data referência: {row['Reference_Date']}\n")
        if row['Expected_Output']:
            f.write(f"   Gabarito: {row['Expected_Output']}\n")
        if row['Required_Patterns']:
            f.write(f"   Padrões exigidos: {row['Required_Patterns']}\n")
        f.write("-" * 120 + "\n")
        f.write("Combinação | V1 Resposta (resumo) | V9 Resposta (resumo) | V1 Hits | V9 Hits | Reps\n")
        f.write("-" * 120 + "\n")
        for comb in all_combs:
            v1_ans = str(row.get(f"{comb}_V1_Answer", ""))[:80] + "..." if len(str(row.get(f"{comb}_V1_Answer", ""))) > 80 else str(row.get(f"{comb}_V1_Answer", ""))
            v9_ans = str(row.get(f"{comb}_V9_Answer", ""))[:80] + "..." if len(str(row.get(f"{comb}_V9_Answer", ""))) > 80 else str(row.get(f"{comb}_V9_Answer", ""))
            v1_hits = row.get(f"{comb}_V1_Required_Hits", "N/A")
            v9_hits = row.get(f"{comb}_V9_Required_Hits", "N/A")
            reps = row.get(f"{comb}_num_repetitions", 0)
            f.write(f"{comb:30} | {v1_ans:20} | {v9_ans:20} | {v1_hits:5} | {v9_hits:5} | {reps:3}\n")
        f.write("\nMédias das Métricas:\n")
        f.write("Combinação | " + " | ".join([f"V1_{m}" for m in sorted(all_metric_names)]) + " | " + " | ".join([f"V9_{m}" for m in sorted(all_metric_names)]) + "\n")
        f.write("-" * 120 + "\n")
        for comb in all_combs:
            v1_means = [f"{row.get(f'{comb}_V1_{m}_Mean', np.nan):.3f}" if not pd.isna(row.get(f'{comb}_V1_{m}_Mean', np.nan)) else "—" for m in sorted(all_metric_names)]
            v9_means = [f"{row.get(f'{comb}_V9_{m}_Mean', np.nan):.3f}" if not pd.isna(row.get(f'{comb}_V9_{m}_Mean', np.nan)) else "—" for m in sorted(all_metric_names)]
            f.write(f"{comb:30} | " + " | ".join(v1_means) + " | " + " | ".join(v9_means) + "\n")
        f.write("\n" + "=" * 120 + "\n")

print(f"✅ TXT salvo em: {OUTPUT_TXT}")

print("\n🎉 Processamento concluído! Estrutura pivotada gerada:")
print(f"   📊 Excel: {OUTPUT_EXCEL}")
print(f"   📝 Markdown: {OUTPUT_MD}")
print(f"   📄 TXT: {OUTPUT_TXT}")