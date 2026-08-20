import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from collections import Counter
import os

# ============================================================================
# CONFIGURAÇÃO
# ============================================================================
OUTPUT_DIR = r"04_vetorizacao/tests/analise_temporal_vs_semantica"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ============================================================================
# CARREGAR DADOS
# ============================================================================
df_trad = pd.read_csv(r"04_vetorizacao/tests/resultados_sematicos/resultados_busca_20260701_185834.csv")
df_temp = pd.read_csv(r"04_vetorizacao/tests/resultados_semanticos_temporais/resultados_busca_temporal_20260817_162450.csv")

# Filtra apenas os ranks 1 a 5 para comparação justa
df_trad = df_trad[df_trad['rank'].isin([1,2,3,4,5])]
df_temp = df_temp[df_temp['rank'].isin([1,2,3,4,5])]

# Cria listas de documentos por pergunta
trad_dict = df_trad.groupby('pergunta_id').apply(
    lambda g: {'docs': g.sort_values('rank')['doc_id'].tolist(),
               'dists': g.sort_values('rank')['distancia'].tolist(),
               'dates': g.sort_values('rank')['data_original'].tolist()}
).to_dict()

temp_dict = df_temp.groupby('pergunta_id').apply(
    lambda g: {'docs': g.sort_values('rank')['doc_id'].tolist(),
               'dists': g.sort_values('rank')['distancia_original'].tolist(),
               'gaps': g.sort_values('rank')['temporal_gap_years'].tolist(),
               'dates': g.sort_values('rank')['data_post_original'].tolist()}
).to_dict()

# ============================================================================
# MÉTRICAS POR PERGUNTA
# ============================================================================
resultados = []

for pid in trad_dict.keys():
    if pid not in temp_dict:
        continue
    
    trad = trad_dict[pid]
    temp = temp_dict[pid]
    
    # Top 1 mudou?
    top1_changed = trad['docs'][0] != temp['docs'][0]
    
    # Overlap no Top 5
    overlap = len(set(trad['docs']) & set(temp['docs']))
    
    # Distância semântica média do Top 5
    avg_dist_trad = np.mean(trad['dists'])
    avg_dist_temp = np.mean(temp['dists'])
    dist_change = avg_dist_temp - avg_dist_trad
    
    # Gap temporal médio - cálculo correto para a versão tradicional
    gaps_trad = []
    for date_str in trad['dates']:
        try:
            dt = pd.to_datetime(date_str)
            gap = (pd.to_datetime('2026-06-23') - dt).days / 365.25
            gaps_trad.append(gap)
        except:
            gaps_trad.append(0)
    avg_gap_trad = np.mean(gaps_trad) if gaps_trad else 0
    
    # Gap temporal médio da versão temporal
    avg_gap_temp = np.mean(temp['gaps']) if temp['gaps'] else 0
    
    # Classificação do impacto
    if avg_gap_temp < avg_gap_trad - 0.5 and overlap >= 3:
        impacto = "MELHOROU (recentes, mesmo contexto)"
    elif avg_gap_temp < avg_gap_trad - 0.5 and overlap < 3:
        impacto = "PREJUDICOU (recentes, mas perdeu contexto)"
    elif abs(avg_gap_temp - avg_gap_trad) <= 0.5:
        impacto = "NEUTRO (sem mudança significativa)"
    else:
        impacto = "INDEFINIDO"
    
    resultados.append({
        "pergunta_id": pid,
        "top1_mudou": top1_changed,
        "overlap_top5": overlap,
        "dist_media_trad": round(avg_dist_trad, 2),
        "dist_media_temp": round(avg_dist_temp, 2),
        "delta_distancia": round(dist_change, 2),
        "gap_medio_trad": round(avg_gap_trad, 2),
        "gap_medio_temp": round(avg_gap_temp, 2),
        "delta_gap": round(avg_gap_temp - avg_gap_trad, 2),
        "impacto": impacto
    })

df_res = pd.DataFrame(resultados)

# ============================================================================
# RELATÓRIO ESTATÍSTICO
# ============================================================================
print("="*80)
print("RELATÓRIO DE IMPACTO DA PENALIDADE TEMPORAL")
print("="*80)
print(f"Total de perguntas analisadas: {len(df_res)}")

print("\n📊 CLASSIFICAÇÃO GERAL:")
print(df_res['impacto'].value_counts().to_string())

print("\n📈 MÉDIAS GERAIS:")
print(f"  Overlap médio no Top 5: {df_res['overlap_top5'].mean():.2f} / 5")
print(f"  % de vezes que o Top 1 mudou: {(df_res['top1_mudou'].sum() / len(df_res) * 100):.1f}%")
print(f"  Variação média da distância semântica: {df_res['delta_distancia'].mean():+.2f} (positivo = piorou)")
print(f"  Redução média do gap temporal: {df_res['delta_gap'].mean():+.2f} anos (negativo = melhorou)")

df_res.to_csv(os.path.join(OUTPUT_DIR, "analise_impacto_temporal.csv"), index=False)

# ============================================================================
# GRÁFICOS SEPARADOS E MELHORADOS
# ============================================================================

# Configuração geral
sns.set_style("whitegrid")
plt.rcParams['figure.figsize'] = (10, 6)
plt.rcParams['font.size'] = 11

# -------------------------------------------------------------------------
# GRÁFICO 1: Distribuição dos Impactos (Barras com cores)
# -------------------------------------------------------------------------
fig1, ax1 = plt.subplots(figsize=(10, 6))
impact_counts = df_res['impacto'].value_counts()
# Ordem personalizada: MELHOROU, NEUTRO, PREJUDICOU, INDEFINIDO
order = ['MELHOROU (recentes, mesmo contexto)', 
         'NEUTRO (sem mudança significativa)',
         'PREJUDICOU (recentes, mas perdeu contexto)',
         'INDEFINIDO']
impact_counts = impact_counts.reindex([o for o in order if o in impact_counts.index])

colors = {'MELHOROU (recentes, mesmo contexto)': '#2ecc71',
          'NEUTRO (sem mudança significativa)': '#3498db',
          'PREJUDICOU (recentes, mas perdeu contexto)': '#e74c3c',
          'INDEFINIDO': '#95a5a6'}
bar_colors = [colors.get(c, '#95a5a6') for c in impact_counts.index]

bars = ax1.bar(impact_counts.index, impact_counts.values, color=bar_colors, edgecolor='black', linewidth=1.2)
ax1.set_title('Impacto da Penalidade Temporal na Recuperação de Documentos', fontsize=14, fontweight='bold')
ax1.set_ylabel('Número de Perguntas', fontsize=12)
ax1.set_xlabel('Categoria de Impacto', fontsize=12)

# Adicionar valores nas barras
for bar in bars:
    height = bar.get_height()
    ax1.text(bar.get_x() + bar.get_width()/2., height + 0.5,
             f'{int(height)}', ha='center', va='bottom', fontsize=11, fontweight='bold')

# Porcentagem embaixo do eixo X
total = len(df_res)
for i, (label, count) in enumerate(impact_counts.items()):
    pct = (count / total) * 100
    # ax1.text(i, -1.5, f'{pct:.1f}%', ha='center', va='top', fontsize=10, color='gray')

plt.xticks(rotation=15, ha='right')
plt.tight_layout()
plt.savefig(os.path.join(OUTPUT_DIR, 'grafico_impacto_categorias.png'), dpi=150, bbox_inches='tight')
plt.show()

# -------------------------------------------------------------------------
# GRÁFICO 2: Boxplot Comparativo: Distância Semântica (Trad vs Temp)
# -------------------------------------------------------------------------
fig2, ax2 = plt.subplots(figsize=(10, 6))
data_to_plot = [df_res['dist_media_trad'].dropna(), df_res['dist_media_temp'].dropna()]
bp = ax2.boxplot(data_to_plot, patch_artist=True, widths=0.6)
ax2.set_xticklabels(['Busca Tradicional', 'Busca Temporal'])
ax2.set_ylabel('Distância Semântica Média (Top 5)', fontsize=12)
ax2.set_title('Comparação da Distância Semântica Média por Busca', fontsize=14, fontweight='bold')

# Cores
colors_box = ['#3498db', '#e67e22']
for patch, color in zip(bp['boxes'], colors_box):
    patch.set_facecolor(color)
    patch.set_alpha(0.7)

# Linhas
for whisker in bp['whiskers']:
    whisker.set(color='gray', linewidth=1.5)
for cap in bp['caps']:
    cap.set(color='gray', linewidth=1.5)
for median in bp['medians']:
    median.set(color='black', linewidth=2)

# Adicionar linha de referência
ax2.axhline(y=df_res['dist_media_trad'].mean(), color='blue', linestyle='--', alpha=0.5, label=f"Média Trad: {df_res['dist_media_trad'].mean():.1f}")
ax2.axhline(y=df_res['dist_media_temp'].mean(), color='orange', linestyle='--', alpha=0.5, label=f"Média Temp: {df_res['dist_media_temp'].mean():.1f}")
ax2.legend()

plt.tight_layout()
plt.savefig(os.path.join(OUTPUT_DIR, 'grafico_distancia_semantica.png'), dpi=150, bbox_inches='tight')
plt.show()

# -------------------------------------------------------------------------
# GRÁFICO 3: Boxplot Comparativo: Gap Temporal (Trad vs Temp)
# -------------------------------------------------------------------------
fig3, ax3 = plt.subplots(figsize=(10, 6))
data_gaps = [df_res['gap_medio_trad'].dropna(), df_res['gap_medio_temp'].dropna()]
bp2 = ax3.boxplot(data_gaps, patch_artist=True, widths=0.6)
ax3.set_xticklabels(['Busca Tradicional', 'Busca Temporal'])
ax3.set_ylabel('Gap Temporal Médio (anos)', fontsize=12)
ax3.set_title('Comparação da Atualidade dos Documentos (Top 5)', fontsize=14, fontweight='bold')

colors_box2 = ['#3498db', '#e67e22']
for patch, color in zip(bp2['boxes'], colors_box2):
    patch.set_facecolor(color)
    patch.set_alpha(0.7)

for whisker in bp2['whiskers']:
    whisker.set(color='gray', linewidth=1.5)
for cap in bp2['caps']:
    cap.set(color='gray', linewidth=1.5)
for median in bp2['medians']:
    median.set(color='black', linewidth=2)

# Linhas de média
ax3.axhline(y=df_res['gap_medio_trad'].mean(), color='blue', linestyle='--', alpha=0.5, label=f"Média Trad: {df_res['gap_medio_trad'].mean():.1f} anos")
ax3.axhline(y=df_res['gap_medio_temp'].mean(), color='orange', linestyle='--', alpha=0.5, label=f"Média Temp: {df_res['gap_medio_temp'].mean():.1f} anos")
ax3.legend()

plt.tight_layout()
plt.savefig(os.path.join(OUTPUT_DIR, 'grafico_gap_temporal.png'), dpi=150, bbox_inches='tight')
plt.show()

# -------------------------------------------------------------------------
# GRÁFICO 4: Scatter Plot: Relação entre ΔDistância e ΔGap
# -------------------------------------------------------------------------
fig4, ax4 = plt.subplots(figsize=(10, 6))
scatter = ax4.scatter(df_res['delta_distancia'], df_res['delta_gap'], 
                      c=df_res['overlap_top5'], cmap='viridis', s=80, alpha=0.7, edgecolors='black', linewidth=0.5)
ax4.axhline(y=0, color='red', linestyle='--', alpha=0.3)
ax4.axvline(x=0, color='red', linestyle='--', alpha=0.3)
ax4.set_xlabel('Δ Distância Semântica (positivo = piorou)', fontsize=12)
ax4.set_ylabel('Δ Gap Temporal (negativo = melhorou)', fontsize=12)
ax4.set_title('Relação entre Perda Semântica e Ganho Temporal\n(Cor = Overlap no Top 5)', fontsize=14, fontweight='bold')

# Adicionar legenda de cores
cbar = plt.colorbar(scatter)
cbar.set_label('Overlap no Top 5 (documentos em comum)', fontsize=11)

# Anotar quadrantes
ax4.text(0.05, 0.95, 'Melhorou Temporal\nPiorou Semântico', transform=ax4.transAxes, 
         fontsize=10, va='top', ha='left', bbox=dict(boxstyle="round,pad=0.3", facecolor='yellow', alpha=0.3))
ax4.text(0.05, 0.05, 'Melhorou ambos', transform=ax4.transAxes,
         fontsize=10, va='bottom', ha='left', bbox=dict(boxstyle="round,pad=0.3", facecolor='green', alpha=0.3))
ax4.text(0.75, 0.95, 'Piorou ambos', transform=ax4.transAxes,
         fontsize=10, va='top', ha='right', bbox=dict(boxstyle="round,pad=0.3", facecolor='red', alpha=0.3))
ax4.text(0.75, 0.05, 'Piorou Temporal\nMelhorou Semântico', transform=ax4.transAxes,
         fontsize=10, va='bottom', ha='right', bbox=dict(boxstyle="round,pad=0.3", facecolor='yellow', alpha=0.3))

plt.tight_layout()
plt.savefig(os.path.join(OUTPUT_DIR, 'grafico_scatter_delta.png'), dpi=150, bbox_inches='tight')
plt.show()

# -------------------------------------------------------------------------
# GRÁFICO 5: Barras Empilhadas - Overlap por Categoria de Impacto
# -------------------------------------------------------------------------
fig5, ax5 = plt.subplots(figsize=(10, 6))
# Calcular média de overlap por categoria
overlap_by_impact = df_res.groupby('impacto')['overlap_top5'].mean().reindex(
    ['MELHOROU (recentes, mesmo contexto)', 'NEUTRO (sem mudança significativa)',
     'PREJUDICOU (recentes, mas perdeu contexto)', 'INDEFINIDO'])
# Remover NaN
overlap_by_impact = overlap_by_impact.dropna()

bars5 = ax5.bar(overlap_by_impact.index, overlap_by_impact.values, 
                color=['#2ecc71', '#3498db', '#e74c3c', '#95a5a6'], 
                edgecolor='black', linewidth=1.2)
ax5.set_ylabel('Overlap Médio no Top 5 (de 5)', fontsize=12)
ax5.set_xlabel('Categoria de Impacto', fontsize=12)
ax5.set_title('Overlap Semântico por Categoria de Impacto', fontsize=14, fontweight='bold')
ax5.set_ylim(0, 5.5)

# Adicionar valores
for bar in bars5:
    height = bar.get_height()
    ax5.text(bar.get_x() + bar.get_width()/2., height + 0.1,
             f'{height:.1f}', ha='center', va='bottom', fontsize=11, fontweight='bold')

plt.xticks(rotation=15, ha='right')
plt.tight_layout()
plt.savefig(os.path.join(OUTPUT_DIR, 'grafico_overlap_por_impacto.png'), dpi=150, bbox_inches='tight')
plt.show()

print(f"\n✅ Todos os gráficos salvos em: {OUTPUT_DIR}")
print("Arquivos gerados:")
print("  - analise_impacto_temporal.csv (dados brutos)")
print("  - grafico_impacto_categorias.png (distribuição dos impactos)")
print("  - grafico_distancia_semantica.png (boxplot distâncias)")
print("  - grafico_gap_temporal.png (boxplot gaps)")
print("  - grafico_scatter_delta.png (scatter Δ distância vs Δ gap)")
print("  - grafico_overlap_por_impacto.png (overlap médio por categoria)")