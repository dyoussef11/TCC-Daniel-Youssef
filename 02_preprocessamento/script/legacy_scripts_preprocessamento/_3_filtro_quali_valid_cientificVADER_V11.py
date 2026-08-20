# _2_filtro_qualidade_validado_cientificamente.py (ATUALIZADO)

import os
import json
import numpy as np
import pandas as pd
import shutil
from pathlib import Path
from core.paths import PREPROCESSAMENTO_DATA

# ============ NOVOS CAMINHOS BASEADOS NO SEU OUTPUT ============
CAMINHO_METRICAS = PREPROCESSAMENTO_DATA / "Contagem_Analise_VaderV6_CALIBRADO" / "prevalencia_com_diversidade.csv"
CAMINHO_INPUT_JSON = PREPROCESSAMENTO_DATA / "Dados_Limpos_IniciaisV3"
CAMINHO_SAIDA_FINAL = PREPROCESSAMENTO_DATA / "Dados_Final_Threshold_V11"

# ============ THRESHOLDS CALIBRADOS COM SEUS DADOS ============
# Baseado no output da sua execução:
# - 783 modelos totais
# - Média diversidade: 3.8/5 temas
# - Média temas por post: 1.05
# - 523 modelos (66.8%) têm ≥4 temas

THRESHOLDS_BY_RIGOR = {
    "exploratorio": {
        "posts_unicos": 20,           # mínimo para ter poder estatístico básico
        "densidade_tecnica": 0.3,     # muito permissivo (pega quase todos)
        "diversidade_temas_modelo": 2,  # pelo menos 2 temas diferentes
        "media_temas_por_post": 0.5,    # permite posts com só 1 tema
        "engajamento": 1.0
    },
    "padrao": {
        "posts_unicos": 35,           # acima da média de poder (0.55)
        "densidade_tecnica": 0.8,     # filtra modelos muito silenciosos
        "diversidade_temas_modelo": 3,  # recomendado: 3+ temas (abaixo da média 3.8)
        "media_temas_por_post": 0.7,    # evita perfis muito rasos
        "engajamento": 1.5
    },
    "conservador": {
        "posts_unicos": 50,           # poder 0.70
        "densidade_tecnica": 1.5,     # top ~33% em densidade
        "diversidade_temas_modelo": 4,  # alta diversidade (top 66.8%)
        "media_temas_por_post": 0.9,    # posts tendem a mencionar temas múltiplos
        "engajamento": 2.5
    },
    "rigoroso": {
        "posts_unicos": 100,          # poder 0.94 (excelente)
        "densidade_tecnica": 3.0,     # top ~20% em densidade
        "diversidade_temas_modelo": 5,  # cobre TODOS os temas
        "media_temas_por_post": 1.2,    # posts frequentemente multitemáticos
        "engajamento": 5.0
    }
}

def verificar_colunas(df):
    """Verifica e mapeia colunas necessárias (ATUALIZADO)"""
    colunas = {}
    
    colunas['posts'] = 'posts_unicos' if 'posts_unicos' in df.columns else None
    colunas['densidade'] = 'densidade_tecnica' if 'densidade_tecnica' in df.columns else None
    colunas['diversidade'] = 'diversidade_temas_modelo' if 'diversidade_temas_modelo' in df.columns else None
    colunas['media_temas_post'] = 'media_temas_por_post' if 'media_temas_por_post' in df.columns else None
    colunas['engajamento'] = 'engajamento' if 'engajamento' in df.columns else None
    colunas['total_mencoes'] = 'total_mencoes' if 'total_mencoes' in df.columns else None
    
    # Modelo
    if 'modelo' in df.columns:
        colunas['modelo'] = 'modelo'
    elif 'modelo_busca_utilizado' in df.columns:
        colunas['modelo'] = 'modelo_busca_utilizado'
    else:
        colunas['modelo'] = None
    
    return colunas

def aplicar_filtro_cientifico(rigor="conservador", dry_run=True):
    """Aplica filtro com thresholds calibrados para seus dados"""
    
    if not CAMINHO_SAIDA_FINAL.exists() and not dry_run:
        CAMINHO_SAIDA_FINAL.mkdir(parents=True)
    
    # Carrega dados (agora com diversidade!)
    df = pd.read_csv(CAMINHO_METRICAS, sep=';')
    print(f"\n📊 Dados carregados: {len(df)} modelos")
    print(f"📋 Colunas disponíveis: {list(df.columns)}")
    
    colunas = verificar_colunas(df)
    print(f"\n📌 Colunas mapeadas: {colunas}")
    
    thresholds = THRESHOLDS_BY_RIGOR.get(rigor, THRESHOLDS_BY_RIGOR["conservador"])
    
    print("="*70)
    print("📊 FILTRO DE QUALIDADE CIENTÍFICA (CALIBRADO PARA SEUS DADOS)")
    print("="*70)
    print(f"🎯 Rigor: {rigor.upper()}")
    print(f"📏 Thresholds:")
    for k, v in thresholds.items():
        print(f"   - {k}: {v}")
    
    if dry_run:
        print("\n⚠️ MODO DRY RUN - Apenas simulação")
    
    # Estatísticas descritivas dos seus dados
    print(f"\n📊 DISTRIBUIÇÃO DOS SEUS DADOS (n={len(df)}):")
    if colunas['densidade']:
        print(f"   Densidade - p25: {df[colunas['densidade']].quantile(0.25):.2f} | p50: {df[colunas['densidade']].median():.2f} | p75: {df[colunas['densidade']].quantile(0.75):.2f}")
    if colunas['diversidade']:
        print(f"   Diversidade - média: {df[colunas['diversidade']].mean():.1f}/{5} | moda: {df[colunas['diversidade']].mode().iloc[0]}")
    if colunas['media_temas_post']:
        print(f"   Média temas/post - p25: {df[colunas['media_temas_post']].quantile(0.25):.2f} | p50: {df[colunas['media_temas_post']].median():.2f} | p75: {df[colunas['media_temas_post']].quantile(0.75):.2f}")
    if colunas['engajamento']:
        print(f"   Engajamento - p25: {df[colunas['engajamento']].quantile(0.25):.1f} | p50: {df[colunas['engajamento']].median():.1f} | p75: {df[colunas['engajamento']].quantile(0.75):.1f}")
    
    # Aplica thresholds
    mask = pd.Series([True] * len(df))
    
    if colunas['posts'] and thresholds['posts_unicos'] > 0:
        mask = mask & (df[colunas['posts']] >= thresholds['posts_unicos'])
        print(f"\n✅ Após filtro posts ≥ {thresholds['posts_unicos']}: {mask.sum()} modelos")
    
    if colunas['densidade'] and thresholds['densidade_tecnica'] > 0:
        mask = mask & (df[colunas['densidade']] >= thresholds['densidade_tecnica'])
        print(f"✅ Após filtro densidade ≥ {thresholds['densidade_tecnica']}: {mask.sum()} modelos")
    
    if colunas['diversidade'] and thresholds['diversidade_temas_modelo'] > 0:
        mask = mask & (df[colunas['diversidade']] >= thresholds['diversidade_temas_modelo'])
        print(f"✅ Após filtro diversidade ≥ {thresholds['diversidade_temas_modelo']}: {mask.sum()} modelos")
    
    if colunas['media_temas_post'] and thresholds['media_temas_por_post'] > 0:
        mask = mask & (df[colunas['media_temas_post']] >= thresholds['media_temas_por_post'])
        print(f"✅ Após filtro média temas/post ≥ {thresholds['media_temas_por_post']}: {mask.sum()} modelos")
    
    if colunas['engajamento'] and thresholds['engajamento'] > 0:
        mask = mask & (df[colunas['engajamento']] >= thresholds['engajamento'])
        print(f"✅ Após filtro engajamento ≥ {thresholds['engajamento']}: {mask.sum()} modelos")
    
    aprovados = df[mask].copy()
    
    print(f"\n" + "="*60)
    print(f"📊 RESULTADO DO FILTRO CIENTÍFICO")
    print(f"="*60)
    print(f"   - Modelos analisados: {len(df):,}")
    print(f"   - Modelos aprovados: {len(aprovados):,} ({len(aprovados)/len(df)*100:.1f}%)")
    
    if len(aprovados) > 0 and not dry_run:
        # Salva lista de aprovados
        aprovados.to_csv(CAMINHO_SAIDA_FINAL / f"modelos_aprovados_{rigor}.csv", 
                         index=False, sep=';', encoding='utf-8-sig')
        
        # Copia arquivos JSON
        if colunas['modelo']:
            modelos_aprovados = set(aprovados[colunas['modelo']].astype(str).unique())
            print(f"\n📁 Procurando JSONs para {len(modelos_aprovados)} modelos...")
            
            if CAMINHO_INPUT_JSON.exists():
                copiados = 0
                for arq in os.listdir(CAMINHO_INPUT_JSON):
                    if not arq.endswith('.json'):
                        continue
                    try:
                        with open(CAMINHO_INPUT_JSON / arq, 'r', encoding='utf-8') as f:
                            dados = json.load(f)
                        modelo_json = dados.get('modelo_busca_utilizado') or dados.get('modelo')
                        if modelo_json and modelo_json in modelos_aprovados:
                            shutil.copy2(CAMINHO_INPUT_JSON / arq, CAMINHO_SAIDA_FINAL / f"{rigor}_{arq}")
                            copiados += 1
                    except:
                        pass
                print(f"   - Arquivos JSON copiados: {copiados}")
            else:
                print(f"   ⚠️ Pasta não encontrada: {CAMINHO_INPUT_JSON}")
    
    # Gera comparativo entre cenários
    gerar_comparativo_cenarios(df, colunas)
    
    return aprovados

def gerar_comparativo_cenarios(df, colunas):
    """Gera tabela comparativa de todos os cenários de rigor"""
    
    print(f"\n📊 COMPARAÇÃO ENTRE CENÁRIOS DE RIGOR:")
    print("-"*80)
    print(f"{'Rigor':<15} | {'Posts ≥':<8} | {'Dens ≥':<8} | {'Div ≥':<8} | {'Méd T/p ≥':<10} | {'Eng ≥':<8} | {'Aprovados':<10} | {'%':<6}")
    print("-"*80)
    
    for rigor, th in THRESHOLDS_BY_RIGOR.items():
        mask = pd.Series([True] * len(df))
        
        if colunas['posts'] and th['posts_unicos'] > 0:
            mask = mask & (df[colunas['posts']] >= th['posts_unicos'])
        if colunas['densidade'] and th['densidade_tecnica'] > 0:
            mask = mask & (df[colunas['densidade']] >= th['densidade_tecnica'])
        if colunas['diversidade'] and th['diversidade_temas_modelo'] > 0:
            mask = mask & (df[colunas['diversidade']] >= th['diversidade_temas_modelo'])
        if colunas['media_temas_post'] and th['media_temas_por_post'] > 0:
            mask = mask & (df[colunas['media_temas_post']] >= th['media_temas_por_post'])
        if colunas['engajamento'] and th['engajamento'] > 0:
            mask = mask & (df[colunas['engajamento']] >= th['engajamento'])
        
        n_aprovados = mask.sum()
        pct = n_aprovados / len(df) * 100
        
        print(f"{rigor:<15} | {th['posts_unicos']:<8} | {th['densidade_tecnica']:<8.1f} | {th['diversidade_temas_modelo']:<8} | {th['media_temas_por_post']:<10.1f} | {th['engajamento']:<8.1f} | {n_aprovados:<10} | {pct:.1f}%")
    
    print("-"*80)
    print(f"\n💡 RECOMENDAÇÃO:")
    print(f"   - Para análise exploratória: use 'padrao' (~{THRESHOLDS_BY_RIGOR['padrao']['posts_unicos']} posts)")
    print(f"   - Para publicação: use 'conservador' (~{THRESHOLDS_BY_RIGOR['conservador']['posts_unicos']} posts)")
    print(f"   - Seu dataset tem {len(df)} modelos no total")

if __name__ == "__main__":
    print("="*70)
    print("🔬 FILTRO DE QUALIDADE CIENTÍFICA - VERSÃO CALIBRADA")
    print("="*70)
    
    # Verifica se o arquivo com diversidade existe
    if not CAMINHO_METRICAS.exists():
        print(f"\n❌ Arquivo não encontrado: {CAMINHO_METRICAS}")
        print("   Execute primeiro o script de análise com diversidade!")
        exit(1)
    
    # Mostra comparação de cenários primeiro
    df_test = pd.read_csv(CAMINHO_METRICAS, sep=';')
    colunas = verificar_colunas(df_test)
    gerar_comparativo_cenarios(df_test, colunas)
    
    # Pergunta qual rigor usar
    print("\n" + "="*70)
    print("OPÇÕES DE EXECUÇÃO:")
    print("   dry_run=True  → apenas simulação (recomendado primeiro)")
    print("   dry_run=False → copia arquivos")
    print("="*70)
    
    rigor_escolhido = input("\n📌 Qual rigor deseja usar? (exploratorio/padrao/conservador/rigoroso) [padrao]: ") or "padrao"
    
    print("\n🔍 Executando SIMULAÇÃO primeiro...")
    aplicar_filtro_cientifico(rigor=rigor_escolhido, dry_run=True)
    
    resposta = input(f"\n\n✅ Deseja executar o filtro com rigor '{rigor_escolhido}' (copiar arquivos)? (s/N): ")
    if resposta.lower() == 's':
        print("\n🚀 Executando filtro REAL...")
        aplicar_filtro_cientifico(rigor=rigor_escolhido, dry_run=False)
    else:
        print("\n⚠️ Nenhum arquivo foi copiado.")