import ijson
from pathlib import Path

from core.paths import PREPROCESSAMENTO_DATA
# --- CONFIGURAÇÃO DE CAMINHOS (Ajuste conforme sua estrutura) ---
# Se o arquivo estiver na mesma pasta:
CAMINHO_ENTRADA = PREPROCESSAMENTO_DATA / 'reddit_notebook_dados_limpos.json'

def analisar_extensao_caracteres(caminho_json):
    if not caminho_json.exists():
        print(f"❌ Arquivo não encontrado: {caminho_json}")
        return

    maior_extensao = 0
    post_id_maior = ""
    total_posts = 0
    acumulado_caracteres = 0

    print(f"🔍 Analisando extensões de texto em: {caminho_json.name}...")

    try:
        with open(caminho_json, 'rb') as f:
            # Itera sobre os objetos da lista principal
            objetos = ijson.items(f, 'item')
            
            for item in objetos:
                posts = item.get('posts', [])
                for post in posts:
                    total_posts += 1
                    
                    # Simula a montagem do conteúdo que vai para o prompt:
                    titulo = post.get('titulo_limpo', '')
                    corpo = post.get('conteudo_texto_limpo', '')
                    # Limitamos aos 10 primeiros conforme seu script original
                    comentarios = post.get('comentarios', [])[:10]
                    texto_comentarios = "\n".join([c.get('conteudo_limpo', '') for c in comentarios])
                    
                    # Conteúdo total concatenado
                    conteudo_full = f"{titulo} {corpo} {texto_comentarios}"
                    tamanho_atual = len(conteudo_full)
                    
                    acumulado_caracteres += tamanho_atual
                    
                    if tamanho_atual > maior_extensao:
                        maior_extensao = tamanho_atual
                        post_id_maior = post.get('id', 'N/A')

        if total_posts > 0:
            media = acumulado_caracteres / total_posts
            print("\n" + "="*40)
            print("📊 RESULTADO DA ANÁLISE DE CONTEXTO")
            print("="*40)
            print(f"✅ Total de posts analisados: {total_posts}")
            print(f"🔥 Maior post (caracteres):   {maior_extensao:,}")
            print(f"📝 Média de caracteres:      {media:.2f}")
            print(f"🆔 ID do maior post:         {post_id_maior}")
            print("-"*40)
            
            # Estimativa de Tokens (Média de 1 token ~ 4 caracteres para inglês/código)
            est_tokens = maior_extensao / 3.5
            print(f"🧮 Estimativa de Tokens (Pior Caso): ~{int(est_tokens)} tokens")
            
            if est_tokens > 32000:
                print("\n⚠️ ALERTA: O maior post pode exceder limites de contexto padrão de alguns SLMs!")
            else:
                print("\n💡 DICA: O Qwen costuma lidar bem com até 32k ou 128k de contexto, "
                      "então deve processar tranquilamente.")
            print("="*40)

    except Exception as e:
        print(f"❌ Erro ao processar: {e}")

if __name__ == "__main__":
    analisar_extensao_caracteres(CAMINHO_ENTRADA)