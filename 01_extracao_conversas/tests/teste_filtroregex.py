import re
import pandas as pd
from core.paths import DATASET_FINAL_CSV

# Regex que suporta 4 ou 5 segmentos
pattern = re.compile(
    r'^(?P<marca>[^_]+)_'                    # Marca
    r'(?:(?P<modelo_generico>[^_]+)_)?'      # Modelo genérico (opcional)
    r'(?P<modelo_limpo>[^_]+?)_'             # Modelo limpo
    r'(?P<cpu>.+?)_'                         # CPU (qualquer caractere até o último _)
    r'(?P<ram>\d+)'                          # RAM
    r'(?:gb|g|gb\w*)?$'                      # Opcional: gb, g, ou outros sufixos
)

# Regex alternativo para IDs que podem ter partes extras (ex: "2_corei7_16")
pattern_alternativo = re.compile(
    r'^(?P<marca>[^_]+)_'
    r'(?:(?P<modelo_generico>[^_]+)_)?'
    r'(?:(?P<modelo_limpo>[^_]+?)_)?'
    r'(?P<cpu>[^_]+?)_'
    r'(?P<ram>\d+)(?:gb|g)?$'
)

def parse_sku(sku, pattern):
    """Tenta parsear uma SKU com diferentes padrões"""
    if pd.isna(sku) or not isinstance(sku, str):
        return None
    
    # Primeiro tenta o padrão principal
    match = pattern.match(sku)
    if match:
        return match.groupdict()
    
    # Se falhar, tenta o padrão alternativo
    match = pattern_alternativo.match(sku)
    if match:
        return match.groupdict()
    
    return None

# Carregar o CSV
caminho = DATASET_FINAL_CSV / "dataset_laptops_UNICOS_V7.csv"
df = pd.read_csv(caminho)

# Analisar todas as SKUs
total = len(df)
detectadas = 0
nao_detectadas = []
resultados = []

for idx, sku in enumerate(df['id_unico']):
    parsed = parse_sku(sku, pattern)
    if parsed:
        detectadas += 1
        resultados.append(parsed)
    else:
        nao_detectadas.append((idx, sku))

print(f"Total de SKUs: {total}")
print(f"Detectadas: {detectadas} ({detectadas/total*100:.2f}%)")
print(f"Não detectadas: {len(nao_detectadas)} ({len(nao_detectadas)/total*100:.2f}%)")

# Analisar padrões das não detectadas
print("\n=== ANÁLISE DAS SKUs NÃO DETECTADAS ===")
tipos_problemas = {
    'formato_gen_na': 0,
    'cpu_com_caracteres_especiais': 0,
    'ram_com_sufixo_estranho': 0,
    'numero_incorreto_campos': 0,
    'outros': 0
}

for idx, sku in nao_detectadas[:50]:  # Analisa primeiras 50
    if sku.startswith('gen_') and sku.endswith('_na'):
        tipos_problemas['formato_gen_na'] += 1
    elif re.search(r'[®™©]', sku):
        tipos_problemas['cpu_com_caracteres_especiais'] += 1
    elif re.search(r'ram[^_]+$', sku):
        tipos_problemas['ram_com_sufixo_estranho'] += 1
    else:
        partes = sku.split('_')
        if len(partes) not in [4, 5]:
            tipos_problemas['numero_incorreto_campos'] += 1
        else:
            tipos_problemas['outros'] += 1
            print(f"  Exemplo não classificado: {sku}")

print("\nDistribuição dos problemas:")
for tipo, count in tipos_problemas.items():
    print(f"  {tipo}: {count}")