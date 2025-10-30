import requests
import time
import random
from datetime import datetime

# Cabeçalhos realistas
HEADERS = {
    'User-Agent': random.choice([
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5_2) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15'
    ]),
    'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
}

# URLs a testar
urls_teste = [
    ("Inspirion 15 3511", "https://www.dell.com/community/pt/conversations/inspiron-laptops/inspirion-15-3511/647fa152f4ccf8a8de687f19?keyword=%22G5%2015%205590%22,G5 15 5590"),
    
]

# Intervalo entre verificações (em segundos)
INTERVALO = 30 * 60  # 30 minutos

def testar_links():
    print(f"\n🕒 {datetime.now().strftime('%d/%m/%Y %H:%M:%S')} — Iniciando verificação dos links...\n")

    desbloqueado = False
    for nome, url in urls_teste:
        pausa = random.uniform(2, 4)
        print(f"⏳ Aguardando {pausa:.1f}s antes de testar '{nome}'...")
        time.sleep(pausa)

        try:
            r = requests.get(url, headers=HEADERS, timeout=10)
            status = r.status_code
            tamanho = len(r.content)
            print(f"➡️ {nome} | Status: {status} | Tamanho: {tamanho} bytes")

            if status == 200:
                print(f"   ✅ OK — '{nome}' está acessível novamente!\n")
                desbloqueado = True
            elif status == 403:
                print("   ⚠️ Ainda bloqueado (HTTP 403).\n")
            else:
                print(f"   ℹ️ Resposta inesperada: {status}\n")

        except requests.exceptions.RequestException as e:
            print(f"   ❌ Erro ao acessar '{nome}': {e}\n")

    return desbloqueado


if __name__ == "__main__":
    while True:
        if testar_links():
            print("🎉 Pelo menos um link voltou a responder com sucesso (HTTP 200)!")
            print("🧭 Encerrando monitoramento automático.\n")
            break

        print(f"⌛ Aguardando {INTERVALO / 60:.0f} minutos para nova verificação...\n")
        time.sleep(INTERVALO)
