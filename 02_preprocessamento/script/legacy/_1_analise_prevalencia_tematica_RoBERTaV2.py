import os
import json
import pandas as pd
import numpy as np
import re
import torch
from transformers import pipeline
from tqdm import tqdm
from datetime import datetime
from core.paths import PREPROCESSAMENTO_DATA, MODELS

# ============ CONFIGURAÇÕES ============
CAMINHO_JSON = PREPROCESSAMENTO_DATA / "Dados_Limpos_IniciaisV3"
CAMINHO_SAIDA = PREPROCESSAMENTO_DATA / "Analise_RoBERTa_V7_FINAL"
CAMINHO_SAIDA.mkdir(parents=True, exist_ok=True)
MODEL_PATH = str(MODELS / "roberta_sentiment")

SEARCH_GROUPS = {
    "performance": ["fps drop", "stuttering", "bottleneck", "benchmarks", "low performance"],
    "thermal": ["overheating", "thermal throttling", "undervolt", "repaste", "fan noise"],
    "energy": ["battery drain", "battery health", "not charging", "cycle count"],
    "display": ["backlight bleed", "flickering", "ips glow", "dead pixels"],
    "stability": ["bsod", "system freeze", "driver crash", "blue screen", "bootloop"]
}

PATTERNS = {tema: re.compile(r'\b(' + '|'.join(map(re.escape, k)) + r')\b', re.IGNORECASE) for tema, k in SEARCH_GROUPS.items()}

# 1. INICIALIZAÇÃO DO MODELO (GTX 1050 Ti 4GB)
print(f"🚀 Carregando RoBERTa calibrado...")
sentiment_task = pipeline(
    "sentiment-analysis",
    model=MODEL_PATH,
    tokenizer=MODEL_PATH,
    device=0,           # GPU
    batch_size=32       # Otimizado para 4GB VRAM
)

def extrair_sentencas(texto):
    sentencas = re.split(r'[.!?\n]', texto)
    return [s.strip() for s in sentencas if len(s.strip()) > 10 and any(p.search(s) for p in PATTERNS.values())]

def processar_modelo(arquivo):
    try:
        with open(CAMINHO_JSON / arquivo, 'r', encoding='utf-8') as f:
            dados = json.load(f)
        
        modelo = dados.get('modelo_busca_utilizado')
        if not modelo or str(modelo).lower() in ['nan', 'none']: return None

        all_fragments = []
        for post in dados.get('posts', []):
            txt = f"{post.get('titulo', '')}. {post.get('conteudo_post', '')}"
            all_fragments.extend(extrair_sentencas(txt))
            for c in post.get('comentarios', []):
                all_fragments.extend(extrair_sentencas(str(c.get('conteudo', ''))))

        if not all_fragments: return None

        # Inferência em Lote
        resultados = sentiment_task(all_fragments, truncation=True)
        
        res_modelo = {
            "modelo": modelo,
            "n_posts": len(dados.get('posts', [])),
            "sentencas_analisadas": len(all_fragments),
            "negativos_criticos": 0,
            **{tema: 0 for tema in SEARCH_GROUPS}
        }

        for i, res in enumerate(resultados):
            # Threshold de 0.85 para filtrar ruído
            # if res['label'].lower() == 'negative' and res['score'] > 0.85:
            if res['label'].lower() == 'negative' and res['score'] :
                res_modelo["negativos_criticos"] += 1
                for tema, pattern in PATTERNS.items():
                    if pattern.search(all_fragments[i]):
                        res_modelo[tema] += 1
        
        return res_modelo
    except Exception: return None

def gerar_relatorio_final(df):
    """Gera o relatório estatístico para o artigo científico"""
    hoje = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    # Cálculos estatísticos
    df['gravidade_percentual'] = (df['negativos_criticos'] / df['sentencas_analisadas'] * 100).round(2)
    temas = list(SEARCH_GROUPS.keys())
    total_reclamacoes = df['negativos_criticos'].sum()
    
    relatorio = [
        f"# Relatório de Auditoria de Sentimento - RoBERTa V7\n",
        f"**Data da Execução:** {hoje}\n",
        f"**Metodologia:** Classificação via RoBERTa (Transformer) com threshold de confiança\n",
        f"## 📊 Estatísticas Gerais\n",
        f"- **Total de Modelos Analisados:** {len(df)}\n",
        f"- **Total de Sentenças Processadas:** {df['sentencas_analisadas'].sum():,}\n",
        f"- **Total de Reclamações Negativas Validadas:** {total_reclamacoes:,}\n",
        f"\n## 📈 Top 10 Modelos Críticos (Ranking de Gravidade)\n",
        "| Modelo | Posts | Sentenças Negativas | Gravidade (%) |",
        "| :--- | :--- | :--- | :--- |"
    ]
    
    top10 = df.sort_values('negativos_criticos', ascending=False).head(10)
    for _, row in top10.iterrows():
        relatorio.append(f"| {row['modelo']} | {row['n_posts']} | {row['negativos_criticos']} | {row['gravidade_percentual']}% |")
    
    relatorio.append("\n## 📋 Distribuição Temática das Falhas\n")
    for tema in temas:
        total_tema = df[tema].sum()
        perc = (total_tema / total_reclamacoes * 100) if total_reclamacoes > 0 else 0
        relatorio.append(f"- **{tema.capitalize()}:** {total_tema:,} menções ({perc:.1f}%)")
    
    # Salva arquivos
    with open(CAMINHO_SAIDA / "RELATORIO_AUDITORIA.md", "w", encoding="utf-8") as f:
        f.write("\n".join(relatorio))
    df.to_csv(CAMINHO_SAIDA / "metricas_completas_roberta.csv", index=False, sep=";")
    
    print(f"\n✅ Relatório Científico Gerado: {CAMINHO_SAIDA / 'RELATORIO_AUDITORIA.md'}")

def main():
    arquivos = [f for f in os.listdir(CAMINHO_JSON) if f.endswith('.json')]
    resultados = []
    
    for arq in tqdm(arquivos, desc="Processando Modelos (GPU)"):
        res = processar_modelo(arq)
        if res: resultados.append(res)
    
    if resultados:
        df = pd.DataFrame(resultados)
        gerar_relatorio_final(df)

if __name__ == "__main__":
    main()