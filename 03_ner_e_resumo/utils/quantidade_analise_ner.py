from core.paths import NER_DATA
import json
from pathlib import Path

def contar_analises_ia(dados):
    # Предполагаем, что данные - это словарь с ключом 'posts'
    if isinstance(dados, dict) and 'posts' in dados and isinstance(dados['posts'], list):
        # Считаем количество постов, у которых есть 'analise_ia'
        # Можно просто len(dados['posts']), если все имеют
        return sum(1 for post in dados['posts'] if isinstance(post, dict) and 'analise_ia' in post)
    return 0

def main():
    caminho = NER_DATA / "Base_Conhecimento_ResumidaV13_VERIFICADA"
    if not caminho.exists():
        print(f"Erro: Caminho não encontrado: {caminho}")
        return

    arquivos = list(caminho.glob("*.json"))
    if not arquivos:
        print(f"Nenhum arquivo .json encontrado em {caminho}")
        return

    print(f"📁 Processando {len(arquivos)} arquivo(s)...\n")
    total_analises = 0
    contagens = []

    for arq in arquivos:
        try:
            with open(arq, 'r', encoding='utf-8') as f:
                dados = json.load(f)
            qtd = contar_analises_ia(dados)
            total_analises += qtd
            contagens.append((arq.name, qtd))
        except Exception as e:
            print(f"  ❌ Erro ao ler {arq.name}: {e}")
            contagens.append((arq.name, 0))

    # Exibe contagens por arquivo
    print("📄 Quantidade de análises_ia por arquivo:")
    for nome, qtd in contagens:
        print(f"  {nome}: {qtd}")
    print(f"\n✅ TOTAL DE ANÁLISES_IA: {total_analises}")

if __name__ == "__main__":
    main()