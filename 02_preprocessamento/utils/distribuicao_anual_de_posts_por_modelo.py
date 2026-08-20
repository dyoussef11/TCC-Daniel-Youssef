"""
Distribuição Temporal dos Posts
Analisa a quantidade de posts por ano (e por modelo) a partir dos dados JSON.
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

DATA_LIMITE = datetime(2026, 3, 31)

def extrair_data(post):
    campos_data = [
        'data_post',          # <-- prioridade máxima
        'data_postagem',
        'created_utc',
        'data_criacao',
        'timestamp',
        'date',
        'data'
    ]
    for campo in campos_data:
        valor = post.get(campo)
        if valor:
            try:
                if isinstance(valor, (int, float)):
                    if valor > 1e12:
                        valor = valor / 1000
                    return datetime.fromtimestamp(valor)
                elif isinstance(valor, str):
                    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%d/%m/%Y', '%Y-%m-%dT%H:%M:%S'):
                        try:
                            return datetime.strptime(valor, fmt)
                        except ValueError:
                            continue
            except Exception:
                continue
    return None

def processar_arquivo(arquivo):
    try:
        with open(CAMINHO_JSON / arquivo, 'r', encoding='utf-8') as f:
            dados = json.load(f)
        modelo = dados.get('modelo_original', 'desconhecido')
        posts = dados.get('posts', [])
        contagem = defaultdict(int)
        sem_data = 0
        ignorados_futuro = 0
        for post in posts:
            data = extrair_data(post)
            if data is None:
                sem_data += 1
                continue
            if data > DATA_LIMITE:
                ignorados_futuro += 1
                continue
            contagem[(modelo, data.year)] += 1
        return {
            'arquivo': arquivo,
            'contagem': dict(contagem),
            'sem_data': sem_data,
            'ignorados_futuro': ignorados_futuro,
            'total_posts': len(posts)
        }
    except Exception as e:
        return {'erro': True, 'arquivo': arquivo, 'mensagem': str(e)}

def analisar_distribuicao_temporal():
    arquivos = [f for f in os.listdir(CAMINHO_JSON) if f.endswith('.json')]
    print("="*70)
    print("📅 DISTRIBUIÇÃO TEMPORAL DOS POSTS")
    print("="*70)
    print(f"📁 Total de arquivos: {len(arquivos)}")
    print(f"📂 Diretório: {CAMINHO_JSON}")
    print(f"⏳ Data limite: {DATA_LIMITE.strftime('%B/%Y')}")
    print("="*70)
    
    resultados = []
    with ProcessPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(processar_arquivo, arq): arq for arq in arquivos}
        for future in tqdm(as_completed(futures), total=len(arquivos), desc="Processando"):
            resultado = future.result()
            if isinstance(resultado, dict) and not resultado.get('erro', False):
                resultados.append(resultado)
            elif isinstance(resultado, dict) and resultado.get('erro', False):
                print(f"⚠️ Erro no arquivo {resultado['arquivo']}: {resultado['mensagem']}")
    
    if not resultados:
        print("❌ Nenhum resultado válido!")
        return
    
    agregado = defaultdict(int)
    total_posts = 0
    total_sem_data = 0
    total_ignorados = 0
    for r in resultados:
        total_posts += r.get('total_posts', 0)
        total_sem_data += r.get('sem_data', 0)
        total_ignorados += r.get('ignorados_futuro', 0)
        for (modelo, ano), qtd in r.get('contagem', {}).items():
            agregado[(modelo, ano)] += qtd
    
    dados_agg = []
    for (modelo, ano), qtd in agregado.items():
        dados_agg.append({'modelo': modelo, 'ano': ano, 'quantidade': qtd})
    
    if not dados_agg:
        print("⚠️ Nenhum post com data válida encontrado!")
        return
    
    df = pd.DataFrame(dados_agg)
    total_por_ano = df.groupby('ano')['quantidade'].sum().reset_index()
    total_global = total_por_ano['quantidade'].sum()
    total_por_ano['percentual_global'] = (total_por_ano['quantidade'] / total_global * 100).round(1)
    
    total_por_modelo = df.groupby('modelo')['quantidade'].sum().reset_index().rename(columns={'quantidade': 'total_modelo'})
    df = df.merge(total_por_modelo, on='modelo')
    df['percentual_por_modelo'] = (df['quantidade'] / df['total_modelo'] * 100).round(1)
    df = df.sort_values(['modelo', 'ano'])
    
    df.to_csv(CAMINHO_SAIDA / "distribuicao_temporal_por_modelo.csv", index=False, sep=';', encoding='utf-8-sig')
    total_por_ano.to_csv(CAMINHO_SAIDA / "distribuicao_temporal_global.csv", index=False, sep=';', encoding='utf-8-sig')
    
    print("\n" + "="*70)
    print("📊 DISTRIBUIÇÃO TEMPORAL (GERAL)")
    print("="*70)
    for _, row in total_por_ano.iterrows():
        print(f"   {row['ano']}: {row['quantidade']:>8,} posts ({row['percentual_global']:>5.1f}%)")
    
    print("\n📈 RESUMO POR MODELO (top 5):")
    print("-"*70)
    top_modelos = total_por_modelo.sort_values('total_modelo', ascending=False).head(5)
    for _, row in top_modelos.iterrows():
        modelo = row['modelo']
        total = row['total_modelo']
        print(f"\n🔹 {modelo} ({total:,} posts)")
        sub = df[df['modelo'] == modelo].sort_values('ano')
        for _, r in sub.iterrows():
            print(f"      {r['ano']}: {r['quantidade']:>6,} posts ({r['percentual_por_modelo']:>5.1f}%)")
    
    print(f"\n✅ Arquivos salvos em: {CAMINHO_SAIDA}")
    return df, total_por_ano

if __name__ == "__main__":
    analisar_distribuicao_temporal()