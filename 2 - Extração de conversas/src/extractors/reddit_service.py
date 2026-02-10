
import praw
import time
import datetime
import os
import sys
from pathlib import Path
from src.core.base_extractor import BaseExtractor

class RedditService(BaseExtractor):
    def __init__(self):
        super().__init__(platform="reddit")
        
        # 1. Forçamos o caminho absoluto para a pasta onde está este script
        # __file__ é reddit_service.py -> .parent é a pasta 'extractors'
        config_folder = r"2 - Extração de conversas\src\extractors\praw.ini"
        
        # 2. Definimos a variável de ambiente APONTANDO PARA A PASTA
        os.environ['PRAW_CONFIG_PATH'] = str(config_folder)

        try:
            # 3. Usamos site_name="default" (o PRAW mapeia [DEFAULT] para minúsculo internamente)
            self.reddit = praw.Reddit(site_name="DEFAULT")
            self.params = self.config["reddit_params"]
        except Exception as e:
            raise Exception(f"Falha na autenticação do Reddit: {e}")

    def buscar_modelo(self, modelo_busca):
        # ... (seu código de busca continua igual)
        lista_posts = []
        variacoes = self.params["search_variations"]
        subreddits = self.reddit.subreddit(self.params["subreddits"])
        for var in variacoes:
            query = f"{modelo_busca} {var}"
            print(f"    🔍 Buscando no Reddit: '{query}'")
            try:
                search_results = subreddits.search(query, limit=self.params["limit_posts_per_keyword"])
                for post in search_results:
                    lista_posts.append({
                        "id": post.id,
                        "titulo": post.title,
                        "texto": post.selftext,
                        "score": post.score,
                        "num_comentarios": post.num_comments,
                        "subreddit": post.subreddit.display_name,
                        "data": datetime.datetime.fromtimestamp(post.created_utc).strftime('%Y-%m-%d'),
                        "url": f"https://reddit.com{post.permalink}"
                    })
                time.sleep(1)
            except Exception as e:
                print(f"    ⚠️ Erro na query '{query}': {e}")
        return lista_posts