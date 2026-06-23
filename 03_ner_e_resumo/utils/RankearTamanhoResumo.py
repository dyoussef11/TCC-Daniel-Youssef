import json
from pathlib import Path
from charset_normalizer import detect
from tqdm import tqdm

from core.paths import NER_DATA

try:
    from core.paths import NER_DATA
    DIR_ENTRADA = NER_DATA / 'Base_Conhecimento_ResumidaV13_VERIFICADA'
except ImportError:
    DIR_ENTRADA = Path("./data/Dados_Final_Threshold_V12")

def analisar_tamanho_base():
    ranking_geral = []
    arquivos = list(DIR_ENTRADA.glob("*.json"))
    
    if not arquivos:
        print(f"❌ Nenhum arquivo encontrado em: {DIR_ENTRADA}")
        return

    print(f"🔍 Analisando {len(arquivos)} arquivos em {DIR_ENTRADA}...")

    for arq_path in tqdm(arquivos, desc="Lendo arquivos"):
        try:
            with open(arq_path, 'r', encoding='utf-8') as f:
                dados = json.load(f)
            
            modelo_nome = dados.get('id_notebook', arq_path.stem)
            posts = dados.get('posts', [])

            for post in posts:
                p_id = post.get('id', 'N/A')
                # --- Contagem da análise da IA ---
                analise_ia = post.get('analise_ia')
                if analise_ia:
                    # Se for uma lista de análises, converte tudo para string JSON
                    if isinstance(analise_ia, list):
                        analise_text = json.dumps(analise_ia, ensure_ascii=False)
                    else:
                        analise_text = json.dumps(analise_ia, ensure_ascii=False)
                    tamanho_analise = len(analise_text)
                else:
                    tamanho_analise = 0

                total_caracteres = (
                    tamanho_analise
                )
                
                ranking_geral.append({
                    "id": p_id,
                    "modelo": modelo_nome,
                    "arquivo": arq_path.name,
                    "tamanho_analise": tamanho_analise,
                    "tamanho_total": total_caracteres,
                    "n_comentarios": len(post.get('comentarios', []))
                })
        except Exception as e:
            print(f"⚠️ Erro ao processar {arq_path.name}: {e}")

    # Ordenar pelo tamanho total (do maior para o menor)
    ranking_geral.sort(key=lambda x: x['tamanho_total'], reverse=True)

    # Exibir os 20 maiores posts
    print("\n" + "="*100)
    print(f"{'RANK':<5} | {'ID POST':<15} | {'TAMANHO TOTAL':<15} | {'TAM. ANÁLISE':<13} | {'#COMENT':<8} | {'MODELO'}")
    print("-" * 100)
    
    for i, item in enumerate(ranking_geral[:50], 1):
        print(f"{i:<5} | {str(item['id']):<15} | {item['tamanho_total']:<15,} | {item['tamanho_analise']:<13,} | {item['n_comentarios']:<8} | {item['modelo'][:35]}")
    
    print("="*100)
    
    # Estatísticas
    if ranking_geral:
        total_posts = len(ranking_geral)
        media_total = sum(item['tamanho_total'] for item in ranking_geral) / total_posts
        media_analise = sum(item['tamanho_analise'] for item in ranking_geral) / total_posts
        print(f"📊 Total de Posts Analisados: {total_posts}")
        print(f"📈 Média de Caracteres por Post (total): {media_total:.0f}")
        print(f"📈 Média de Caracteres da análise IA: {media_analise:.0f}")
        print(f"🔝 Post mais pesado: {ranking_geral[0]['tamanho_total']:,} caracteres (análise: {ranking_geral[0]['tamanho_analise']:,})")

if __name__ == "__main__":
    analisar_tamanho_base()