import pandas as pd
import numpy as np
from scipy import stats
from pathlib import Path
import argparse

def calcular_significancia(csv_path: Path, alpha: float = 0.05):
    df = pd.read_csv(csv_path)
    
    # Lista de métricas que você quer comparar (apenas as que existem no CSV)
    metricas_candidatas = [
        'Faithfulness',
        'Answer_Relevancy',
        'Contextual_Relevancy',
        'Contextual_Precision',
        'Contextual_Recall',
        'Behavioral_Guardrails'
    ]
    
    # Filtra métricas que realmente têm colunas V1 e V9 no CSV
    metricas = []
    for m in metricas_candidatas:
        col_v1 = f'V1_{m}_Score'
        col_v9 = f'V9_{m}_Score'
        if col_v1 in df.columns and col_v9 in df.columns:
            metricas.append(m)
    
    if not metricas:
        print("⚠️ Nenhuma métrica encontrada no CSV para análise.")
        return None
    
    resultados = []
    
    for metrica in metricas:
        col_v1 = f'V1_{metrica}_Score'
        col_v9 = f'V9_{metrica}_Score'
        
        # Remove linhas com NaN
        dados = df[[col_v1, col_v9]].dropna()
        if len(dados) < 3:
            print(f"⚠️ Poucos dados para {metrica} (n={len(dados)}), ignorando.")
            continue
        
        v1 = dados[col_v1]
        v9 = dados[col_v9]
        diff = v9 - v1
        
        # Estatísticas descritivas
        media_v1 = v1.mean()
        media_v9 = v9.mean()
        media_diff = diff.mean()
        std_diff = diff.std(ddof=1)
        
        # Teste t pareado
        t_stat, p_t = stats.ttest_rel(v9, v1)
        
        # Teste de Wilcoxon (mais robusto para escores)
        try:
            w_stat, p_w = stats.wilcoxon(v9, v1, alternative='two-sided')
        except Exception as e:
            print(f"⚠️ Wilcoxon falhou para {metrica}: {e}")
            w_stat, p_w = np.nan, np.nan
        
        # Cohen's d pareado
        cohen_d = media_diff / std_diff if std_diff != 0 else 0.0
        
        n = len(dados)
        
        resultados.append({
            'Métrica': metrica,
            'N': n,
            'Média V1': media_v1,
            'Média V9': media_v9,
            'Diferença (V9 - V1)': media_diff,
            'DP das diferenças': std_diff,
            't-statistic': t_stat,
            'p-valor (t-test)': p_t,
            'Wilcoxon W': w_stat,
            'p-valor (Wilcoxon)': p_w,
            "Cohen's d": cohen_d
        })
    
    if not resultados:
        print("⚠️ Nenhum resultado calculado (dados insuficientes).")
        return None
    
    df_resultados = pd.DataFrame(resultados)
    
    # Correção de Bonferroni
    n_testes = len(df_resultados)
    alpha_bonf = alpha / n_testes if n_testes > 0 else alpha
    
    # Determina significância baseada no Wilcoxon (se disponível)
    # Se p-valor for NaN, considera não significativo
    p_col = 'p-valor (Wilcoxon)'
    df_resultados['Significante (p < 0.05)'] = df_resultados[p_col].apply(
        lambda p: p < alpha if pd.notna(p) else False
    )
    df_resultados['Significante (Bonferroni)'] = df_resultados[p_col].apply(
        lambda p: p < alpha_bonf if pd.notna(p) else False
    )
    
    # Formatação para exibição
    pd.set_option('display.float_format', '{:.4f}'.format)
    print("\n" + "="*80)
    print(f"ANÁLISE DE SIGNIFICÂNCIA ESTATÍSTICA (V1 vs V9)")
    print(f"Arquivo: {csv_path.name}")
    print(f"α original = {alpha}, α Bonferroni = {alpha_bonf:.5f}")
    print("="*80)
    print(df_resultados.to_string(index=False))
    
    # Salva resultados em CSV
    output_path = csv_path.parent / f"significancia_{csv_path.stem}.csv"
    df_resultados.to_csv(output_path, index=False)
    print(f"\n✅ Resultados salvos em: {output_path}")
    
    return df_resultados

def analise_por_tipo(csv_path: Path, alpha: float = 0.05):
    df = pd.read_csv(csv_path)
    if 'Test_Type' not in df.columns:
        print("⚠️ Coluna 'Test_Type' não encontrada. Analisando todo o conjunto.")
        calcular_significancia(csv_path, alpha)
        return
    
    tipos = df['Test_Type'].unique()
    for tipo in tipos:
        print(f"\n{'='*60}")
        print(f"SUBCONJUNTO: {tipo.upper()}")
        df_tipo = df[df['Test_Type'] == tipo]
        if df_tipo.empty:
            print(f"⚠️ Nenhum dado para o tipo {tipo}")
            continue
        temp_path = csv_path.parent / f"temp_{tipo}_{csv_path.stem}.csv"
        df_tipo.to_csv(temp_path, index=False)
        calcular_significancia(temp_path, alpha)
        temp_path.unlink()  # remove temporário

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Análise estatística comparativa V1 vs V9")
    parser.add_argument("csv_file", type=Path, help="Caminho para o CSV gerado pelo DeepEval")
    parser.add_argument("--alpha", type=float, default=0.05, help="Nível de significância (padrão 0.05)")
    parser.add_argument("--by_type", action="store_true", help="Analisar separadamente por tipo de teste")
    args = parser.parse_args()
    
    if not args.csv_file.exists():
        print(f"❌ Arquivo não encontrado: {args.csv_file}")
        exit(1)
    
    if args.by_type:
        analise_por_tipo(args.csv_file, args.alpha)
    else:
        calcular_significancia(args.csv_file, args.alpha)