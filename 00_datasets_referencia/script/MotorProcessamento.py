import re
import logging
import pandas as pd
from pathlib import Path
from typing import Dict, Optional
from ConfiguracaoProcessamento import ConfiguracaoModelos
from LimpadorProcessamento import LimpadorModelos

logger = logging.getLogger(__name__)

class TransformadorLaptops:
    def __init__(self, config: ConfiguracaoModelos, limpador: LimpadorModelos):
        self.config = config
        self.limpador = limpador

    def limpar_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        for col in df.select_dtypes(include=['object']).columns:
            df[col] = df[col].astype(str).str.strip().str.lower()
        return df

    def extrair_regex(self, texto: str, chave: str) -> str:
        if pd.isna(texto) or texto == 'nan' or texto == '':
            return "não identificado"
        padrao = self.config.PADROES_HARDWARE.get(chave)
        if not padrao: 
            return "não identificado"
        match = re.search(padrao, str(texto), re.IGNORECASE)
        return match.group(0).strip().lower() if match else "não identificado"

    def classificar_categoria(self, row: pd.Series) -> str:
        modelo = str(row.get('modelo_completo', ''))
        gpu = str(row.get('gpu', ''))
        
        if any(kw.lower() in modelo for kw in self.config.CATEGORIAS.get('KEYWORDS_GAMER', [])) or 'rtx' in gpu or 'gtx' in gpu:
            return 'gamer'
        if any(kw.lower() in modelo for kw in self.config.CATEGORIAS.get('KEYWORDS_CREATOR', [])) or 'quadro' in gpu:
            return 'creator'
        if any(kw.lower() in modelo for kw in self.config.CATEGORIAS.get('KEYWORDS_BUSINESS', [])):
            return 'business'
        return 'geral'


    def gerar_id_unico(self, row: pd.Series) -> str:
        """Gera ID único baseado no modelo limpo + especificações chave"""
        def fix(x): 
            return str(x).replace(' ', '').lower() if x != "não identificado" else "na"
        
        # Usa o modelo_limpo que já inclui a marca
        modelo = fix(row.get('modelo_limpo', 'gen'))
        cpu = fix(row.get('cpu', 'na'))
        ram = fix(row.get('ram', 'na'))
        storage = fix(row.get('storage', 'na'))
        
        return f"{modelo}_{cpu}_{ram}_{storage}"

    def processar_arquivo(self, caminho: Path, mapeamento: Dict[str, any]) -> Optional[pd.DataFrame]:
        try:
            enc = 'latin1' if 'Unveiling' in caminho.name else 'utf-8'
            df = pd.read_csv(caminho, encoding=enc)
            
            mapeamentos_simples = {}
            mapeamentos_compostos = {}
            
            for chave, valor in mapeamento.items():
                if isinstance(valor, list):
                    mapeamentos_compostos[chave.lower()] = valor
                else:
                    mapeamentos_simples[chave] = valor

            colunas_reais_map = {c.lower(): c for c in df.columns}

            for col_destino, colunas_originais in mapeamentos_compostos.items():
                colunas_validas = [colunas_reais_map[c.lower()] for c in colunas_originais if c.lower() in colunas_reais_map]
                if colunas_validas:
                    df[col_destino] = df[colunas_validas].astype(str).agg(' '.join, axis=1)
                else:
                    logger.warning(f"Nenhuma das colunas {colunas_originais} foi encontrada para gerar '{col_destino}' em {caminho.name}")
                    df[col_destino] = "não identificado"
            
            df = df.rename(columns=mapeamentos_simples)
            df = self.limpar_dataframe(df)

            if 'modelo_completo' in df.columns:
                mask_vazio = df['modelo_completo'].isin(['', 'nan', 'none', 'não identificado']) | df['modelo_completo'].isna()
                if mask_vazio.sum():
                    logger.info(f"Removidas {mask_vazio.sum()} linhas com modelo_completo vazio")
                df = df[~mask_vazio]    

            if df.empty: 
                return None

            campos_hardware = {
                'cpu': 'cpu', 'gpu': 'gpu', 'ram': 'ram', 
                'storage': 'storage', 'tela': 'screen', 'ano_lancamento': 'ano'
            }
            
            for col_df, chave_regex in campos_hardware.items():
                if col_df not in df.columns:
                    df[col_df] = "não identificado"
                
                df[col_df] = df.apply(
                    lambda row: self.extrair_regex(row['modelo_completo'], chave_regex) 
                    if str(row.get(col_df, "não identificado")) in ["não identificado", "nan", "none", ""] 
                    else str(row[col_df]),
                    axis=1
                )
            # Dentro do método de processamento do dataframe:
            
            df['modelo_limpo'] = df['modelo_completo'].apply(self.limpador.extrair_modelo)
            df['modelo_limpo'] = df['modelo_limpo'].fillna('modelo_nao_identificado').astype(str)
            # df['modelo_generico'] = df['modelo_limpo'].apply(self.limpador.extrair_nome_generico)
            df['modelo_generico'] = df.apply(
                lambda row: self.limpador.extrair_nome_generico(
                    str(row['modelo_limpo']), 
                    str(row.get('marca', ''))
                ), 
                axis=1
            )
            df['modelo_busca_praw'] = df['modelo_limpo'].apply(self.limpador.extrair_modelo_pesquisa)

            mask_vazio_limpo = df['modelo_limpo'] == ''
            mask_gen_invalido = df['modelo_generico'] == 'modelo_nao_identificado'
            mask_uma_palavra = ~df['modelo_generico'].str.contains('_', na=False)
            mask_numero = df['modelo_limpo'].str.isdigit() | df['modelo_generico'].str.isdigit()

            mask_total_exclusao = mask_vazio_limpo | mask_gen_invalido | mask_uma_palavra | mask_numero
            
            if mask_total_exclusao.sum():
                logger.info(f"Filtros de validação aplicados: Removidas {mask_total_exclusao.sum()} linhas inválidas/órfãs")
                df = df[~mask_total_exclusao]

            df = df[~((df['cpu'] == "não identificado") & (df['ram'] == "não identificado"))]
            if df.empty: 
                return None

            df['categoria'] = df.apply(self.classificar_categoria, axis=1)
            df['id_unico'] = df.apply(self.gerar_id_unico, axis=1)

            colunas_ordenadas = []
            for col in self.config.COLUNAS_PADRAO:
                if col == "modelo_completo":
                    colunas_ordenadas.append("modelo_generico")
                    colunas_ordenadas.append("modelo_limpo")
                colunas_ordenadas.append(col)
            
            for col in colunas_ordenadas:
                if col not in df.columns: 
                    df[col] = "não identificado"
                
            return df[colunas_ordenadas + ['id_unico']]

        except Exception as e:
            logger.error(f"Erro ao processar {caminho.name}: {e}")
            return None