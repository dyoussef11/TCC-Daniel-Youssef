"""
Análise de Prevalência com VADER Calibrado - ALINHADO COM BUSCA REDDIT
Apenas contagem bruta de menções negativas por tema
Usa EXATAMENTE os mesmos termos da coleta original do Reddit
"""
import os
import json
import pandas as pd
import numpy as np
import re
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm

from core.paths import PREPROCESSAMENTO_DATA

# ============ CONFIGURAÇÕES ============
CAMINHO_JSON = PREPROCESSAMENTO_DATA / "Dados_Limpos_IniciaisV3"
CAMINHO_SAIDA = PREPROCESSAMENTO_DATA / "Contagem_Analise_VaderV5_CALIBRADO"
CAMINHO_SAIDA.mkdir(parents=True, exist_ok=True)

# ============================================================
# TEMAS E PALAVRAS-CHAVE - EXATAMENTE OS MESMOS DA BUSCA REDDIT
# ============================================================
# Estes termos foram utilizados na coleta original via API do Reddit
# para garantir consistência metodológica entre coleta e análise

SEARCH_GROUPS = {
    "stability": {"keywords": [
            "bsod", "system freeze", "driver crash", "blue screen", "bootloop",
            "crash", "freeze", "freezing", "hang", "unstable", "lock up",
            "reboot", "restart", "shutdown", "black screen", "no post",
            "bios", "boot", "startup", "wake", "sleep", "hibernate"
        ]},
    "display": {"keywords": [
            "backlight bleed", "flickering", "ips glow", "dead pixels",
            "screen issue", "display problem", "pixel", "bleed", "backlight",
            "screen flicker", "panel", "screen tear", "color accuracy", "brightness"
        ]},
    "energy": {"keywords": [
            "battery drain", "battery health", "not charging", "cycle count",
            "battery life", "poor battery", "battery issue", "power adapter",
            "charger", "battery problem", "battery wear", "power draw", "watt"
        ]},
    "thermal": {"keywords": [
            "overheating", "thermal throttling", "undervolt", "repaste", "fan noise",
            "hot", "temperature", "throttle", "thermal", "heat", "cooling",
            "fan", "loud", "high temp", "thermal paste", "cpu temp", "gpu temp",
            "degrees", "celsius", "hotspot", "prochot"
        ]},
    "performance": {"keywords": [
            "fps drop", "stuttering", "bottleneck", "low performance",
            "lag", "frame drop", "low fps", "poor performance",
            "slow", "sluggish", "choppy", "stutter", "underperform",
            "power limit", "tdp", "wattage", "clock speed", "utilization"
        ]}
}


# Pré-compilação Regex
PATTERNS = {
    tema: re.compile(r'\b(' + '|'.join(map(re.escape, cfg["keywords"])) + r')\b', re.IGNORECASE)
    for tema, cfg in SEARCH_GROUPS.items()
}

analyzer = SentimentIntensityAnalyzer()

def analisar_mencao_calibrada(texto, match, threshold_vader=-0.15):
    """Análise calibrada de sentimento com threshold -0.15"""
    start = max(0, match.start() - 100)
    end = min(len(texto), match.end() + 100)
    contexto = texto[start:end]
    compound = analyzer.polarity_scores(contexto)['compound']
    return compound < threshold_vader, compound

def contar_palavras(texto):
    return len(re.findall(r'\w+', texto))

def processar_arquivo(arquivo):
    try:
        with open(CAMINHO_JSON / arquivo, 'r', encoding='utf-8') as f:
            dados = json.load(f)
        
        modelo = dados.get('modelo_busca_utilizado')
        posts = dados.get('posts', [])
        
        res = {
            "modelo": modelo,
            "posts_unicos": len(posts),
            "palavras": 0,
            "comentarios_total": 0
        }
        
        # Inicializa contadores para cada tema
        for tema in SEARCH_GROUPS:
            res[tema] = 0
            res[f"{tema}_compound_mean"] = []
        
        for post in posts:
            txt_post = f"{post.get('titulo', '')} {post.get('conteudo_post', '')}".lower()
            res["palavras"] += contar_palavras(txt_post)
            
            for tema, pattern in PATTERNS.items():
                compounds = []
                for match in pattern.finditer(txt_post):
                    is_neg, compound = analisar_mencao_calibrada(txt_post, match)
                    if is_neg:
                        res[tema] += 1
                    compounds.append(compound)
                if compounds:
                    res[f"{tema}_compound_mean"].extend(compounds)
            
            # Processa comentários
            for coment in post.get('comentarios', []):
                txt_c = str(coment.get('conteudo', '')).lower()
                if not txt_c:
                    continue
                
                res["palavras"] += contar_palavras(txt_c)
                res["comentarios_total"] += 1
                
                for tema, pattern in PATTERNS.items():
                    for match in pattern.finditer(txt_c):
                        is_neg, compound = analisar_mencao_calibrada(txt_c, match)
                        if is_neg:
                            res[tema] += 1
        
        # Converte listas de compound para média
        for tema in SEARCH_GROUPS:
            compounds = res[f"{tema}_compound_mean"]
            res[f"{tema}_compound_mean"] = np.mean(compounds) if compounds else 0.0
        
        return res
    except Exception as e:
        return f"Erro em {arquivo}: {e}"

def analisar_prevalencia_reddit_aligned():
    arquivos = [f for f in os.listdir(CAMINHO_JSON) if f.endswith('.json')]
    resultados = []
    
    print("="*70)
    print("📊 ANÁLISE VADER CALIBRADA - ALINHADA COM BUSCA REDDIT")
    print("="*70)
    print(f"📁 Total de arquivos: {len(arquivos)}")
    print(f"🔍 Termos por tema:")
    for tema, cfg in SEARCH_GROUPS.items():
        print(f"   - {tema}: {len(cfg['keywords'])} termos")
    print(f"⚙️ Threshold VADER: -0.15 (calibrado para domínio técnico)")
    
    with ProcessPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(processar_arquivo, arq): arq for arq in arquivos}
        for future in tqdm(as_completed(futures), total=len(arquivos), desc="Processando"):
            resultado = future.result()
            if isinstance(resultado, dict):
                resultados.append(resultado)
    
    df = pd.DataFrame(resultados)
    temas = list(SEARCH_GROUPS.keys())
    
    # Métricas básicas
    df['total_mencoes'] = df[temas].sum(axis=1)
    df['densidade_tecnica'] = (df['total_mencoes'] / df['palavras'] * 1000).fillna(0).round(2)
    df['temas_cobertos'] = (df[temas] > 0).sum(axis=1)
    df['engajamento'] = (df['comentarios_total'] / df['posts_unicos']).fillna(0).round(2)
    
    # Percentuais por tema
    for tema in temas:
        df[f"{tema}_percentual"] = (df[tema] / df['total_mencoes'] * 100).fillna(0).round(1)
    
    # Ordena e salva
    df_sorted = df.sort_values('densidade_tecnica', ascending=False)
    
    df_sorted.to_csv(
        CAMINHO_SAIDA / "prevalencia_sem_pesos.csv", 
        index=False, sep=';', encoding='utf-8-sig'
    )
    
    colunas_resumo = ['modelo', 'posts_unicos', 'palavras', 'total_mencoes', 
                      'densidade_tecnica', 'temas_cobertos', 'engajamento'] + temas
    df_resumo = df_sorted[colunas_resumo].copy()
    df_resumo.to_csv(
        CAMINHO_SAIDA / "prevalencia_sem_pesos_resumo.csv", 
        index=False, sep=';', encoding='utf-8-sig'
    )
    
    # ============ RELATÓRIO ============
    print("\n" + "="*70)
    print("📊 RELATÓRIO DE PREVALÊNCIA (ALINHADO COM BUSCA REDDIT)")
    print("="*70)
    
    print(f"\n📈 TOP 10 MODELOS COM MAIOR DENSIDADE DE PROBLEMAS:")
    print("-"*60)
    top10 = df_sorted.head(10)
    for i, row in top10.iterrows():
        print(f"{row['modelo']:<35} | {row['densidade_tecnica']:.2f} menções/1k palavras | {row['total_mencoes']} total")
    
    print(f"\n📊 DISTRIBUIÇÃO TEMÁTICA (média por modelo):")
    print("-"*60)
    for tema in temas:
        media = df[tema].mean()
        std = df[tema].std()
        total = df[tema].sum()
        pct_total = total / df['total_mencoes'].sum() * 100
        print(f"{tema:<15} | média: {media:.1f} | desvio: {std:.1f} | total: {total} ({pct_total:.1f}%)")
    
    print(f"\n📊 CORRELAÇÃO ENTRE TEMAS (matriz de Pearson):")
    print("-"*60)
    corr_matrix = df[temas].corr()
    for tema in temas:
        correlations = corr_matrix[tema].sort_values(ascending=False)
        print(f"\n{tema}:")
        for other, corr in correlations.items():
            if other != tema:
                print(f"   ↔ {other}: {corr:.2f}")
    
    # Estatísticas de cobertura
    print(f"\n📊 ESTATÍSTICAS DE COBERTURA:")
    print("-"*60)
    print(f"   Total de menções: {df['total_mencoes'].sum():,}")
    print(f"   Média de menções/modelo:  {df['total_mencoes'].mean():.1f}")
    print(f"   Modelos com pelo menos 1 menção: {(df['total_mencoes'] > 0).sum()} ({((df['total_mencoes'] > 0).sum()/len(df))*100:.1f}%)")
    print(f"   Modelos com ≥ 2 temas: {(df['temas_cobertos'] >= 2).sum()} ({((df['temas_cobertos'] >= 2).sum()/len(df))*100:.1f}%)")
    
    print(f"\n✅ Arquivos salvos em: {CAMINHO_SAIDA}")
    print(f"   - prevalencia_sem_pesos.csv (completo)")
    print(f"   - prevalencia_sem_pesos_resumo.csv (resumido)")

if __name__ == "__main__":
    analisar_prevalencia_reddit_aligned()