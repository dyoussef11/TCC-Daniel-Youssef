import json
import pandas as pd
from pathlib import Path
import logging

# Configura logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

from core.paths import (
    DATASET_CONFIG,
    DATASET_FINAL_CSV,
    DATASET_GAMER
)

def encontrar_coluna_marca(df: pd.DataFrame, mapeamento_colunas: dict) -> str:
    """
    Encontra qual coluna original mapeia para 'marca' baseando-se estritamente no JSON.
    """
    for coluna_original, coluna_destino in mapeamento_colunas.items():
        if coluna_destino == "marca":
            return coluna_original
    return None

def extrair_marca_do_modelo(modelo_limpo: str) -> str:
    """
    Tenta extrair a marca pegando a primeira palavra do modelo limpo (separado por underline).
    """
    if not isinstance(modelo_limpo, str) or not modelo_limpo:
        return "nao_identificado"
    
    partes = modelo_limpo.split('_')
    return partes[0] if partes else "nao_identificado"

def main():
    PATH_CONFIG = DATASET_CONFIG
    INPUT_DIR = DATASET_GAMER /"em_tratamento"/"limpos_underline"
    
    # Caminhos dos arquivos de saída
    PASTA_SAIDA = DATASET_GAMER /"em_tratamento"/ "unificados"
    ARQUIVO_FINAL = PASTA_SAIDA / "laptops_centralizado_modelos.csv"
    ARQUIVO_DUPLICADOS = PASTA_SAIDA / "laptops_modelos_duplicados.csv"
    
    logger.info(f"📁 Lendo arquivos de: {INPUT_DIR}")
    
    try:
        with open(PATH_CONFIG / "mapeamento_arquivos_aprimorado.json", 'r', encoding='utf-8') as f:
            mapeamentos_json = json.load(f)["mapeamentos"]
    except Exception as e:
        logger.error(f"❌ Erro ao carregar mapeamento JSON: {e}")
        return

    dataframes_consolidados = []

    for item in mapeamentos_json:
        arquivo_original = item["arquivo"]
        nome_arquivo_limpo = f"limpo_{arquivo_original.replace('/', '_').replace('\\', '_')}"
        caminho_arquivo = INPUT_DIR / nome_arquivo_limpo
        
        if not caminho_arquivo.exists():
            logger.warning(f"⚠️ Arquivo limpo não encontrado: {nome_arquivo_limpo}")
            continue
            
        logger.info(f"📦 Extraindo dados de: {nome_arquivo_limpo}")
        
        try:
            # Adicionamos uma coluna identificando a origem para rastrear no arquivo de duplicados
            df = pd.read_csv(caminho_arquivo, encoding='utf-8')
        except Exception as e:
            logger.error(f"   ❌ Erro ao ler {nome_arquivo_limpo}: {e}")
            continue

        coluna_modelo_limpo = 'modelo_completo_limpo'
        if coluna_modelo_limpo not in df.columns:
            logger.error(f"   ❌ Coluna '{coluna_modelo_limpo}' não encontrada neste arquivo!")
            continue
            
        df_temp = pd.DataFrame()
        df_temp['modelo_completo'] = df[coluna_modelo_limpo].astype(str)
        df_temp['origem_dataset'] = arquivo_original  # Guarda de qual arquivo esse dado veio
        
        coluna_marca_original = encontrar_coluna_marca(df, item.get("colunas", {}))
        
        if coluna_marca_original and coluna_marca_original in df.columns:
            df_temp['marca'] = df[coluna_marca_original].astype(str).str.strip().str.lower()
        else:
            df_temp['marca'] = df_temp['modelo_completo'].apply(extrair_marca_do_modelo)
            
        dataframes_consolidados.append(df_temp)

    if dataframes_consolidados:
        logger.info("🔄 Concatenando todos os datasets...")
        df_final = pd.concat(dataframes_consolidados, ignore_index=True)
        
        # Limpezas básicas de segurança
        # df_final = df_final.dropna(subset=['modelo_completo', 'marca'])
        df_final = df_final.dropna(subset=['marca','modelo_completo'])
        df_final = df_final[(df_final['modelo_completo'] != '') & (df_final['marca'] != '')]
        
        linhas_totais = len(df_final)
        
        # --- LOGICA DOS DUPLICADOS ---
        # subset=['marca', 'modelo_completo'] identifica duplicados considerando a combinação dos dois
        # keep=False garante que TODAS as ocorrências do duplicado apareçam (para você ver a origem de cada um)
        df_duplicados = df_final[df_final.duplicated(subset=['marca', 'modelo_completo'], keep=False)].copy()
        
        # Ordena para que os modelos repetidos fiquem juntos no arquivo de auditoria
        df_duplicados = df_duplicados.sort_values(by=['marca', 'modelo_completo'])
        
        # Aplica o drop_duplicates oficial para o arquivo limpo final (mantendo a primeira ocorrência)
        df_limpo_final = df_final.drop_duplicates(subset=['marca', 'modelo_completo']).reset_index(drop=True)
        # Removemos a coluna de origem do arquivo principal para manter o padrão que você pediu antes
        df_limpo_final = df_limpo_final.drop(columns=['origem_dataset'])

        # REORDENA AS COLUNAS: 'marca' na primeira posição, depois 'modelo_completo'
        colunas_ordenadas = ['marca', 'modelo_completo']
        df_limpo_final = df_limpo_final[colunas_ordenadas]

        linhas_finais = len(df_limpo_final)
        
        logger.info(f"📊 Total de registros processados: {linhas_totais}")
        logger.info(f"✨ Total após remover duplicatas: {linhas_finais}")
        logger.info(f"🔍 Total de linhas duplicadas encontradas: {len(df_duplicados)}")
        
        # Garante a criação da pasta
        PASTA_SAIDA.mkdir(parents=True, exist_ok=True)
        
        # Salva o arquivo principal (Limpo)
        try:
            df_limpo_final.to_csv(ARQUIVO_FINAL, index=False, encoding='utf-8')
            logger.info(f"✅ Dataset centralizado salvo em: {ARQUIVO_FINAL}")
        except Exception as e:
            logger.error(f"❌ Erro ao salvar o arquivo unificado: {e}")
            
        # Salva o arquivo de Auditoria de Duplicados
        try:
            if not df_duplicados.empty:
                df_duplicados.to_csv(ARQUIVO_DUPLICADOS, index=False, encoding='utf-8')
                logger.info(f"📁 Arquivo contendo as duplicatas salvo em: {ARQUIVO_DUPLICADOS}")
            else:
                logger.info("ℹ️ Nenhuma duplicata encontrada para salvar.")
        except Exception as e:
            logger.error(f"❌ Erro ao salvar o arquivo de duplicados: {e}")
            
    else:
        logger.error("❌ Nenhum dado foi processado com sucesso para consolidação.")

if __name__ == "__main__":
    main()