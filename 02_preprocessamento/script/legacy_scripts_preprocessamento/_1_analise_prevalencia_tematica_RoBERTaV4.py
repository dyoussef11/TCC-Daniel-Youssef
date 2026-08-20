"""
ANÁLISE RoBERTa V9 - HIPER OTIMIZADA
Estratégia: Coleta TODAS as sentenças primeiro, processa em batches gigantes na GPU
"""
import os
import json
import pandas as pd
import numpy as np
import re
import torch
from transformers import pipeline
from tqdm import tqdm
from datetime import datetime
from collections import defaultdict
from core.paths import PREPROCESSAMENTO_DATA, MODELS

# ============ CONFIGURAÇÕES ============
CAMINHO_JSON = PREPROCESSAMENTO_DATA / "Dados_Limpos_IniciaisV3"
CAMINHO_SAIDA = PREPROCESSAMENTO_DATA / "Analise_RoBERTa_V9_OTIMIZADO"
CAMINHO_SAIDA.mkdir(parents=True, exist_ok=True)
MODEL_PATH = str(MODELS / "roberta_sentiment")

# Keywords expandidas para classificação temática
SEARCH_GROUPS = {
    "performance": [
        "fps drop", "stuttering", "bottleneck", "low performance",
        "lag", "frame drop", "low fps", "poor performance",
        "slow", "sluggish", "choppy", "stutter", "underperform",
        "power limit", "tdp", "wattage", "clock speed", "utilization"
    ],
    "thermal": [
        "overheating", "thermal throttling", "undervolt", "repaste", "fan noise",
        "hot", "temperature", "throttle", "thermal", "heat", "cooling",
        "fan", "loud", "high temp", "thermal paste", "cpu temp", "gpu temp",
        "degrees", "celsius", "hotspot", "prochot"
    ],
    "energy": [
        "battery drain", "battery health", "not charging", "cycle count",
        "battery life", "poor battery", "battery issue", "power adapter",
        "charger", "battery problem", "battery wear", "power draw", "watt"
    ],
    "display": [
        "backlight bleed", "flickering", "ips glow", "dead pixels",
        "screen issue", "display problem", "pixel", "bleed", "backlight",
        "screen flicker", "panel", "screen tear", "color accuracy", "brightness"
    ],
    "stability": [
        "bsod", "system freeze", "driver crash", "blue screen", "bootloop",
        "crash", "freeze", "freezing", "hang", "unstable", "lock up",
        "reboot", "restart", "shutdown", "black screen", "no post",
        "bios", "boot", "startup", "wake", "sleep", "hibernate"
    ]
}

PATTERNS = {
    tema: re.compile(r'\b(' + '|'.join(map(re.escape, k)) + r')\b', re.IGNORECASE) 
    for tema, k in SEARCH_GROUPS.items()
}

# ============ PASSO 1: COLETA TODAS AS SENTENÇAS ============
def extrair_sentencas(texto, min_chars=15):
    """Extrai sentenças válidas de um texto"""
    if not texto or len(texto.strip()) < min_chars:
        return []
    
    # Divide por pontuação
    sentencas = re.split(r'[.!?\n]+', texto)
    
    resultado = []
    for s in sentencas:
        s = s.strip()
        # Remove URLs e caracteres muito especiais
        s = re.sub(r'https?://\S+', '', s)
        s = re.sub(r'[^\w\s\-\'.,!?()#@]', '', s)
        if len(s) >= min_chars:
            resultado.append(s)
    
    return resultado

def classificar_temas(sentenca):
    """Classifica uma sentença nos temas"""
    temas = []
    for tema, pattern in PATTERNS.items():
        if pattern.search(sentenca):
            temas.append(tema)
    return temas if temas else ["geral"]

def coletar_todas_sentencas():
    """
    PASSO 1: Varre todos os JSONs e coleta sentenças em uma lista global
    Retorna: (sentencas_global, mapeamento_modelos)
    """
    print("📁 PASSO 1: Coletando todas as sentenças...")
    
    arquivos = [f for f in os.listdir(CAMINHO_JSON) if f.endswith('.json')]
    
    sentencas_global = []
    mapeamento = {}  # indice_da_sentenca -> (modelo, n_posts)
    modelo_sentencas = defaultdict(list)  # modelo -> [indices]
    
    idx_atual = 0
    
    for arq in tqdm(arquivos, desc="Varrendo JSONs"):
        try:
            with open(CAMINHO_JSON / arq, 'r', encoding='utf-8') as f:
                dados = json.load(f)
            
            # Identifica modelo
            modelo = (dados.get('modelo_busca_utilizado') or 
                     dados.get('modelo_original') or 
                     dados.get('modelo', 'desconhecido'))
            
            if not modelo or str(modelo).lower() in ['nan', 'none', '']:
                continue
            
            modelo = str(modelo)[:100]
            n_posts = len(dados.get('posts', []))
            
            # Coleta sentenças de TODOS os posts deste modelo
            sentencas_modelo = []
            
            for post in dados.get('posts', []):
                # Título
                sentencas_modelo.extend(extrair_sentencas(post.get('titulo', '')))
                # Conteúdo
                sentencas_modelo.extend(extrair_sentencas(post.get('conteudo_post', '')))
                # Comentários
                for coment in post.get('comentarios', []):
                    sentencas_modelo.extend(extrair_sentencas(str(coment.get('conteudo', ''))))
            
            # Limita a 300 sentenças por modelo para evitar dominância
            if len(sentencas_modelo) > 300:
                # Amostragem: início, meio e fim
                n = len(sentencas_modelo)
                indices = (list(range(100)) + 
                          list(range(n//2 - 50, n//2 + 50)) + 
                          list(range(n-100, n)))
                indices = sorted(set(i for i in indices if 0 <= i < n))
                sentencas_modelo = [sentencas_modelo[i] for i in indices[:300]]
            
            if len(sentencas_modelo) >= 3:  # Mínimo 3 sentenças
                # Adiciona à lista global
                for sentenca in sentencas_modelo:
                    sentencas_global.append(sentenca)
                    mapeamento[idx_atual] = {
                        'modelo': modelo,
                        'n_posts': n_posts
                    }
                    modelo_sentencas[modelo].append(idx_atual)
                    idx_atual += 1
                    
        except Exception as e:
            continue
    
    print(f"✅ Coleta concluída:")
    print(f"   - Total de sentenças: {len(sentencas_global):,}")
    print(f"   - Total de modelos: {len(modelo_sentencas)}")
    print(f"   - Média sentenças/modelo: {len(sentencas_global)/len(modelo_sentencas):.0f}")
    
    return sentencas_global, mapeamento, modelo_sentencas

# ============ PASSO 2: INFERÊNCIA EM LOTE GIGANTE ============
def inferencia_em_lote_gigante(sentencas_global, batch_size=64):
    """
    PASSO 2: Processa TODAS as sentenças de uma vez em batches otimizados
    """
    print(f"\n🚀 PASSO 2: Inferência em lote ({len(sentencas_global):,} sentenças)...")
    
    # Carrega modelo
    sentiment_task = pipeline(
        "sentiment-analysis",
        model=MODEL_PATH,
        tokenizer=MODEL_PATH,
        device=0,
        batch_size=batch_size,
        truncation=True,
        max_length=128,  # Reduz tamanho máximo para acelerar
        padding=True
    )
    
    # Processa em chunks de 10,000 para não estourar memória
    chunk_size = 10000
    resultados = []
    
    for i in tqdm(range(0, len(sentencas_global), chunk_size), desc="Inferência GPU"):
        chunk = sentencas_global[i:i + chunk_size]
        
        # Processa o chunk
        resultados_chunk = sentiment_task(chunk)
        resultados.extend(resultados_chunk)
        
        # Limpa cache da GPU periodicamente
        if i % (chunk_size * 3) == 0 and i > 0:
            torch.cuda.empty_cache()
    
    print(f"✅ Inferência concluída: {len(resultados):,} resultados")
    return resultados

# ============ PASSO 3: AGREGAÇÃO POR MODELO ============
def agregar_por_modelo(resultados, mapeamento, modelo_sentencas, sentencas_global):
    """
    PASSO 3: Agrega resultados por modelo
    """
    print(f"\n📊 PASSO 3: Agregando resultados por modelo...")
    
    resultados_modelos = {}
    
    for modelo, indices in tqdm(modelo_sentencas.items(), desc="Agregando"):
        res = {
            "modelo": modelo,
            "n_posts": mapeamento[indices[0]]['n_posts'],
            "sentencas_analisadas": len(indices),
            "negativos_total": 0,
            "negativos_criticos": 0,
            "positivos": 0,
            **{tema: 0 for tema in SEARCH_GROUPS},
            "geral": 0
        }
        
        for idx in indices:
            result = resultados[idx]
            sentenca = sentencas_global[idx]
            
            if result['label'].lower() == 'negative':
                res["negativos_total"] += 1
                
                # if result['score'] >= 0.85:
                if result['score'] >= 0.85:
                    res["negativos_criticos"] += 1
                    temas = classificar_temas(sentenca)
                    for tema in temas:
                        if tema in res:
                            res[tema] += 1
            else:
                res["positivos"] += 1
        
        resultados_modelos[modelo] = res
    
    print(f"✅ Agregação concluída: {len(resultados_modelos)} modelos")
    return resultados_modelos

# ============ PASSO 4: RELATÓRIO FINAL ============
def gerar_relatorio_final(resultados_modelos):
    """Gera relatório e CSV"""
    hoje = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    # Converte para DataFrame
    df = pd.DataFrame(list(resultados_modelos.values()))
    
    # Métricas
    df['gravidade_percentual'] = (df['negativos_criticos'] / df['sentencas_analisadas'] * 100).round(2)
    df['taxa_negatividade'] = (df['negativos_total'] / df['sentencas_analisadas'] * 100).round(2)
    
    temas = list(SEARCH_GROUPS.keys()) + ['geral']
    total_reclamacoes = df['negativos_criticos'].sum()
    
    # Relatório Markdown
    relatorio = [
        f"# Relatório de Auditoria - RoBERTa V9 (OTIMIZADO)\n",
        f"**Data:** {hoje}\n",
        f"**Método:** Processamento em lote global + agregação\n",
        f"**Threshold:** ≥ 0.85 de confiança\n\n",
        f"## 📊 Estatísticas Gerais\n",
        f"- Modelos analisados: **{len(df)}**\n",
        f"- Sentenças processadas: **{df['sentencas_analisadas'].sum():,}**\n",
        f"- Reclamações (alta confiança): **{total_reclamacoes:,}**\n",
        f"- Taxa média de negatividade: **{df['taxa_negatividade'].mean():.1f}%**\n\n",
        f"## 📈 Top 20 Modelos Críticos\n",
        "| # | Modelo | Posts | Sentenças | Negativos | Gravidade |",
        "|---|--------|-------|-----------|-----------|-----------|"
    ]
    
    top20 = df.nlargest(20, 'negativos_criticos')
    for i, (_, row) in enumerate(top20.iterrows(), 1):
        relatorio.append(
            f"| {i} | {row['modelo'][:50]} | {row['n_posts']} | "
            f"{row['sentencas_analisadas']} | {row['negativos_criticos']} | "
            f"{row['gravidade_percentual']:.1f}% |"
        )
    
    relatorio.append("\n## 📋 Distribuição Temática\n")
    relatorio.append("| Tema | Menções | % |")
    relatorio.append("|------|---------|---|")
    
    for tema in temas:
        total_tema = df[tema].sum()
        perc = (total_tema / total_reclamacoes * 100) if total_reclamacoes > 0 else 0
        relatorio.append(f"| {tema.capitalize()} | {total_tema:,} | {perc:.1f}% |")
    
    # Salva
    with open(CAMINHO_SAIDA / "RELATORIO_FINAL.md", "w", encoding="utf-8") as f:
        f.write("\n".join(relatorio))
    
    # CSV
    cols = ['modelo', 'n_posts', 'sentencas_analisadas', 'negativos_total',
            'negativos_criticos', 'positivos', 'gravidade_percentual', 
            'taxa_negatividade'] + temas
    df[cols].to_csv(CAMINHO_SAIDA / "metricas_completas.csv", 
                    index=False, sep=";", encoding='utf-8-sig')
    
    print(f"\n✅ Relatórios salvos em: {CAMINHO_SAIDA}")
    
    # Estatísticas de tempo (estimado)
    return df

# ============ EXECUÇÃO PRINCIPAL ============
def main():
    import time
    inicio = time.time()
    
    print("="*70)
    print("🚀 ANÁLISE RoBERTa V9 - PROCESSAMENTO EM LOTE GLOBAL")
    print("="*70)
    
    # PASSO 1: Coleta (rápido, CPU)
    t1 = time.time()
    sentencas_global, mapeamento, modelo_sentencas = coletar_todas_sentencas()
    print(f"⏱️  Tempo coleta: {time.time() - t1:.1f}s")
    
    # PASSO 2: Inferência (GPU otimizada)
    t2 = time.time()
    resultados = inferencia_em_lote_gigante(sentencas_global, batch_size=64)
    print(f"⏱️  Tempo inferência: {time.time() - t2:.1f}s")
    
    # PASSO 3: Agregação (rápido, CPU)
    t3 = time.time()
    resultados_modelos = agregar_por_modelo(resultados, mapeamento, modelo_sentencas, sentencas_global)
    print(f"⏱️  Tempo agregação: {time.time() - t3:.1f}s")
    
    # PASSO 4: Relatório
    df = gerar_relatorio_final(resultados_modelos)
    
    print(f"\n⏱️  TEMPO TOTAL: {time.time() - inicio:.1f}s")
    print(f"📊 Modelos processados: {len(df)}")
    print(f"📊 Sentenças analisadas: {len(sentencas_global):,}")

if __name__ == "__main__":
    main()