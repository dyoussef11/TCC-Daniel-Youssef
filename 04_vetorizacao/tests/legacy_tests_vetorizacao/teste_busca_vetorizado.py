import json
from pathlib import Path
import sys

from core.paths import VETORIZATION_SCRIPT

for path in [VETORIZATION_SCRIPT]:
    if str(path) not in sys.path:
        sys.path.append(str(path))


from mapeamento_modelos import carregar_mapeamento_por_modelo_limpo, obter_nome_modelo

# Carrega um arquivo NER de exemplo
with open('NER_g15_5530_15_2023_na_na_na.json') as f:
    dados = json.load(f)

modelo_original = dados.get('modelo_original', '')
modelo_generico = dados.get('modelo_generico', '')

# Simula o mapeamento
mapa = carregar_mapeamento_por_modelo_limpo(Path('dataset_laptops_UNICOS_V10.csv'))
nome = obter_nome_modelo(modelo_original, modelo_generico, 'dell', mapa)
print(nome)  # Deve imprimir 'Dell G15 5530' ou similar