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
CAMINHO_SAIDA = PREPROCESSAMENTO_DATA / "Analise_RoBERTa_V8_CORRIGIDO"
CAMINHO_SAIDA.mkdir(parents=True, exist_ok=True)
MODEL_PATH = str(MODELS / "roberta_sentiment")

# Keywords EXPANDIDAS para matching temático (não para filtrar sentenças!)
SEARCH_GROUPS = {
    "performance": [
        "fps drop", "stuttering", "bottleneck", "benchmarks", "low performance",
        "lag", "frame drop", "frame rate", "low fps", "poor performance",
        "slow", "sluggish", "choppy", "stutter", "underperform",
        "power limit", "tdp", "wattage", "clock speed", "utilization"
    ],
    "thermal": [
        "overheating", "thermal throttling", "undervolt", "repaste", "fan noise",
        "hot", "temperature", "throttle", "thermal", "heat", "cooling",
        "fan", "loud", "high temp", "thermal paste", "cpu temp", "gpu temp",
        "degrees", "celsius", "fahrenheit", "hotspot", "prochot"
    ],
    "energy": [
        "battery drain", "battery health", "not charging", "cycle count",
        "battery life", "poor battery", "battery issue", "power adapter",
        "charger", "power brick", "battery problem", "battery wear",
        "battery", "charge", "discharge", "power draw", "watt"
    ],
    "display": [
        "backlight bleed", "flickering", "ips glow", "dead pixels",
        "screen issue", "display problem", "pixel", "bleed", "backlight",
        "screen flicker", "monitor issue", "panel", "screen tear",
        "screen", "display", "monitor", "color accuracy", "brightness"
    ],
    "stability": [
        "bsod", "system freeze", "driver crash", "blue screen", "bootloop",
        "crash", "freeze", "freezing", "hang", "unstable", "lock up",
        "reboot", "restart", "shutdown", "black screen", "no post",
        "bios", "boot", "startup", "wake", "sleep", "hibernate"
    ]
}

# Compila patterns para classificação temática (não para filtro!)
PATTERNS = {
    tema: re.compile(r'\b(' + '|'.join(map(re.escape, k)) + r')\b', re.IGNORECASE) 
    for tema, k in SEARCH_GROUPS.items()
}

# ============ INICIALIZAÇÃO DO MODELO ============
print(f"🚀 Carregando RoBERTa...")
sentiment_task = pipeline(
    "sentiment-analysis",
    model=MODEL_PATH,
    tokenizer=MODEL_PATH,
    device=0,
    batch_size=32
)

def extrair_sentencas(texto):
    """
    CORRIGIDO: Extrai TODAS as sentenças relevantes, não apenas as com keywords exatas.
    """
    if not texto or len(texto.strip()) < 15:
        return []
    
    # Divide por pontuação e quebras de linha
    sentencas = re.split(r'[.!?\n]+', texto)
    
    sentencas_filtradas = []
    for s in sentencas:
        s = s.strip()
        # Apenas filtra por tamanho mínimo e remove URLs/menções
        if len(s) > 15 and not s.startswith('http'):
            # Remove caracteres especiais excessivos mas mantém texto
            s_clean = re.sub(r'[^\w\s\-\'.,!?()]', '', s)
            if len(s_clean) > 15:
                sentencas_filtradas.append(s_clean)
    
    return sentencas_filtradas

def classificar_temas(sentenca):
    """
    Classifica uma sentença nos temas usando as keywords expandidas.
    Retorna lista de temas encontrados.
    """
    temas_encontrados = []
    for tema, pattern in PATTERNS.items():
        if pattern.search(sentenca):
            temas_encontrados.append(tema)
    return temas_encontrados if temas_encontrados else ["geral"]  # "geral" para sentenças sem keyword específica

def processar_modelo(arquivo):
    try:
        with open(CAMINHO_JSON / arquivo, 'r', encoding='utf-8') as f:
            dados = json.load(f)
        
        # Tenta múltiplos campos para o nome do modelo
        modelo = (dados.get('modelo_busca_utilizado') or 
                 dados.get('modelo_original') or 
                 dados.get('modelo') or 
                 dados.get('id_notebook', '').replace('_', ' '))
        
        # Só pula se realmente não encontrou nenhum identificador
        if not modelo or str(modelo).lower() in ['nan', 'none', '']:
            print(f"⚠️ Modelo sem identificação: {arquivo}")
            return None
        
        # Coleta TODAS as sentenças
        all_fragments = []
        for post in dados.get('posts', []):
            # Título
            titulo = post.get('titulo', '')
            all_fragments.extend(extrair_sentencas(titulo))
            
            # Conteúdo do post
            conteudo = post.get('conteudo_post', '')
            all_fragments.extend(extrair_sentencas(conteudo))
            
            # Comentários
            for c in post.get('comentarios', []):
                comentario = str(c.get('conteudo', ''))
                all_fragments.extend(extrair_sentencas(comentario))
        
        # Se não encontrou nenhuma sentença válida, pula
        if len(all_fragments) < 3:  # Mínimo de 3 sentenças para ser significativo
            return None
        
        # Limita a 500 sentenças por modelo para evitar estouro de memória
        if len(all_fragments) > 500:
            # Amostragem estratificada: pega primeiras 100, meio 200, últimas 200
            n = len(all_fragments)
            indices = list(range(min(100, n))) + \
                     list(range(n//2 - 100, n//2 + 100)) + \
                     list(range(max(0, n-200), n))
            indices = sorted(set(i for i in indices if 0 <= i < n))
            all_fragments = [all_fragments[i] for i in indices[:500]]
        
        # Inferência em Lote
        try:
            resultados = sentiment_task(all_fragments, truncation=True, max_length=512)
        except Exception as e:
            print(f"❌ Erro na inferência do modelo {modelo}: {e}")
            return None
        
        res_modelo = {
            "modelo": str(modelo)[:100],  # Limita tamanho do nome
            "n_posts": len(dados.get('posts', [])),
            "sentencas_analisadas": len(all_fragments),
            "negativos_criticos": 0,
            "negativos_total": 0,
            "positivos": 0,
            **{tema: 0 for tema in SEARCH_GROUPS},
            "geral": 0  # Sentenças negativas sem keyword específica
        }
        
        for i, res in enumerate(resultados):
            if res['label'].lower() == 'negative':
                res_modelo["negativos_total"] += 1
                
                # Threshold de confiança (85% para alta confiança)
                if res['score'] >= 0.85:
                    res_modelo["negativos_criticos"] += 1
                    
                    # Classifica temas
                    temas = classificar_temas(all_fragments[i])
                    for tema in temas:
                        if tema in res_modelo:
                            res_modelo[tema] += 1
            else:
                res_modelo["positivos"] += 1
        
        return res_modelo
        
    except Exception as e:
        print(f"❌ Erro processando {arquivo}: {str(e)[:100]}")
        return None

def gerar_relatorio_final(df):
    """Gera o relatório estatístico completo"""
    hoje = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    # Cálculos
    df['gravidade_percentual'] = (df['negativos_criticos'] / df['sentencas_analisadas'] * 100).round(2)
    df['taxa_negatividade'] = (df['negativos_total'] / df['sentencas_analisadas'] * 100).round(2)
    
    temas = list(SEARCH_GROUPS.keys()) + ['geral']
    total_reclamacoes = df['negativos_criticos'].sum()
    
    relatorio = [
        f"# Relatório de Auditoria de Sentimento - RoBERTa V8 (CORRIGIDO)\n",
        f"**Data da Execução:** {hoje}\n",
        f"**Metodologia:** Classificação via RoBERTa com threshold de confiança ≥ 0.85\n",
        f"**Correções Aplicadas:**",
        f"- Removido filtro de keywords na extração de sentenças",
        f"- Adicionado fallback para nome do modelo",
        f"- Adicionado limite de 500 sentenças/modelo para performance",
        f"- Adicionada categoria 'geral' para sentenças sem keyword específica\n",
        f"## 📊 Estatísticas Gerais\n",
        f"- **Total de Modelos Analisados:** {len(df)}\n",
        f"- **Total de Sentenças Processadas:** {df['sentencas_analisadas'].sum():,}\n",
        f"- **Total de Sentenças Negativas (qualquer confiança):** {df['negativos_total'].sum():,}\n",
        f"- **Total de Reclamações Negativas (alta confiança ≥ 0.85):** {total_reclamacoes:,}\n",
        f"- **Taxa Média de Negatividade:** {df['taxa_negatividade'].mean():.1f}%\n",
        f"\n## 📈 Top 15 Modelos Críticos (Ranking de Gravidade)\n",
        "| # | Modelo | Posts | Sentenças | Negativos (Alta Conf.) | Gravidade (%) | Taxa Neg. Total (%) |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |"
    ]
    
    top15 = df.nlargest(15, 'negativos_criticos')
    for i, (_, row) in enumerate(top15.iterrows(), 1):
        relatorio.append(
            f"| {i} | {row['modelo']} | {row['n_posts']} | {row['sentencas_analisadas']} | "
            f"{row['negativos_criticos']} | {row['gravidade_percentual']:.1f}% | {row['taxa_negatividade']:.1f}% |"
        )
    
    relatorio.append("\n## 📋 Distribuição Temática das Falhas (Alta Confiança)\n")
    relatorio.append("| Tema | Menções | % do Total |")
    relatorio.append("| :--- | :--- | :--- |")
    
    for tema in temas:
        total_tema = df[tema].sum()
        perc = (total_tema / total_reclamacoes * 100) if total_reclamacoes > 0 else 0
        relatorio.append(f"| {tema.capitalize()} | {total_tema:,} | {perc:.1f}% |")
    
    # Análise de correlação
    relatorio.append("\n## 📊 Análise de Correlação\n")
    if len(df) > 5:
        corr = df[['n_posts', 'sentencas_analisadas', 'negativos_criticos', 'gravidade_percentual']].corr()
        relatorio.append("### Correlação entre métricas:")
        relatorio.append(f"- Posts vs Sentenças Negativas: {corr.loc['n_posts', 'negativos_criticos']:.2f}")
        relatorio.append(f"- Sentenças vs Negativas: {corr.loc['sentencas_analisadas', 'negativos_criticos']:.2f}")
    
    # Salva arquivos
    with open(CAMINHO_SAIDA / "RELATORIO_AUDITORIA.md", "w", encoding="utf-8") as f:
        f.write("\n".join(relatorio))
    
    # Salva CSV completo
    cols_salvar = ['modelo', 'n_posts', 'sentencas_analisadas', 'negativos_total', 
                   'negativos_criticos', 'positivos', 'gravidade_percentual', 
                   'taxa_negatividade'] + temas
    df[cols_salvar].to_csv(CAMINHO_SAIDA / "metricas_completas_roberta.csv", 
                           index=False, sep=";", encoding='utf-8-sig')
    
    print(f"\n✅ Relatórios salvos em: {CAMINHO_SAIDA}")
    print(f"   - RELATORIO_AUDITORIA.md")
    print(f"   - metricas_completas_roberta.csv")

def main():
    arquivos = [f for f in os.listdir(CAMINHO_JSON) if f.endswith('.json')]
    print(f"📁 Total de arquivos JSON encontrados: {len(arquivos)}")
    
    resultados = []
    erros = 0
    vazios = 0
    
    for arq in tqdm(arquivos, desc="Processando Modelos (GPU)"):
        res = processar_modelo(arq)
        if res:
            if res['sentencas_analisadas'] > 0:
                resultados.append(res)
            else:
                vazios += 1
        else:
            erros += 1
    
    print(f"\n📊 Resumo do Processamento:")
    print(f"   - Total de arquivos: {len(arquivos)}")
    print(f"   - Modelos processados com sucesso: {len(resultados)}")
    print(f"   - Modelos sem sentenças válidas: {vazios}")
    print(f"   - Erros/pulados: {erros}")
    
    if resultados:
        df = pd.DataFrame(resultados)
        print(f"\n📊 Estatísticas dos dados processados:")
        print(f"   - Total de sentenças: {df['sentencas_analisadas'].sum():,}")
        print(f"   - Média de sentenças/modelo: {df['sentencas_analisadas'].mean():.0f}")
        print(f"   - Total negativos (alta conf.): {df['negativos_criticos'].sum():,}")
        print(f"   - Modelo com mais sentenças: {df.loc[df['sentencas_analisadas'].idxmax(), 'modelo']} ({df['sentencas_analisadas'].max()})")
        
        gerar_relatorio_final(df)
    else:
        print("❌ Nenhum modelo foi processado com sucesso!")

if __name__ == "__main__":
    main()