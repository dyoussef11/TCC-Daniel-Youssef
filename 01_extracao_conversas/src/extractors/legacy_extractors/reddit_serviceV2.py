import praw
import datetime
import time
import configparser
from pathlib import Path
from core_extration.base_extractor import BaseExtractor

class RedditService(BaseExtractor):
    def __init__(self):
        super().__init__(platform="reddit")
        
        # Carregamento das credenciais do praw.ini
        caminho_ini: Path = self.root_dir / "src/extractors/praw.ini"
        config_pra = configparser.ConfigParser()
        
        if not caminho_ini.exists():
            raise FileNotFoundError(f"Arquivo praw.ini não encontrado em: {caminho_ini}")
            
        config_pra.read(caminho_ini, encoding='utf-8')

        try:
            self.reddit = praw.Reddit(
                client_id=config_pra['DEFAULT']['client_id'],
                client_secret=config_pra['DEFAULT']['client_secret'],
                user_agent=config_pra['DEFAULT']['user_agent']
            )
            # Carrega parâmetros do seu JSON: search_groups, subreddits, etc.
            self.params = self.config["reddit_params"]
        except Exception as e:
            raise Exception(f"Falha na conexão com a API do Reddit: {e}")

    def consultar_limites_api(self):
        """Monitora a saúde da cota de requisições."""
        stats = self.reddit.auth.limits
        return {
            "restante": stats.get('remaining'),
            "reset_em": stats.get('reset_timestamp')
        }

    def buscar_modelo(self, modelo_busca, time_filter="year"):
        lista_posts = []
        ids_processados = set()
        subreddits = self.reddit.subreddit(self.params["subreddits"])
        
        for categoria, termos in self.params["search_groups"].items():
            termos_query = " OR ".join([f'"{t}"' for t in termos])
            query = f'{modelo_busca} ({termos_query})'
            
            tentativas = 10
            sucesso = False
            
            while tentativas > 0 and not sucesso:
                try:
                    print(f"    🔍 Categoria [{categoria}]: {query}")
                    search_results = subreddits.search(query, limit=100, time_filter=time_filter)
                    
                    for post in search_results:
                        if post.id in ids_processados or post.over_18 or not post.selftext:
                            continue
                        
                        post.comments.replace_more(limit=0)
                        
                        comentarios = []
                        comment_list = post.comments.list()
                        for comment in comment_list:
                            if len(comment.body) < 10 or "I am a bot" in comment.body:
                                continue
                            
                            comentarios.append({
                                "id": comment.id,
                                "conteudo": comment.body,
                                "score": comment.score,
                                "data_comentario": datetime.datetime.fromtimestamp(
                                    comment.created_utc
                                ).timestamp()
                            })

                        if len(comentarios) > 0 or len(post.selftext) > 10:
                            # --- LÓGICA DE IDENTIFICAÇÃO DE TERMOS ---
                            texto_para_busca = (post.title + " " + post.selftext).lower()
                            termos_encontrados = [t for t in termos if t.lower() in texto_para_busca]
                            
                            # Se a lista estiver vazia, define o marcador. Caso contrário, mantém a lista.
                            # Usei "termo_nao_encontrado_no_corpo" pois o Reddit achou o post, 
                            # então o termo deve estar nos comentários ou foi uma busca por proximidade.
                            marcador_termos = termos_encontrados if termos_encontrados else ["without_search_groups"]

                            lista_posts.append({
                                "id": post.id,
                                "titulo": post.title,
                                "conteudo_post": post.selftext,
                                "subreddit": post.subreddit.display_name,
                                "flair": post.link_flair_text,
                                "score": post.score,
                                "upvote_ratio": post.upvote_ratio,
                                "num_comments": post.num_comments,
                                "categoria": categoria,
                                "termos_especificos": marcador_termos, # <--- Marcador aplicado aqui
                                "url": f"https://reddit.com{post.permalink}",
                                "data_post": datetime.datetime.fromtimestamp(
                                    post.created_utc).timestamp(), 
                                "comentarios": sorted(comentarios, key=lambda x: x['score'], reverse=True)
                            })
                            ids_processados.add(post.id)
                    
                    sucesso = True
                    
                except Exception as e:
                    if "429" in str(e):
                        print(f"    🛑 Rate Limit (429). Dormindo 40s...")
                        time.sleep(40)
                        tentativas -= 1
                    else:
                        print(f"    ⚠️ Erro na categoria {categoria}: {e}")
                        break

        return lista_posts