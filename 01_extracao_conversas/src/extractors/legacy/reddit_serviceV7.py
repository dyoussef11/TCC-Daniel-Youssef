import asyncpraw
import asyncio
import datetime
import configparser
import re
from pathlib import Path
from core_extration.base_extractor import BaseExtractor

class RedditServiceV7Async(BaseExtractor):
    def __init__(self):
        super().__init__(platform="reddit")
        
        # Carregamento de configurações[cite: 1, 3]
        self.params = self.config["reddit_params"]
        self.termos_negativos = self.params.get("negative_terms", [])
        self.subreddits_alvo = self.params.get("subreddits", "all")
        
        # Carregar credenciais do praw.ini
        caminho_ini: Path = self.root_dir / "src/extractors/praw.ini"
        self.config_pra = configparser.ConfigParser()
        if not caminho_ini.exists():
            raise FileNotFoundError(f"Arquivo praw.ini não encontrado em: {caminho_ini}")
        self.config_pra.read(caminho_ini, encoding='utf-8')

    async def __aenter__(self):
        """Inicializa a sessão assíncrona da API."""
        self.reddit = asyncpraw.Reddit(
            client_id=self.config_pra['DEFAULT']['client_id'],
            client_secret=self.config_pra['DEFAULT']['client_secret'],
            user_agent=self.config_pra['DEFAULT']['user_agent']
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Fecha a sessão da API ao sair do contexto."""
        await self.reddit.close()

    def _gerar_lotes(self, lista, n):
        """Divide a lista de termos em lotes para evitar queries muito longas."""
        for i in range(0, len(lista), n):
            yield lista[i:i + n]

    async def _analisar_tema_subreddit(self, subreddit_name):
        """Verifica se o subreddit é comercial/venda[cite: 1]."""
        blacklist_temas = ["sale", "deal", "price", "discount", "store", "promo", "coupon", "marketplace"]
        try:
            subreddit = await self.reddit.subreddit(subreddit_name)
            # await é necessário para acessar atributos que exigem requisição
            desc = (getattr(subreddit, 'public_description', "") or "").lower()
            texto_meta = f"{subreddit_name.lower()} {desc}"
            if any(termo in texto_meta for termo in blacklist_temas):
                return False, f"Subreddit Comercial (r/{subreddit_name})"
        except:
            pass 
        return True, None

    async def _filtrar_post(self, post, modelo_limpo, ids_processados):
        """Filtros de qualidade para garantir relevância técnica[cite: 1, 4]."""
        if post.id in ids_processados: return False, "Duplicado"
        if getattr(post, 'over_18', False): return False, "NSFW"
        
        # OTIMIZAÇÃO: Ignora posts sem comentários[cite: 4]
        if getattr(post, 'num_comments', 0) == 0:
            return False, "Sem comentários"
            
        if not post.selftext or len(post.selftext) < 20: 
            return False, "Muito curto"
        
        # Validação do Subreddit
        tema_ok, motivo = await self._analisar_tema_subreddit(post.subreddit.display_name)
        if not tema_ok: return False, motivo

        texto_completo = (post.title + " " + post.selftext).lower()
        if modelo_limpo.lower() not in texto_completo:
            return False, "Modelo ausente no texto"
        
        return True, None

    async def buscar_modelo(self, modelo_busca, time_filter="year"):
        lista_posts = []
        ids_processados = set()
        
        # Limpeza preventiva: remove "gaming" e limpa SKUs
        modelo_limpo = re.sub(r'\bgaming\b', '', modelo_busca, flags=re.IGNORECASE).replace('"', '').strip()
        
        subreddits = await self.reddit.subreddit(self.subreddits_alvo)
        string_negativa = " ".join([f"-{t}" for t in self.termos_negativos])

        print(f"\n🚀 EXTRAÇÃO ASYNC: {modelo_limpo}")
        stats = {"aceitos": 0, "descartados": 0}

        for categoria, todos_os_termos in self.params["search_groups"].items():
            # Lotes de 8 termos para não estourar o limite de 512 chars da query[cite: 1]
            for lote in self._gerar_lotes(todos_os_termos, 8):
                termos_query = " OR ".join([f'"{t}"' for t in lote]) 
                query = f'"{modelo_limpo}" ({termos_query}) {string_negativa}'
                
                try:
                    search_results = subreddits.search(query, limit=self.params["limit_posts_per_keyword"], time_filter=time_filter)
                    
                    async for post in search_results:
                        manter, motivo = await self._filtrar_post(post, modelo_limpo, ids_processados)
                        
                        if not manter:
                            stats["descartados"] += 1
                            continue

                        # Carregamento assíncrono de comentários[cite: 1]
                        await post.comments.replace_more(limit=0)
                        comentarios = []
                        
                        # Converte a floresta de comentários em lista de forma assíncrona
                        comments_list = await post.comments.list()
                        for comment in comments_list[:25]:
                            if len(comment.body) > 10 and "I am a bot" not in comment.body:
                                comentarios.append({
                                    "id": comment.id,
                                    "conteudo": comment.body,
                                    "score": comment.score
                                })

                        if len(comentarios) > 0:
                            texto_analise = (post.title + " " + post.selftext).lower()
                            termos_encontrados = [t for t in lote if t.lower() in texto_analise]
                            
                            lista_posts.append({
                                "id": post.id,
                                "titulo": post.title,
                                "subreddit": post.subreddit.display_name,
                                "categoria": categoria,
                                "termos_especificos": termos_encontrados or ["discussao_geral"],
                                "num_comments": post.num_comments,
                                "data_post": datetime.datetime.fromtimestamp(post.created_utc).timestamp(),
                                "comentarios": comentarios
                            })
                            ids_processados.add(post.id)
                            stats["aceitos"] += 1

                except Exception as e:
                    if "429" in str(e):
                        print("🛑 RATE LIMIT! Dormindo 60s...")
                        await asyncio.sleep(60)
                    else:
                        print(f"⚠️ Erro no lote {categoria}: {e}")

        return lista_posts