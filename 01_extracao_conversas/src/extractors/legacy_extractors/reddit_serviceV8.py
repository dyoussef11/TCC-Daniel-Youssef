import asyncpraw
import asyncio
import datetime
import configparser
import re
import traceback # Para logar o erro completo se persistir
from pathlib import Path
from core_extration.base_extractor import BaseExtractor

class RedditServiceV8Async(BaseExtractor):
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
        """Gerador puro: lida com listas nulas ou vazias sem quebrar o loop."""
        if not lista:
            return
        for i in range(0, len(lista), n):
            yield lista[i:i + n]

    async def _analisar_tema_subreddit(self, subreddit_obj):
        """Verifica temas comerciais com suporte a cache para evitar processamento repetido."""
        blacklist_temas = ["sale", "deal", "price", "discount", "store", "promo", "coupon", "marketplace"]
        
        try:
            # 1. Identifica o nome do subreddit (atributo síncrono no asyncpraw)
            nome = subreddit_obj.display_name.lower()

            # 2. Se já analisamos este subreddit antes, retorna o resultado guardado
            if nome in self.cache_subreddits:
                return self.cache_subreddits[nome]

            # 3. Se não está no cache, realiza a análise de texto
            desc = (getattr(subreddit_obj, 'public_description', "") or "").lower()
            
            # Verifica se algum termo proibido está no nome ou na descrição
            if any(termo in f"{nome} {desc}" for termo in blacklist_temas):
                resultado = (False, f"Subreddit Comercial (r/{nome})")
            else:
                resultado = (True, None)

            # 4. GUARDA o resultado no cache antes de retornar
            self.cache_subreddits[nome] = resultado
            return resultado

        except Exception:
            # Em caso de erro na API ao acessar atributos, permite a passagem para não travar a extração
            return True, None

    async def _filtrar_post(self, post, modelo_limpo, ids_processados):
        """Filtra posts de baixa qualidade. Retorna SEMPRE uma tupla (bool, str)."""
        if post.id in ids_processados: return False, "Duplicado"
        if getattr(post, 'over_18', False): return False, "NSFW"
        if getattr(post, 'num_comments', 0) == 0: return False, "Sem comentários"
        
        if not post.subreddit: return False, "Sem Subreddit"

        tema_ok, motivo = await self._analisar_tema_subreddit(post.subreddit)
        if not tema_ok: return False, motivo

        # Proteção contra selftext nulo (None + str gera erro)
        texto_completo = (post.title + " " + (post.selftext or "")).lower()
        if modelo_limpo.lower() not in texto_completo:
            return False, "Modelo ausente no texto"
        
        return True, None

    async def buscar_modelo(self, modelo_busca, time_filter="year", task_id=None):
        lista_posts = []
        ids_processados = set()
        modelo_limpo = re.sub(r'\bgaming\b', '', modelo_busca, flags=re.IGNORECASE).replace('"', '').strip()
        
        subreddits = await self.reddit.subreddit(self.subreddits_alvo)
        string_negativa = " ".join([f"-{t}" for t in self.termos_negativos])

        # NOVO: Prefixo para identificar qual task está logando
        prefixo = f"[{task_id[:20]}]" if task_id else ""
        
        # Remove o print do modelo (já está no extrator)
        # print(f"\n🔍 Buscando: '{modelo_limpo}'")
        
        total_categorias = len(self.params.get("search_groups", {}))
        for idx_cat, (categoria, todos_os_termos) in enumerate(self.params.get("search_groups", {}).items(), 1):
            if not todos_os_termos: continue

            lotes = list(self._gerar_lotes(todos_os_termos, 8))
            
            # NOVO: Mostra categoria atual de forma mais compacta
            print(f"{prefixo}📂 [{idx_cat}/{total_categorias}] {categoria}", end=": ")
            
            posts_categoria = 0
            for idx_lote, lote in enumerate(lotes, 1):
                query = f'"{modelo_limpo}" ({" OR ".join([f'"{t}"' for t in lote])}) {string_negativa}'
                
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
            
            # NOVO: Resumo da categoria
            if posts_categoria > 0:
                print(f"= {posts_categoria} posts")
            else:
                print(f"0 posts")
        
        # Resumo final mais compacto
        if lista_posts:
            print(f"{prefixo}✅ Total: {len(lista_posts)} posts em {sum(1 for p in lista_posts if p['categoria'])} categorias")
        else:
            print(f"{prefixo}⏭️  Nenhum post encontrado")
        
        return lista_posts

    async def consultar_limites_api(self):
        """Retorna limites de forma segura."""
        try:
            stats = self.reddit.auth.limits
            return {
                "restante": stats.get('remaining'),
                "reset_em": stats.get('reset_timestamp')
            }
        except:
            return {"restante": 0, "reset_em": 0}