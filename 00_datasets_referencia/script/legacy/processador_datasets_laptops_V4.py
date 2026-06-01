import sys
import pandas as pd
import json
import re
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional

from core.paths import ( 
    DATASET_CONFIG,
    DATASET_KAGGLE,
    DATASET_FINAL_CSV 
)

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

    def _normalizar_texto(self, texto: str) -> str:
        """Auxiliar para converter espaços/hífens em underlines e limpar caracteres."""
        if not texto:
            return ""
        # Remove caracteres especiais mantendo letras, números, pontos e underlines
        termo = re.sub(r'[^\w\s\.-]', '', texto.lower())
        # Substitui espaços, hífens e barras por um único underline
        termo = re.sub(r'[\s\-,/]+', '_', termo)
        # Remove underlines duplicados ou nas extremidades
        termo = re.sub(r'_{2,}', '_', termo)
        return termo.strip('_')

    def extrair_modelo(self, texto: str) -> str:
        if not isinstance(texto, str) or texto.lower() == 'nan':
            return "modelo_nao_identificado"
        
        nome = texto.strip().lower()
        
        # 1. Limpeza de termos genéricos do JSON
        for termo in self.termos_genericos:
            nome = re.sub(termo, '', nome, flags=re.IGNORECASE).strip()

        # 2. Corte nas especificações técnicas do JSON
        match = self.regex_corte.search(nome)
        if match:
            nome = nome[:match.start()].strip()

        # Transforma o modelo completo limpo com a formatação de underline
        return self._normalizar_texto(nome)
    
    def extrair_nome_generico(self, modelo_limpo: str) -> str:
        """
        Extrai a família do notebook mantendo ao menos uma indicação específica (ex: 't1', 'gf63')
        antes do SKU completo. Interrompe o processo assim que encontra o primeiro termo misto.
        """
        if modelo_limpo == "modelo_nao_identificado":
            return modelo_limpo
        
        # Divide pelos underlines gerados no passo anterior
        partes = modelo_limpo.split('_')
        if not partes or partes == ['']:
            return "modelo_nao_identificado"
            
        generico = []
        
        for p in partes:
            # Se a parte contiver números (termo misto ou numérico)
            if any(char.isdigit() for char in p):
                # Se for um termo curto (até 4 ou 5 caracteres), nós o incluímos como indicador de série
                # NOTA: Use <= 4 para cobrir exatamente 'gf63' (4), 't1' (2), 'v15' (3).
                # Se quiser incluir linhas como 'book2' (5) ou 'anv15' (5), mude para <= 5.
                if len(p) <= 4:
                    generico.append(p)
                
                # Interrompe o loop IMEDIATAMENTE no primeiro termo com número.
                # Isso garante que o resto do SKU longo (ex: '12uc', '846in') seja ignorado.
                break
                
            generico.append(p)
        
        # Caso a lista fique vazia (ex: se o modelo começasse direto com um SKU longo inválido)
        if not generico:
            return partes[0]
            
        return "_".join(generico).strip('_')
    
    def extrair_modelo_pesquisa(self, modelo_limpo: str) -> str:
        """
        Cria um termo ideal para busca no Reddit usando underline como separador interno,
        mas retornando com espaços para a query da API PRAW ser mais eficiente.
        """
        if modelo_limpo == "modelo_nao_identificado":
            return "modelo não identificado"
        
        partes = modelo_limpo.split('_')
        if len(partes) <= 1:
            return modelo_limpo.replace('_', ' ')

        resultado = [partes[0]] # Mantém a marca
        
        for p in partes[1:]:
            is_serie = any(char.isdigit() for char in p) and len(p) <= 6
            is_familia = p in ['omen', 'legion', 'victus', 'thin', 'pavilion', 'probook', 'nitro', 'tuf']
            
            if is_serie or is_familia:
                resultado.append(p)
                if len(resultado) >= 3: 
                    break
            elif len(resultado) < 2: 
                resultado.append(p)
            else:
                break
                
        return " ".join(resultado).strip()
    

class ProcessadorDatasetLaptops:
    def __init__(self, config: ConfiguracaoProcessamento, limpador: LimpadorModelos):
        self.config = config
        self.limpador = limpador

    def limpar_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """Padroniza strings: remove espaços extras e converte para minúsculo."""
        for col in df.select_dtypes(include=['object']).columns:
            df[col] = df[col].astype(str).str.strip().str.lower()
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
        """Gera assinatura baseada em Marca + Modelo Limpo + CPU + RAM."""
        def fix(x): return str(x).lower().replace(' ', '').strip() if x != "não identificado" else "na"
        marca = fix(row.get('marca', 'gen'))
        modelo = fix(row.get('modelo_limpo', 'gen'))
        cpu = fix(row.get('cpu'))
        ram = fix(row.get('ram'))
        return f"{marca}_{modelo[:30]}_{cpu}_{ram}"

    def processar_arquivo(self, caminho: Path, mapeamento: Dict[str, str]) -> Optional[pd.DataFrame]:
        try:
            enc = 'latin1' if 'Unveiling' in caminho.name else 'utf-8'
            df = pd.read_csv(caminho, encoding=enc)
            
            # 1. Renomear conforme mapeamento
            df = df.rename(columns={k: v.lower() for k, v in mapeamento.items()})
            
            # 2. Limpeza inicial e Lowercase Global
            df = self.limpar_dataframe(df)

            if 'modelo_completo' in df.columns:
                df['modelo_completo'] = df['modelo_completo'].astype(str).str.strip()
                mask_vazio = df['modelo_completo'].isin(['', 'nan', 'none', 'NaN', 'None']) | df['modelo_completo'].isna()
                if mask_vazio.sum():
                    logger.info(f"Removidas {mask_vazio.sum()} linhas com modelo_completo vazio")
                df = df[~mask_vazio]    

            # 3. Lógica "Plano B": Extração de Hardware
            campos_hardware = {
                'cpu': 'cpu', 'gpu': 'gpu', 'ram': 'ram', 
                'storage': 'storage', 'tela': 'screen', 'ano_lancamento': 'ano'
            }
            
            for col_df, chave_regex in campos_hardware.items():
                if col_df not in df.columns:
                    df[col_df] = "não identificado"
                
                # Extração via Regex (garantindo lower)
                df[col_df] = df.apply(
                    lambda row: self.extrair_regex(row['modelo_completo'], chave_regex) 
                    if str(row.get(col_df, "não identificado")).lower() in ["não identificado", "nan", "none", ""] 
                    else str(row[col_df]).lower(),
                    axis=1
                )

            # 4. Limpeza do Nome do Modelo (Preserva SKUs e converte para lower)
            df['modelo_limpo'] = df['modelo_completo'].apply(self.limpador.extrair_modelo).str.lower()
            df['modelo_generico'] = df['modelo_limpo'].apply(self.limpador.extrair_nome_generico).str.lower()
            df['modelo_busca_praw'] = df['modelo_limpo'].apply(self.limpador.extrair_modelo_pesquisa).str.lower()

            # --- NOVOS FILTROS PARA REMOVER MODELOS INVÁLIDOS ---
            # 1. Remove linhas onde modelo_limpo é vazio
            mask_vazio_limpo = df['modelo_limpo'] == ''
            if mask_vazio_limpo.sum():
                logger.info(f"Removidas {mask_vazio_limpo.sum()} linhas com modelo_limpo vazio")
            df = df[~mask_vazio_limpo]

            # 2. Remove linhas onde modelo_generico é "modelo_nao_identificado"
            mask_gen_invalido = df['modelo_generico'] == 'modelo_nao_identificado'
            if mask_gen_invalido.sum():
                logger.info(f"Removidas {mask_gen_invalido.sum()} linhas com modelo_generico não identificado")
            df = df[~mask_gen_invalido]

            # 3. Remove linhas onde modelo_limpo ou modelo_generico é apenas número (ex.: "9", "123")
            mask_numero = df['modelo_limpo'].str.isdigit() | df['modelo_generico'].str.isdigit()
            if mask_numero.sum():
                logger.info(f"Removidas {mask_numero.sum()} linhas com modelo numérico inválido")
            df = df[~mask_numero]
            # --------------------------------------------------

            # 5. Filtro de Segurança (Remove acessórios)
            df = df[~((df['cpu'] == "não identificado") & (df['ram'] == "não identificado"))]
            if df.empty: return None

            # 6. Classificação e IDs
            df['categoria'] = df.apply(self.classificar_categoria, axis=1)
            df['id_unico'] = df.apply(self.gerar_id_unico, axis=1)

            # 7. Organização Final das Colunas
            colunas_ordenadas = []
            for col in self.config.COLUNAS_PADRAO:
                if col == "modelo_completo":
                    # colunas_ordenadas.append("modelo_busca_praw") # Termo simplificado
                    colunas_ordenadas.append("modelo_generico") # Adiciona o genérico primeiro
                    colunas_ordenadas.append("modelo_limpo")
                colunas_ordenadas.append(col)
            
            # Preenche colunas padrão faltantes e garante lower final
            for col in colunas_ordenadas:
                if col not in df.columns: 
                    df[col] = "não identificado"
                else:
                    df[col] = df[col].astype(str).str.lower()
                
            return df[colunas_ordenadas + ['id_unico']]

        except Exception as e:
            logger.error(f"Erro ao processar {caminho.name}: {e}")
            return None

# ==================== EXECUÇÃO PRINCIPAL ====================

if __name__ == "__main__":
    PATH_CONFIG = DATASET_CONFIG
    PATH_DADOS = DATASET_KAGGLE
    # PATH_OUTPUT = DATASET_FINAL_CSV / "dataset_laptops_UNICOS_V3.csv"
    # PATH_OUTPUT = DATASET_FINAL_CSV / "dataset_laptops_UNICOS_V4.csv"
    PATH_OUTPUT = DATASET_FINAL_CSV / "dataset_laptops_UNICOS_V5.csv"

    try:
        # Carregamento de configurações
        config = ConfiguracaoProcessamento.carregar(PATH_CONFIG / "hardware_rules.json")
        limpador = LimpadorModelos(PATH_CONFIG / "models_rules.json")
        
        with open(PATH_CONFIG / "mapeamento_arquivos_aprimorado.json", 'r', encoding='utf-8') as f:
            mapeamentos_json = json.load(f)["mapeamentos"]

        processador = ProcessadorDatasetLaptops(config, limpador)
        datasets_validados = []

        # Loop de processamento por arquivo
        for item in mapeamentos_json:
            caminho_csv = PATH_DADOS / item["arquivo"]
            if caminho_csv.exists():
                logger.info(f"Processando: {item['arquivo']}")
                df_p = processador.processar_arquivo(caminho_csv, item["colunas"])
                if df_p is not None: 
                    datasets_validados.append(df_p)

        # Consolidação e Remoção de Duplicatas
        if datasets_validados:
            df_final = pd.concat(datasets_validados, ignore_index=True)
            total_antes = len(df_final)
            
            # Drop duplicates baseado no ID Único gerado
            df_final = df_final.drop_duplicates(subset=['id_unico'], keep='first')
            
            PATH_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
            df_final.to_csv(PATH_OUTPUT, index=False)
            
            logger.info("=" * 50)
            logger.info(f"✅ Concluído! Dataset salvo em: {PATH_OUTPUT}")
            logger.info(f"📊 Estatísticas: Total Bruto: {total_antes} | Únicos (Lower): {len(df_final)}")
            logger.info("=" * 50)
        else:
            logger.error("Nenhum dado processado com sucesso.")

    except Exception as e:
        logger.error(f"Erro fatal no script: {e}")