import pandas as pd
from pathlib import Path
import logging
import shutil
from core.paths import (
    DATASET_FINAL_CSV,
    EXTRACAO_DATA
)

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def main():
    # Caminhos
    caminho_csv = DATASET_FINAL_CSV / "dataset_laptops_UNICOS_V10.csv"
    diretorio_bruto = EXTRACAO_DATA / "brutoV10"

    # Validações
    if not caminho_csv.exists():
        logger.error(f"CSV não encontrado: {caminho_csv}")
        return

    if not diretorio_bruto.exists() or not diretorio_bruto.is_dir():
        logger.error(f"Diretório bruto não encontrado: {diretorio_bruto}")
        return

    # 1. Carregar os IDs válidos do CSV
    df = pd.read_csv(caminho_csv)
    if 'id_unico' not in df.columns:
        logger.error("Coluna 'id_unico' não encontrada no CSV.")
        return

    ids_validos = set(df['id_unico'].astype(str).str.strip())
    logger.info(f"✅ IDs válidos carregados do CSV: {len(ids_validos)}")

    # 2. Listar todos os arquivos do diretório bruto
    todos_arquivos = [p for p in diretorio_bruto.glob("*") if p.is_file()]
    logger.info(f"📁 Total de arquivos em 'brutoV10': {len(todos_arquivos)}")

    # 3. Identificar os arquivos cujo nome (sem extensão) NÃO está no CSV
    arquivos_para_remover = []
    for arquivo in todos_arquivos:
        id_arquivo = arquivo.stem  # nome sem extensão
        if id_arquivo not in ids_validos:
            arquivos_para_remover.append(arquivo)

    logger.warning(f"⚠️ Arquivos SEM correspondência no CSV: {len(arquivos_para_remover)}")

    if not arquivos_para_remover:
        logger.info("🎉 Nenhum arquivo órfão encontrado. Nada a fazer.")
        return

    # Exibir os primeiros 10 arquivos órfãos para conferência
    logger.info("📋 Exemplos de arquivos que serão movidos:")
    for arq in arquivos_para_remover[:10]:
        logger.info(f"   - {arq.name}")

    # 4. Criar uma pasta de "lixeira" dentro do diretório bruto
    pasta_lixeira = EXTRACAO_DATA / "removidos_sem_id"
    pasta_lixeira.mkdir(exist_ok=True)

    logger.info(f"📦 Movendo arquivos para: {pasta_lixeira}")

    # 5. Mover os arquivos (em vez de deletar)
    for arq in arquivos_para_remover:
        try:
            destino = pasta_lixeira / arq.name
            shutil.move(str(arq), str(destino))
        except Exception as e:
            logger.error(f"❌ Erro ao mover {arq.name}: {e}")

    logger.info(f"✅ {len(arquivos_para_remover)} arquivos movidos com sucesso para '{pasta_lixeira}'.")

    # (Opcional) Se você quiser DELETAR PERMANENTEMENTE, descomente o bloco abaixo
    # e comente o shutil.move acima.
    #
    # for arq in arquivos_para_remover:
    #     try:
    #         arq.unlink()  # deleta permanentemente
    #     except Exception as e:
    #         logger.error(f"Erro ao deletar {arq.name}: {e}")
    # logger.info(f"{len(arquivos_para_remover)} arquivos deletados permanentemente.")

if __name__ == "__main__":
    main()