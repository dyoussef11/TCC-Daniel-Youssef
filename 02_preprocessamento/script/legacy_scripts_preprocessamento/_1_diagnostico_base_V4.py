import os
import json
import pandas as pd
from tqdm import tqdm
from collections import Counter
from core.paths import PREPROCESSAMENTO_DATA

CAMINHO_JSON = PREPROCESSAMENTO_DATA / "Dados_Limpos_IniciaisV7"
CAMINHO_SAIDA = PREPROCESSAMENTO_DATA / "informacoes_iniciais2"
CAMINHO_SAIDA.mkdir(parents=True, exist_ok=True)

def analisar_base_bruta():
    stats = []
    arquivos = [f for f in os.listdir(CAMINHO_JSON) if f.endswith('.json')]
    
    print(f"🔍 Analisando {len(arquivos)} arquivos JSON...")
    
    for arq in tqdm(arquivos):
        with open(CAMINHO_JSON / arq, 'r', encoding='utf-8') as f:
            dados = json.load(f)
        
        modelo = dados.get('"modelo_original', 'desconhecido')
        posts = dados.get('posts', [])
        
        total_comentarios = sum(len(p.get('comentarios', [])) for p in posts)
        
        # Contagem simples de texto
        corpo_texto = ""
        for p in posts:
            corpo_texto += f" {p.get('titulo', '')} {p.get('conteudo_post', '')}"
            for c in p.get('comentarios', []):
                corpo_texto += f" {c.get('conteudo', '')}"
        
        stats.append({
            'modelo': modelo,
            'n_posts': len(posts),
            'n_comentarios': total_comentarios,
            'total_caracteres': len(corpo_texto),
            'estimativa_sentencas': corpo_texto.count('.') + corpo_texto.count('?')
        })

    df = pd.DataFrame(stats)
    
    print("\n" + "="*50)
    print("📊 RESULTADOS BÁSICOS DA BASE V3")
    print("="*50)
    print(f"Total de Modelos (SKUs): {len(df)}")
    print(f"Total de Posts: {df['n_posts'].sum()}")
    print(f"Modelo com MAIOR volume: {df.nlargest(1, 'n_posts')['modelo'].values[0]} ({df['n_posts'].max()} posts)")
    print(f"Modelo com MENOR volume: {df.nsmallest(1, 'n_posts')['modelo'].values[0]} ({df['n_posts'].min()} posts)")
    print(f"Mediana de posts por modelo: {df['n_posts'].median()}")
    
    # Salva para usarmos no próximo passo
    df.to_csv(CAMINHO_SAIDA / "diagnostico_base_v3.csv", index=False, sep=';')
    return df

if __name__ == "__main__":
    analisar_base_bruta()