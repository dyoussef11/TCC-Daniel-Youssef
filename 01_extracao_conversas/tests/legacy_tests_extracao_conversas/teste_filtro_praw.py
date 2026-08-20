import praw
import configparser
from pathlib import Path
import re

from core.paths import EXTRACAO_SRC_EXTRACTORS

# 1. Configuração de acesso (Lendo do seu praw.ini)
def iniciar_reddit():
    # Seguindo o caminho que você definiu no reddit_serviceV2.py
    caminho_ini: Path = EXTRACAO_SRC_EXTRACTORS / "praw.ini" 
    config = configparser.ConfigParser()
    
    if not caminho_ini.exists():
        print(f"❌ Erro: Arquivo {caminho_ini} não encontrado.")
        return None

    config.read(caminho_ini, encoding='utf-8')
    return praw.Reddit(
        client_id=config['DEFAULT']['client_id'],
        client_secret=config['DEFAULT']['client_secret'],
        user_agent="TestFilterBot/1.0 (by u/DanielYoussef)" # User-agent sugerido
    )

# 2. Lógica de Filtragem (Baseada nos seus search_groups)
SEARCH_GROUPS = {
    "performance": ["fps drop", "stuttering", "bottleneck", "benchmarks", "low performance"],
    "thermal": ["overheating", "thermal throttling", "undervolt", "repaste", "fan noise"],
    "stability": ["bsod", "system freeze", "driver crash"]
}

SUBREDDIT_BLACKLIST = ["laptopdeals", "suggestalaptop", "promos", "coupons"]

def eh_relevante(post, modelo_alvo):
    # Filtro 1: Subreddit de venda/promoção
    if post.subreddit.display_name.lower() in SUBREDDIT_BLACKLIST:
        return False, "Subreddit Comercial"

    texto_completo = (post.title + " " + post.selftext).lower()
    
    # Filtro 2: O modelo alvo deve estar no texto (Evita falso positivo da busca)
    if modelo_alvo.lower() not in texto_completo:
        return False, "Modelo não citado no corpo"

    # Filtro 3: Deve conter ao menos um termo técnico dos seus grupos
    termos_tecnicos = [t for sublista in SEARCH_GROUPS.values() for t in sublista]
    tem_termo = any(t in texto_completo for t in termos_tecnicos)
    
    if not tem_termo:
        return False, "Sem termos técnicos (Provavelmente post genérico)"

    return True, "RELEVANTE"

# 3. Execução do Teste
def executar_teste(modelo_para_busca="Legion 5"):
    reddit = iniciar_reddit()
    if not reddit: return

    print(f"🚀 Iniciando busca real para: '{modelo_para_busca}' em r/all")
    print("-" * 60)

    # Buscando 50 posts para o teste (para ser rápido)
    resultados = reddit.subreddit("all").search(modelo_para_busca, limit=50, time_filter="year")

    aprovados = 0
    descartados = 0

    for post in resultados:
        relevante, motivo = eh_relevante(post, modelo_para_busca)
        
        if relevante:
            aprovados += 1
            print(f"✅ [APROVADO] r/{post.subreddit.display_name}")
            print(f"   Título: {post.title[:70]}...")
        else:
            descartados += 1
            print(f"❌ [DESCARTADO] Motivo: {motivo} | r/{post.subreddit.display_name}")

    print("-" * 60)
    print(f"📊 Resumo do Teste:")
    print(f"   Posts Analisados: {aprovados + descartados}")
    print(f"   Posts Úteis: {aprovados}")
    print(f"   Lixo Filtrado: {descartados}")

if __name__ == "__main__":
    # Você pode trocar por qualquer modelo do seu CSV
    executar_teste("HP Victus")