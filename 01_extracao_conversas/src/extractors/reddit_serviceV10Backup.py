import asyncpraw
import asyncio
import datetime
import configparser
import re
import unicodedata
from pathlib import Path
from core_extration.base_extractor import BaseExtractor

class RedditServiceV10Async(BaseExtractor):
    def __init__(self):
        super().__init__(platform="reddit")
        self.params = self.config["reddit_params"]
        self.termos_negativos = self.params.get("negative_terms", [])
        self.subreddits_alvo = self.params.get("subreddits", "all")
        
        caminho_ini: Path = self.root_dir / "src/extractors/praw.ini"
        self.config_pra = configparser.ConfigParser()
        self.config_pra.read(caminho_ini, encoding='utf-8')
        self.cache_subreddits = {}

    async def __aenter__(self):
        self.reddit = asyncpraw.Reddit(
            client_id=self.config_pra['DEFAULT']['client_id'],
            client_secret=self.config_pra['DEFAULT']['client_secret'],
            user_agent=self.config_pra['DEFAULT']['user_agent']
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.reddit.close()

    def _gerar_lotes(self, lista, n):
        if not lista:
            return
        for i in range(0, len(lista), n):
            yield lista[i:i + n]

    async def _analisar_tema_subreddit(self, subreddit_obj):
        blacklist_temas = ["sale", "deal", "price", "discount", "store", "promo", "coupon", "marketplace"]
        try:
            nome = subreddit_obj.display_name.lower()
            if nome in self.cache_subreddits:
                return self.cache_subreddits[nome]
            desc = (getattr(subreddit_obj, 'public_description', "") or "").lower()
            if any(termo in f"{nome} {desc}" for termo in blacklist_temas):
                resultado = (False, f"Subreddit Comercial (r/{nome})")
            else:
                resultado = (True, None)
            self.cache_subreddits[nome] = resultado
            return resultado
        except Exception:
            return True, None

    async def _filtrar_post_basico(self, post):
        """Filtros independentes do modelo (NSFW, sem comentários, subreddit comercial)."""
        if getattr(post, 'over_18', False): return False, "NSFW"
        if getattr(post, 'num_comments', 0) == 0: return False, "Sem comentários"
        if not post.subreddit: return False, "Sem Subreddit"
        tema_ok, motivo = await self._analisar_tema_subreddit(post.subreddit)
        if not tema_ok: return False, motivo
        return True, None

    async def _filtrar_post(self, post, modelo_limpo, ids_processados):
        """Filtro completo com checagem de modelo (mantido para compatibilidade)."""
        if post.id in ids_processados: return False, "Duplicado"
        ok, motivo = await self._filtrar_post_basico(post)
        if not ok: return False, motivo
        texto_completo = (post.title + " " + (post.selftext or "")).lower()
        if modelo_limpo.lower() not in texto_completo:
            return False, "Modelo ausente no texto"
        return True, None

    async def buscar_modelo(self, modelo_busca, time_filter="year", task_id=None):
        """Método original – mantido para compatibilidade, mas não usado na nova pipeline."""
        lista_posts = []
        ids_processados = set()
        modelo_limpo = re.sub(r'\bgaming\b', '', modelo_busca, flags=re.IGNORECASE).replace('"', '').strip()
        
        subreddits = await self.reddit.subreddit(self.subreddits_alvo)
        string_negativa = " ".join([f"-{t}" for t in self.termos_negativos])

        prefixo = f"[{task_id[:20]}]" if task_id else ""
        
        total_categorias = len(self.params.get("search_groups", {}))
        for idx_cat, (categoria, todos_os_termos) in enumerate(self.params.get("search_groups", {}).items(), 1):
            if not todos_os_termos: continue

            lotes = list(self._gerar_lotes(todos_os_termos, 8))
            print(f"{prefixo}📂 [{idx_cat}/{total_categorias}] {categoria}", end=": ")

            posts_categoria = 0
            for idx_lote, lote in enumerate(lotes, 1):
                query = f'"{modelo_limpo}" ({" OR ".join([f'"{t}"' for t in lote])}) {string_negativa}'
                print("A query:",{query})
                
                try:
                    search_results = subreddits.search(query, limit=self.params.get("limit_posts_per_keyword", 100), time_filter=time_filter)
                    
                    posts_lote = 0
                    async for post in search_results:
                        try:
                            manter, motivo = await self._filtrar_post(post, modelo_limpo, ids_processados)
                            if not manter: continue

                            try:
                                await post.load()
                                if post.comments is not None:
                                    await post.comments.replace_more(limit=0)
                                    comentarios = []
                                    comments_list = post.comments.list()
                                    if comments_list:
                                        for comment in comments_list:
                                            corpo = getattr(comment, 'body', "") or ""
                                            if len(corpo) > 10 and "I am a bot" not in corpo:
                                                comentarios.append({
                                                    "id": comment.id,
                                                    "conteudo": corpo,
                                                    "score": comment.score
                                                })
                                else:
                                    comentarios = []
                            except Exception as e:
                                error_str = str(e)
                                if "429" in error_str:
                                    print(f"\n{prefixo}⚠️ Rate limit nos comentários. Aguardando 60s...")
                                    await asyncio.sleep(60)
                                    continue
                                comentarios = []

                            if comentarios:
                                texto_analise = (post.title + " " + (post.selftext or "")).lower()
                                termos_encontrados = [t for t in lote if t.lower() in texto_analise]

                                lista_posts.append({
                                    "id": post.id,
                                    "titulo": post.title,
                                    "selftext": post.selftext or "",
                                    "subreddit": post.subreddit.display_name,
                                    "categoria": categoria,
                                    "termos_especificos": termos_encontrados or ["geral"],
                                    "num_comments": post.num_comments,
                                    "data_post": post.created_utc,
                                    "comentarios": comentarios
                                })
                                ids_processados.add(post.id)
                                posts_lote += 1
                        
                        except Exception as e:
                            error_str = str(e)
                            if "429" in error_str:
                                print(f"\n{prefixo}⚠️ Rate limit. Aguardando 60s...")
                                await asyncio.sleep(60)
                            continue

                    if posts_lote > 0:
                        print(f"{posts_lote} ", end="", flush=True)
                    posts_categoria += posts_lote

                except Exception as e:
                    error_str = str(e)
                    if "429" in error_str:
                        print(f"\n{prefixo}⏳ Rate limit. Aguardando 60s...")
                        await asyncio.sleep(60)
                    else:
                        await asyncio.sleep(5)
            
            if posts_categoria > 0:
                print(f"= {posts_categoria} posts")
            else:
                print(f"0 posts")
        
        if lista_posts:
            print(f"{prefixo}✅ Total: {len(lista_posts)} posts em {sum(1 for p in lista_posts if p['categoria'])} categorias")
        else:
            print(f"{prefixo}⏭️  Nenhum post encontrado")
        
        return lista_posts

    async def buscar_termo_generico(self, termo_generico, time_filter="year", task_id=None):
        """
        Busca posts por termo genérico e retorna (lista_posts, stats).
        """
        lista_posts = []
        stats = {"categorias": {}, "total_posts": 0}
        prefixo = f"[{task_id[:20]}]" if task_id else ""

        try:
            termo_limpo = unicodedata.normalize('NFKD', termo_generico).encode('ASCII', 'ignore').decode('ASCII').strip()
            termo_limpo = termo_limpo.lower().replace('"', '')
            
            ids_processados = set()
            subreddits = await self.reddit.subreddit(self.subreddits_alvo)
            # Se termos_negativos for ['sale', 'shop'], vira: NOT (sale OR shop)
            if self.termos_negativos:
                string_negativa = f"NOT ({' OR '.join(self.termos_negativos)})"
            else:
                string_negativa = ""
            
            total_categorias = len(self.params.get("search_groups", {}))
            total_termos = sum(len(termos) for termos in self.params.get("search_groups", {}).values())
            termo_idx = 0

            for idx_cat, (categoria, todos_os_termos) in enumerate(self.params.get("search_groups", {}).items(), 1):
                if not todos_os_termos: continue

                lotes = list(self._gerar_lotes(todos_os_termos, 5))
                print(f"{prefixo}📂 [{idx_cat}/{total_categorias}] {categoria}", end="", flush=True)

                posts_categoria = 0
                for lote in lotes:
                    termo_idx += len(lote)
                    progresso = f" ({termo_idx}/{total_termos} termos)"
                    
                    query = f'"{termo_limpo}" ({" OR ".join([f'"{t}"' for t in lote])}) {string_negativa}'
                    
                    try:
                        print(f"\n   🔎 Buscando lote {termo_idx}/{total_termos}...", end="", flush=True)
                        search_start = datetime.datetime.now()
                        
                        # search_results = subreddits.search(query, limit=self.params.get("limit_posts_per_keyword", 100), time_filter=time_filter)
                        search_results = subreddits.search(query, limit=self.params.get("limit_posts_per_keyword", 1000), time_filter=time_filter,syntax="lucene")
                        
                        posts_lote = 0
                        async for post in search_results:
                            if post.id in ids_processados: continue
                            
                            manter, _ = await self._filtrar_post_basico(post)
                            if not manter: continue

                            try:
                                await post.load()
                                comentarios = []
                                if post.comments:
                                    await post.comments.replace_more(limit=0)
                                    for comment in post.comments.list():
                                        corpo = getattr(comment, 'body', "") or ""
                                        if len(corpo) > 10 and "I am a bot" not in corpo:
                                            comentarios.append({
                                                "id": comment.id,
                                                "conteudo": corpo,
                                                "score": comment.score
                                            })
                                
                                if comentarios:
                                    selftext = post.selftext or ""
                                    texto_analise = (post.title + " " + selftext).lower()
                                    termos_encontrados = [t for t in lote if t.lower() in texto_analise]

                                    lista_posts.append({
                                        "id": post.id,
                                        "titulo": post.title,
                                        "selftext": selftext,
                                        "subreddit": post.subreddit.display_name,
                                        "categoria": categoria,
                                        "termos_especificos": termos_encontrados or ["geral"],
                                        "num_comments": post.num_comments,
                                        "data_post": post.created_utc,
                                        "comentarios": comentarios
                                    })
                                    ids_processados.add(post.id)
                                    posts_lote += 1
                            
                            except Exception as e:
                                if "429" in str(e):
                                    print(" [⏳ Rate limit] ", end="", flush=True)
                                    await asyncio.sleep(60)
                                continue
                        
                        search_time = (datetime.datetime.now() - search_start).total_seconds()
                        if posts_lote > 0:
                            print(f" +{posts_lote} posts ({search_time:.1f}s)", end="", flush=True)
                        else:
                            print(f" ∅ ({search_time:.1f}s)", end="", flush=True)
                        
                        posts_categoria += posts_lote

                    except Exception as e:
                        if "429" in str(e):
                            print(" [⏳ Rate limit] ", end="", flush=True)
                            await asyncio.sleep(60)
                        else:
                            print(f" [⚠️ Erro: {str(e)[:30]}]", end="", flush=True)
                            await asyncio.sleep(2)

                print(f" = {posts_categoria} posts")  # Nova linha após categoria

        except Exception as e:
            print(f"\n{prefixo}❌ Erro crítico na busca: {e}")

        stats["total_posts"] = len(lista_posts)
        for p in lista_posts:
            cat = p['categoria']
            stats["categorias"][cat] = stats["categorias"].get(cat, 0) + 1

        if lista_posts:
            print(f"{prefixo}✅ Sucesso: {len(lista_posts)} posts.")
        else:
            print(f"{prefixo}⏭️ Nenhum post encontrado.")

        return lista_posts, stats

    async def consultar_limites_api(self):
        try:
            stats = self.reddit.auth.limits
            return {
                "restante": stats.get('remaining'),
                "reset_em": stats.get('reset_timestamp')
            }
        except:
            return {"restante": 0, "reset_em": 0}