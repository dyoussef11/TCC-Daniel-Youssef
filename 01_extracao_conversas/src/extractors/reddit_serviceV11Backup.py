import asyncpraw
import asyncio
import datetime
import configparser
import re
import unicodedata
from pathlib import Path
from core_extration.base_extractor import BaseExtractor

class RedditServiceV11Async(BaseExtractor):
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
        if getattr(post, 'over_18', False):
            return False, "NSFW"
        if getattr(post, 'num_comments', 0) == 0:
            return False, "Sem comentários"
        if not post.subreddit:
            return False, "Sem Subreddit"
        tema_ok, motivo = await self._analisar_tema_subreddit(post.subreddit)
        if not tema_ok:
            return False, motivo
        return True, None

    # -------------------------------------------------------------------------
    # BUSCA LEVE – sem comentários, com log_func ASSÍNCRONO (cada mensagem é uma linha completa)
    # -------------------------------------------------------------------------
    async def buscar_termo_generico_leve(self, termo_generico, time_filter="year", log_func=None):
        """
        Busca posts por termo genérico. Retorna (lista_posts, stats).
        Os posts NÃO contêm comentários.
        log_func: função assíncrona que aceita uma string (mensagem completa) e a imprime.
                  Se None, usa print padrão.
        """
        lista_posts = []
        stats = {"categorias": {}, "total_posts": 0}

        # Define um log_func padrão se não fornecido
        if log_func is None:
            async def log_func(msg):
                print(msg)

        termo_limpo = unicodedata.normalize('NFKD', termo_generico).encode('ASCII', 'ignore').decode('ASCII').strip()
        termo_limpo = termo_limpo.lower().replace('"', '')

        ids_processados = set()
        subreddits = await self.reddit.subreddit(self.subreddits_alvo)

        if self.termos_negativos:
            string_negativa = f"NOT ({' OR '.join(self.termos_negativos)})"
        else:
            string_negativa = ""

        total_categorias = len(self.params.get("search_groups", {}))
        total_termos = sum(len(termos) for termos in self.params.get("search_groups", {}).values())
        termo_idx = 0

        for idx_cat, (categoria, todos_os_termos) in enumerate(self.params.get("search_groups", {}).items(), 1):
            if not todos_os_termos:
                continue

            lotes = list(self._gerar_lotes(todos_os_termos, 5))
            await log_func(f"📂 [{idx_cat}/{total_categorias}] {categoria}")

            posts_categoria = 0
            for lote in lotes:
                termo_idx += len(lote)
                # query = f'"{termo_limpo}" ({" OR ".join([f'"{t}"' for t in lote])}) {string_negativa}'
                termos_lote = [f'"{t}"' for t in lote]
                query = f'"{termo_limpo}" ({" OR ".join(termos_lote)}) {string_negativa}'
                try:
                    # Mensagem única para o lote (sem fragmentação)
                    search_start = datetime.datetime.now()
                    search_results = subreddits.search(
                        query,
                        limit=self.params.get("limit_posts_per_keyword", 1000),
                        time_filter=time_filter,
                        syntax="lucene"
                    )

                    posts_lote = 0
                    async for post in search_results:
                        if post.id in ids_processados:
                            continue
                        manter, _ = await self._filtrar_post_basico(post)
                        if not manter:
                            continue
                        lista_posts.append({
                            "id": post.id,
                            "titulo": post.title,
                            "selftext": post.selftext or "",
                            "subreddit": post.subreddit.display_name,
                            "num_comments": post.num_comments,
                            "data_post": post.created_utc,
                            "categoria": categoria
                        })
                        ids_processados.add(post.id)
                        posts_lote += 1

                    search_time = (datetime.datetime.now() - search_start).total_seconds()
                    if posts_lote > 0:
                        msg = f"   🔎 Buscando lote {termo_idx}/{total_termos}... +{posts_lote} posts ({search_time:.1f}s)"
                    else:
                        msg = f"   🔎 Buscando lote {termo_idx}/{total_termos}... ∅ ({search_time:.1f}s)"
                    await log_func(msg)
                    posts_categoria += posts_lote

                except Exception as e:
                    if "429" in str(e):
                        await log_func(f"   🔎 Lote {termo_idx}/{total_termos}: ⏳ Rate limit")
                        await asyncio.sleep(60)
                    else:
                        await log_func(f"   🔎 Lote {termo_idx}/{total_termos}: ⚠️ Erro: {str(e)[:30]}")
                        await asyncio.sleep(2)

            await log_func(f" = {posts_categoria} posts")

        stats["total_posts"] = len(lista_posts)
        for p in lista_posts:
            cat = p['categoria']
            stats["categorias"][cat] = stats["categorias"].get(cat, 0) + 1

        if lista_posts:
            await log_func(f"✅ Sucesso (leve): {len(lista_posts)} posts.")
        else:
            await log_func(f"⏭️ Nenhum post encontrado (leve).")

        return lista_posts, stats

    # -------------------------------------------------------------------------
    # CARREGAR COMENTÁRIOS SOB DEMANDA
    # -------------------------------------------------------------------------
    async def carregar_comentarios_do_post(self, post_id):
        try:
            submission = await self.reddit.submission(id=post_id)
            await submission.load()
            comentarios = []
            if submission.comments:
                await submission.comments.replace_more(limit=0)
                for comment in submission.comments.list():
                    corpo = getattr(comment, 'body', "") or ""
                    if len(corpo) > 10 and "I am a bot" not in corpo:
                        comentarios.append({
                            "id": comment.id,
                            "conteudo": corpo,
                            "score": comment.score, 
                            "data_comentario": comment.created_utc
                        })
            return comentarios
        except Exception:
            return []

    # -------------------------------------------------------------------------
    # MÉTODOS ANTIGOS (mantidos para compatibilidade)
    # -------------------------------------------------------------------------
    async def buscar_termo_generico(self, termo_generico, time_filter="year", task_id=None):
        pass

    async def buscar_modelo(self, modelo_busca, time_filter="year", task_id=None):
        pass

    async def consultar_limites_api(self):
        try:
            stats = self.reddit.auth.limits
            return {
                "restante": stats.get('remaining'),
                "reset_em": stats.get('reset_timestamp')
            }
        except:
            return {"restante": 0, "reset_em": 0}