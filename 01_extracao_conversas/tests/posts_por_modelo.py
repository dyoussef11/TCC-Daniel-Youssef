import json
import sys
from pathlib import Path
from core.paths import EXTRACAO_DATA, DATASET_FINAL_CSV

DIRETORIO_BRUTO = EXTRACAO_DATA / 'brutoV10'

def extrair_total_posts_ijson(caminho_arquivo):
    """Extrai 'total_posts' usando ijson (leitura incremental, ideal para arquivos grandes)."""
    import ijson
    try:
        with open(caminho_arquivo, 'rb') as f:
            parser = ijson.parse(f)
            for prefix, event, value in parser:
                if prefix == 'total_posts' and event == 'number':
                    return value
    except Exception as e:
        print(f"Erro ao processar {caminho_arquivo.name} com ijson: {e}", file=sys.stderr)
    return None

def extrair_total_posts_json_load(caminho_arquivo):
    """Extrai 'total_posts' carregando o JSON inteiro (pode consumir mais memória)."""
    try:
        with open(caminho_arquivo, 'r', encoding='utf-8') as f:
            dados = json.load(f)
        return dados.get('total_posts')
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
        print(f"Erro ao ler {caminho_arquivo.name}: {e}", file=sys.stderr)
        return None

def main(usar_ijson=True):
    if not DIRETORIO_BRUTO.exists():
        print(f"Diretório não encontrado: {DIRETORIO_BRUTO}", file=sys.stderr)
        return

    extractor = extrair_total_posts_ijson if usar_ijson else extrair_total_posts_json_load

    resultados = {}
    for arquivo in DIRETORIO_BRUTO.glob("*.json"):
        # print(f"Processando: {arquivo.name}")
        total = extractor(arquivo)
        if total is not None:
            resultados[arquivo.name] = total
        else:
            print(f"  -> Chave 'total_posts' não encontrada ou erro ao ler.")

    # Ordena os resultados em ordem decrescente (do maior total_posts para o menor)
    resultados_ordenados = sorted(resultados.items(), key=lambda item: item[1], reverse=True)

    print("\n--- RESULTADOS (ORDEM DECRESCENTE) ---")
    for nome, valor in resultados_ordenados:
        print(f"{nome}: total_posts = {valor}")

    # Opcional: salvar ordenado em um arquivo
    with open(DATASET_FINAL_CSV.parent / 'extraido_total_posts_ordenado.txt', 'w') as f:
        for nome, valor in resultados_ordenados:
            f.write(f"{nome},{valor}\n")

if __name__ == "__main__":
    try:
        import ijson
        print("Usando ijson para leitura eficiente.")
        main(usar_ijson=True)
    except ImportError:
        print("ijson não está instalado. Usando json.load padrão (pode consumir mais memória).")
        print("Para melhor desempenho com arquivos grandes, instale: pip install ijson")
        main(usar_ijson=False)