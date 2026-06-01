import praw
import datetime
import time
import configparser
from pathlib import Path
from core_extration.base_extractor import BaseExtractor

class RedditServiceV5(BaseExtractor):
    def __init__(self):
        super().__init__(platform="reddit")
        
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

            self.params = self.config["reddit_params"]
            self.termos_negativos = self.params.get("negative_terms", [])
            
        except Exception as e:
            raise Exception(f"Falha na conexão com a API do Reddit: {e}")

    def consultar_limites_api(self):
        stats = self.reddit.auth.limits
        return {
            "restante": stats.get('remaining'),
            "reset_em": stats.get('reset_timestamp')
        }

    def _analisar_tema_subreddit(self, subreddit):
        """Verifica se o subreddit é comercial/venda pela descrição pública."""
        blacklist_temas = ["sale", "deal", "price", "discount", "store", "promo", "coupon", "marketplace"]
        try:
            desc = (subreddit.public_description or "").lower()
            nome = subreddit.display_name.lower()
            texto_meta = f"{nome} {desc}"
            if any(termo in texto_meta for termo in blacklist_temas):
                return False, f"Subreddit Comercial (r/{nome})"
        except:
            pass # Alguns subs privados podem dar erro ao acessar descrição
        return True, None

    def _filtrar_post(self, post, modelo_limpo, ids_processados):
        """Filtros de qualidade para garantir relevância técnica."""

        if post.id in ids_processados: return False, "Duplicado"

        if post.over_18: return False, "NSFW"

        # --- NOVA REGRA: IGNORAR ZERO COMENTÁRIOS ---
        if post.num_comments == 0: 
            return False, "Sem comentários"

        if not post.selftext or len(post.selftext) < 20: return False, "Muito curto"
        
        tema_ok, motivo = self._analisar_tema_subreddit(post.subreddit)

        if not tema_ok: return False, motivo

        texto_completo = (post.title + " " + post.selftext).lower()
        if modelo_limpo.lower() not in texto_completo:
            return False, "Modelo ausente no texto"
        
        return True, None

    def buscar_modelo(self, modelo_busca, time_filter="year"):
        lista_posts = []
        ids_processados = set()
        modelo_limpo = modelo_busca.replace('"', '')
        subreddits = self.reddit.subreddit(self.params["subreddits"])
        
        # Cria a string de exclusão: "-sale -deal -price ..."
        string_negativa = " ".join([f"-{t}" for t in self.termos_negativos])

        # Log de início de tarefa
        print(f"\n{'='*60}\n🚀 INICIANDO EXTRAÇÃO: {modelo_busca}\n{'='*60}")
        stats_geral = {"aceitos": 0, "descartados": 0}

        for categoria, termos in self.params["search_groups"].items():
            # Query otimizada para o Reddit[cite: 10, 11]
            termos_query = " OR ".join([f'"{t}"' for t in termos[:12]]) 
            # query = f'"{modelo_limpo}" ({termos_query})'
            query = f'"{modelo_limpo}" ({termos_query}) {string_negativa}'
            
            # print(f"\n🔍 Query [{categoria}]: {query[:80]}...")
            print(f"\n🔍 Query Otimizada [{categoria}]: {query}...")
            
            try:
                # Busca com o limite de 1000 posts do V4[cite: 8, 11]
                search_results = subreddits.search(
                    query, 
                    limit=self.params["limit_posts_per_keyword"], 
                    time_filter=time_filter
                )
                
                count_cat = 0
                for post in search_results:
                    manter, motivo = self._filtrar_post(post, modelo_limpo, ids_processados)
                    
                    if not manter:
                        stats_geral["descartados"] += 1
                        continue

                    # Processamento de comentários
                    post.comments.replace_more(limit=0)
                    comentarios = []
                    for comment in post.comments.list():
                        if len(comment.body) > 10 and "I am a bot" not in comment.body:
                            comentarios.append({
                                "id": comment.id,
                                "conteudo": comment.body,
                                "score": comment.score
                            })

                
                    # GARANTIA DE PREENCHIMENTO: Cruza o texto com TODOS os termos da categoria[cite: 10, 11]
                    texto_analise = (post.title + " " + post.selftext).lower()
                    termos_encontrados = [t for t in termos if t.lower() in texto_analise]
                    
                    # Se achou o post mas nenhum termo exato (devido a busca flexível do Reddit)
                    if not termos_encontrados:
                        termos_encontrados = ["discussao_geral"]

                    lista_posts.append({
                        "id": post.id,
                        "titulo": post.title,
                        "subreddit": post.subreddit.display_name,
                        "categoria": categoria,
                        "termos_especificos": termos_encontrados, # <--- Garantia de preenchimento
                        "num_comments": post.num_comments,
                        "data_post": datetime.datetime.fromtimestamp(post.created_utc).timestamp(),
                        "comentarios": comentarios
                    })
                    ids_processados.add(post.id)
                    count_cat += 1
                    stats_geral["aceitos"] += 1

                print(f"   ✅ Categoria finalizada: {count_cat} posts relevantes encontrados.")

            except Exception as e:
                if "429" in str(e):
                    print("   🛑 RATE LIMIT! Dormindo 40s para reset...")
                    time.sleep(40)
                else:
                    print(f"   ⚠️ Erro na categoria {categoria}: {e}")

        # Resumo final do modelo para o log[cite: 11]
        print(f"\n📊 RESUMO {modelo_busca}: {stats_geral['aceitos']} aceitos | {stats_geral['descartados']} filtrados.")
        return lista_posts