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
        
        # 🔥 Configurações otimizadas
        self.comment_limit = 50      # Limite de comentários por post
        self.comment_sort = "top"    # Ordena por relevância
        self.max_concurrency = 6     # Será ajustado dinamicamente

    async def __aenter__(self):
        self.reddit = asyncpraw.Reddit(
            client_id=self.config_pra['DEFAULT']['client_id'],
            client_secret=self.config_pra['DEFAULT']['client_secret'],
            user_agent=self.config_pra['DEFAULT']['user_agent'],
            ratelimit_seconds=600  # 🔥 Aguarda até 10 minutos em caso de rate limit
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

    async def _extrair_comentarios_otimizado(self, post):
        """
        🔥 VERSÃO OTIMIZADA: Extrai comentários sem requisições redundantes.
        - Não chama post.load() (já está carregado)
        - Configura limites antes de acessar a árvore
        - Remove nós MoreComments sem chamadas de rede
        """
        comentarios = []
        
        try:
            # 🔥 Configura limites ANTES de interagir com a árvore de comentários
            post.comment_limit = self.comment_limit
            post.comment_sort = self.comment_sort
            
            # 🔥 Remove marcadores de paginação SEM fazer requisições de rede
            await post.comments.replace_more(limit=0)
            
            # Lista comentários já carregados (sem novas requisições)
            for comment in post.comments.list():
                corpo = getattr(comment, 'body', "") or ""
                # Filtra comentários muito curtos e bots
                if len(corpo) > 10 and "I am a bot" not in corpo:
                    comentarios.append({
                        "id": comment.id,
                        "conteudo": corpo,
                        "score": getattr(comment, 'score', 0)
                    })
        except Exception as e:
            error_str = str(e)
            if "429" in error_str:
                print(" [⏳ Rate limit em comentários] ", end="", flush=True)
                await asyncio.sleep(60)
            # Se falhar, retorna lista vazia (melhor que quebrar o fluxo)
        
        return comentarios

    # async def buscar_termo_generico(self, termo_generico, time_filter="year", task_id=None):
    #     """
    #     🔥 VERSÃO OTIMIZADA: Busca posts por termo genérico.
    #     Principais melhorias:
    #     - Remove await post.load() (redundante)
    #     - Usa _extrair_comentarios_otimizado()
    #     - Configuração de limites já aplicada
    #     """
    #     lista_posts = []
    #     stats = {"categorias": {}, "total_posts": 0}
    #     prefixo = f"[{task_id[:20]}]" if task_id else ""

    #     try:
    #         termo_limpo = unicodedata.normalize('NFKD', termo_generico).encode('ASCII', 'ignore').decode('ASCII').strip()
    #         termo_limpo = termo_limpo.lower().replace('"', '')
            
    #         ids_processados = set()
    #         subreddits = await self.reddit.subreddit(self.subreddits_alvo)
            
    #         # Constrói string de termos negativos
    #         if self.termos_negativos:
    #             string_negativa = f"NOT ({' OR '.join(self.termos_negativos[:10])})"  # Limita a 10 termos
    #         else:
    #             string_negativa = ""
            
    #         total_categorias = len(self.params.get("search_groups", {}))
            
    #         for idx_cat, (categoria, todos_os_termos) in enumerate(self.params.get("search_groups", {}).items(), 1):
    #             if not todos_os_termos:
    #                 continue

    #             lotes = list(self._gerar_lotes(todos_os_termos, 5))
    #             print(f"{prefixo}📂 [{idx_cat}/{total_categorias}] {categoria}", end="", flush=True)

    #             posts_categoria = 0
                
    #             for lote in lotes:
    #                 # Constrói query: (termo_generico) AND (termo1 OR termo2) NOT (negativos)
    #                 termos_lote = [f'"{t}"' if ' ' in t else t for t in lote]
    #                 query = f'"{termo_limpo}" ({" OR ".join(termos_lote)}) {string_negativa}'
                    
    #                 try:
    #                     print(f"\n   🔎 Buscando lote...", end="", flush=True)
    #                     search_start = datetime.datetime.now()
                        
    #                     # 🔥 Busca com limite de 1000 posts por query
    #                     search_results = subreddits.search(
    #                         query, 
    #                         limit=self.params.get("limit_posts_per_keyword", 1000), 
    #                         time_filter=time_filter,
    #                         syntax="lucene"
    #                     )
                        
    #                     posts_lote = 0
    #                     async for post in search_results:
    #                         if post.id in ids_processados:
    #                             continue
                            
    #                         # Filtro básico (NSFW, sem comentários, subreddit comercial)
    #                         manter, motivo = await self._filtrar_post_basico(post)
    #                         if not manter:
    #                             continue

    #                         # 🔥 REMOVIDO: await post.load() - desnecessário!
    #                         # O objeto post já vem completamente hidratado do search()
                            
    #                         # 🔥 Extrai comentários com método otimizado
    #                         comentarios = await self._extrair_comentarios_otimizado(post)
                            
    #                         if comentarios:
    #                             # Identifica quais termos da categoria aparecem no post
    #                             texto_analise = f"{post.title} {post.selftext or ''}".lower()
    #                             termos_encontrados = [t for t in lote if t.lower() in texto_analise]
                                
    #                             lista_posts.append({
    #                                 "id": post.id,
    #                                 "titulo": post.title,
    #                                 "selftext": post.selftext or "",
    #                                 "subreddit": post.subreddit.display_name,
    #                                 "categoria": categoria,
    #                                 "termos_especificos": termos_encontrados or ["geral"],
    #                                 "num_comments": post.num_comments,
    #                                 "data_post": post.created_utc,
    #                                 "comentarios": comentarios
    #                             })
    #                             ids_processados.add(post.id)
    #                             posts_lote += 1
                        
    #                     search_time = (datetime.datetime.now() - search_start).total_seconds()
    #                     if posts_lote > 0:
    #                         print(f" +{posts_lote} posts ({search_time:.1f}s)", end="", flush=True)
    #                     else:
    #                         print(f" ∅ ({search_time:.1f}s)", end="", flush=True)
                        
    #                     posts_categoria += posts_lote

    #                 except Exception as e:
    #                     error_str = str(e)
    #                     if "429" in error_str:
    #                         print(" [⏳ Rate limit] ", end="", flush=True)
    #                         await asyncio.sleep(60)
    #                     elif "414" in error_str:
    #                         print(f" [⚠️ Query muito longa] ", end="", flush=True)
    #                     else:
    #                         print(f" [⚠️ Erro: {str(e)[:30]}]", end="", flush=True)
    #                         await asyncio.sleep(2)

    #             print(f" = {posts_categoria} posts")

    #     except Exception as e:
    #         print(f"\n{prefixo}❌ Erro crítico na busca: {e}")

    #     stats["total_posts"] = len(lista_posts)
    #     for p in lista_posts:
    #         cat = p['categoria']
    #         stats["categorias"][cat] = stats["categorias"].get(cat, 0) + 1

    #     if lista_posts:
    #         print(f"{prefixo}✅ Sucesso: {len(lista_posts)} posts.")
    #     else:
    #         print(f"{prefixo}⏭️ Nenhum post encontrado.")

    #     return lista_posts, stats
    async def buscar_termo_generico(self, query_completa, time_filter="year", task_id=None):
        """
        🔥 VERSÃO CORRIGIDA: Busca posts usando uma query completa (já formatada).
        O parâmetro 'query_completa' já deve conter a estrutura: (termos) AND (modelos)
        """
        lista_posts = []
        stats = {"categorias": {}, "total_posts": 0}
        prefixo = f"[{task_id[:20]}]" if task_id else ""

        try:
            ids_processados = set()
            subreddits = await self.reddit.subreddit(self.subreddits_alvo)
            
            # 🔥 NÃO adiciona aspas extras - a query já vem pronta
            query = query_completa
            
            print(f"{prefixo}🔍 Executando query: {query[:100]}...")
            
            try:
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
                    
                    # Filtro básico
                    manter, motivo = await self._filtrar_post_basico(post)
                    if not manter:
                        continue
                    
                    # Extrai comentários
                    comentarios = await self._extrair_comentarios_otimizado(post)
                    
                    if comentarios:
                        lista_posts.append({
                            "id": post.id,
                            "titulo": post.title,
                            "selftext": post.selftext or "",
                            "subreddit": post.subreddit.display_name,
                            "categoria": task_id if task_id else "geral",
                            "termos_especificos": [],
                            "num_comments": post.num_comments,
                            "data_post": post.created_utc,
                            "comentarios": comentarios
                        })
                        ids_processados.add(post.id)
                        posts_lote += 1
                
                search_time = (datetime.datetime.now() - search_start).total_seconds()
                print(f" +{posts_lote} posts ({search_time:.1f}s)")
                
            except Exception as e:
                error_str = str(e)
                if "429" in error_str:
                    print(" [⏳ Rate limit] ")
                    await asyncio.sleep(60)
                elif "414" in error_str:
                    print(f" [⚠️ Query muito longa ({len(query)} chars)] ")
                else:
                    print(f" [⚠️ Erro: {str(e)[:50]}] ")

        except Exception as e:
            print(f"\n{prefixo}❌ Erro crítico na busca: {e}")

        stats["total_posts"] = len(lista_posts)
        
        if lista_posts:
            print(f"{prefixo}✅ Sucesso: {len(lista_posts)} posts.")
        else:
            print(f"{prefixo}⏭️ Nenhum post encontrado.")

        return lista_posts, stats

    # 🔥 MÉTODO MANTIDO PARA COMPATIBILIDADE (mas otimizado)
    async def buscar_modelo(self, modelo_busca, time_filter="year", task_id=None):
        """
        Método mantido para compatibilidade com código legado.
        Prefira usar buscar_termo_generico() para novas implementações.
        """
        lista_posts = []
        ids_processados = set()
        modelo_limpo = re.sub(r'\bgaming\b', '', modelo_busca, flags=re.IGNORECASE).replace('"', '').strip()
        
        subreddits = await self.reddit.subreddit(self.subreddits_alvo)
        
        if self.termos_negativos:
            string_negativa = f"NOT ({' OR '.join(self.termos_negativos[:10])})"
        else:
            string_negativa = ""

        prefixo = f"[{task_id[:20]}]" if task_id else ""
        
        total_categorias = len(self.params.get("search_groups", {}))
        
        for idx_cat, (categoria, todos_os_termos) in enumerate(self.params.get("search_groups", {}).items(), 1):
            if not todos_os_termos:
                continue

            lotes = list(self._gerar_lotes(todos_os_termos, 8))
            print(f"{prefixo}📂 [{idx_cat}/{total_categorias}] {categoria}", end=": ")

            posts_categoria = 0
            for lote in lotes:
                query = f'"{modelo_limpo}" ({" OR ".join([f'"{t}"' for t in lote])}) {string_negativa}'
                
                try:
                    search_results = subreddits.search(
                        query, 
                        limit=self.params.get("limit_posts_per_keyword", 100), 
                        time_filter=time_filter
                    )
                    
                    posts_lote = 0
                    async for post in search_results:
                        try:
                            if post.id in ids_processados:
                                continue
                                
                            manter, motivo = await self._filtrar_post_basico(post)
                            if not manter:
                                continue

                            # 🔥 OTIMIZADO: remove load() redundante
                            # Verifica se modelo está no texto
                            texto_completo = f"{post.title} {post.selftext or ''}".lower()
                            if modelo_limpo.lower() not in texto_completo:
                                continue

                            # 🔥 OTIMIZADO: extrai comentários sem load()
                            comentarios = await self._extrair_comentarios_otimizado(post)

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
                            if "429" in str(e):
                                print(f"\n{prefixo}⚠️ Rate limit. Aguardando 60s...")
                                await asyncio.sleep(60)
                            continue

                    if posts_lote > 0:
                        print(f"{posts_lote} ", end="", flush=True)
                    posts_categoria += posts_lote

                except Exception as e:
                    if "429" in str(e):
                        print(f"\n{prefixo}⏳ Rate limit. Aguardando 60s...")
                        await asyncio.sleep(60)
                    else:
                        await asyncio.sleep(5)
            
            if posts_categoria > 0:
                print(f"= {posts_categoria} posts")
            else:
                print(f"0 posts")
        
        if lista_posts:
            print(f"{prefixo}✅ Total: {len(lista_posts)} posts")
        else:
            print(f"{prefixo}⏭️ Nenhum post encontrado")
        
        return lista_posts

    async def consultar_limites_api(self):
        """Retorna informações sobre o rate limit atual."""
        try:
            stats = self.reddit.auth.limits
            return {
                "restante": stats.get('remaining'),
                "reset_em": stats.get('reset_timestamp'),
                "usado": stats.get('used'),
                "limite_total": stats.get('limit')
            }
        except:
            return {"restante": 0, "reset_em": 0, "usado": 0, "limite_total": 0}


# =================================================================
# CLASSE AUXILIAR PARA TESTE
# =================================================================
async def testar_service():
    """Função de teste para verificar se as otimizações estão funcionando."""
    print("\n🧪 Testando RedditServiceV10Async Otimizado...\n")
    
    async with RedditServiceV10Async() as service:
        # Testa busca simples
        termo = "zephyrus g14"
        print(f"🔍 Buscando por: '{termo}'")
        
        posts, stats = await service.buscar_termo_generico(
            termo, 
            time_filter="month",  # Apenas último mês para teste
            task_id="TESTE"
        )
        
        print(f"\n📊 Resultados:")
        print(f"   - Posts encontrados: {len(posts)}")
        print(f"   - Categorias: {stats['categorias']}")
        
        # Verifica rate limit
        limites = await service.consultar_limites_api()
        print(f"\n📈 Rate Limit atual:")
        print(f"   - Requisições restantes: {limites['restante']}")
        print(f"   - Limite total: {limites['limite_total']}")


if __name__ == "__main__":
    asyncio.run(testar_service())