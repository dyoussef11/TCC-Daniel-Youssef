import praw
import configparser
from pathlib import Path
import re

# Importando seus caminhos definidos
from core.paths import EXTRACAO, EXTRACAO_SRC_EXTRACTORS

def iniciar_reddit():
    caminho_ini: Path = EXTRACAO_SRC_EXTRACTORS / "praw.ini"
    config = configparser.ConfigParser()
    
    if not caminho_ini.exists():
        print(f"❌ Erro: Arquivo {caminho_ini} não encontrado.")
        return None

    config.read(caminho_ini, encoding='utf-8')
    return praw.Reddit(
        client_id=config['DEFAULT']['client_id'],
        client_secret=config['DEFAULT']['client_secret'],
        user_agent="ThemeFilterBot/1.0 (by u/DanielYoussef)"
    )

# Grupos de palavras para identificar o "TEMA" do Subreddit pela descrição
TEMAS_FILTRO = {
    "comercial": ["sale", "deal", "price", "discount", "store", "buy", "sell", "marketplace", "promo", "coupon"],
    "tecnico": ["support", "tech", "help", "gaming", "performance", "laptop", "community", "drivers", "hardware"]
}

def analisar_tema_subreddit(subreddit_obj):
    """
    Analisa se a descrição do subreddit condiz com o tema de pesquisa técnica.
    """
    # Pega a descrição pública (pode ser vazia)
    desc = (subreddit_obj.public_description or "").lower()
    nome = subreddit_obj.display_name.lower()
    meta_texto = f"{nome} {desc}"

    # Verifica se o tema parece ser comercial (Vendas/Ofertas)
    if any(palavra in meta_texto for palavra in TEMAS_FILTRO["comercial"]):
        return False, "Tema Comercial/Vendas"
    
    # Se tiver palavras técnicas ou for um sub de marca (comum em notebooks)
    if any(palavra in meta_texto for palavra in TEMAS_FILTRO["tecnico"]):
        return True, "Tema Técnico/Comunidade"

    # Caso não tenha descrição clara, deixamos passar se não for explicitamente comercial
    return True, "Tema Neutro (Permitido)"

def eh_relevante(post, modelo_alvo):
    # 1. Filtro de Tema por Descrição do Subreddit
    # Nota: subreddit_obj.public_description faz uma chamada de API extra se não estiver em cache
    tema_valido, motivo_tema = analisar_tema_subreddit(post.subreddit)
    if not tema_valido:
        return False, motivo_tema

    texto_completo = (post.title + " " + post.selftext).lower()
    
    # 2. Garantia de Menção ao Modelo
    if modelo_alvo.lower() not in texto_completo:
        return False, "Modelo não citado no corpo"

    # 3. Filtro de Termos Técnicos (Performance/Thermal)
    # Pegando do seu dicionário original de buscas
    SEARCH_GROUPS = {
        "perf": ["fps drop", "stuttering", "bottleneck", "benchmarks"],
        "therm": ["overheating", "thermal throttling", "undervolt", "repaste"],
        "stab": ["bsod", "system freeze", "driver crash"]
    }
    termos_tecnicos = [t for sublista in SEARCH_GROUPS.values() for t in sublista]
    if not any(t in texto_completo for t in termos_tecnicos):
        return False, "Sem termos técnicos (Post genérico)"

    return True, "RELEVANTE"

def executar_teste(modelo_para_busca="victus_15_fb0157ax"):
    reddit = iniciar_reddit()
    if not reddit: return

    # Limpando o modelo para a busca (removendo SKU muito específico se necessário)
    query_busca = modelo_para_busca.split('_')[0] + " " + modelo_para_busca.split('_')[1]
    
    print(f"🚀 Buscando: '{query_busca}' | Analisando Temas de Subreddits...")
    print("-" * 70)

    # Aumentamos o limite para ver a filtragem de "temas" em ação
    resultados = reddit.subreddit("all").search(query_busca, limit=30, time_filter="year")

    for post in resultados:
        relevante, motivo = eh_relevante(post, modelo_para_busca)
        status = "✅ [OK]" if relevante else f"❌ [{motivo}]"
        print(f"{status} r/{post.subreddit.display_name}: {post.title[:50]}...")

if __name__ == "__main__":
    executar_teste()