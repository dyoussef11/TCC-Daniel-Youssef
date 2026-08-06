from core.paths import PREPROCESSAMENTO_DATA
import json
from pathlib import Path

LIMITE = 30  # máximo de comentários por post
CHAVE_POSTS = 'posts'  # se o JSON for um dict com essa chave
CHAVE_COMENTARIOS = 'comentarios'  # chave dentro de cada post para comentários

def processar(dados):
    posts = 0
    comentarios = 0
    if isinstance(dados, dict):
        # Se tem chave de posts, usa
        if CHAVE_POSTS in dados and isinstance(dados[CHAVE_POSTS], list):
            lista = dados[CHAVE_POSTS]
            posts = len(lista)
            for item in lista:
                if isinstance(item, dict):
                    # procura por comentários
                    for chave in [CHAVE_COMENTARIOS, 'comments', 'comentarios', 'respostas']:
                        if chave in item and isinstance(item[chave], list):
                            comentarios += min(len(item[chave]), LIMITE)
                            break
            return posts, comentarios
        else:
            # Tenta recursivamente em cada valor
            for v in dados.values():
                p, c = processar(v)
                posts += p
                comentarios += c
            return posts, comentarios
    elif isinstance(dados, list):
        # Assume que a lista contém posts (se for o caso)
        # Mas só faz isso se não houver um dict com chave de posts no nível superior
        # Se chegou aqui, é porque o JSON é uma lista diretamente
        posts = len(dados)
        for item in dados:
            if isinstance(item, dict):
                for chave in [CHAVE_COMENTARIOS, 'comments', 'comentarios', 'respostas']:
                    if chave in item and isinstance(item[chave], list):
                        comentarios += min(len(item[chave]), LIMITE)
                        break
        return posts, comentarios
    else:
        return 0, 0

def main():
    caminho = PREPROCESSAMENTO_DATA / "Dados_Limpos_IniciaisV12"
    if not caminho.exists():
        print("Caminho não existe")
        return
    if caminho.is_dir():
        total_posts = 0
        total_comentarios = 0
        for arq in caminho.glob("*.json"):
            with open(arq) as f:
                dados = json.load(f)
            p, c = processar(dados)
            total_posts += p
            total_comentarios += c
            print(f"{arq.name}: {p} posts, {c} comentários")
        print(f"Total: {total_posts} posts, {total_comentarios} comentários")
    else:
        with open(caminho) as f:
            dados = json.load(f)
        p, c = processar(dados)
        print(f"Posts: {p}, Comentários: {c}")

if __name__ == "__main__":
    main()