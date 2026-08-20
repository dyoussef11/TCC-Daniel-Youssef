"""
Análise de Prevalência com VADER Calibrado - SEM PESOS DE SEVERIDADE
Apenas contagem bruta de menções negativas por tema
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
CAMINHO_JSON = PREPROCESSAMENTO_DATA / "Dados_Limpos_IniciaisV2"  # Ajuste conforme necessário
CAMINHO_SAIDA = PREPROCESSAMENTO_DATA / "Contagem_Analise_VaderV4_CALIBRADO"
CAMINHO_SAIDA.mkdir(parents=True, exist_ok=True)

# Temas com palavras-chave (SEM pesos de severidade)
SEARCH_GROUPS = {
    "performance": {
        "keywords": ["fps drop", "stuttering", "bottleneck", "benchmarks", "low performance", "lag", "1% low", "drops"]
    },
    "thermal": {
        "keywords": ["overheating", "thermal throttling", "undervolt", "repaste", "fan noise", "temp", "°c", "thermal paste", "hot", "degrees"]
    },
    "energy": {
        "keywords": ["battery drain", "battery health", "not charging", "cycle count", "autonomy", "watt", "mah", "discharge", "adapter"]
    },
    "display": {
        "keywords": ["backlight bleed", "flickering", "ips glow", "dead pixels", "ghosting", "panel"]
    },
    "stability": {
        "keywords": ["bsod", "system freeze", "driver crash", "blue screen", "bootloop", "hanging", "restart", "shut down", "error 41"]
    }
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
            res[tema] = 0  # Contagem bruta de menções negativas
            res[f"{tema}_compound_mean"] = []
        
        for post in posts:
            txt_post = f"{post.get('titulo', '')} {post.get('conteudo_post', '')}".lower()
            res["palavras"] += contar_palavras(txt_post)
            
            for tema, pattern in PATTERNS.items():
                compounds = []
                for match in pattern.finditer(txt_post):
                    is_neg, compound = analisar_mencao_calibrada(txt_post, match)
                    if is_neg:
                        res[tema] += 1  # Contagem bruta
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
                            res[tema] += 1  # Contagem bruta
        
        # Converte listas de compound para média
        for tema in SEARCH_GROUPS:
            compounds = res[f"{tema}_compound_mean"]
            res[f"{tema}_compound_mean"] = np.mean(compounds) if compounds else 0.0
        
        return res
    except Exception as e:
        return f"Erro em {arquivo}: {e}"

def analisar_prevalencia_sem_pesos():
    arquivos = [f for f in os.listdir(CAMINHO_JSON) if f.endswith('.json')]
    resultados = []
    
    print(f"📊 Análise VADER Calibrada (threshold = -0.15) - SEM PESOS")
    print(f"📁 Total de arquivos: {len(arquivos)}")
    
    with ProcessPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(processar_arquivo, arq): arq for arq in arquivos}
        for future in tqdm(as_completed(futures), total=len(arquivos), desc="Processando"):
            resultado = future.result()
            if isinstance(resultado, dict):
                resultados.append(resultado)
    
    df = pd.DataFrame(resultados)
    temas = list(SEARCH_GROUPS.keys())
    
    # Métricas básicas (SEM ponderação)
    df['total_mencoes'] = df[temas].sum(axis=1)
    df['densidade_tecnica'] = (df['total_mencoes'] / df['palavras'] * 1000).fillna(0).round(2)
    df['temas_cobertos'] = (df[temas] > 0).sum(axis=1)
    df['engajamento'] = (df['comentarios_total'] / df['posts_unicos']).fillna(0).round(2)
    
    # Ordena por densidade técnica (total de menções negativas por mil palavras)
    df_sorted = df.sort_values('densidade_tecnica', ascending=False)
    
    # Versão com destaque para os temas mais frequentes em cada modelo
    for tema in temas:
        df[f"{tema}_percentual"] = (df[tema] / df['total_mencoes'] * 100).fillna(0).round(1)
    
    # Salva CSV completo
    df_sorted.to_csv(
        CAMINHO_SAIDA / "prevalencia_sem_pesos.csv", 
        index=False, sep=';', encoding='utf-8-sig'
    )
    
    # Salva versão resumida (apenas as colunas principais)
    colunas_resumo = ['modelo', 'posts_unicos', 'palavras', 'total_mencoes', 
                      'densidade_tecnica', 'temas_cobertos', 'engajamento'] + temas
    df_resumo = df_sorted[colunas_resumo].copy()
    df_resumo.to_csv(
        CAMINHO_SAIDA / "prevalencia_sem_pesos_resumo.csv", 
        index=False, sep=';', encoding='utf-8-sig'
    )
    
    # ============ RELATÓRIO ============
    print("\n" + "="*70)
    print("📊 RELATÓRIO DE PREVALÊNCIA (SEM PESOS DE SEVERIDADE)")
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
        print(f"{tema:<15} | média: {media:.1f} | desvio: {std:.1f} | total: {df[tema].sum()}")
    
    print(f"\n📊 CORRELAÇÃO ENTRE TEMAS (matriz de Pearson):")
    print("-"*60)
    corr_matrix = df[temas].corr()
    for tema in temas:
        correlations = corr_matrix[tema].sort_values(ascending=False)
        print(f"\n{tema}:")
        for other, corr in correlations.items():
            if other != tema:
                print(f"   ↔ {other}: {corr:.2f}")
    
    print(f"\n✅ Arquivos salvos em: {CAMINHO_SAIDA}")
    print(f"   - prevalencia_sem_pesos.csv (completo)")
    print(f"   - prevalencia_sem_pesos_resumo.csv (resumido)")

if __name__ == "__main__":
    analisar_prevalencia_sem_pesos()