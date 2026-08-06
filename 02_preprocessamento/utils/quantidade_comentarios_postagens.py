from core.paths import PREPROCESSAMENTO_DATA
import json
from pathlib import Path

# ========== NOMES DAS CHAVES (ajuste aqui se necessário) ==========
CHAVES_POSTS = ['posts', 'postagens', 'publicacoes', 'topicos']
CHAVES_COMENTARIOS = ['comments', 'comentarios', 'respostas', 'replies']
TIPOS_POST = ['post', 'postagem', 'publicacao', 'topico']
TIPOS_COMENTARIO = ['comment', 'comentario', 'resposta', 'reply']

def contar_posts_e_comentarios(dados):
    """
    Retorna uma tupla (total_posts, total_comentarios) percorrendo a estrutura recursivamente.
    """
    posts = 0
    comentarios = 0

    if isinstance(dados, dict):
        # 1) Procura por chaves específicas de posts e comentários no nível atual
        chave_posts = None
        chave_comentarios = None

        for key in dados.keys():
            if key.lower() in CHAVES_POSTS:
                chave_posts = key
            if key.lower() in CHAVES_COMENTARIOS:
                chave_comentarios = key

        # Se achou uma lista de posts, conta os posts e os comentários internos
        if chave_posts and isinstance(dados[chave_posts], list):
            lista_posts = dados[chave_posts]
            posts += len(lista_posts)
            for post in lista_posts:
                if isinstance(post, dict):
                    for k in CHAVES_COMENTARIOS:
                        if k in post and isinstance(post[k], list):
                            comentarios += len(post[k])

        # Se achou uma lista de comentários separada, soma
        if chave_comentarios and isinstance(dados[chave_comentarios], list):
            comentarios += len(dados[chave_comentarios])

        # Se não achou nenhuma chave específica, desce recursivamente nos valores
        if not chave_posts and not chave_comentarios:
            for valor in dados.values():
                p, c = contar_posts_e_comentarios(valor)
                posts += p
                comentarios += c

        return posts, comentarios

    elif isinstance(dados, list):
        if not dados:
            return 0, 0

        primeiro = dados[0]

        # 2) Caso: lista de dicionários com campo "tipo"
        if isinstance(primeiro, dict) and all(isinstance(item, dict) for item in dados):
            tem_tipo = any('tipo' in item for item in dados)
            if tem_tipo:
                for item in dados:
                    tipo = item.get('tipo', '').lower()
                    if tipo in TIPOS_POST:
                        posts += 1
                        # Comentários podem estar aninhados dentro do post
                        for k in CHAVES_COMENTARIOS:
                            if k in item and isinstance(item[k], list):
                                comentarios += len(item[k])
                    elif tipo in TIPOS_COMENTARIO:
                        comentarios += 1
                return posts, comentarios

            # 3) Caso: lista de posts, cada um com uma lista interna de comentários
            tem_comentario_interno = any(
                any(k in item for k in CHAVES_COMENTARIOS) for item in dados
            )
            if tem_comentario_interno:
                posts += len(dados)
                for item in dados:
                    for k in CHAVES_COMENTARIOS:
                        if k in item and isinstance(item[k], list):
                            comentarios += len(item[k])
                return posts, comentarios

        # 4) Fallback: percorre cada item da lista recursivamente
        for item in dados:
            if isinstance(item, (dict, list)):
                p, c = contar_posts_e_comentarios(item)
                posts += p
                comentarios += c
            else:
                # Se for um item simples (string, número), conta como comentário
                comentarios += 1

        return posts, comentarios

    # Se não for dict nem list, ignora (não conta)
    return 0, 0


def main():
    caminho = PREPROCESSAMENTO_DATA / "Dados_Limpos_IniciaisV12"

    if not caminho.exists():
        print(f"Erro: Caminho não encontrado: {caminho}")
        return

    total_posts = 0
    total_comentarios = 0
    arquivos_processados = []

    # Se for um diretório, processa todos os .json
    if caminho.is_dir():
        arquivos = list(caminho.glob("*.json"))
        if not arquivos:
            print(f"Nenhum arquivo .json encontrado em {caminho}")
            return

        print(f"📁 Diretório encontrado. Processando {len(arquivos)} arquivo(s)...\n")
        for arq in arquivos:
            try:
                with open(arq, 'r', encoding='utf-8') as f:
                    dados = json.load(f)
                p, c = contar_posts_e_comentarios(dados)
                total_posts += p
                total_comentarios += c
                arquivos_processados.append((arq.name, p, c))
            except Exception as e:
                print(f"  ❌ Erro ao ler {arq.name}: {e}")

        # Resumo por arquivo
        print("📄 Detalhamento por arquivo:")
        for nome, p, c in arquivos_processados:
            print(f"  {nome}: {p} post(s) e {c} comentário(s)")
        print(f"\n✅ TOTAL GERAL:")
        print(f"   Posts: {total_posts}")
        print(f"   Comentários: {total_comentarios}")

    # Se for um arquivo, processa apenas ele
    elif caminho.is_file():
        try:
            with open(caminho, 'r', encoding='utf-8') as f:
                dados = json.load(f)
        except Exception as e:
            print(f"Erro ao ler arquivo: {e}")
            return

        # Mostra um resumo da estrutura para ajudar na depuração
        if isinstance(dados, dict):
            print("🔍 Estrutura do JSON (chaves principais):")
            for chave in list(dados.keys())[:10]:  # mostra até 10 chaves
                print(f"  - {chave} ({type(dados[chave]).__name__})")
            print()

        posts, comentarios = contar_posts_e_comentarios(dados)
        print(f"✅ RESULTADO:")
        print(f"   Total de Posts: {posts}")
        print(f"   Total de Comentários: {comentarios}")

    else:
        print("O caminho não é um arquivo nem um diretório válido.")


if __name__ == "__main__":
    main()