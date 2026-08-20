"""
Dimensão Temporal por Modelo
Calcula, para cada modelo, o período de atividade (primeiro post, último post, último comentário)
e a duração em dias.
"""

import os
import json
from datetime import datetime
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
import pandas as pd
from tqdm import tqdm

from core.paths import PREPROCESSAMENTO_DATA

# ============ CONFIGURAÇÕES ============
CAMINHO_JSON = PREPROCESSAMENTO_DATA / "Dados_Limpos_IniciaisV12"
CAMINHO_SAIDA = PREPROCESSAMENTO_DATA / 'analises_dados' / "analise_temporal"
CAMINHO_SAIDA.mkdir(parents=True, exist_ok=True)


def extrair_timestamp(post):
    """
    Extrai o timestamp do post a partir do campo 'data_post'.
    Retorna timestamp (float) ou None.
    """
    valor = post.get('data_post')
    if valor is None:
        return None
    try:
        # Se for string, tenta converter para float
        if isinstance(valor, str):
            valor = float(valor)
        # Se for int/float, já é timestamp
        if isinstance(valor, (int, float)):
            # Se > 1e12, são milissegundos
            if valor > 1e12:
                valor = valor / 1000
            return float(valor)
    except Exception:
        pass
    return None


def extrair_timestamp_comentario(comentario):
    """
    Extrai o timestamp do comentário a partir do campo 'data_comentario'.
    """
    valor = comentario.get('data_comentario')
    if valor is None:
        return None
    try:
        if isinstance(valor, str):
            valor = float(valor)
        if isinstance(valor, (int, float)):
            if valor > 1e12:
                valor = valor / 1000
            return float(valor)
    except Exception:
        pass
    return None


def processar_arquivo(arquivo):
    """
    Processa um arquivo e retorna, para cada modelo, listas de timestamps
    de posts e de comentários (para encontrar min/max).
    """
    try:
        with open(CAMINHO_JSON / arquivo, 'r', encoding='utf-8') as f:
            dados = json.load(f)

        modelo = dados.get('modelo_original', 'desconhecido')
        posts = dados.get('posts', [])

        posts_ts = []
        comentarios_ts = []

        for post in posts:
            ts_post = extrair_timestamp(post)
            if ts_post is not None:
                posts_ts.append(ts_post)

            # Comentários
            for coment in post.get('comentarios', []):
                ts_coment = extrair_timestamp_comentario(coment)
                if ts_coment is not None:
                    comentarios_ts.append(ts_coment)

        return {
            'modelo': modelo,
            'posts_ts': posts_ts,
            'comentarios_ts': comentarios_ts,
            'total_posts': len(posts),
            'total_comentarios': sum(len(p.get('comentarios', [])) for p in posts)
        }

    except Exception as e:
        return {'erro': True, 'arquivo': arquivo, 'mensagem': str(e)}


def analisar_dimensao_temporal():
    """
    Função principal que agrega por modelo e gera o CSV.
    """
    arquivos = [f for f in os.listdir(CAMINHO_JSON) if f.endswith('.json')]

    print("="*70)
    print("📅 DIMENSÃO TEMPORAL POR MODELO")
    print("="*70)
    print(f"📁 Total de arquivos: {len(arquivos)}")
    print("="*70)

    # Agrupa resultados por modelo
    dados_modelo = defaultdict(lambda: {
        'posts_ts': [],
        'comentarios_ts': [],
        'total_posts': 0,
        'total_comentarios': 0
    })

    # Processa arquivos em paralelo
    with ProcessPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(processar_arquivo, arq): arq for arq in arquivos}
        for future in tqdm(as_completed(futures), total=len(arquivos), desc="Processando"):
            resultado = future.result()
            if isinstance(resultado, dict) and not resultado.get('erro', False):
                modelo = resultado['modelo']
                dados_modelo[modelo]['posts_ts'].extend(resultado['posts_ts'])
                dados_modelo[modelo]['comentarios_ts'].extend(resultado['comentarios_ts'])
                dados_modelo[modelo]['total_posts'] += resultado['total_posts']
                dados_modelo[modelo]['total_comentarios'] += resultado['total_comentarios']
            elif isinstance(resultado, dict) and resultado.get('erro', False):
                print(f"⚠️ Erro no arquivo {resultado['arquivo']}: {resultado['mensagem']}")

    if not dados_modelo:
        print("❌ Nenhum dado processado!")
        return

    # Monta lista para DataFrame
    linhas = []
    for modelo, dados in dados_modelo.items():
        posts_ts = dados['posts_ts']
        comentarios_ts = dados['comentarios_ts']

        # Datas mínimas e máximas
        primeiro_post = min(posts_ts) if posts_ts else None
        ultimo_post = max(posts_ts) if posts_ts else None
        ultimo_comentario = max(comentarios_ts) if comentarios_ts else None

        # Converte para datetime para exibição
        def ts_to_str(ts):
            return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S') if ts else None

        # Calcula duração em dias (entre primeiro post e último comentário, se disponível)
        if primeiro_post and ultimo_comentario:
            duracao_dias = (ultimo_comentario - primeiro_post) / 86400
        elif primeiro_post and ultimo_post:
            duracao_dias = (ultimo_post - primeiro_post) / 86400
        else:
            duracao_dias = None

        linhas.append({
            'modelo': modelo,
            'primeiro_post': ts_to_str(primeiro_post),
            'ultimo_post': ts_to_str(ultimo_post),
            'ultimo_comentario': ts_to_str(ultimo_comentario),
            'duracao_dias': round(duracao_dias, 1) if duracao_dias is not None else None,
            'total_posts': dados['total_posts'],
            'total_comentarios': dados['total_comentarios'],
            'qtd_posts_com_data': len(posts_ts),
            'qtd_comentarios_com_data': len(comentarios_ts)
        })

    df = pd.DataFrame(linhas)

    # Ordena por duração (decrescente)
    df = df.sort_values('duracao_dias', ascending=False, na_position='last')

    # Salva CSV
    df.to_csv(
        CAMINHO_SAIDA / "dimensao_temporal_por_modelo.csv",
        index=False, sep=';', encoding='utf-8-sig'
    )

    # ============ RELATÓRIO ============
    print("\n" + "="*70)
    print("📊 DIMENSÃO TEMPORAL - RESUMO")
    print("="*70)
    # Exibe os 10 modelos com maior duração
    top_duracao = df.dropna(subset=['duracao_dias']).head(10)
    if not top_duracao.empty:
        print("\n🏆 Top 10 modelos por duração (dias entre primeiro post e último comentário):")
        for _, row in top_duracao.iterrows():
            print(f"   {row['modelo']:<40} | {row['duracao_dias']:>8.1f} dias | {row['total_posts']:>3} posts | {row['total_comentarios']:>4} comentários")

    print("\n📊 Estatísticas gerais:")
    print(f"   Total de modelos analisados: {len(df)}")
    print(f"   Modelos com pelo menos um post com data: {df['qtd_posts_com_data'].gt(0).sum()}")
    print(f"   Modelos com pelo menos um comentário com data: {df['qtd_comentarios_com_data'].gt(0).sum()}")

    print(f"\n✅ Arquivo salvo: {CAMINHO_SAIDA / 'dimensao_temporal_por_modelo.csv'}")

    return df


if __name__ == "__main__":
    analisar_dimensao_temporal()