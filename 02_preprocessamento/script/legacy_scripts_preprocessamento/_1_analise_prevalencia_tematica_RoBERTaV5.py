"""
PIPELINE RoBERTa CORRIGIDO - UFSM/SEMISH 2026
ABSA (Aspect-Based Sentiment Analysis) para Hardware
Implementa:
1. Segmentação por sentença com filtro de aspecto
2. Negação contextual (polaridade invertida)
3. Pesos de severidade por tema
4. Threshold de confiança > 0.90
5. Otimização para GTX 1050 Ti (4GB VRAM)
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
CAMINHO_SAIDA = PREPROCESSAMENTO_DATA / "Analise_RoBERTa_ABSA_V1"
CAMINHO_SAIDA.mkdir(parents=True, exist_ok=True)
MODEL_PATH = str(MODELS / "roberta_sentiment")

# ============ DEFINIÇÃO DE TEMAS COM PESOS DE SEVERIDADE ============
# Pesos baseados no impacto no usuário (fundamentação teórica necessária)
THEMES = {
    "stability": {
        "keywords": [
            "bsod", "system freeze", "driver crash", "blue screen", "bootloop",
            "crash", "freeze", "freezing", "hang", "unstable", "lock up",
            "reboot", "restart", "shutdown", "black screen", "no post",
            "bios", "boot", "startup", "wake", "sleep", "hibernate"
        ],
        "weight": 1.5,  # Falhas críticas: perda total de funcionalidade
        "category": "critical",
        "description": "Falhas que impedem o uso do equipamento"
    },
    "display": {
        "keywords": [
            "backlight bleed", "flickering", "ips glow", "dead pixels",
            "screen issue", "display problem", "pixel", "bleed", "backlight",
            "screen flicker", "panel", "screen tear", "color accuracy", "brightness"
        ],
        "weight": 1.5,  # Falhas físicas: requer substituição de hardware
        "category": "critical",
        "description": "Defeitos físicos permanentes na tela"
    },
    "energy": {
        "keywords": [
            "battery drain", "battery health", "not charging", "cycle count",
            "battery life", "poor battery", "battery issue", "power adapter",
            "charger", "battery problem", "battery wear", "power draw", "watt"
        ],
        "weight": 1.2,  # Degradação de hardware: piora com o tempo
        "category": "degradation",
        "description": "Problemas que tendem a se agravar com o uso"
    },
    "thermal": {
        "keywords": [
            "overheating", "thermal throttling", "undervolt", "repaste", "fan noise",
            "hot", "temperature", "throttle", "thermal", "heat", "cooling",
            "fan", "loud", "high temp", "thermal paste", "cpu temp", "gpu temp",
            "degrees", "celsius", "hotspot", "prochot"
        ],
        "weight": 1.0,  # Falhas de uso/software: podem ser mitigadas
        "category": "performance",
        "description": "Problemas relacionados a temperatura e refrigeração"
    },
    "performance": {
        "keywords": [
            "fps drop", "stuttering", "bottleneck", "low performance",
            "lag", "frame drop", "low fps", "poor performance",
            "slow", "sluggish", "choppy", "stutter", "underperform",
            "power limit", "tdp", "wattage", "clock speed", "utilization"
        ],
        "weight": 1.0,  # Falhas de uso/software: podem ser configuradas
        "category": "performance",
        "description": "Problemas de desempenho e velocidade"
    }
}

# Compila padrões regex para detecção de aspectos
PATTERNS = {
    tema: re.compile(
        r'\b(' + '|'.join(map(re.escape, info["keywords"])) + r')\b', 
        re.IGNORECASE
    ) 
    for tema, info in THEMES.items()
}

# ============ NEGAÇÃO CONTEXTUAL ============
NEGATION_PATTERNS = [
    # Padrões que INVERTEM a polaridade (negativo → positivo)
    re.compile(r'\b(no|not|never|without|free of|absence of|zero|lack of)\s+(' + 
               '|'.join([
                   'overheat', 'throttl', 'bsod', 'crash', 'freeze', 'flicker',
                   'dead pixel', 'backlight bleed', 'battery drain', 'stutter',
                   'lag', 'bottleneck', 'issue', 'problem', 'fail', 'defect'
               ]) + r')\b', re.IGNORECASE),
    
    # Padrões que indicam SOLUÇÃO (não problema)
    re.compile(r'\b(fixed|solved|resolved|repaired|updated|patched|upgraded)\s+'
               r'(the|my|this|that)?\s*(' + 
               '|'.join([
                   'overheat', 'throttl', 'bsod', 'crash', 'freeze', 'flicker',
                   'dead pixel', 'backlight bleed', 'battery drain', 'stutter',
                   'lag', 'bottleneck', 'issue', 'problem'
               ]) + r')\b', re.IGNORECASE),
    
    # Frases que indicam AUSÊNCIA de problema
    re.compile(r'\b(works? (perfectly|fine|great|well)|no issues?|'
               r'runs? (perfectly|smoothly|great|well)|'
               r'haven\'?t (had|experienced|seen) any)\b', re.IGNORECASE),
]

def detectar_negacao_contextual(sentenca):
    """
    Detecta se uma sentença que contém keyword é na verdade:
    - Uma negação ("no overheating")
    - Uma solução ("fixed the crash")
    - Uma ausência ("works perfectly, no issues")
    
    Retorna: True se a polaridade deve ser INVERTIDA
    """
    for pattern in NEGATION_PATTERNS:
        if pattern.search(sentenca):
            return True
    return False

# ============ EXTRAÇÃO DE SENTENÇAS COM FILTRO DE ASPECTO ============
def extrair_sentencas_com_aspecto(texto, min_chars=20, max_chars=500):
    """
    Extrai APENAS sentenças que contêm PELO MENOS UM aspecto alvo.
    Filtra frases genéricas sem keyword técnica.
    """
    if not texto or len(texto.strip()) < min_chars:
        return []
    
    # Divide por pontuação
    sentencas = re.split(r'[.!?\n]+', texto)
    
    resultado = []
    for s in sentencas:
        # Limpeza
        s = re.sub(r'https?://\S+', '', s.strip())
        s = re.sub(r'[^\w\s\-\'.,!?()#@]', '', s)
        
        # Filtro de comprimento (otimização VRAM)
        if len(s) > max_chars:
            s = s[:max_chars]
        
        # SÓ INCLUI se contém pelo menos um aspecto (keyword técnica)
        if len(s) >= min_chars:
            for pattern in PATTERNS.values():
                if pattern.search(s):
                    resultado.append(s)
                    break  # Achou um aspecto, não precisa verificar outros
    
    return resultado

# ============ CLASSIFICAÇÃO DE ASPECTOS ============
def identificar_aspectos(sentenca):
    """
    Identifica quais temas/aspectos estão presentes na sentença.
    Retorna lista de temas.
    """
    temas_encontrados = []
    for tema, pattern in PATTERNS.items():
        if pattern.search(sentenca):
            temas_encontrados.append(tema)
    return temas_encontrados if temas_encontrados else ["geral"]

# ============ COLETA DE SENTENÇAS (OTIMIZADA) ============
def coletar_sentencas_com_aspectos():
    """
    Varre todos os JSONs e coleta APENAS sentenças que contêm aspectos técnicos.
    """
    print("📁 Coletando sentenças COM ASPECTOS TÉCNICOS...")
    
    arquivos = [f for f in os.listdir(CAMINHO_JSON) if f.endswith('.json')]
    
    sentencas_global = []
    mapeamento = {}
    modelo_sentencas = defaultdict(list)
    stats_coleta = defaultdict(int)
    
    idx_atual = 0
    
    for arq in tqdm(arquivos, desc="Varrendo JSONs"):
        try:
            with open(CAMINHO_JSON / arq, 'r', encoding='utf-8') as f:
                dados = json.load(f)
            
            modelo = (dados.get('modelo_busca_utilizado') or 
                     dados.get('modelo_original') or 
                     dados.get('modelo', 'desconhecido'))
            
            if not modelo or str(modelo).lower() in ['nan', 'none', '']:
                continue
            
            modelo = str(modelo)[:100]
            n_posts = len(dados.get('posts', []))
            
            sentencas_modelo = []
            
            for post in dados.get('posts', []):
                # Título (peso maior na análise)
                sentencas_modelo.extend(extrair_sentencas_com_aspecto(post.get('titulo', '')))
                stats_coleta['titulos_processados'] += 1
                
                # Conteúdo do post
                sentencas_modelo.extend(extrair_sentencas_com_aspecto(post.get('conteudo_post', '')))
                stats_coleta['posts_processados'] += 1
                
                # Comentários
                for coment in post.get('comentarios', []):
                    sentencas_modelo.extend(extrair_sentencas_com_aspecto(str(coment.get('conteudo', ''))))
                    stats_coleta['comentarios_processados'] += 1
            
            # Limita a 300 sentenças por modelo
            if len(sentencas_modelo) > 300:
                n = len(sentencas_modelo)
                indices = (list(range(100)) + 
                          list(range(n//2 - 50, n//2 + 50)) + 
                          list(range(n-100, n)))
                indices = sorted(set(i for i in indices if 0 <= i < n))
                sentencas_modelo = [sentencas_modelo[i] for i in indices[:300]]
                stats_coleta['modelos_truncados'] += 1
            
            if len(sentencas_modelo) >= 3:
                for sentenca in sentencas_modelo:
                    sentencas_global.append(sentenca)
                    mapeamento[idx_atual] = {
                        'modelo': modelo,
                        'n_posts': n_posts
                    }
                    modelo_sentencas[modelo].append(idx_atual)
                    idx_atual += 1
                    
        except Exception as e:
            stats_coleta['erros'] += 1
            continue
    
    print(f"\n✅ Coleta concluída:")
    print(f"   - Sentenças com aspectos: {len(sentencas_global):,}")
    print(f"   - Modelos: {len(modelo_sentencas)}")
    print(f"   - Média sentenças/modelo: {len(sentencas_global)/max(1,len(modelo_sentencas)):.0f}")
    print(f"   - Modelos truncados (>300 sentenças): {stats_coleta['modelos_truncados']}")
    
    return sentencas_global, mapeamento, modelo_sentencas

# ============ INFERÊNCIA OTIMIZADA PARA GTX 1050 Ti ============
def inferencia_absa(sentencas_global, batch_size=32):
    """
    Inferência otimizada para 4GB VRAM:
    - dynamic_padding=True
    - max_length=128
    - batch_size reduzido
    - Limpeza de cache periódica
    """
    print(f"\n🚀 Inferência ABSA ({len(sentencas_global):,} sentenças)...")
    
    sentiment_task = pipeline(
        "sentiment-analysis",
        model=MODEL_PATH,
        tokenizer=MODEL_PATH,
        device=0,
        batch_size=batch_size,
        truncation=True,
        max_length=128,
        padding=True,  # dynamic padding
        framework="pt"
    )
    
    chunk_size = 8000  # Reduzido para 4GB VRAM
    resultados = []
    
    for i in tqdm(range(0, len(sentencas_global), chunk_size), desc="GPU Inference"):
        chunk = sentencas_global[i:i + chunk_size]
        
        try:
            resultados_chunk = sentiment_task(chunk)
            resultados.extend(resultados_chunk)
        except RuntimeError as e:
            if "out of memory" in str(e):
                print(f"\n⚠️ OOM no chunk {i//chunk_size}. Reduzindo batch...")
                torch.cuda.empty_cache()
                # Retry com batch menor
                for j in range(0, len(chunk), 16):
                    subchunk = chunk[j:j+16]
                    resultados.extend(sentiment_task(subchunk))
            else:
                raise e
        
        # Limpa cache a cada 3 chunks
        if i % (chunk_size * 3) == 0 and i > 0:
            torch.cuda.empty_cache()
    
    print(f"✅ Inferência concluída: {len(resultados):,} classificações")
    return resultados

# ============ AGREGAÇÃO COM PESOS DE SEVERIDADE ============
def agregar_com_pesos_severidade(resultados, mapeamento, modelo_sentencas, sentencas_global):
    """
    Agregação com:
    1. Threshold de confiança > 0.90
    2. Detecção de negação contextual
    3. Pesos de severidade por tema
    """
    print(f"\n📊 Agregando com pesos de severidade...")
    
    resultados_modelos = {}
    stats = {
        'negacoes_detectadas': 0,
        'positivos_descartados': 0,
        'baixa_confianca_descartados': 0,
        'sentencas_negativas_validas': 0
    }
    
    for modelo, indices in tqdm(modelo_sentencas.items(), desc="Agregando"):
        res = {
            "modelo": modelo,
            "n_posts": mapeamento[indices[0]]['n_posts'],
            "sentencas_analisadas": len(indices),
            "negativos_total": 0,
            "negativos_criticos": 0,
            "positivos": 0,
            "negacoes": 0,
            **{tema: 0 for tema in THEMES},
            f"score_ponderado": 0.0,  # Índice composto com pesos
            "geral": 0
        }
        
        for idx in indices:
            result = resultados[idx]
            sentenca = sentencas_global[idx]
            label = result['label'].lower()
            score = result['score']
            
            # REGRA DE OURO: Apenas negativos com confiança > 0.90
            if label == 'negative' and score > 0.90:
                # Verifica negação contextual
                if detectar_negacao_contextual(sentenca):
                    res["negacoes"] += 1
                    stats['negacoes_detectadas'] += 1
                    continue  # Descarta esta menção!
                
                res["negativos_criticos"] += 1
                stats['sentencas_negativas_validas'] += 1
                
                # Identifica aspectos e aplica pesos
                temas = identificar_aspectos(sentenca)
                for tema in temas:
                    if tema in THEMES:
                        peso = THEMES[tema]["weight"]
                        res[tema] += 1 * peso
                        res["score_ponderado"] += peso
                    elif tema == "geral":
                        res["geral"] += 1
                        res["score_ponderado"] += 0.5  # Peso reduzido para "geral"
                
            elif label == 'negative' and score <= 0.90:
                stats['baixa_confianca_descartados'] += 1
                res["negativos_total"] += 1  # Ainda conta como negativo total
            else:
                stats['positivos_descartados'] += 1
                res["positivos"] += 1
        
        resultados_modelos[modelo] = res
    
    print(f"\n📊 Estatísticas da Filtragem:")
    print(f"   Negações detectadas e descartadas: {stats['negacoes_detectadas']:,}")
    print(f"   Positivos descartados: {stats['positivos_descartados']:,}")
    print(f"   Baixa confiança descartados: {stats['baixa_confianca_descartados']:,}")
    print(f"   Sentenças negativas VÁLIDAS: {stats['sentencas_negativas_validas']:,}")
    
    return resultados_modelos

# ============ RELATÓRIO FINAL ============
def gerar_relatorio_absa(resultados_modelos):
    """Relatório no formato ABSA para SEMISH 2026"""
    hoje = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    df = pd.DataFrame(list(resultados_modelos.values()))
    
    # Métricas
    df['gravidade_absoluta'] = df['negativos_criticos']
    df['gravidade_percentual'] = (df['negativos_criticos'] / df['sentencas_analisadas'] * 100).round(2)
    df['score_ponderado_norm'] = (df['score_ponderado'] / df['sentencas_analisadas'] * 100).round(2)
    
    temas = list(THEMES.keys()) + ['geral']
    
    # Relatório
    relatorio = f"""# Relatório ABSA - RoBERTa para Hardware
## UFSM - V1 2026

**Data:** {hoje}
**Metodologia:** Aspect-Based Sentiment Analysis com RoBERTa
**Threshold:** confiança > 0.90 | **Negação contextual:** Ativada | **Pesos:** Stability/Display=1.5, Energy=1.2, Thermal/Performance=1.0

---

## 📊 Estatísticas Gerais

- **Modelos analisados:** {len(df)}
- **Sentenças com aspectos técnicos:** {df['sentencas_analisadas'].sum():,}
- **Sentenças negativas válidas (pós-filtros):** {df['negativos_criticos'].sum():,}
- **Negações contextuais detectadas:** {df['negacoes'].sum():,}

## 📈 Top 15 Modelos por Gravidade Ponderada

| # | Modelo | Posts | Sentenças | Negativos Válidos | Gravidade (%) | Score Ponderado |
|---|--------|-------|-----------|-------------------|---------------|-----------------|
"""
    
    top15 = df.nlargest(15, 'score_ponderado_norm')
    for i, (_, row) in enumerate(top15.iterrows(), 1):
        relatorio += f"| {i} | {row['modelo'][:40]} | {row['n_posts']} | {row['sentencas_analisadas']} | {row['negativos_criticos']} | {row['gravidade_percentual']:.1f}% | {row['score_ponderado_norm']:.1f} |\n"
    
    relatorio += "\n## 📋 Distribuição Temática Ponderada\n\n"
    relatorio += "| Tema | Peso | Menções Brutas | Menções Ponderadas | % Ponderado | Categoria |\n"
    relatorio += "|------|------|----------------|--------------------|-------------|----------|\n"
    
    total_ponderado = sum(df[tema].sum() for tema in temas if tema != 'geral')
    
    for tema in temas:
        if tema == 'geral':
            continue
        info = THEMES[tema]
        total_tema = df[tema].sum()
        pct = (total_tema / max(1, total_ponderado)) * 100
        relatorio += f"| {tema.capitalize()} | {info['weight']}x | {int(total_tema/info['weight'])} | {total_tema:.0f} | {pct:.1f}% | {info['category']} |\n"
    
    # Salva
    with open(CAMINHO_SAIDA / "RELATORIO_ABSA_V1.md", "w", encoding="utf-8") as f:
        f.write(relatorio)
    
    # CSV
    cols_salvar = ['modelo', 'n_posts', 'sentencas_analisadas', 'negativos_total',
                   'negativos_criticos', 'positivos', 'negacoes', 
                   'gravidade_percentual', 'score_ponderado_norm'] + temas
    df[cols_salvar].to_csv(CAMINHO_SAIDA / "metricas_absa.csv",
                           index=False, sep=";", encoding='utf-8-sig')
    
    print(f"\n✅ Relatórios salvos em: {CAMINHO_SAIDA}")
    return df

# ============ EXECUÇÃO PRINCIPAL ============
def main():
    import time
    inicio = time.time()
    
    print("="*70)
    print("🎓 PIPELINE ABSA - RoBERTa v1")
    print("   Aspect-Based Sentiment Analysis para Hardware")
    print("="*70)
    
    # PASSO 1: Coleta seletiva (apenas sentenças com aspectos)
    t1 = time.time()
    sentencas_global, mapeamento, modelo_sentencas = coletar_sentencas_com_aspectos()
    print(f"⏱️  Coleta: {time.time() - t1:.1f}s")
    
    # PASSO 2: Inferência otimizada para 4GB VRAM
    t2 = time.time()
    resultados = inferencia_absa(sentencas_global, batch_size=32)
    print(f"⏱️  Inferência: {time.time() - t2:.1f}s")
    
    # PASSO 3: Agregação com pesos de severidade
    t3 = time.time()
    resultados_modelos = agregar_com_pesos_severidade(
        resultados, mapeamento, modelo_sentencas, sentencas_global
    )
    print(f"⏱️  Agregação: {time.time() - t3:.1f}s")
    
    # PASSO 4: Relatório
    df = gerar_relatorio_absa(resultados_modelos)
    
    print(f"\n⏱️  TEMPO TOTAL: {time.time() - inicio:.1f}s")
    print(f"📊 Modelos processados: {len(df)}")
    print(f"📊 Sentenças com aspectos: {len(sentencas_global):,}")

if __name__ == "__main__":
    main()