"""
FILTRO DE QUALIDADE CIENTÍFICA - RoBERTa V2 (CORRIGIDO)
Baseado nos resultados estatísticos reais
"""
import os
import json
import numpy as np
import pandas as pd
import shutil
from pathlib import Path
from datetime import datetime
from core.paths import PREPROCESSAMENTO_DATA

# --- CONFIGURAÇÕES ---
CAMINHO_METRICAS = PREPROCESSAMENTO_DATA / "Analise_RoBERTa_ABSA_V1" / "metricas_absa.csv"
CAMINHO_INPUT_JSON = PREPROCESSAMENTO_DATA / "Dados_Limpos_IniciaisV3"
CAMINHO_SAIDA_FINAL = PREPROCESSAMENTO_DATA / "Dados_Final_RoBERTa_Threshold_V3"
CAMINHO_SAIDA_FINAL.mkdir(parents=True, exist_ok=True)

# ============ ATUALIZAR THRESHOLDS ============
THRESHOLDS_BY_RIGOR = {
    "exploratorio": {
        "n_posts": 30,
        "gravidade_percentual": 0.8,      # Ajustado para score ponderado
        "score_ponderado_norm": 1.0,      # NOVO: threshold para score ponderado
        "temas_cobertos": 1,
        "entropia_tematica": 0.0,
        "descricao": "Análise ampla ABSA. ~150 modelos"
    },
    "padrao": {
        "n_posts": 50,
        "gravidade_percentual": 2.0,
        "score_ponderado_norm": 2.5,      # NOVO
        "temas_cobertos": 2,
        "entropia_tematica": 0.3,
        "descricao": "Equilibrado ABSA. ~70-80 modelos"
    },
    "conservador": {
        "n_posts": 64,
        "gravidade_percentual": 3.5,
        "score_ponderado_norm": 4.0,      # NOVO: score ponderado mínimo
        "temas_cobertos": 2,
        "entropia_tematica": 0.5,
        "descricao": "Publicação SEMISH. ~40-50 modelos"
    },
    "rigoroso": {
        "n_posts": 100,
        "gravidade_percentual": 5.0,
        "score_ponderado_norm": 6.0,      # NOVO
        "temas_cobertos": 3,
        "entropia_tematica": 0.8,
        "descricao": "Elite ABSA. ~5-10 modelos"
    }
}

def verificar_colunas(df):
    """Mapeia colunas necessárias"""
    colunas = {}
    
    # Posts
    if 'n_posts' in df.columns:
        colunas['posts'] = 'n_posts'
    elif 'posts_unicos' in df.columns:
        colunas['posts'] = 'posts_unicos'
    else:
        raise ValueError("Coluna de posts não encontrada!")
    
    # Gravidade
    if 'gravidade_percentual' in df.columns:
        colunas['gravidade'] = 'gravidade_percentual'
    elif 'densidade_tecnica' in df.columns:
        colunas['gravidade'] = 'densidade_tecnica'
    else:
        # Tenta calcular
        if 'negativos_criticos' in df.columns and 'sentencas_analisadas' in df.columns:
            df['gravidade_percentual'] = (df['negativos_criticos'] / df['sentencas_analisadas'] * 100)
            colunas['gravidade'] = 'gravidade_percentual'
        else:
            raise ValueError("Não foi possível determinar coluna de gravidade!")
    
    # Modelo
    for col in ['modelo', 'modelo_busca_utilizado', 'modelo_original']:
        if col in df.columns:
            colunas['modelo'] = col
            break
    
    if 'modelo' not in colunas:
        raise ValueError("Coluna de modelo não encontrada!")
    
    return colunas

def calcular_entropia(df):
    """Calcula entropia temática de Shannon"""
    if 'entropia_tematica' in df.columns:
        return df
    
    temas = ['performance', 'thermal', 'energy', 'display', 'stability', 'geral']
    temas_existentes = [t for t in temas if t in df.columns]
    
    if not temas_existentes:
        print("⚠️ Nenhuma coluna temática encontrada. Entropia = 0 para todos.")
        df['entropia_tematica'] = 0.0
        return df
    
    def calc_entropy(row):
        counts = np.array([max(0, row[t]) for t in temas_existentes])
        total = counts.sum()
        if total == 0:
            return 0.0
        probs = counts[counts > 0] / total
        return -np.sum(probs * np.log(probs))
    
    df['entropia_tematica'] = df.apply(calc_entropy, axis=1)
    return df

def calcular_temas_cobertos(df):
    """Calcula número de temas cobertos por modelo"""
    if 'temas_cobertos' in df.columns:
        return df
    
    temas = ['performance', 'thermal', 'energy', 'display', 'stability', 'geral']
    temas_existentes = [t for t in temas if t in df.columns]
    
    if temas_existentes:
        df['temas_cobertos'] = (df[temas_existentes] > 0).sum(axis=1)
    else:
        df['temas_cobertos'] = 0
    
    return df

def diagnosticar_dados(df, colunas):
    """Mostra distribuições para calibrar thresholds"""
    print("\n" + "="*70)
    print("📊 DIAGNÓSTICO DOS DADOS")
    print("="*70)
    
    print(f"\n1. n_posts:")
    for p in [10, 25, 50, 75, 90]:
        print(f"   P{p}: {df[colunas['posts']].quantile(p/100):.0f}")
    print(f"   Média: {df[colunas['posts']].mean():.0f}")
    print(f"   Mediana: {df[colunas['posts']].median():.0f}")
    
    print(f"\n2. Gravidade Percentual:")
    for p in [10, 25, 50, 75, 90]:
        print(f"   P{p}: {df[colunas['gravidade']].quantile(p/100):.2f}%")
    print(f"   Média: {df[colunas['gravidade']].mean():.2f}%")
    print(f"   Mediana: {df[colunas['gravidade']].median():.2f}%")
    
    print(f"\n3. Temas Cobertos:")
    print(df['temas_cobertos'].value_counts().sort_index().to_string())
    print(f"   Média: {df['temas_cobertos'].mean():.2f}")
    
    print(f"\n4. Entropia Temática:")
    for p in [10, 25, 50, 75, 90]:
        print(f"   P{p}: {df['entropia_tematica'].quantile(p/100):.3f}")
    print(f"   Média: {df['entropia_tematica'].mean():.3f}")
    print(f"   Mediana: {df['entropia_tematica'].median():.3f}")

def aplicar_filtro_cientifico(rigor="conservador", dry_run=True):
    """Aplica filtro de qualidade com thresholds calibrados"""
    
    print("="*70)
    print("🔬 FILTRO DE QUALIDADE CIENTÍFICA - RoBERTa V2")
    print("="*70)
    
    # Carrega dados
    df = pd.read_csv(CAMINHO_METRICAS, sep=';')
    print(f"\n✅ Dados carregados: {len(df)} modelos")
    
    # Prepara colunas
    colunas = verificar_colunas(df)
    df = calcular_temas_cobertos(df)
    df = calcular_entropia(df)
    
    # Diagnóstico
    diagnosticar_dados(df, colunas)
    
    # Thresholds
    th = THRESHOLDS_BY_RIGOR.get(rigor)
    if not th:
        print(f"❌ Rigor '{rigor}' não encontrado. Use: {list(THRESHOLDS_BY_RIGOR.keys())}")
        return None
    
    print(f"\n" + "="*70)
    print(f"🎯 APLICANDO FILTRO: {rigor.upper()}")
    print(f"="*70)
    print(f"Thresholds:")
    for k, v in th.items():
        print(f"   {k}: {v}")
    
    # Aplica filtro progressivamente
    mask = pd.Series(True, index=df.index)
    
    # Filtro 1: Posts
    mask = mask & (df[colunas['posts']] >= th['n_posts'])
    print(f"\n✅ Após n_posts ≥ {th['n_posts']}: {mask.sum()} modelos ({mask.sum()/len(df)*100:.1f}%)")
    
    # Filtro 2: Gravidade
    mask = mask & (df[colunas['gravidade']] >= th['gravidade_percentual'])
    print(f"✅ Após gravidade ≥ {th['gravidade_percentual']}%: {mask.sum()} modelos ({mask.sum()/len(df)*100:.1f}%)")
    
    # Filtro 3: Temas
    if 'temas_cobertos' in th and th['temas_cobertos'] > 0:
        mask = mask & (df['temas_cobertos'] >= th['temas_cobertos'])
        print(f"✅ Após temas ≥ {th['temas_cobertos']}: {mask.sum()} modelos ({mask.sum()/len(df)*100:.1f}%)")
    
    # Filtro 4: Entropia
    if 'entropia_tematica' in th and th['entropia_tematica'] > 0:
        mask = mask & (df['entropia_tematica'] >= th['entropia_tematica'])
        print(f"✅ Após entropia ≥ {th['entropia_tematica']}: {mask.sum()} modelos ({mask.sum()/len(df)*100:.1f}%)")
    
    # NOVO: Filtro por score ponderado (métrica principal do ABSA)
    if 'score_ponderado_norm' in th and 'score_ponderado_norm' in df.columns:
        mask = mask & (df['score_ponderado_norm'] >= th['score_ponderado_norm'])
        print(f"✅ Após score_ponderado ≥ {th['score_ponderado_norm']}: {mask.sum()} modelos")
    
    # NOVO: Filtro por negações (modelos com muitas negações detectadas = dados mais limpos)
    if 'negacoes' in df.columns:
        # Modelos com pelo menos algumas negações detectadas (indicador de qualidade)
        # Não é um filtro rígido, apenas informativo
        negacoes_median = df.loc[mask, 'negacoes'].median() if mask.sum() > 0 else 0
        print(f"ℹ️  Mediana de negações detectadas nos aprovados: {negacoes_median:.0f}")
        
    aprovados = df[mask].copy()
    
    # Resultado final
    print(f"\n" + "="*70)
    print(f"📊 RESULTADO FINAL ({rigor.upper()})")
    print(f"="*70)
    print(f"Modelos analisados: {len(df)}")
    print(f"Modelos aprovados: {len(aprovados)} ({len(aprovados)/len(df)*100:.1f}%)")
    
    if len(aprovados) > 0:
        print(f"\nTop 10 aprovados por gravidade:")
        top10 = aprovados.nlargest(10, colunas['gravidade'])
        for i, (_, row) in enumerate(top10.iterrows(), 1):
            print(f"  {i:2d}. {row[colunas['modelo']][:50]:<50} | {row[colunas['gravidade']]:.1f}%")
        
        if not dry_run:
            # Salva CSV
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_csv = CAMINHO_SAIDA_FINAL / f"modelos_aprovados_{rigor}_{timestamp}.csv"
            aprovados.to_csv(output_csv, index=False, sep=';', encoding='utf-8-sig')
            print(f"\n✅ CSV salvo: {output_csv}")
            
            # Copia JSONs
            copiados = 0
            for modelo in aprovados[colunas['modelo']].unique():
                # Tenta diferentes padrões de nome de arquivo
                possiveis_nomes = [
                    f"{modelo}.json",
                    f"{modelo.replace(' ', '_')}.json",
                    f"{modelo.lower().replace(' ', '_')}.json"
                ]
                
                copiado = False
                for nome in possiveis_nomes:
                    origem = CAMINHO_INPUT_JSON / nome
                    if origem.exists():
                        destino = CAMINHO_SAIDA_FINAL / f"{rigor}_{nome}"
                        shutil.copy2(origem, destino)
                        copiados += 1
                        copiado = True
                        break
                
                if not copiado:
                    # Tenta busca parcial
                    for arq in CAMINHO_INPUT_JSON.glob("*.json"):
                        if modelo.lower().replace(' ', '') in arq.stem.lower().replace(' ', ''):
                            destino = CAMINHO_SAIDA_FINAL / f"{rigor}_{arq.name}"
                            shutil.copy2(arq, destino)
                            copiados += 1
                            break
            
            print(f"✅ JSONs copiados: {copiados}")
    else:
        print("\n⚠️ NENHUM modelo aprovado! Thresholds muito restritivos.")
    
    return aprovados

def comparar_rigores(df, colunas):
    """Compara quantos modelos passam em cada nível de rigor"""
    print("\n" + "="*70)
    print("📊 COMPARAÇÃO ENTRE NÍVEIS DE RIGOR")
    print("="*70)
    print(f"{'Rigor':<15} {'n_posts':<10} {'Gravidade':<12} {'Temas':<8} {'Entropia':<10} {'Aprovados':<12} {'%':<8}")
    print("-"*75)
    
    for nome, th in THRESHOLDS_BY_RIGOR.items():
        mask = (
            (df[colunas['posts']] >= th['n_posts']) &
            (df[colunas['gravidade']] >= th['gravidade_percentual']) &
            (df['temas_cobertos'] >= th.get('temas_cobertos', 0)) &
            (df['entropia_tematica'] >= th.get('entropia_tematica', 0))
        )
        n = mask.sum()
        pct = n / len(df) * 100
        print(f"{nome:<15} {th['n_posts']:<10} {th['gravidade_percentual']:<12} "
              f"{th.get('temas_cobertos', 0):<8} {th.get('entropia_tematica', 0):<10.1f} "
              f"{n:<12} {pct:<8.1f}%")

if __name__ == "__main__":
    # 1. Diagnóstico - simula todos os rigores
    df = pd.read_csv(CAMINHO_METRICAS, sep=';')
    colunas = verificar_colunas(df)
    df = calcular_temas_cobertos(df)
    df = calcular_entropia(df)
    diagnosticar_dados(df, colunas)
    comparar_rigores(df, colunas)
    
    # 2. Pergunta qual rigor aplicar
    print("\n" + "="*70)
    print("Qual nível de rigor deseja aplicar?")
    print("  1. exploratorio (mais modelos, menos restritivo)")
    print("  2. padrao (equilibrado)")
    print("  3. conservador (recomendado para publicação)")
    print("  4. rigoroso (apenas casos mais graves)")
    
    opcao = input("\nOpção (1-4) [default=3]: ").strip()
    
    mapa = {'1': 'exploratorio', '2': 'padrao', '3': 'conservador', '4': 'rigoroso'}
    rigor = mapa.get(opcao, 'conservador')
    
    # 3. Executa
    aprovados = aplicar_filtro_cientifico(rigor=rigor, dry_run=False)