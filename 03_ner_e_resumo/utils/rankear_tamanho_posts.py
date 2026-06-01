import json
from pathlib import Path
from tqdm import tqdm

# Importação seguindo a lógica do seu config.py
try:
    from core.paths import PREPROCESSAMENTO_DATA
    # DIR_ENTRADA = PREPROCESSAMENTO_DATA / 'Dados_Final_Threshold_V12'
    DIR_ENTRADA = PREPROCESSAMENTO_DATA / 'Dados_Limpos_IniciaisV10'
except ImportError:
    # Fallback caso execute fora do ambiente principal
    DIR_ENTRADA = Path("./data/Dados_Final_Threshold_V12")

def analisar_tamanho_base():
    ranking_geral = []

    # 1. Obter lista de arquivos
    arquivos = list(DIR_ENTRADA.glob("*.json"))
    
    if not arquivos:
        print(f"❌ Nenhum arquivo encontrado em: {DIR_ENTRADA}")
        return

    print(f"🔍 Analisando {len(arquivos)} arquivos em {DIR_ENTRADA}...")

    for arq_path in tqdm(arquivos, desc="Lendo arquivos"):
        try:
            with open(arq_path, 'r', encoding='utf-8') as f:
                dados = json.load(f)
            
            modelo_nome = dados.get('modelo_busca_utilizado', arq_path.stem)
            posts = dados.get('posts', [])

            for post in posts:
                p_id = post.get('id', 'N/A')
                titulo = post.get('titulo', '')
                corpo = post.get('conteudo_post', '')
                
                # Soma o conteúdo de todos os comentários
                comentarios_texto = "".join([c.get('conteudo', '') for c in post.get('comentarios', [])])
                
                total_caracteres = len(titulo) + len(corpo) + len(comentarios_texto)
                
                ranking_geral.append({
                    "id": p_id,
                    "modelo": modelo_nome,
                    "arquivo": arq_path.name,
                    "tamanho": total_caracteres,
                    "n_comentarios": len(post.get('comentarios', []))
                })
        except Exception as e:
            print(f"⚠️ Erro ao processar {arq_path.name}: {e}")

    # 2. Ordenar pelo tamanho (do maior para o menor)
    ranking_geral.sort(key=lambda x: x['tamanho'], reverse=True)

    # 3. Exibir Resultados
    print("\n" + "="*80)
    print(f"{'RANK':<5} | {'ID POST':<15} | {'TAMANHO (Chars)':<15} | {'MODELO'}")
    print("-" * 80)
    
    # Exibe o Top 20 posts mais pesados
    for i, item in enumerate(ranking_geral[:20], 1):
        print(f"{i:<5} | {str(item['id']):<15} | {item['tamanho']:<15,} | {item['modelo'][:35]}")
    
    print("="*80)
    
    # Estatísticas Rápidas
    if ranking_geral:
        media = sum(item['tamanho'] for item in ranking_geral) / len(ranking_geral)
        print(f"📊 Total de Posts Analisados: {len(ranking_geral)}")
        print(f"📈 Média de Caracteres por Post: {media:.0f}")
        print(f"🔝 Post mais pesado: {ranking_geral[0]['tamanho']:,} caracteres")

if __name__ == "__main__":
    analisar_tamanho_base()