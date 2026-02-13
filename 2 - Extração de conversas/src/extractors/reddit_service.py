import praw
import time
import datetime
import os
import sys
from pathlib import Path
import configparser

# --- BOOTSTRAP DE CAMINHO DO PROJETO ---
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.paths import (


EXTRACAO_SRC_EXTRACTORS,
EXTRACAO_SRC,
EXTRACAO

)

from core_extration.base_extractor import BaseExtractor

class RedditService(BaseExtractor):
    def __init__(self):
        super().__init__(platform="reddit")
        
        # 1. Localização do arquivo praw.ini usando suas variáveis de path
        caminho_ini = EXTRACAO_SRC_EXTRACTORS / "praw.ini"
        
        # 2. Leitura manual das configurações para evitar erros de ambiente
        config_pra = configparser.ConfigParser()
        if not caminho_ini.exists():
            raise FileNotFoundError(f"Arquivo não encontrado em: {caminho_ini}")
            
        config_pra.read(caminho_ini, encoding='utf-8')

        try:
            # 3. Passagem direta das credenciais para o PRAW
            # Isso ignora qualquer necessidade de variáveis de ambiente
            self.reddit = praw.Reddit(
                client_id=config_pra['DEFAULT']['client_id'],
                client_secret=config_pra['DEFAULT']['client_secret'],
                user_agent=config_pra['DEFAULT']['user_agent']
            )
            
            self.params = self.config["reddit_params"]
            
        except KeyError as e:
            raise Exception(f"Chave {e} não encontrada no praw.ini. Verifique o cabeçalho [DEFAULT].")
        except Exception as e:
            raise Exception(f"Falha na autenticação do Reddit: {e}")

    def buscar_modelo(self, modelo_busca):
        """
        Realiza a busca no Reddit capturando texto e upvotes de posts e comentários.
        """
        lista_posts = []
        variacoes = self.params["search_variations"] #
        subreddits = self.reddit.subreddit(self.params["subreddits"]) #
        
        for var in variacoes:
            query = f"{modelo_busca} {var}"
            print(f"    🔍 Buscando no Reddit: '{query}'")
            try:
                search_results = subreddits.search(
                    query, 
                    limit=self.params["limit_posts_per_keyword"]
                )
                
                for post in search_results:
                    # Carrega os comentários de forma plana, ignorando o botão "load more"
                    post.comments.replace_more(limit=0)
                    
                    comentarios_extraidos = []
                    # Capturamos os 10 melhores comentários com seu respectivo score
                    for comment in post.comments.list()[:10]:
                        comentarios_extraidos.append({
                            "id": comment.id,
                            "autor_comentario": str(comment.author),
                            "conteudo": comment.body,
                            "upvotes": comment.score,  # <-- CAPTURA DE UPVOTES DO COMENTÁRIO
                            "data_publicacao": datetime.datetime.fromtimestamp(
                                comment.created_utc
                            ).isoformat()
                        })

                    lista_posts.append({
                        "id": post.id, #
                        "titulo": post.title, #
                        "texto": post.selftext, #
                        "upvotes": post.score,  # <-- CAPTURA DE UPVOTES DO POST
                        "num_comentarios": post.num_comments, #
                        "comentarios": comentarios_extraidos,
                        "subreddit": post.subreddit.display_name, #
                        "data": datetime.datetime.fromtimestamp(
                            post.created_utc
                        ).strftime('%Y-%m-%d'), #
                        "url": f"https://reddit.com{post.permalink}" #
                    })
                
                time.sleep(1) #
                
            except Exception as e:
                print(f"    ⚠️ Erro na query '{query}': {e}")
                continue
                
        return lista_posts  