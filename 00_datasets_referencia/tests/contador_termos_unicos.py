import csv
from collections import Counter
from pathlib import Path
from core.paths import DATASET_FINAL_CSV

# Caminho do arquivo CSV de entrada
PATH_OUTPUT = DATASET_FINAL_CSV / "dataset_laptops_UNICOS_V10.csv"

def contar_termos_modelo_completo(caminho_csv):
    """
    Lê o CSV, extrai termos da coluna 'modelo_completo' (split por '_'),
    e retorna um Counter com a frequência de cada termo.
    """
    contador = Counter()
    
    with open(caminho_csv, 'r', encoding='utf-8') as f:
        # Detecta o delimitador (assumindo vírgula; se for ponto e vírgula, ajuste)
        leitor = csv.DictReader(f)
        
        # Verifica se a coluna 'modelo_completo' existe
        if 'modelo_completo' not in leitor.fieldnames:
            print(f"ERRO: A coluna 'modelo_completo' não foi encontrada no CSV.")
            print(f"Colunas disponíveis: {leitor.fieldnames}")
            return contador
        
        for linha in leitor:
            valor = linha.get('modelo_completo', '').strip()
            if not valor:
                continue
            # Divide por underscore e remove espaços extras de cada termo
            termos = [termo.strip() for termo in valor.split('_') if termo.strip()]
            contador.update(termos)
    
    return contador

def salvar_resultados(contador, arquivo_saida=None):
    """
    Exibe e opcionalmente salva os resultados em ordem decrescente de frequência.
    """
    # Ordena do termo mais frequente para o menos frequente
    itens_ordenados = contador.most_common()
    
    print(f"\n{'TERMO':<30} | {'FREQUÊNCIA':>10}")
    print("-" * 45)
    for termo, freq in itens_ordenados:
        print(f"{termo:<30} | {freq:>10}")
    
    if arquivo_saida:
        with open(arquivo_saida, 'w', encoding='utf-8', newline='') as f:
            escritor = csv.writer(f)
            escritor.writerow(['termo', 'frequencia'])
            escritor.writerows(itens_ordenados)
        print(f"\nResultados salvos em: {arquivo_saida}")

if __name__ == "__main__":
    if not PATH_OUTPUT.exists():
        print(f"Arquivo não encontrado: {PATH_OUTPUT}")
    else:
        contagem = contar_termos_modelo_completo(PATH_OUTPUT)
        if contagem:
            # Salva o resultado em um CSV próximo (opcional)
            arquivo_saida = DATASET_FINAL_CSV / "frequencia_termos_modelo_completo.csv"
            salvar_resultados(contagem, arquivo_saida)
        else:
            print("Nenhum termo foi extraído (coluna vazia ou inexistente).")