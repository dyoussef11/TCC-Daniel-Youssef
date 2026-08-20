import json
import sys
from collections import defaultdict
from pathlib import Path
import csv

def load_data(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if isinstance(data, dict):
        data = [data]
    return data

def count_summaries_by_model(data):
    counts = defaultdict(int)
    for entry in data:
        metadata = entry.get('metadata')
        if not metadata:
            continue
        model = metadata.get('model')
        summary = metadata.get('summary')
        if model and summary is not None:
            counts[model] += 1
    return dict(counts)

def print_counts(counts, sort_by='count', reverse=True):
    """Exibe a contagem em formato legível."""
    items = sorted(counts.items(), key=lambda x: x[1] if sort_by == 'count' else x[0], reverse=reverse)
    print("MODEL".ljust(50) + "COUNT")
    print("-" * 60)
    for model, count in items:
        print(f"{model[:48].ljust(50)} {count}")

def export_csv(counts, output_file):
    """Salva a lista em CSV."""
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['model', 'summary_count'])
        for model, count in sorted(counts.items()):
            writer.writerow([model, count])
    print(f"Arquivo CSV salvo como: {output_file}")

def list_summaries_for_model(data, model_name):
    """Exibe todos os resumos de um modelo específico."""
    found = False
    for entry in data:
        metadata = entry.get('metadata', {})
        if metadata.get('model') == model_name:
            summary = metadata.get('summary')
            if summary:
                print(f"- {summary}")
                found = True
    if not found:
        print(f"Nenhum resumo encontrado para o modelo '{model_name}'.")

def main():
    # Caminho padrão
    file_path = "04_vetorizacao/data/base_conhecimento_multilingueV9.meta.json"
    
    # Se passar argumentos, interpreta como comando
    if len(sys.argv) > 1:
        # Primeiro argumento pode ser o caminho do arquivo ou um comando especial
        if sys.argv[1] in ['--csv', '--list']:
            # Usa o caminho padrão e o comando vem depois
            pass
        else:
            # Assume que é o caminho do arquivo
            file_path = sys.argv[1]
    
    if not Path(file_path).exists():
        print(f"Arquivo não encontrado: {file_path}")
        return
    
    data = load_data(file_path)
    counts = count_summaries_by_model(data)
    
    if not counts:
        print("Nenhum resumo encontrado.")
        return
    
    # Processa comandos adicionais
    if '--csv' in sys.argv:
        output_csv = r"04_vetorizacao/utils/contagem_modelos.csv"
        export_csv(counts, output_csv)
    
    if '--list' in sys.argv:
        # O próximo argumento é o nome do modelo
        try:
            model_idx = sys.argv.index('--list') + 1
            if model_idx < len(sys.argv):
                model_name = sys.argv[model_idx]
                list_summaries_for_model(data, model_name)
            else:
                print("Uso: --list <nome_do_modelo>")
        except ValueError:
            print("Uso: --list <nome_do_modelo>")
    
    # Sempre exibe a contagem (a menos que só queira CSV ou list)
    if '--csv' not in sys.argv and '--list' not in sys.argv:
        print_counts(counts)
    elif '--list' in sys.argv:
        print_counts(counts)  # exibe a contagem junto com a lista de resumos

if __name__ == "__main__":
    main()