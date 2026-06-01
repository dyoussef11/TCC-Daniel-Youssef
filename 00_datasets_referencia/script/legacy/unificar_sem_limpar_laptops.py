import sys
import pandas as pd
import json
import logging
from pathlib import Path
from typing import Dict, Optional, List, Union

from core.paths import ( 
    DATASET_CONFIG,
    DATASET_KAGGLE,
    DATASET_FINAL_CSV 
)

# --- CONFIGURAÇÃO DE LOGS ---
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


class ProcessadorJuncaoSimples:
    """
    Versão SIMPLIFICADA que apenas faz o JOIN dos datasets
    SEM limpeza, SEM deduplicação, SEM processamento de modelos
    """
    
    def __init__(self):
        self.datasets_carregados = []
    
    def _concatenar_colunas(self, row: pd.Series, colunas: List[str], separador: str = ' ') -> str:
        """Concatena múltiplas colunas com separador"""
        valores = []
        for col in colunas:
            valor = row.get(col, '')
            if pd.notna(valor) and str(valor).strip() not in ['', 'nan', 'None']:
                valores.append(str(valor).strip())
        return separador.join(valores)
    
    def _processar_mapeamento(self, df: pd.DataFrame, mapeamento: Dict[str, Union[str, List[str]]]) -> pd.DataFrame:
        """
        Processa o mapeamento CORRETAMENTE:
        - Chave: nome da coluna original no CSV (ou None para expressões)
        - Valor: nome da coluna padronizada no dataset final
        - Se valor é uma LISTA, concatena as colunas
        - Se valor é uma string com '+', avalia como expressão
        """
        dados_padronizados = {}
        
        for col_original, col_padronizada in mapeamento.items():
            # Caso 1: É uma LISTA de colunas para concatenar
            if isinstance(col_original, list):
                valores = []
                for idx in range(len(df)):
                    valor = self._concatenar_colunas(df.iloc[idx], col_original, ' ')
                    valores.append(valor)
                dados_padronizados[col_padronizada] = valores
                logger.debug(f"✅ Concatenação: {col_padronizada} = {col_original}")
            
            # Caso 2: É uma string com '+' (expressão)
            elif isinstance(col_original, str) and '+' in col_original:
                valores = []
                for idx in range(len(df)):
                    try:
                        env = {col: df.iloc[idx][col] for col in df.columns}
                        resultado = eval(col_original, {"__builtins__": {}}, env)
                        valores.append(str(resultado).strip() if resultado else "")
                    except:
                        valores.append("")
                dados_padronizados[col_padronizada] = valores
                logger.debug(f"✅ Expressão: {col_padronizada} = {col_original}")
            
            # Caso 3: Coluna normal
            elif col_original in df.columns:
                dados_padronizados[col_padronizada] = df[col_original].tolist()
                logger.debug(f"📋 Coluna mapeada: {col_original} -> {col_padronizada}")
            
            # Caso 4: Coluna não encontrada
            else:
                logger.warning(f"⚠️ Coluna '{col_original}' não encontrada")
                dados_padronizados[col_padronizada] = [None] * len(df)
        
        # Cria DataFrame com as colunas padronizadas
        df_resultado = pd.DataFrame(dados_padronizados)
        
        return df_resultado
    
    def carregar_e_mapear(self, caminho: Path, mapeamento: Dict[str, Union[str, List[str]]]) -> Optional[pd.DataFrame]:
        """
        Carrega o CSV e aplica o mapeamento
        """
        try:
            # Detecta encoding
            enc = 'latin1' if 'Unveiling' in caminho.name else 'utf-8'
            df = pd.read_csv(caminho, encoding=enc)
            
            logger.info(f"📋 Colunas originais: {list(df.columns)}")
            
            # Aplica mapeamento
            df_processado = self._processar_mapeamento(df, mapeamento)
            
            # Adiciona origem
            df_processado['origem_arquivo'] = caminho.name
            
            # Remove linhas totalmente vazias nas colunas principais
            colunas_principais = [col for col in ['marca', 'modelo_completo'] if col in df_processado.columns]
            if colunas_principais:
                df_processado = df_processado.dropna(subset=colunas_principais, how='all')
            
            logger.info(f"✅ Carregado: {caminho.name} | Linhas: {len(df_processado)} | Colunas: {len(df_processado.columns)}")
            return df_processado
            
        except Exception as e:
            logger.error(f"❌ Erro ao carregar {caminho.name}: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def juntar_datasets(self, dataframes: List[pd.DataFrame]) -> pd.DataFrame:
        """Junta múltiplos DataFrames"""
        if not dataframes:
            return pd.DataFrame()
        
        if len(dataframes) == 1:
            return dataframes[0]
        
        df_final = pd.concat(dataframes, ignore_index=True, sort=False)
        logger.info(f"🔗 Join concluído: {len(df_final)} linhas totais")
        return df_final


def processar_juncao_sem_limpeza():
    """
    Função principal que executa APENAS a junção dos datasets
    """
    
    path_config = DATASET_CONFIG
    path_dados = DATASET_KAGGLE
    path_output = DATASET_FINAL_CSV / "dataset_laptops_JUNTADO_RAW.csv"
    
    try:
        # Carrega o mapeamento
        with open(path_config / "mapeamento_arquivos_aprimorado.json", 'r', encoding='utf-8') as f:
            mapeamentos_json = json.load(f)["mapeamentos"]
        
        processador = ProcessadorJuncaoSimples()
        datasets_carregados = []
        
        # Processa cada arquivo
        for item in mapeamentos_json:
            caminho_csv = path_dados / item["arquivo"]
            
            if caminho_csv.exists():
                logger.info(f"📂 Processando: {item['arquivo']}")
                logger.info(f"   Mapeamento: {item['colunas']}")
                
                # NÃO inverte mais! Usa o mapeamento diretamente
                df = processador.carregar_e_mapear(caminho_csv, item['colunas'])
                
                if df is not None and not df.empty:
                    datasets_carregados.append(df)
                    logger.info(f"   ✅ Sucesso! {len(df)} linhas, {len(df.columns)} colunas")
                else:
                    logger.warning(f"   ⚠️ Falhou ou vazio")
            else:
                logger.warning(f"⚠️ Arquivo não encontrado: {item['arquivo']}")
        
        # Junta tudo
        if datasets_carregados:
            df_final = processador.juntar_datasets(datasets_carregados)
            
            path_output.parent.mkdir(parents=True, exist_ok=True)
            df_final.to_csv(path_output, index=False, encoding='utf-8')
            
            # Relatório
            logger.info("=" * 50)
            logger.info(f"✅ Junção concluída!")
            logger.info(f"📁 Arquivo salvo: {path_output}")
            logger.info(f"📊 Total de registros: {len(df_final)}")
            logger.info(f"📊 Total de colunas: {len(df_final.columns)}")
            
            # Amostra dos dados
            colunas_mostrar = ['marca', 'modelo_completo', 'cpu', 'ram', 'storage', 'gpu', 'tela', 'origem_arquivo']
            colunas_existentes = [col for col in colunas_mostrar if col in df_final.columns]
            
            if colunas_existentes:
                print("\n📊 AMOSTRA DOS DADOS (primeiras 5 linhas):")
                print(df_final[colunas_existentes].head(5).to_string())
            else:
                print("\n📊 Primeiras 5 linhas (todas as colunas):")
                print(df_final.head(5).to_string())
            
            logger.info("=" * 50)
            
        else:
            logger.error("❌ Nenhum dataset foi carregado com sucesso.")
            
    except Exception as e:
        logger.error(f"❌ Erro fatal: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    processar_juncao_sem_limpeza()