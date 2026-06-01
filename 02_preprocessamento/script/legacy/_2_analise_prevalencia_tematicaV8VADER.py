import os
import json
import pandas as pd
import numpy as np
import re
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm

from core.paths import PREPROCESSAMENTO_DATA, EXTRACAO_DATA

# ============ CONFIGURAÇÕES ============
# Agora apontamos para os dados limpos com placeholders
CAMINHO_JSON = PREPROCESSAMENTO_DATA / "Dados_Limpos_IniciaisV5"
CAMINHO_SAIDA = PREPROCESSAMENTO_DATA / "Analise_Vader_V7_INTEGRADA"
CAMINHO_SAIDA.mkdir(parents=True, exist_ok=True)

analyzer = SentimentIntensityAnalyzer()

def calcular_sentimento_especifico(texto, termos, threshold=-0.15):
    """
    Analisa o sentimento apenas no entorno dos termos que 
    causaram a captura do post.
    """
    if not texto or not termos:
        return 0, []

    mencoes_criticas = 0
    scores_encontrados = []

    for termo in termos:
        # Busca exata do termo técnico (case insensitive)[cite: 16]
        for match in re.finditer(rf"\b{re.escape(termo)}\b", texto, re.IGNORECASE):
            # Janela de contexto de 120 caracteres para capturar adjetivos[cite: 16]
            start = max(0, match.start() - 120)
            end = min(len(texto), match.end() + 120)
            contexto = texto[start:end]
            
            score = analyzer.polarity_scores(contexto)['compound']
            scores_encontrados.append(score)
            
            # Se o score for menor que o threshold, validamos como 'Crítico'[cite: 16]
            if score <= threshold:
                mencoes_criticas += 1
                
    return mencoes_criticas, scores_encontrados

def processar_arquivo(arquivo):
    """Processa um arquivo JSON de notebook individual[cite: 14]."""
    try:
        with open(CAMINHO_JSON / arquivo, 'r', encoding='utf-8') as f:
            dados = json.load(f)
        
        modelo = dados.get('modelo_original')
        id_notebook = dados.get('id_notebook')
        posts = dados.get('posts', [])
        
        # Estrutura base de resposta por modelo[cite: 16]
        res = {
            "id_notebook": id_notebook,
            "modelo": modelo,
            "total_posts_processados": len(posts),
            "mencoes_criticas_totais": 0,
            "score_medio_geral": 0.0,
            "detalhe_por_categoria": {}
        }
        
        all_scores = []
        categorias_vistas = set()

        for post in posts:
            cat = post.get('categoria', 'unassigned')
            termos = post.get('termos_especificos', [])
            categorias_vistas.add(cat)

            if cat not in res["detalhe_por_categoria"]:
                res["detalhe_por_categoria"][cat] = {"criticos": 0, "scores": []}

            # 1. Analisa Título e Conteúdo do Post
            txt_post = f"{post.get('titulo')} {post.get('conteudo_post')}"
            criticos_p, scores_p = calcular_sentimento_especifico(txt_post, termos)
            
            # 2. Analisa Comentários[cite: 14]
            criticos_c = 0
            scores_c = []
            for coment in post.get('comentarios', []):
                c_crit, c_scores = calcular_sentimento_especifico(coment['conteudo'], termos)
                criticos_c += c_crit
                scores_c.extend(c_scores)

            # Acumula resultados[cite: 16]
            total_criticos = criticos_p + criticos_c
            res["detalhe_por_categoria"][cat]["criticos"] += total_criticos
            res["detalhe_por_categoria"][cat]["scores"].extend(scores_p + scores_c)
            
            res["mencoes_criticas_totais"] += total_criticos
            all_scores.extend(scores_p + scores_c)

        # Finaliza médias e limpa listas para o CSV final
        res["score_medio_geral"] = np.mean(all_scores) if all_scores else 0.0
        res["diversidade_temas"] = len(categorias_vistas)
        
        # Flatten para o DataFrame (facilita salvar em CSV)
        for cat in res["detalhe_por_categoria"]:
            res[f"criticos_{cat}"] = res["detalhe_por_categoria"][cat]["criticos"]
            res[f"score_{cat}"] = np.mean(res["detalhe_por_categoria"][cat]["scores"]) if res["detalhe_por_categoria"][cat]["scores"] else 0.0
        
        del res["detalhe_por_categoria"] # Remove o dicionário aninhado
        return res

    except Exception as e:
        return f"Erro em {arquivo}: {e}"

def executar_analise_v7():
    arquivos = [f for f in os.listdir(CAMINHO_JSON) if f.endswith('.json')]
    
    print(f"📊 Iniciando Análise VADER V7 em {len(arquivos)} modelos...")
    print(f"   (Foco: Validação de Sentimento em Termos Técnicos Garantidos)")

    resultados = []
    with ProcessPoolExecutor() as executor:
        futures = {executor.submit(processar_arquivo, arq): arq for arq in arquivos}
        for future in tqdm(as_completed(futures), total=len(arquivos), desc="Analisando Sentimento"):
            res = future.result()
            if isinstance(res, dict):
                resultados.append(res)

    # Salva os resultados[cite: 16]
    df = pd.DataFrame(resultados).fillna(0)
    df.to_csv(CAMINHO_SAIDA / "analise_vader_integrada_v7.csv", index=False, sep=';', encoding='utf-8-sig')
    
    print(f"\n✅ Análise concluída! Resultados em: {CAMINHO_SAIDA}")

if __name__ == "__main__":
    executar_analise_v7()