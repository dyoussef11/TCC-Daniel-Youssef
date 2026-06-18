import pandas as pd
from pathlib import Path
import logging
from core.paths import (
    DATASET_CONFIG,
    DATASET_GAMER,
    DATASET_KAGGLE,
    DATASET_FINAL_CSV,
    EXTRACAO_DATA   # certifique-se de que esta variável existe em core.paths
)

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def main():
    # Caminho do dataset final
    caminho_csv = DATASET_FINAL_CSV / "dataset_laptops_UNICOS_V10.csv"
    
    # Diretório com os arquivos originais
    diretorio_bruto = EXTRACAO_DATA / "brutoV10"
    
    if not caminho_csv.exists():
        logger.error(f"Arquivo CSV não encontrado: {caminho_csv}")
        return
    
    if not diretorio_bruto.exists() or not diretorio_bruto.is_dir():
        logger.error(f"Diretório bruto não encontrado: {diretorio_bruto}")
        return
    
    # 1. Carregar o CSV
    df = pd.read_csv(caminho_csv)
    logger.info(f"CSV carregado: {len(df)} registros")
    
    if 'id_unico' not in df.columns:
        logger.error("Coluna 'id_unico' não encontrada no CSV.")
        return
    
    # 2. Obter todos os nomes de arquivos (sem extensão) do diretório bruto
    arquivos = [p.stem for p in diretorio_bruto.glob("*") if p.is_file()]
    logger.info(f"Arquivos encontrados no diretório bruto: {len(arquivos)}")
    
    # 3. Converter a lista de ids do CSV para conjunto para comparação rápida
    ids_csv = set(df['id_unico'].astype(str).str.strip())
    ids_arquivos = set(arquivos)
    
    # 4. IDs que estão no CSV mas NÃO têm arquivo correspondente
    ids_orfãos = ids_csv - ids_arquivos
    logger.info(f"IDs sem arquivo correspondente: {len(ids_orfãos)}")
    
    if ids_orfãos:
        logger.warning("Lista de IDs órfãos (presentes no CSV, mas sem arquivo):")
        for idx, id_ in enumerate(sorted(ids_orfãos), 1):
            logger.warning(f"  {idx}. {id_}")
    else:
        logger.info("Todos os IDs do CSV possuem arquivo correspondente.")
    
    # 5. (Opcional) Filtrar o DataFrame mantendo apenas os registros com arquivo
    df_filtrado = df[df['id_unico'].astype(str).str.strip().isin(ids_arquivos)]
    logger.info(f"Registros após filtro (com arquivo): {len(df_filtrado)}")
    
    # Salvar o novo CSV filtrado (ou sobrescrever o original)
    # caminho_saida = DATASET_FINAL_CSV / "dataset_laptops_UNICOS_V10_com_arquivos.csv"
    # df_filtrado.to_csv(caminho_saida, index=False, encoding='utf-8')
    # logger.info(f"Novo CSV salvo em: {caminho_saida}")
    
    # Exibir também os IDs que estão nos arquivos mas não no CSV (opcional)
    ids_extra = ids_arquivos - ids_csv
    if ids_extra:
        logger.info(f"IDs que existem como arquivo, mas não estão no CSV: {len(ids_extra)}")
        # (opcional) listar os primeiros 10
        for id_ in sorted(ids_extra)[:10]:
            logger.info(f"  {id_}")

if __name__ == "__main__":
    main()