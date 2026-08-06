import json
import logging
from pathlib import Path
import pandas as pd
from configuracao_processamento import ConfiguracaoModelos
from limpador_processamento import LimpadorModelos
from motor_processamento import TransformadorLaptops

from core.paths import ( 
    DATASET_CONFIG,
    DATASET_GAMER,
    DATASET_KAGGLE,
    DATASET_FINAL_CSV 
)

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def main():
    PATH_CONFIG: Path = DATASET_CONFIG
    PATH_DADOS = DATASET_KAGGLE
    
    PATH_OUTPUT: Path  = DATASET_FINAL_CSV / "dataset_laptops_UNICOS_V10.csv"
    PASTA_SAIDA: Path  = DATASET_GAMER /"em_tratamento"/ "unificados"
    # Caminho para o arquivo centralizado
    ARQUIVO_CENTRALIZADO: Path  = PASTA_SAIDA / "laptops_centralizado_modelos.csv"

    try:
        # Inicializa os módulos modulares
        config = ConfiguracaoModelos.carregar(PATH_CONFIG / "hardware_rules.json")
        limpador = LimpadorModelos(PATH_CONFIG / "models_rules.json")
        processador = TransformadorLaptops(config, limpador)
        
        # Verifica se o arquivo centralizado existe
        if ARQUIVO_CENTRALIZADO.exists():
            logger.info(f"Processando arquivo centralizado: {ARQUIVO_CENTRALIZADO.name}")
            
            # Lê o arquivo diretamente (sem o processar_arquivo que tem muitos filtros)
            df = pd.read_csv(ARQUIVO_CENTRALIZADO, encoding='utf-8')
            
            # Limpa e padroniza
            df = processador.limpar_dataframe(df)
            
            # Verifica se tem dados
            if df.empty:
                logger.error("DataFrame vazio após limpeza")
                return
            
            logger.info(f"Linhas após limpeza: {len(df)}")
            
            # Extrai hardware do modelo_completo
            campos_hardware = ['cpu', 'gpu', 'ram', 'storage', 'tela', 'ano_lancamento']
            for campo in campos_hardware:
                chave_regex = campo if campo != 'ano_lancamento' else 'ano'
                df[campo] = df['modelo_completo'].apply(
                    lambda x: processador.extrair_regex(x, chave_regex)
                )
            
            # Extrai modelo limpo e genérico
            df['modelo_limpo'] = df['modelo_completo'].apply(limpador.extrair_modelo)
            df['modelo_generico'] = df.apply(
                lambda row: limpador.extrair_nome_generico(
                    str(row['modelo_limpo']), 
                    str(row.get('marca', ''))
                ), 
                axis=1
            )
            df['modelo_busca_praw'] = df['modelo_limpo'].apply(limpador.extrair_modelo_pesquisa)
            
            # Remove linhas com modelo inválido (mas não remove todas!)
            mask_valido = (df['modelo_limpo'] != 'modelo_nao_identificado') & (df['modelo_generico'] != 'modelo_nao_identificado')
            df = df[mask_valido]
            
            if df.empty:
                logger.error("Todos os modelos foram considerados inválidos")
                return
            
            logger.info(f"Linhas após validação: {len(df)}")
            
            # Classifica categoria
            df['categoria'] = df.apply(processador.classificar_categoria, axis=1)
            
            # Gera ID único
            df['id_unico'] = df.apply(processador.gerar_id_unico, axis=1)
            
            # Remove duplicatas
            df = df.drop_duplicates(subset=['id_unico'], keep='first')
            
            # Organiza colunas de saída
            colunas_saida = [
                'marca', 'modelo_completo', 'modelo_limpo', 'modelo_generico', 
                'modelo_busca_praw', 'cpu', 'ram', 'storage', 'gpu', 
                'tela', 'ano_lancamento', 'categoria', 'id_unico'
            ]
            
            # Garante que todas as colunas existem
            for col in colunas_saida:
                if col not in df.columns:
                    df[col] = "não identificado"
            
            # Salva o resultado
            PATH_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
            df[colunas_saida].to_csv(PATH_OUTPUT, index=False)
            
            logger.info("=" * 50)
            logger.info(f"✅ Concluído! Dataset salvo em: {PATH_OUTPUT}")
            logger.info(f"📊 Estatísticas: Total processado: {len(df)}")
            logger.info(f"📊 Colunas geradas: {list(df.columns)}")
            logger.info("=" * 50)
            
            # Mostra alguns exemplos
            logger.info("\n📋 Exemplos de modelos processados:")
            for idx, row in df.head(5).iterrows():
                logger.info(f"  {idx+1}. Original: {row['modelo_completo'][:80]}...")
                logger.info(f"     Limpo: {row['modelo_limpo']}")
                logger.info(f"     Genérico: {row['modelo_generico']}")
                logger.info(f"     CPU: {row['cpu']} | RAM: {row['ram']}")
                logger.info("")
            
        else:
            logger.warning(f"Arquivo centralizado não encontrado em: {ARQUIVO_CENTRALIZADO}")

    except Exception as e:
        logger.error(f"Erro fatal no script: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()