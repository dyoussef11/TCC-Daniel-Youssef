import praw
import datetime
import time
import configparser
from pathlib import Path
from core_extration.base_extractor import BaseExtractor

# # Lista de subreddits comerciais/promoções para ignorar
# BLACKLIST_SUBREDDITS = {
#     "laptopdeals", "laptopdealsindia", "suggestalaptop", "bangaloremarketplace",
#     "promos", "coupons", "hardwareswaptr", "indian_flex", "hyderabadbuysell",
#     "pakgamers", "buildapcsales", "test", "bilgisayar", "askvenezuela",
#     "cachyos", "it", "sffpc", "eldenring", "indotech", "laptops",
#     "gamingsetups", "battlestations", "setup", "pcmasterracememes",
#     "gaminglaptopdeals", "laptopdealseurope", "gaminglaptopdealsuk"
# }

class RedditServiceV2(BaseExtractor):
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

    def _filtrar_post(self, post, modelo_limpo, ids_processados):
        """
        Aplica todos os filtros de qualidade em um post.
        Retorna (True, None) se o post deve ser mantido, ou (False, "motivo") se descartado.
        """
        # # Filtro 1: Blacklist de subreddits comerciais/promoções
        # if post.subreddit.display_name.lower() in BLACKLIST_SUBREDDITS:
        #     return False, f"Subreddit comercial: r/{post.subreddit.display_name}"
        
        # Filtro 2: Validações básicas
        if post.id in ids_processados:
            return False, "ID duplicado"
        if post.over_18:
            return False, "Conteúdo +18"
        if not post.selftext or len(post.selftext) < 15:
            return False, "Post sem texto ou muito curto"
        
        # Filtro 3: O modelo alvo PRECISA estar no texto
        texto_para_busca = (post.title + " " + post.selftext).lower()
        if modelo_limpo.lower() not in texto_para_busca:
            return False, "Modelo não mencionado no corpo do post"
        
        # Filtro 4: Verifica se há conteúdo técnico relevante
        todos_termos = []
        for termos_lista in self.params["search_groups"].values():
            todos_termos.extend(termos_lista)
        
        tem_termo_tecnico = any(termo.lower() in texto_para_busca for termo in todos_termos)
        
        # Lista de palavras-chave de venda/promoção para filtrar
        termos_venda = ["for sale", "selling", "buy now", "discount", "deal", 
                       "price dropped", "on sale", "coupon", "promo code"]
        eh_post_venda = any(termo in texto_para_busca for termo in termos_venda)
        
        if eh_post_venda:
            return False, "Post de venda/promoção detectado"
        
        # Se não tem termo técnico e não parece ser um post legítimo de problema/dúvida
        if not tem_termo_tecnico:
            # Verifica se pelo menos parece ser uma pergunta sobre o hardware
            termos_pergunta = ["help", "issue", "problem", "question", "anyone", 
                             "advice", "fix", "how to", "why is", "please"]
            eh_pergunta = any(termo in texto_para_busca for termo in termos_pergunta)
            
            if not eh_pergunta:
                return False, "Conteúdo genérico sem termo técnico ou dúvida"
        
        return True, None

    def buscar_modelo(self, modelo_busca, time_filter="year"):
        """
        Busca posts do Reddit para um modelo específico, aplicando todos os filtros.
        
        Args:
            modelo_busca: string de busca (já deve vir formatada com aspas)
            time_filter: filtro temporal (hour, day, week, month, year, all)
        """
        lista_posts = []
        ids_processados = set()
        
        # Remove as aspas para verificações internas
        modelo_limpo = modelo_busca.replace('"', '')
        subreddits = self.reddit.subreddit(self.params["subreddits"])
        
        print(f"\n📊 Iniciando busca para: {modelo_busca}")
        posts_descartados = {}
        
        for categoria, termos in self.params["search_groups"].items():
            termos_query = " OR ".join([f'"{t}"' for t in termos])
            query = f'{modelo_busca} ({termos_query})'
            
            tentativas = 10
            sucesso = False
            
            while tentativas > 0 and not sucesso:
                try:
                    print(f"  🔍 Categoria [{categoria}]: {query[:100]}...")
                    search_results = subreddits.search(query, limit=100, time_filter=time_filter)
                    
                    posts_categoria = 0
                    for post in search_results:
                        # Aplica todos os filtros
                        manter, motivo = self._filtrar_post(post, modelo_limpo, ids_processados)
                        
                        if not manter:
                            posts_descartados[motivo] = posts_descartados.get(motivo, 0) + 1
                            continue
                        
                        posts_categoria += 1
                        post.comments.replace_more(limit=0)
                        
                        # Processa comentários
                        comentarios = []
                        comment_list = post.comments.list()
                        for comment in comment_list[:20]:  # Limita a 20 comentários por post
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

                        if len(comentarios) > 0 or len(post.selftext) > 30:
                            # Identifica termos específicos encontrados
                            texto_para_busca = (post.title + " " + post.selftext).lower()
                            termos_encontrados = [t for t in termos if t.lower() in texto_para_busca]
                            marcador_termos = termos_encontrados if termos_encontrados else ["discussao_geral"]

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
                                "termos_especificos": marcador_termos,
                                "url": f"https://reddit.com{post.permalink}",
                                "data_post": datetime.datetime.fromtimestamp(
                                    post.created_utc).timestamp(),
                                "comentarios": sorted(comentarios, key=lambda x: x['score'], reverse=True)
                            })
                            ids_processados.add(post.id)
                    
                    print(f"    ✅ Posts aceitos na categoria: {posts_categoria}")
                    sucesso = True
                    
                except Exception as e:
                    if "429" in str(e):
                        print(f"    🛑 Rate Limit (429). Dormindo 40s...")
                        time.sleep(40)
                        tentativas -= 1
                    else:
                        print(f"    ⚠️ Erro na categoria {categoria}: {e}")
                        break
        
        # Resumo dos descartes
        print(f"\n📈 Resumo da busca para {modelo_busca}:")
        print(f"   Total de posts aceitos: {len(lista_posts)}")
        if posts_descartados:
            print("   Posts descartados por motivo:")
            for motivo, quantidade in sorted(posts_descartados.items(), key=lambda x: x[1], reverse=True):
                print(f"     - {motivo}: {quantidade}")
        
        return lista_posts