# 03_filtro_qualidade_validado_cientificamente.py (VERSÃO FINAL - CORRIGIDA)
import os
import json
import numpy as np
import pandas as pd
import shutil
from pathlib import Path
from core.paths import PREPROCESSAMENTO_DATA

# --- CONFIGURAÇÕES DE CAMINHO (VERIFICAR) ---
CAMINHO_METRICAS = PREPROCESSAMENTO_DATA / "Contagem_Analise_VaderV5_CALIBRADO" / "prevalencia_sem_pesos.csv"
CAMINHO_INPUT_JSON = PREPROCESSAMENTO_DATA / "Dados_Limpos_IniciaisV3"  # ALTERAR se for V3
CAMINHO_SAIDA_FINAL = PREPROCESSAMENTO_DATA / "Dados_Final_Threshold_V10_ALINHADO"

# --- THRESHOLDS REVISADOS (baseados nos dados reais) ---
# Distribuição real (do seu relatório):
# - densidade_tecnica: p25=0.48, p50=0.87, p75=1.32
# - poder estatístico: n=20=0.33, n=30=0.48, n=50=0.70, n=70=0.84

THRESHOLDS_BY_RIGOR = {
    "exploratorio": {
        "posts_unicos": 30,           # poder 0.48 (mínimo)
        "densidade_tecnica": 0.4,     # abaixo do p25 (permissivo)
        "temas_cobertos": 1,
        "entropia_tematica": 0.3,     # muito permissivo
        "engajamento": 2.0
    },
    "padrao": {
        "posts_unicos": 50,           # poder 0.70 (aceitável para exploratório)
        "densidade_tecnica": 0.5,     # ligeiramente acima do p25
        "temas_cobertos": 2,
        "entropia_tematica": 0.5,     # metade da mediana (0.87)
        "engajamento": 2.5
    },
    "conservador": {
        "posts_unicos": 70,           # poder 0.84 (adequado para publicações)
        "densidade_tecnica": 0.9,     # próximo da mediana (0.87)
        "temas_cobertos": 3,
        "entropia_tematica": 0.8,     # próximo da mediana (0.90)
        "engajamento": 3.0
    },
    "rigoroso": {
        "posts_unicos": 100,          # poder 0.94 (excelente)
        "densidade_tecnica": 1.3,     # percentil 75 (1.32)
        "temas_cobertos": 4,
        "entropia_tematica": 1.2,     # diversidade alta
        "engajamento": 4.0
    }
}

def verificar_colunas(df):
    """Verifica e mapeia colunas necessárias"""
    colunas = {}
    
    # Posts
    colunas['posts'] = 'posts_unicos' if 'posts_unicos' in df.columns else None
    
    # Densidade
    if 'densidade_tecnica' in df.columns:
        colunas['densidade'] = 'densidade_tecnica'
    elif 'densidade_ponderada' in df.columns:
        colunas['densidade'] = 'densidade_ponderada'
    else:
        colunas['densidade'] = None
    
    # Temas
    colunas['temas'] = 'temas_cobertos' if 'temas_cobertos' in df.columns else None
    
    # Engajamento
    colunas['engajamento'] = 'engajamento' if 'engajamento' in df.columns else None
    
    # Modelo (pode ter nomes diferentes)
    if 'modelo' in df.columns:
        colunas['modelo'] = 'modelo'
    elif 'modelo_busca_utilizado' in df.columns:
        colunas['modelo'] = 'modelo_busca_utilizado'
    elif 'modelo_original' in df.columns:
        colunas['modelo'] = 'modelo_original'
    else:
        colunas['modelo'] = None
    
    return colunas

def calcular_entropia(df):
    """Calcula entropia temática se não existir"""
    if 'entropia_tematica' in df.columns:
        return df
    
    temas = ['performance', 'thermal', 'energy', 'display', 'stability']
    temas_existentes = [t for t in temas if t in df.columns]
    
    if not temas_existentes:
        print("⚠️ Nenhuma coluna de tema encontrada! Entropia será 0 para todos.")
        df['entropia_tematica'] = 0.0
        return df
    
    def calc_entropy(row):
        counts = np.array([row[t] for t in temas_existentes])
        total = counts.sum()
        if total == 0:
            return 0.0
        probs = counts[counts > 0] / total
        return -np.sum(probs * np.log(probs))
    
    df['entropia_tematica'] = df.apply(calc_entropy, axis=1)
    
    # Estatísticas da entropia calculada
    print(f"\n📊 Entropia calculada (n={len(df)}):")
    print(f"   - Mínimo: {df['entropia_tematica'].min():.3f}")
    print(f"   - Mediana: {df['entropia_tematica'].median():.3f}")
    print(f"   - Máximo: {df['entropia_tematica'].max():.3f}")
    print(f"   - Teórico máximo (log2(5)): 2.322")
    
    return df

def aplicar_filtro_cientifico(rigor="conservador", dry_run=True):
    """
    Aplica filtro com diferentes níveis de rigor.
    
    rigor: 'exploratorio', 'padrao', 'conservador', 'rigoroso'
    dry_run: se True, apenas simula e não copia arquivos
    
    Recomendação: usar 'conservador' (n=70, densidade=0.9) para publicações
    """
    if not CAMINHO_SAIDA_FINAL.exists() and not dry_run:
        CAMINHO_SAIDA_FINAL.mkdir(parents=True)
    
    # Carrega dados
    df = pd.read_csv(CAMINHO_METRICAS, sep=';')
    print(f"\n📊 Colunas disponíveis no CSV: {list(df.columns)}")
    
    # Verifica colunas
    colunas = verificar_colunas(df)
    print(f"\n📌 Colunas mapeadas: {colunas}")
    
    # Verifica colunas essenciais
    if colunas['posts'] is None:
        raise ValueError("Coluna 'posts_unicos' não encontrada!")
    if colunas['densidade'] is None:
        raise ValueError("Coluna de densidade não encontrada!")
    
    # Calcula entropia
    df = calcular_entropia(df)
    
    thresholds = THRESHOLDS_BY_RIGOR.get(rigor, THRESHOLDS_BY_RIGOR["conservador"])
    
    print("="*70)
    print("📊 FILTRO DE QUALIDADE CIENTÍFICA (VERSÃO ALINHADA)")
    print("="*70)
    print(f"📁 Arquivo de métricas: {CAMINHO_METRICAS}")
    print(f"🎯 Rigor: {rigor.upper()}")
    print(f"📏 Thresholds:")
    for k, v in thresholds.items():
        print(f"   - {k}: {v}")
    
    if dry_run:
        print("\n⚠️ MODO DRY RUN - Apenas simulação, sem copiar arquivos")
    
    # Estatísticas descritivas da densidade
    print(f"\n📊 Distribuição da Densidade Técnica (n={len(df)}):")
    print(f"   - Percentil 10: {df[colunas['densidade']].quantile(0.10):.3f}")
    print(f"   - Percentil 25: {df[colunas['densidade']].quantile(0.25):.3f}")
    print(f"   - Mediana: {df[colunas['densidade']].median():.3f}")
    print(f"   - Percentil 75: {df[colunas['densidade']].quantile(0.75):.3f}")
    print(f"   - Percentil 90: {df[colunas['densidade']].quantile(0.90):.3f}")
    print(f"   - Média: {df[colunas['densidade']].mean():.3f}")
    
    # Aplica thresholds
    mask = pd.Series([True] * len(df))
    
    mask = mask & (df[colunas['posts']] >= thresholds['posts_unicos'])
    print(f"\n✅ Após filtro posts ≥ {thresholds['posts_unicos']}: {mask.sum()} modelos")
    
    mask = mask & (df[colunas['densidade']] >= thresholds['densidade_tecnica'])
    print(f"✅ Após filtro densidade ≥ {thresholds['densidade_tecnica']}: {mask.sum()} modelos")
    
    if colunas['temas'] and thresholds['temas_cobertos'] > 0:
        mask = mask & (df[colunas['temas']] >= thresholds['temas_cobertos'])
        print(f"✅ Após filtro temas ≥ {thresholds['temas_cobertos']}: {mask.sum()} modelos")
    
    mask = mask & (df['entropia_tematica'] >= thresholds['entropia_tematica'])
    print(f"✅ Após filtro entropia ≥ {thresholds['entropia_tematica']}: {mask.sum()} modelos")
    
    if colunas['engajamento'] and thresholds['engajamento'] > 0:
        mask = mask & (df[colunas['engajamento']] >= thresholds['engajamento'])
        print(f"✅ Após filtro engajamento ≥ {thresholds['engajamento']}: {mask.sum()} modelos")
    
    aprovados = df[mask].copy()
    
    print(f"\n" + "="*60)
    print(f"📊 RESULTADO DO FILTRO CIENTÍFICO")
    print(f"="*60)
    print(f"   - Modelos analisados: {len(df)}")
    print(f"   - Modelos aprovados: {len(aprovados)} ({len(aprovados)/len(df)*100:.1f}%)")
    
    if len(aprovados) > 0:
        print(f"\n📈 ESTATÍSTICAS DOS APROVADOS:")
        print(f"   - Posts totais: {aprovados[colunas['posts']].sum():,}")
        print(f"   - Média posts/modelo: {aprovados[colunas['posts']].mean():.1f}")
        print(f"   - Densidade média: {aprovados[colunas['densidade']].mean():.3f}")
        if colunas['engajamento']:
            print(f"   - Engajamento médio: {aprovados[colunas['engajamento']].mean():.1f}")
        print(f"   - Entropia média: {aprovados['entropia_tematica'].mean():.3f}")
    
    if not dry_run:
        # Salva lista de aprovados
        aprovados.to_csv(CAMINHO_SAIDA_FINAL / f"modelos_aprovados_{rigor}.csv", 
                         index=False, sep=';', encoding='utf-8-sig')
        
        # Copia arquivos JSON
        if colunas['modelo']:
            modelos_aprovados = set(aprovados[colunas['modelo']].astype(str).unique())
            print(f"\n📁 Procurando JSONs para {len(modelos_aprovados)} modelos...")
            
            if not CAMINHO_INPUT_JSON.exists():
                print(f"⚠️ Pasta não encontrada: {CAMINHO_INPUT_JSON}")
            else:
                copiados = 0
                nao_encontrados = 0
                
                for arq in os.listdir(CAMINHO_INPUT_JSON):
                    if not arq.endswith('.json'):
                        continue
                    
                    try:
                        with open(CAMINHO_INPUT_JSON / arq, 'r', encoding='utf-8') as f:
                            dados = json.load(f)
                        
                        # Tenta diferentes campos para identificar o modelo
                        modelo_json = dados.get('modelo_busca_utilizado') or dados.get('modelo') or dados.get('modelo_original')
                        
                        if modelo_json and modelo_json in modelos_aprovados:
                            if not CAMINHO_SAIDA_FINAL.exists():
                                CAMINHO_SAIDA_FINAL.mkdir(parents=True)
                            shutil.copy2(CAMINHO_INPUT_JSON / arq, CAMINHO_SAIDA_FINAL / f"{rigor}_{arq}")
                            copiados += 1
                    except Exception as e:
                        print(f"   ⚠️ Erro ao processar {arq}: {e}")
                        nao_encontrados += 1
                
                print(f"   - Arquivos JSON copiados: {copiados}")
                if nao_encontrados > 0:
                    print(f"   - Erros/ignorados: {nao_encontrados}")
        else:
            print("\n⚠️ Não foi possível identificar a coluna de modelo para copiar JSONs")
    else:
        print("\n⚠️ DRY RUN: Nenhum arquivo foi copiado. Remova dry_run=False para executar.")
    
    # Gera relatório comparativo
    gerar_relatorio_comparativo(df, rigor, colunas)
    
    return aprovados

def gerar_relatorio_comparativo(df, rigor_used, colunas):
    """Gera relatório comparativo dos thresholds"""
    
    relatorio = []
    relatorio.append("# Relatório de Validação de Thresholds (Versão Alinhada)\n")
    relatorio.append(f"## Rigor utilizado: {rigor_used.upper()}\n")
    relatorio.append(f"Data da execução: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    relatorio.append("## Estatísticas da Densidade Técnica\n")
    relatorio.append(f"- Percentil 10: {df[colunas['densidade']].quantile(0.10):.3f}")
    relatorio.append(f"- Percentil 25: {df[colunas['densidade']].quantile(0.25):.3f}")
    relatorio.append(f"- Mediana: {df[colunas['densidade']].median():.3f}")
    relatorio.append(f"- Percentil 75: {df[colunas['densidade']].quantile(0.75):.3f}")
    relatorio.append(f"- Percentil 90: {df[colunas['densidade']].quantile(0.90):.3f}")
    relatorio.append(f"- Média: {df[colunas['densidade']].mean():.3f}")
    
    relatorio.append("\n## Estatísticas da Entropia Temática\n")
    relatorio.append(f"- Mínimo: {df['entropia_tematica'].min():.3f}")
    relatorio.append(f"- Mediana: {df['entropia_tematica'].median():.3f}")
    relatorio.append(f"- Máximo: {df['entropia_tematica'].max():.3f}")
    relatorio.append(f"- Teórico máximo (log2(5)): 2.322")
    
    relatorio.append("\n## Comparação de Cenários\n")
    relatorio.append("| Rigor | n mínimo | Densidade | Temas | Entropia | Engajamento | Modelos | % |")
    relatorio.append("|-------|----------|-----------|-------|----------|-------------|---------|---|")
    
    for rigor, th in THRESHOLDS_BY_RIGOR.items():
        mask = (df[colunas['posts']] >= th['posts_unicos'])
        mask = mask & (df[colunas['densidade']] >= th['densidade_tecnica'])
        mask = mask & (df['entropia_tematica'] >= th['entropia_tematica'])
        
        if colunas['temas'] and th['temas_cobertos'] > 0:
            mask = mask & (df[colunas['temas']] >= th['temas_cobertos'])
        
        if colunas['engajamento'] and th['engajamento'] > 0:
            mask = mask & (df[colunas['engajamento']] >= th['engajamento'])
        
        n_aprovados = mask.sum()
        pct = n_aprovados / len(df) * 100
        
        relatorio.append(f"| {rigor} | {th['posts_unicos']} | {th['densidade_tecnica']} | {th['temas_cobertos']} | {th['entropia_tematica']} | {th['engajamento']} | {n_aprovados} | {pct:.1f}% |")
    
    # Adiciona tabela de poder estatístico
    relatorio.append("\n## Poder Estatístico por Threshold\n")
    relatorio.append("| n_posts | Poder | Recomendação |")
    relatorio.append("|---------|-------|--------------|")
    
    poder_dados = {20: 0.33, 30: 0.48, 40: 0.60, 50: 0.70, 60: 0.78, 70: 0.84, 80: 0.88, 90: 0.92, 100: 0.94}
    for n, poder in poder_dados.items():
        if poder >= 0.80:
            rec = "✅ Adequado para publicações"
        elif poder >= 0.70:
            rec = "⚠️ Aceitável para exploratório"
        elif poder >= 0.50:
            rec = "❌ Abaixo do ideal"
        else:
            rec = "❌ Inadequado"
        relatorio.append(f"| {n} | {poder:.2f} | {rec} |")
    
    with open(CAMINHO_SAIDA_FINAL / "relatorio_thresholds.md", 'w', encoding='utf-8') as f:
        f.write('\n'.join(relatorio))
    
    print(f"\n📄 Relatório: {CAMINHO_SAIDA_FINAL / 'relatorio_thresholds.md'}")

if __name__ == "__main__":
    print("="*70)
    print("🔬 FILTRO DE QUALIDADE CIENTÍFICA")
    print("="*70)
    
    # Teste rápido - verifica se os dados carregam
    try:
        df_test = pd.read_csv(CAMINHO_METRICAS, sep=';')
        print(f"\n✅ Dados carregados: {len(df_test)} modelos")
        print(f"📋 Colunas: {list(df_test.columns)}")
        
        # Verifica se tem 'modelo' no CSV
        if 'modelo' not in df_test.columns and 'modelo_busca_utilizado' not in df_test.columns:
            print("\n⚠️ ATENÇÃO: Nenhuma coluna de modelo identificada!")
            print("   O CSV pode usar 'modelo_busca_utilizado' ou 'modelo_original'")
        
    except Exception as e:
        print(f"\n❌ Erro ao carregar dados: {e}")
        print(f"   Verifique se o arquivo existe em: {CAMINHO_METRICAS}")
        exit(1)
    
    print("\n" + "="*70)
    print("OPÇÕES DE EXECUÇÃO:")
    print("   dry_run=True  → apenas simulação")
    print("   dry_run=False → copia arquivos")
    print("="*70)
    
    # Executa simulação primeiro (recomendado)
    print("\n🔍 Executando SIMULAÇÃO...")
    aplicar_filtro_cientifico(rigor="conservador", dry_run=True)
    
    # Pergunta se quer executar de verdade
    resposta = input("\n\n✅ Deseja executar o filtro de verdade (copiar arquivos)? (s/N): ")
    if resposta.lower() == 's':
        print("\n🚀 Executando filtro REAL...")
        aplicar_filtro_cientifico(rigor="conservador", dry_run=False)
        
        # Opcional: executar outros rigores
        resposta2 = input("\n\n📊 Deseja também executar o filtro PADRÃO? (s/N): ")
        if resposta2.lower() == 's':
            aplicar_filtro_cientifico(rigor="padrao", dry_run=False)
    else:
        print("\n⚠️ Nenhum arquivo foi copiado. Execute com dry_run=False quando estiver pronto.")