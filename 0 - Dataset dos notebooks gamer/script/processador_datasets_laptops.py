import pandas as pd
import json
import re
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional

# --- CONFIGURAÇÃO DE LOGS ---
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class ConfiguracaoProcessamento:
    COLUNAS_PADRAO: List[str] = field(default_factory=list)
    PADROES_HARDWARE: Dict[str, str] = field(default_factory=dict)
    CATEGORIAS: Dict[str, List[str]] = field(default_factory=dict)

    @classmethod
    def carregar(cls, caminho: Path):
        with open(caminho, 'r', encoding='utf-8') as f:
            return cls(**json.load(f))

class ProcessadorDatasetLaptops:
    def __init__(self, config: ConfiguracaoProcessamento):
        self.config = config

    def limpar_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """Converte todas as colunas de texto para minúsculo e remove espaços."""
        for col in df.select_dtypes(include=['object']).columns:
            df[col] = df[col].astype(str).str.lower().str.strip()
        return df

    def extrair_regex(self, texto: str, chave: str) -> str:
        """Busca hardware no texto usando os padrões do JSON."""
        if pd.isna(texto) or texto == 'nan' or texto == '':
            return "não identificado"
        
        padrao = self.config.PADROES_HARDWARE.get(chave)
        if not padrao:
            return "não identificado"
        
        # O re.IGNORECASE garante que não percamos dados por causa de MAIÚSCULAS
        match = re.search(padrao, str(texto), re.IGNORECASE)
        return match.group(0).strip().lower() if match else "não identificado"

    def classificar_categoria(self, row: pd.Series) -> str:
        """Classifica o notebook com base nas Keywords e GPU."""
        modelo = str(row.get('modelo_completo', '')).lower()
        gpu = str(row.get('gpu', '')).lower()
        
        if any(kw.lower() in modelo for kw in self.config.CATEGORIAS.get('KEYWORDS_GAMER', [])) or 'rtx' in gpu or 'gtx' in gpu:
            return 'gamer'
        if any(kw.lower() in modelo for kw in self.config.CATEGORIAS.get('KEYWORDS_CREATOR', [])) or 'quadro' in gpu:
            return 'creator'
        if any(kw.lower() in modelo for kw in self.config.CATEGORIAS.get('KEYWORDS_BUSINESS', [])):
            return 'business'
        return 'geral'

    def gerar_id_unico(self, row: pd.Series) -> str:
        """Gera uma assinatura digital para evitar duplicatas entre arquivos."""
        def fix(x): return str(x).lower().replace(' ', '') if x != "não identificado" else "na"
        marca = fix(row.get('marca', 'gen'))
        modelo_base = fix(" ".join(str(row.get('modelo_completo', '')).split()[:2]))
        cpu = fix(row.get('cpu'))
        ram = fix(row.get('ram'))
        return f"{marca}_{modelo_base}_{cpu}_{ram}"

    def processar_arquivo(self, caminho: Path, mapeamento: Dict[str, str]) -> Optional[pd.DataFrame]:
        try:
            enc = 'latin1' if 'Unveiling' in caminho.name else 'utf-8'
            df = pd.read_csv(caminho, encoding=enc)
            
            # 1. Renomear e Minuscular
            df = df.rename(columns={k: v.lower() for k, v in mapeamento.items()})
            df = self.limpar_dataframe(df)

            # 2. Extração de Componentes (Força a extração de hardware de 'modelo_completo')
            campos_extrair = {
                'cpu': 'cpu', 'gpu': 'gpu', 'ram': 'ram', 
                'storage': 'storage', 'tela': 'screen', 'ano_lancamento': 'ano'
            }
            
            for col_df, chave_json in campos_extrair.items():
                df[col_df] = df['modelo_completo'].apply(lambda x: self.extrair_regex(x, chave_json))

            # 3. Categorização e ID Único
            df['categoria'] = df.apply(self.classificar_categoria, axis=1)
            df['id_unico'] = df.apply(self.gerar_id_unico, axis=1)

            # Garante que todas as colunas padrão existam no DF final
            for col in self.config.COLUNAS_PADRAO:
                if col not in df.columns: df[col] = "não identificado"
                
            return df[self.config.COLUNAS_PADRAO + ['id_unico']]
        except Exception as e:
            logger.error(f"Erro ao processar {caminho.name}: {e}")
            return None

# ==================== EXECUÇÃO PRINCIPAL ====================

if __name__ == "__main__":
    # Caminhos dinâmicos baseados na localização deste arquivo
    BASE_DIR = Path(__file__).resolve().parent.parent
    PATH_CONFIG = BASE_DIR / "config"
    PATH_DADOS = BASE_DIR / "kruggle_coletados_csv"
    PATH_OUTPUT = BASE_DIR / "dataset_final_csv" / "dataset_laptops_UNICOS.csv"

    try:
        # Carregar arquivos de configuração
        config = ConfiguracaoProcessamento.carregar(PATH_CONFIG / "hardware_rules.json")
        with open(PATH_CONFIG / "mapeamento_arquivos.json", 'r', encoding='utf-8') as f:
            mapeamentos_json = json.load(f)["mapeamentos"]

        processador = ProcessadorDatasetLaptops(config)
        datasets_validados = []

        for item in mapeamentos_json:
            caminho_csv = PATH_DADOS / item["arquivo"]
            if caminho_csv.exists():
                df_processado = processador.processar_arquivo(caminho_csv, item["colunas"])
                if df_processado is not None:
                    datasets_validados.append(df_processado)
            else:
                logger.warning(f"Arquivo não encontrado: {item['arquivo']}")

        if datasets_validados:
            df_final = pd.concat(datasets_validados, ignore_index=True)
            # Remoção de duplicatas pelo ID Digital
            df_final = df_final.drop_duplicates(subset=['id_unico'], keep='first')
            
            PATH_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
            df_final.to_csv(PATH_OUTPUT, index=False)
            logger.info(f"✅ Sucesso! Dataset unificado com {len(df_final)} registros únicos em: {PATH_OUTPUT}")

    except Exception as e:
        logger.error(f"Falha na execução: {e}")