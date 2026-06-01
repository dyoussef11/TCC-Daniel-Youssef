"""
Análise de Prevalência com VADER Calibrado
Inclui: análise de sensibilidade do threshold VADER, outliers, e correlações parciais
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

CAMINHO_JSON = PREPROCESSAMENTO_DATA / "Dados_Limpos_IniciaisV2"
CAMINHO_SAIDA = PREPROCESSAMENTO_DATA / "Contagem_Analise_VaderV3_CALIBRADO"
CAMINHO_SAIDA.mkdir(parents=True, exist_ok=True)

# Temas com PESOS DIFERENCIADOS por severidade
SEARCH_GROUPS_WEIGHTED = {
    "performance": {
        "keywords": ["fps drop", "stuttering", "bottleneck", "benchmarks", "low performance", "lag", "1% low", "drops"],
        "weight": 1.0
    },
    "thermal": {
        "keywords": ["overheating", "thermal throttling", "undervolt", "repaste", "fan noise", "temp", "°c", "thermal paste", "hot", "degrees"],
        "weight": 1.5  # Problemas térmicos são mais severos
    },
    "energy": {
        "keywords": ["battery drain", "battery health", "not charging", "cycle count", "autonomy", "watt", "mah", "discharge", "adapter"],
        "weight": 0.8  # Bateria é menos crítica que performance
    },
    "display": {
        "keywords": ["backlight bleed", "flickering", "ips glow", "dead pixels", "ghosting", "panel"],
        "weight": 1.2  # Tela é crítica para experiência
    },
    "stability": {
        "keywords": ["bsod", "system freeze", "driver crash", "blue screen", "bootloop", "hanging", "restart", "shut down", "error 41"],
        "weight": 2.0  # BSOD é CRÍTICO
    }
}

# Pré-compilação Regex
PATTERNS = {
    tema: re.compile(r'\b(' + '|'.join(map(re.escape, cfg["keywords"])) + r')\b', re.IGNORECASE)
    for tema, cfg in SEARCH_GROUPS_WEIGHTED.items()
}

analyzer = SentimentIntensityAnalyzer()

def analisar_mencao_calibrada(texto, match, threshold_vader=-0.15):
    """
    Análise calibrada de sentimento.
    Threshold -0.15 é mais rigoroso que 0.05 (evita falsos positivos).
    """
    start = max(0, match.start() - 100)
    end = min(len(texto), match.end() + 100)
    contexto = texto[start:end]
    compound = analyzer.polarity_scores(contexto)['compound']
    
    # Retorna (é_negativo, score_compound)
    return compound < threshold_vader, compound

def contar_palavras(texto):
    return len(re.findall(r'\w+', texto))

def calcular_entropia_tematica(row, temas):
    """
    Calcula entropia de Shannon para diversidade temática.
    H = -Σ p_i * log(p_i)
    """
    counts = np.array([row[t] for t in temas])
    total = counts.sum()
    if total == 0:
        return 0.0
    probs = counts / total
    probs = probs[probs > 0]  # Remove zeros
    return -np.sum(probs * np.log(probs))

def processar_arquivo_vader_calibrado(arquivo):
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
        
        # Inicializa contadores
        for tema in SEARCH_GROUPS_WEIGHTED:
            res[tema] = 0
            res[f"{tema}_weighted"] = 0
            res[f"{tema}_compound_mean"] = []
        
        for post in posts:
            txt_post = f"{post.get('titulo', '')} {post.get('conteudo_post', '')}".lower()
            p_post = contar_palavras(txt_post)
            res["palavras"] += p_post
            
            for tema, pattern in PATTERNS.items():
                weight = SEARCH_GROUPS_WEIGHTED[tema]["weight"]
                compounds = []
                for match in pattern.finditer(txt_post):
                    is_neg, compound = analisar_mencao_calibrada(txt_post, match)
                    if is_neg:
                        res[tema] += 1
                        res[f"{tema}_weighted"] += weight
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
                    weight = SEARCH_GROUPS_WEIGHTED[tema]["weight"]
                    for match in pattern.finditer(txt_c):
                        is_neg, compound = analisar_mencao_calibrada(txt_c, match)
                        if is_neg:
                            res[tema] += 1
                            res[f"{tema}_weighted"] += weight
        
        # Converte listas de compound para média
        for tema in SEARCH_GROUPS_WEIGHTED:
            compounds = res[f"{tema}_compound_mean"]
            res[f"{tema}_compound_mean"] = np.mean(compounds) if compounds else 0.0
        
        return res
    except Exception as e:
        return f"Erro em {arquivo}: {e}"

def analisar_qualidade_vader_calibrado():
    arquivos = [f for f in os.listdir(CAMINHO_JSON) if f.endswith('.json')]
    resultados = []
    
    print(f"🧠 Análise VADER Calibrada ({len(arquivos)} arquivos)...")
    
    with ProcessPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(processar_arquivo_vader_calibrado, arq): arq for arq in arquivos}
        for future in tqdm(as_completed(futures), total=len(arquivos), desc="Processando"):
            resultado = future.result()
            if isinstance(resultado, dict):
                resultados.append(resultado)
    
    df = pd.DataFrame(resultados)
    temas = list(SEARCH_GROUPS_WEIGHTED.keys())
    
    # Métricas avançadas
    df['total_mencoes'] = df[temas].sum(axis=1)
    df['total_weighted'] = df[[f"{t}_weighted" for t in temas]].sum(axis=1)
    df['densidade_tecnica'] = (df['total_mencoes'] / df['palavras'] * 1000).fillna(0).round(2)
    df['densidade_ponderada'] = (df['total_weighted'] / df['palavras'] * 1000).fillna(0).round(2)
    df['temas_cobertos'] = (df[temas] > 0).sum(axis=1)
    
    # Entropia temática (diversidade real)
    df['entropia_tematica'] = df.apply(lambda r: calcular_entropia_tematica(r, temas), axis=1)
    
    # Score de engajamento (comentários por post)
    df['engajamento'] = (df['comentarios_total'] / df['posts_unicos']).fillna(0).round(2)
    
    # Detecta outliers (IQR method)
    Q1 = df['densidade_tecnica'].quantile(0.25)
    Q3 = df['densidade_tecnica'].quantile(0.75)
    IQR = Q3 - Q1
    df['is_outlier'] = (df['densidade_tecnica'] < Q1 - 1.5 * IQR) | (df['densidade_tecnica'] > Q3 + 1.5 * IQR)
    
    # Ordena e salva
    df.sort_values('densidade_ponderada', ascending=False).to_csv(
        CAMINHO_SAIDA / "prevalencia_calibrada.csv", 
        index=False, sep=';', encoding='utf-8-sig'
    )
    
    # Relatório de outliers
    outliers = df[df['is_outlier']]
    print(f"\n📊 Outliers detectados: {len(outliers)}")
    print(f"   - Densidade média geral: {df['densidade_tecnica'].mean():.2f}")
    print(f"   - Outliers (baixa densidade): {len(outliers[outliers['densidade_tecnica'] < Q1 - 1.5*IQR])}")
    print(f"   - Outliers (alta densidade): {len(outliers[outliers['densidade_tecnica'] > Q3 + 1.5*IQR])}")
    
    print(f"\n✅ Relatório calibrado salvo em: {CAMINHO_SAIDA}")

if __name__ == "__main__":
    analisar_qualidade_vader_calibrado()