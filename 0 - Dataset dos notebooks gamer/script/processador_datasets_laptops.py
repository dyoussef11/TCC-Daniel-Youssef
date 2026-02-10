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

class LimpadorModelos:
    """Carrega as regras do JSON e limpa o nome do modelo preservando SKUs."""
    def __init__(self, caminho_json: Path):
        with open(caminho_json, 'r', encoding='utf-8') as f:
            config = json.load(f)
            self.termos_genericos = config['termos_genericos']
            self.padroes_corte = config['padroes_corte']
            self.regex_corte = re.compile('|'.join(self.padroes_corte), re.IGNORECASE)

    def extrair_modelo(self, texto: str) -> str:
        if not isinstance(texto, str) or texto.lower() == 'nan':
            return "modelo não identificado"
        
        nome = texto.strip()

        # 1. Limpeza de termos genéricos (Global)
        for termo in self.termos_genericos:
            nome = re.sub(termo, '', nome, flags=re.IGNORECASE).strip()

        # 2. Corte nas especificações técnicas
        match = self.regex_corte.search(nome)
        if match:
            nome = nome[:match.start()].strip()

        # 3. Refinamento final (pontuação e espaços)
        nome = re.sub(r'[\s\-,/]+$', '', nome) 
        nome = re.sub(r'\s+', ' ', nome)      
        
        return nome.strip()

class ProcessadorDatasetLaptops:
    def __init__(self, config: ConfiguracaoProcessamento, limpador: LimpadorModelos):
        self.config = config
        self.limpador = limpador # Recebe o limpador baseado em JSON

    def limpar_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """Padroniza strings: remove espaços extras (mantém case para a limpeza)."""
        for col in df.select_dtypes(include=['object']).columns:
            df[col] = df[col].astype(str).str.strip()
        return df

    def extrair_regex(self, texto: str, chave: str) -> str:
        """Extrai hardware usando os padrões do hardware_rules.json."""
        if pd.isna(texto) or texto == 'nan' or texto == '':
            return "não identificado"
        padrao = self.config.PADROES_HARDWARE.get(chave)
        if not padrao: return "não identificado"
        match = re.search(padrao, str(texto), re.IGNORECASE)
        return match.group(0).strip().lower() if match else "não identificado"

    def classificar_categoria(self, row: pd.Series) -> str:
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
        """Gera assinatura baseada em Marca + Modelo Limpo (com SKU) + CPU + RAM."""
        def fix(x): return str(x).lower().replace(' ', '').strip() if x != "não identificado" else "na"
        marca = fix(row.get('marca', 'gen'))
        # Usa o modelo_limpo (que já contém o SKU) para garantir unicidade
        modelo = fix(row.get('modelo_limpo', 'gen'))
        cpu = fix(row.get('cpu'))
        ram = fix(row.get('ram'))
        return f"{marca}_{modelo[:30]}_{cpu}_{ram}"

    def processar_arquivo(self, caminho: Path, mapeamento: Dict[str, str]) -> Optional[pd.DataFrame]:
        try:
            enc = 'latin1' if 'Unveiling' in caminho.name else 'utf-8'
            df = pd.read_csv(caminho, encoding=enc)
            
            # 1. Mapeamento e Limpeza inicial
            df = df.rename(columns={k: v.lower() for k, v in mapeamento.items()})
            df = self.limpar_dataframe(df)

            # 2. Extração de Componentes (Obrigatório antes de limpar o nome)
            for col_df, chave_json in {'cpu': 'cpu', 'gpu': 'gpu', 'ram': 'ram', 'storage': 'storage', 'tela': 'screen', 'ano_lancamento': 'ano'}.items():
                df[col_df] = df['modelo_completo'].apply(lambda x: self.extrair_regex(x, chave_json))

            # 3. Nova Limpeza de Modelo (JSON)
            df['modelo_limpo'] = df['modelo_completo'].apply(self.limpador.extrair_modelo)

            # 4. Filtro de Acessórios
            df = df[~((df['cpu'] == "não identificado") & (df['ram'] == "não identificado"))]
            if df.empty: return None

            # 5. IDs e Categorias
            df['categoria'] = df.apply(self.classificar_categoria, axis=1)
            df['id_unico'] = df.apply(self.gerar_id_unico, axis=1)

            # Adiciona colunas faltantes como 'não identificado'
            for col in self.config.COLUNAS_PADRAO:
                if col not in df.columns: df[col] = "não identificado"
                
            return df[self.config.COLUNAS_PADRAO + ['id_unico', 'modelo_limpo']]
        except Exception as e:
            logger.error(f"Erro ao processar {caminho.name}: {e}")
            return None

# ==================== EXECUÇÃO PRINCIPAL ====================

if __name__ == "__main__":
    BASE_DIR = Path(__file__).resolve().parent.parent
    PATH_CONFIG = BASE_DIR / "config"
    PATH_DADOS = BASE_DIR / "kruggle_coletados_csv"
    PATH_OUTPUT = BASE_DIR / "dataset_final_csv" / "dataset_laptops_UNICOS.csv"

    try:
        # 1. Carregar Configurações
        config = ConfiguracaoProcessamento.carregar(PATH_CONFIG / "hardware_rules.json")
        limpador = LimpadorModelos(PATH_CONFIG / "models_rules.json") # Novo arquivo JSON
        
        with open(PATH_CONFIG / "mapeamento_arquivos.json", 'r', encoding='utf-8') as f:
            mapeamentos_json = json.load(f)["mapeamentos"]

        # 2. Inicializar Processador com o novo limpador
        processador = ProcessadorDatasetLaptops(config, limpador)
        datasets_validados = []

        for item in mapeamentos_json:
            caminho_csv = PATH_DADOS / item["arquivo"]
            if caminho_csv.exists():
                logger.info(f"Lendo: {item['arquivo']}")
                df_p = processador.processar_arquivo(caminho_csv, item["colunas"])
                if df_p is not None: datasets_validados.append(df_p)

        # 3. Unificar e Salvar
        if datasets_validados:
            df_final = pd.concat(datasets_validados, ignore_index=True)
            total_antes = len(df_final)
            df_final = df_final.drop_duplicates(subset=['id_unico'], keep='first')
            
            PATH_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
            df_final.to_csv(PATH_OUTPUT, index=False)
            logger.info(f"✅ Sucesso! Total: {total_antes} -> Únicos: {len(df_final)}")
        else:
            logger.error("Nenhum dado válido encontrado.")

    except Exception as e:
        logger.error(f"Erro fatal: {e}")