
import pandas as pd


# Supondo que as importações do seu projeto continuem as mesmas
from core.paths import DATASET_FINAL_CSV

print("[Verificação de Duplicatas - Dataset]")
dataset_gamer = pd.read_csv(DATASET_FINAL_CSV / 'dataset_laptops_GAMER_ONLY_V2.csv')
tem_duplicata_nome_modelo = dataset_gamer.duplicated(subset='modelo_limpo').sum()

if tem_duplicata_nome_modelo > 0:
    reformado_dataset_gamer = dataset_gamer.drop_duplicates(subset=["modelo_limpo"])
    print("Quantidade de Duplicatas:",reformado_dataset_gamer)
    
    reformado_dataset_gamer.to_csv(DATASET_FINAL_CSV / 'dataset_laptops_GAMER_ONLY_V2.csv',index=False)
    print("Novo tamanho (Dataset):",len(reformado_dataset_gamer))

else:
    print("R: Sem duplicatas - Nome de modelos.")

