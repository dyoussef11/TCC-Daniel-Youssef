import os
import json
import pandas as pd
import numpy as np
import re
import torch
from transformers import pipeline, AutoModelForSequenceClassification, AutoTokenizer
from tqdm import tqdm
from core.paths import PREPROCESSAMENTO_DATA, MODELS

# ============ CONFIGURAÇÕES ============
CAMINHO_JSON = PREPROCESSAMENTO_DATA / "Dados_Limpos_IniciaisV3"
CAMINHO_SAIDA = PREPROCESSAMENTO_DATA / "Contagem_Analise_RoBERTa_V6"
CAMINHO_SAIDA.mkdir(parents=True, exist_ok=True)

# Caminho local do modelo salvo no teste anterior
MODEL_PATH = str(MODELS / "roberta_sentiment")

# Configuração de Busca (Mantida para consistência)
SEARCH_GROUPS = {
    "performance": ["fps drop", "stuttering", "bottleneck", "benchmarks", "low performance"],
    "thermal": ["overheating", "thermal throttling", "undervolt", "repaste", "fan noise"],
    "energy": ["battery drain", "battery health", "not charging", "cycle count"],
    "display": ["backlight bleed", "flickering", "ips glow", "dead pixels"],
    "stability": ["bsod", "system freeze", "driver crash", "blue screen", "bootloop"]
}

# Pré-compilação Regex
PATTERNS = {
    tema: re.compile(r'\b(' + '|'.join(map(re.escape, k)) + r')\b', re.IGNORECASE)
    for tema, k in SEARCH_GROUPS.items()
}

# 1. INICIALIZAÇÃO DO MODELO (Utilizando sua GTX 1050 Ti)
print(f"🚀 Carregando RoBERTa da pasta local: {MODEL_PATH}")
sentiment_task = pipeline(
    "sentiment-analysis",
    model=MODEL_PATH,
    tokenizer=MODEL_PATH,
    device=0,           # Usa GPU 0
    batch_size=32       # Otimizado para 4GB VRAM
)

def extrair_sentencas_com_keywords(texto):
    """Divide o texto em sentenças e retorna apenas as que contêm keywords"""
    # Regex simples para dividir sentenças por pontuação
    sentencas = re.split(r'[.!?\n]', texto)
    selecionadas = []
    
    for s in sentencas:
        s = s.strip()
        if not s or len(s) < 10: continue
        # Verifica se alguma keyword de qualquer tema está na sentença
        if any(p.search(s) for p in PATTERNS.values()):
            selecionadas.append(s)
    return selecionadas

def processar_modelo_completo(arquivo):
    """Processa um arquivo JSON de modelo usando o pipeline RoBERTa"""
    with open(CAMINHO_JSON / arquivo, 'r', encoding='utf-8') as f:
        dados = json.load(f)
    
    modelo = dados.get('modelo_busca_utilizado')
    if not modelo or str(modelo).lower() in ['nan', 'none']: return None

    posts = dados.get('posts', [])
    all_text_fragments = []
    
    # Coleta todas as sentenças relevantes (posts e comentários)
    for post in posts:
        txt_full = f"{post.get('titulo', '')}. {post.get('conteudo_post', '')}"
        all_text_fragments.extend(extrair_sentencas_com_keywords(txt_full))
        
        for coment in post.get('comentarios', []):
            txt_c = str(coment.get('conteudo', ''))
            all_text_fragments.extend(extrair_sentencas_com_keywords(txt_c))

    if not all_text_fragments:
        return {"modelo": modelo, "total_negativos": 0, "total_analisado": 0}

    # 2. INFERÊNCIA EM LOTE (BATCH) - Alta performance na GPU
    # truncation=True evita erro de textos longos no RoBERTa
    resultados = sentiment_task(all_text_fragments, truncation=True)
    
    # Contabilização
    contagem_temas = {tema: 0 for tema in SEARCH_GROUPS}
    total_negativos = 0

    for i, res in enumerate(resultados):
        # Consideramos problema real se for 'negative' com confiança > 0.85
        if res['label'].lower() == 'negative' and res['score'] > 0.85:
            total_negativos += 1
            sentenca = all_text_fragments[i]
            # Identifica qual tema a sentença negativa pertence
            for tema, pattern in PATTERNS.items():
                if pattern.search(sentenca):
                    contagem_temas[tema] += 1

    return {
        "modelo": modelo,
        "posts_unicos": len(posts),
        "total_negativos": total_negativos,
        "total_analisado": len(all_text_fragments),
        **contagem_temas
    }

def main():
    arquivos = [f for f in os.listdir(CAMINHO_JSON) if f.endswith('.json')]
    final_data = []

    print(f"📊 Iniciando análise de {len(arquivos)} modelos...")
    
    # Diferente do VADER, não usamos ProcessPoolExecutor aqui 
    # porque a GPU prefere processamento sequencial de lotes grandes
    for arq in tqdm(arquivos, desc="Processando Modelos"):
        resultado = processar_modelo_completo(arq)
        if resultado:
            final_data.append(resultado)

    # 3. GERAÇÃO DE RELATÓRIO
    df = pd.DataFrame(final_data)
    df['densidade_roberta'] = (df['total_negativos'] / df['total_analisado'] * 100).fillna(0).round(2)
    
    df.sort_values('total_negativos', ascending=False).to_csv(
        CAMINHO_SAIDA / "prevalencia_roberta_v6.csv", 
        index=False, sep=';', encoding='utf-8-sig'
    )
    
    print(f"\n✅ Análise concluída! Resultados salvos em: {CAMINHO_SAIDA}")
    # Exibe top 5 por volume absoluto de reclamações validadas
    print(df[['modelo', 'total_negativos', 'densidade_roberta']].head(5))

if __name__ == "__main__":
    main()