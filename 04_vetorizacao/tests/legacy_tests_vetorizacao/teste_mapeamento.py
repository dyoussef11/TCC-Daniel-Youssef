# teste_mapeamento.py
import sys
from pathlib import Path
from core.paths import DATASET_FINAL_CSV

from core.paths import VETORIZATION_SCRIPT

for path in [VETORIZATION_SCRIPT]:
    if str(path) not in sys.path:
        sys.path.append(str(path))


from mapeamento_modelos import carregar_mapeamento_por_modelo_limpo, obter_nome_modelo

# Caminho do CSV (ajuste se necessário)
CSV_PATH =  Path(DATASET_FINAL_CSV /"dataset_laptops_UNICOS_V10.csv") 

# Carrega o mapa
mapa = carregar_mapeamento_por_modelo_limpo(CSV_PATH)

# Lista de exemplos: (modelo_original, marca_do_arquivo)
exemplos = [
    ("proart_p16_h7606wp_me021x", "asus"),
    ("g15_5530_15_2023", "dell"),
    ("15_fc0028au", "hp"),
    ("an515_58", "acer"),
    ("vivobook_16x_2023_k3605zf_mb541ws", "asus"),
    ("modelo_inexistente", "marca_teste"),
]

print("=" * 70)
print("🧪 TESTE DE MAPEAMENTO DE MODELOS")
print("=" * 70)

for original, marca in exemplos:
    nome_obtido = obter_nome_modelo(original, marca, mapa)
    print(f"Original: {original}")
    print(f"Marca:    {marca}")
    print(f"Resultado: {nome_obtido}")
    print("-" * 50)