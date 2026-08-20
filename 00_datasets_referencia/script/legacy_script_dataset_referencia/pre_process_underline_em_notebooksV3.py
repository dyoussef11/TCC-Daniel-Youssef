import json
import re
import pandas as pd
from pathlib import Path
import logging

# Configura logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

from core.paths import (
    DATASET_CONFIG,
    DATASET_GAMER,
    DATASET_KAGGLE
)

def limpar_modelo_completo(texto: str) -> str:
    """
    Limpeza padronizada do modelo_completo:
    - Normaliza para minúsculas
    - Remove caracteres especiais: (, ), /
    - Converte hífens (-) e espaços para underscore (_)
    - Remove múltiplos underscores e espaços nas pontas
    """
    if not isinstance(texto, str) or pd.isna(texto) or texto.lower() == 'nan':
        return ""
    
    # Converte para minúsculas e remove espaços em branco nas pontas
    texto = texto.strip().lower()
    
    # 1. Remove os caracteres ( ) /
    texto = re.sub(r'[()/]', '', texto)
    
    # 2. Converte hífens e espaços em underscores
    texto = re.sub(r'[\s\-]+', '_', texto)
    
    # 3. Remove underscores duplicados que possam ter surgido
    texto = re.sub(r'_{2,}', '_', texto)
    
    # Remove underscores residuais nas pontas
    texto = texto.strip('_')
    
    return texto if len(texto) >= 2 else "modelo_nao_identificado"

def encontrar_colunas_originais(df: pd.DataFrame, mapeamento_colunas: dict, nome_arquivo: str) -> list:
    """
    Retorna uma lista de colunas que devem ser unidas para formar o modelo.
    Caso específico para 'Brand-Wise Laptop Price Dataset.csv' solicitado pelo usuário.
    """
    # Força a junção das 6 colunas específicas para este dataset
    if "Brand-Wise Laptop Price Dataset" in nome_arquivo:
        colunas_alvo = ["Company", "Product", "TypeName", "OS", "CPU_model", "GPU_model"]
        # Garante que só vamos usar as colunas que realmente existem no arquivo
        return [col for col in colunas_alvo if col in df.columns]

    # Regra geral para os outros datasets
    for coluna_original, coluna_destino in mapeamento_colunas.items():
        if coluna_destino == "modelo_completo":
            return [coluna_original]
        if isinstance(coluna_destino, list) and "modelo_completo" in coluna_destino:
            # Se no JSON for uma lista, verifica se é uma lista de colunas originais
            return coluna_destino if isinstance(coluna_destino, list) else [coluna_original]
    
    # Fallback
    colunas_conhecidas = ['Model', 'model', 'Product', 'model_name', 'Laptop Name', 'Product name']
    for col in colunas_conhecidas:
        if col in df.columns:
            return [col]
    
    return []

def processar_dataset_limpeza_inicial(caminho_entrada: Path, caminho_saida: Path, mapeamento_colunas: dict):
    """
    Carrega o dataset, une as colunas necessárias, aplica a limpeza e salva
    """
    logger.info(f"📂 Processando: {caminho_entrada.name}")
    
    try:
        enc = 'latin1' if 'Unveiling' in caminho_entrada.name else 'utf-8'
        df = pd.read_csv(caminho_entrada, encoding=enc)
    except Exception as e:
        logger.error(f"   ❌ Erro ao ler arquivo: {e}")
        return None
    
    logger.info(f"   Linhas originais: {len(df)}")
    
    # Encontra a lista de colunas que vão compor o modelo
    colunas_originais = encontrar_colunas_originais(df, mapeamento_colunas, caminho_entrada.name)
    
    if not colunas_originais:
        logger.warning(f"   ⚠️ Não foi possível encontrar colunas de modelo!")
        return None
    
    logger.info(f"   Colunas originais utilizadas: {colunas_originais}")
    
    # Se houver mais de uma coluna, junta os textos com espaço (que depois virará underscore)
    if len(colunas_originais) > 1:
        # astype(str) previne erros com valores nulos ou numéricos durante a junção
        serie_modelo = df[colunas_originais].astype(str).agg(' '.join, axis=1)
    else:
        serie_modelo = df[colunas_originais[0]]
    
    # Aplica a limpeza padronizada
    df['modelo_completo_limpo'] = serie_modelo.astype(str).apply(limpar_modelo_completo)
    
    # Remove linhas que ficaram vazias ou não identificadas
    antes = len(df)
    df = df[df['modelo_completo_limpo'] != '']
    df = df[~df['modelo_completo_limpo'].str.contains('modelo_nao_identificado', na=False)]
    removidas = antes - len(df)
    if removidas > 0:
        logger.info(f"   Removidas {removidas} linhas com modelo inválido")
    
    logger.info(f"   Linhas após limpeza: {len(df)}")
    
    # Mostra exemplos no console
    logger.info(f"\n📊 Exemplos de formatação:")
    for idx, row in df.head(3).iterrows():
        # Mostra o resultado final gerado
        limpo = row['modelo_completo_limpo']
        logger.info(f"   {idx+1}. Resultado Limpo: {limpo}")
    
    # Salva o arquivo modificado
    try:
        caminho_saida.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(caminho_saida, index=False, encoding='utf-8')
        logger.info(f"   ✅ Salvo em: {caminho_saida}")
        return df
    except Exception as e:
        logger.error(f"   ❌ Erro ao salvar: {e}")
        return None

def main():
    PATH_CONFIG = DATASET_CONFIG
    PATH_DADOS = DATASET_KAGGLE
    
    OUTPUT_DIR = DATASET_GAMER /"em_tratamento"/"limpos_underline"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    logger.info(f"📁 Diretório de saída: {OUTPUT_DIR}")
    
    try:
        with open(PATH_CONFIG / "mapeamento_arquivos_aprimorado.json", 'r', encoding='utf-8') as f:
            mapeamentos_json = json.load(f)["mapeamentos"]
    except Exception as e:
        logger.error(f"Erro ao carregar mapeamento: {e}")
        return
    
    for item in mapeamentos_json:
        arquivo = item["arquivo"]
        caminho_entrada = PATH_DADOS / arquivo
        
        if not caminho_entrada.exists():
            logger.warning(f"⚠️ Arquivo não encontrado: {arquivo}")
            continue
        
        nome_saida = f"limpo_{arquivo.replace('/', '_').replace('\\', '_')}"
        caminho_saida = OUTPUT_DIR / nome_saida
        mapeamento_colunas = item.get("colunas", {})
        
        processar_dataset_limpeza_inicial(caminho_entrada, caminho_saida, mapeamento_colunas)
        print("-" * 50)
    
    logger.info("\n🎉 Processamento concluído com as colunas combinadas!")

if __name__ == "__main__":
    main()