import pandas as pd
import sys
from pathlib import Path
import re
import numpy as np
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass


# ==================== CONFIGURAÇÕES CENTRALIZADAS ====================

@dataclass
class ConfiguracaoProcessamento:
    """Centraliza todas as configurações e padrões do processamento"""
    
    # Colunas padrão do dataset final
    COLUNAS_PADRAO: List[str] = None
    
    # Padrões de extração de componentes
    PADROES_CPU: Dict[str, str] = None
    PADROES_GPU: Dict[str, str] = None
    PADROES_RAM: Dict[str, str] = None
    PADROES_STORAGE: Dict[str, str] = None
    PADROES_ANO: Dict[str, str] = None
    
    # Classificações de notebooks
    KEYWORDS_GAMER: List[str] = None
    KEYWORDS_CREATOR: List[str] = None
    KEYWORDS_BUSINESS: List[str] = None
    
    # Subtipos de modelos
    SUBTIPOS: Dict[str, Tuple[List[str], str]] = None
    
    def __post_init__(self):
        self.COLUNAS_PADRAO = [
            'Marca', 'Modelo_Completo', 'CPU', 'GPU', 'Ano_Lancamento', 
            'RAM', 'Storage', 'Tela', 'Peso', 'Tipo_Notebook', 'Subtipo_Modelo'
        ]
        
        # Padrões regex unificados e extensíveis
        self.PADROES_CPU = {
            'intel_gen': r'(?:Intel\s+)?(?:Core\s+)?i[3579][-\s]?\d{4,5}[A-Z]{0,3}',
            'intel_ultra': r'Intel\s+Core\s+Ultra\s+[57]\s+\d{3}[A-Z]{0,2}',
            'intel_gen_simples': r'\d{1,2}th\s+Gen(?:\s+Intel)?(?:\s+Core)?\s+i[3579]',
            'amd_ryzen': r'AMD\s+Ryzen\s+[3579]\s+(?:Pro\s+)?\d{4}[A-Z]{0,3}',
            'amd_ryzen_desc': r'AMD\s+Ryzen\s+[3579]\s+(?:Quad|Hexa|Octa)\s+Core\s+\d{4}[A-Z]{0,2}',
            'apple_m': r'Apple\s+M\d(?:\s+(?:Pro|Max|Ultra))?',
            'qualcomm': r'Snapdragon\s+(?:X\s+)?(?:Elite|Plus)?\s*\d{0,4}',
            'celeron': r'Intel\s+Celeron\s+[A-Z]?\d{4}[A-Z]?',
            'pentium': r'Intel\s+Pentium\s+(?:Silver|Gold)?\s*[A-Z]?\d{4}[A-Z]?'
        }
        
        self.PADROES_GPU = {
            'nvidia_rtx': r'(?:NVIDIA\s+)?(?:GeForce\s+)?RTX\s+\d{4}(?:\s+Ti)?(?:\s+(?:Laptop|Mobile|Max-Q))?',
            'nvidia_gtx': r'(?:NVIDIA\s+)?(?:GeForce\s+)?GTX\s+\d{4}(?:\s+Ti)?(?:\s+(?:Max-Q))?',
            'nvidia_mx': r'(?:NVIDIA\s+)?(?:GeForce\s+)?MX\s*\d{3,4}',
            'amd_radeon': r'AMD\s+Radeon\s+(?:RX\s+)?\d{4}[A-Z]{0,2}(?:\s+M)?',
            'intel_arc': r'Intel\s+Arc\s+[A-Z]?\d{3}[A-Z]?',
            'intel_iris': r'Intel\s+Iris\s+(?:Xe\s+)?(?:Graphics\s+)?\d{0,4}',
            'apple_gpu': r'Apple\s+(?:M\d\s+)?(?:\d{1,2}[-\s]Core\s+)?GPU',
            'integrated': r'(?:Integrated|UHD|HD)\s+(?:Graphics\s+)?\d{0,4}'
        }
        
        self.PADROES_RAM = {
            'simple': r'(\d+)\s*GB(?:\s+RAM)?',
            'detailed': r'(\d+)\s*GB\s+(?:DDR[34X]|LPDDR[345X]|SDRAM)',
        }
        
        self.PADROES_STORAGE = {
            'ssd': r'(\d+)\s*(?:GB|TB)\s+SSD',
            'hdd': r'(\d+)\s*(?:GB|TB)\s+HDD',
            'nvme': r'(\d+)\s*(?:GB|TB)\s+(?:NVMe|PCIe)',
            'combined': r'(\d+)\s*(?:GB|TB)\s+SSD\s*\+\s*(\d+)\s*(?:GB|TB)\s+HDD'
        }
        
        self.PADROES_ANO = {
            'explicit': r'\((\d{4})\)',
            'model_year': r'(?:20\d{2})\s+(?:Edition|Model)'
        }
        
        # Keywords de classificação (agora mais extensivas)
        self.KEYWORDS_GAMER = [
            'GAMING', 'ROG', 'OMEN', 'PREDATOR', 'NITRO', 'LEGION', 
            'TUF', 'BLADE', 'AORUS', 'VICTUS', 'ALIENWARE', 'RAIDER',
            'KATANA', 'SWORD', 'PULSE', 'SCAR', 'FLOW', 'ZEPHYRUS'
        ]
        
        self.KEYWORDS_CREATOR = [
            'CREATOR', 'PROART', 'STUDIO', 'XPS', 'ZBOOK', 'PRECISION',
            'YOGA BOOK', 'QUADRO', 'WORKSTATION'
        ]
        
        self.KEYWORDS_BUSINESS = [
            'VOSTRO', 'LATITUDE', 'THINKPAD', 'PROBOOK', 'ELITEBOOK',
            'SPECTRE', 'ZENBOOK', 'EXPERTBOOK', 'TRAVELMATE'
        ]
        
        # Subtipos detalhados (keywords, descrição)
        self.SUBTIPOS = {
            'ROG Zephyrus Duo': (['ZEPHYRUS DUO'], 'Dual Screen'),
            'ROG Zephyrus G14': (['ZEPHYRUS G14'], 'Performance Compacta'),
            'ROG Zephyrus': (['ZEPHYRUS'], 'Slim Performance'),
            'ROG Strix SCAR': (['STRIX SCAR'], 'High-End Gaming'),
            'ROG Strix': (['STRIX'], 'Gaming Performance'),
            'ROG Flow': (['FLOW'], '2-in-1 Gaming'),
            'TUF Gaming': (['TUF'], 'Gaming Acessível'),
            'HP Omen': (['OMEN'], 'Gaming'),
            'HP Victus': (['VICTUS'], 'Gaming de Entrada'),
            'Acer Predator': (['PREDATOR'], 'Gaming High-End'),
            'Acer Nitro': (['NITRO'], 'Gaming Acessível'),
            'MSI High-End': (['TITAN', 'RAIDER'], 'Titan/Raider'),
            'MSI Mid-Range': (['KATANA', 'SWORD', 'PULSE'], 'Katana/Pulse'),
            'MSI Thin': (['THIN'], 'Gaming Slim'),
            'Lenovo Legion Pro': (['LEGION PRO'], 'High-End Gaming'),
            'Lenovo Legion': (['LEGION'], 'Gaming Performance'),
            'Lenovo LOQ': (['LOQ'], 'Gaming Acessível'),
            'Dell Alienware': (['ALIENWARE'], 'Gaming Premium'),
            'Dell G Series': (['DELL G'], 'Gaming'),
            'Creator/Workstation': (['PROART', 'CREATOR', 'STUDIO'], 'Profissional'),
            'Dell XPS': (['XPS'], 'Premium/Creator'),
            'Asus Zenbook': (['ZENBOOK'], 'Premium/Ultrafino'),
            'Lenovo ThinkPad': (['THINKPAD', 'THINKBOOK'], 'Business/Durabilidade'),
            'HP Spectre': (['SPECTRE'], 'Premium/2-in-1'),
            'Dell Business': (['LATITUDE', 'VOSTRO'], 'Latitude/Vostro'),
            'LG Gram': (['GRAM'], 'Premium/Ultrafino'),
            'Microsoft Surface': (['SURFACE'], 'Premium/2-in-1'),
        }


# ==================== CLASSE PRINCIPAL DE PROCESSAMENTO ====================

class ProcessadorDatasetLaptops:
    """Classe principal para processar e harmonizar datasets de laptops"""
    
    def __init__(self, config: ConfiguracaoProcessamento):
        self.config = config
        self.dfs_processados = []
        
    def extrair_componente(self, texto: str, padroes: Dict[str, str], 
                          prioridade: Optional[List[str]] = None) -> Optional[str]:
        """
        Extrai componente usando padrões regex priorizados
        
        Args:
            texto: Texto para buscar o componente
            padroes: Dicionário de padrões regex
            prioridade: Lista ordenada de chaves de padrões (ordem de busca)
        """
        if pd.isna(texto):
            return None
            
        texto_upper = str(texto).upper()
        ordem = prioridade if prioridade else list(padroes.keys())
        
        for chave in ordem:
            if chave in padroes:
                match = re.search(padroes[chave], texto_upper, re.IGNORECASE)
                if match:
                    return match.group(0).strip()
        return None
    
    def processar_cpu(self, df: pd.DataFrame) -> pd.DataFrame:
        """Processa e padroniza informações de CPU"""
        if 'CPU' not in df.columns or df['CPU'].isna().all():
            if 'Modelo_Completo' in df.columns:
                df['CPU'] = df['Modelo_Completo'].apply(
                    lambda x: self.extrair_componente(x, self.config.PADROES_CPU)
                )
            else:
                df['CPU'] = None
        return df
    
    def processar_gpu(self, df: pd.DataFrame) -> pd.DataFrame:
        """Processa e padroniza informações de GPU"""
        if 'GPU' not in df.columns or df['GPU'].isna().all():
            if 'Modelo_Completo' in df.columns:
                df['GPU'] = df['Modelo_Completo'].apply(
                    lambda x: self.extrair_componente(x, self.config.PADROES_GPU)
                )
            else:
                df['GPU'] = 'Integrated'
        return df
    
    def processar_ram(self, df: pd.DataFrame) -> pd.DataFrame:
        """Processa e padroniza informações de RAM"""
        if 'RAM' in df.columns:
            df['RAM'] = df['RAM'].astype(str).str.extract(r'(\d+)')[0]
        elif 'Modelo_Completo' in df.columns:
            df['RAM'] = df['Modelo_Completo'].apply(
                lambda x: self.extrair_componente(x, self.config.PADROES_RAM)
            )
        return df
    
    def inferir_ano(self, row: pd.Series) -> Optional[int]:
        """Infere o ano de lançamento baseado em CPU, GPU e modelo"""
        if pd.notna(row.get('Ano_Lancamento')):
            return int(row['Ano_Lancamento'])
        
        cpu = str(row.get('CPU', '')).upper()
        gpu = str(row.get('GPU', '')).upper()
        modelo = str(row.get('Modelo_Completo', '')).upper()
        
        # Mapeamento ano -> padrões (do mais recente ao mais antigo)
        mapa_anos = {
            2024: [r'14TH GEN', r'ULTRA \d', r'40[5-9]0', r'8\d{3}HS', r'M4', r'RTX 40'],
            2023: [r'13TH GEN', r'7[579]\d{2}H[X]?', r'3080TI', r'M3', r'RTX 3080 TI'],
            2022: [r'12TH GEN', r'6[89]\d{2}H[S]?', r'30[5678]0', r'M2', r'RTX 30'],
            2021: [r'11TH GEN', r'5[68]\d{2}H[X]?', r'3050', r'3060', r'RTX 3050'],
            2020: [r'10TH GEN', r'4\d{3}H', r'1650', r'1660', r'GTX 1650'],
        }
        
        texto_completo = f"{cpu} {gpu} {modelo}"
        for ano, padroes in mapa_anos.items():
            if any(re.search(p, texto_completo) for p in padroes):
                return ano
        
        return None
    
    def classificar_tipo(self, row: pd.Series) -> str:
        """Classifica o tipo geral do notebook"""
        modelo = str(row.get('Modelo_Completo', '')).upper()
        gpu = str(row.get('GPU', '')).upper()
        cpu = str(row.get('CPU', '')).upper()
        marca = str(row.get('Marca', '')).upper()
        
        # Gamer
        if any(kw in modelo for kw in self.config.KEYWORDS_GAMER):
            return 'Gamer'
        if re.search(r'RTX \d{4}|GTX 1[56]\d{2}|RX [56]\d{3}', gpu):
            return 'Gamer'
        
        # Premium/Business por marca
        if marca == 'APPLE':
            return 'Business/Premium (Apple)'
        if marca == 'LG' and 'GRAM' in modelo:
            return 'Business/Premium (Ultrafino)'
        if marca == 'MICROSOFT' and 'SURFACE' in modelo:
            return 'Business/Premium (Surface)'
        
        # Creator/Workstation
        if any(kw in modelo for kw in self.config.KEYWORDS_CREATOR):
            return 'Creator/Workstation'
        if 'QUADRO' in gpu or 'RTX A' in gpu:
            return 'Creator/Workstation'
        
        # Business
        if any(kw in modelo for kw in self.config.KEYWORDS_BUSINESS):
            return 'Business/Premium'
        
        # Performance baseada em CPU
        if re.search(r'I[57]|R[57]|M\d|ULTRA', cpu):
            return 'Geral/Média Performance'
        
        return 'Geral/Baixa Performance'
    
    def classificar_subtipo(self, row: pd.Series) -> str:
        """Classifica o subtipo específico do modelo"""
        modelo = str(row.get('Modelo_Completo', '')).upper()
        marca = str(row.get('Marca', '')).upper()
        
        for subtipo, (keywords, _) in self.config.SUBTIPOS.items():
            if any(kw in modelo for kw in keywords):
                return subtipo
        
        # Fallback baseado no tipo geral
        tipo = row.get('Tipo_Notebook', '')
        if 'Performance' in tipo:
            return 'Série Geral de Performance'
        
        return 'Outros/Não Classificado'
    
    def extrair_nome_assinatura(self, row: pd.Series) -> str:
        """Extrai nome limpo do modelo para uso em web scraping"""
        modelo = str(row.get('Modelo_Completo', '')).upper().strip()
        marca = str(row.get('Marca', '')).upper().strip()
        
        if not modelo or not marca:
            return str(row.get('Subtipo_Modelo', ''))
        
        # Remove marca
        modelo = re.sub(rf'^{re.escape(marca)}\s+', '', modelo, count=1).strip()
        
        # Remove parênteses e conteúdo
        modelo = re.sub(r'\s*\([^)]*\)\s*', ' ', modelo).strip()
        
        # Remove palavras genéricas
        modelo = re.sub(
            r'^(GAMING|LAPTOP|NOTEBOOK)\s+|\s+(GAMING|LAPTOP|NOTEBOOK)$',
            ' ', modelo, flags=re.IGNORECASE
        ).strip()
        
        # Remove especificações de hardware
        modelo = re.sub(
            r'\s*\d+GB|\d+TB|SSD|HDD|RTX|GTX|INTEL|AMD|CORE|RYZEN\s*',
            ' ', modelo, flags=re.IGNORECASE
        ).strip()
        
        # Trunca em SKUs longos
        modelo = re.sub(r'\s+[A-Z0-9]{6,}.*$', '', modelo)
        modelo = re.sub(r'-[A-Z0-9]{4,}[A-Z].*$', '', modelo)
        
        # Limpeza final
        modelo = re.sub(r'[-/\\:,\s]+', ' ', modelo).strip()
        modelo = re.sub(r'\s+', ' ', modelo).strip()
        
        return modelo if modelo else row.get('Subtipo_Modelo', '')
    
    def processar_arquivo(self, caminho: str, mapeamento: Dict[str, str]) -> Optional[pd.DataFrame]:
        """Processa um arquivo CSV individual"""
        try:
            # Carrega o arquivo
            if 'Unveiling the Top Gaming Laptops' in caminho:
                df = pd.read_csv(caminho, encoding='latin1')
            else:
                df = pd.read_csv(caminho)
            
            # Renomeia colunas
            df = df.rename(columns={k: v for k, v in mapeamento.items() if k in df.columns})
            
            # Extrai marca se não existir
            if 'Marca' not in df.columns and 'Modelo_Completo' in df.columns:
                df['Marca'] = df['Modelo_Completo'].astype(str).str.split().str[0]
            
            # Processa componentes
            df = self.processar_cpu(df)
            df = self.processar_gpu(df)
            df = self.processar_ram(df)
            
            # Garante todas as colunas padrão
            for col in self.config.COLUNAS_PADRAO:
                if col not in df.columns:
                    df[col] = None
            
            return df[self.config.COLUNAS_PADRAO]
            
        except Exception as e:
            print(f"ERRO ao processar {Path(caminho).name}: {e}")
            return None
    
    def processar_dataset_completo(self, arquivos: List[Tuple[str, Dict]]) -> pd.DataFrame:
        """Processa lista completa de arquivos e retorna dataset unificado"""
        dfs = []
        
        for caminho, mapeamento in arquivos:
            df = self.processar_arquivo(str(caminho), mapeamento)
            if df is not None:
                dfs.append(df)
        
        if not dfs:
            raise ValueError("Nenhum arquivo foi processado com sucesso")
        
        # Concatena todos os DataFrames
        dataset = pd.concat(dfs, ignore_index=True)
        
        # Limpeza geral
        dataset['Marca'] = dataset['Marca'].astype(str).str.strip().str.upper()
        dataset.dropna(subset=['Modelo_Completo', 'Marca'], inplace=True)
        
        # Engenharia de features
        dataset['Ano_Lancamento'] = dataset.apply(self.inferir_ano, axis=1)
        dataset['Tipo_Notebook'] = dataset.apply(self.classificar_tipo, axis=1)
        dataset['Subtipo_Modelo'] = dataset.apply(self.classificar_subtipo, axis=1)
        dataset['Nome_Assinatura'] = dataset.apply(self.extrair_nome_assinatura, axis=1)
        
        # Cria ID único
        dataset['ID_UNICO_CONFIG'] = (
            dataset['Marca'] + '_' +
            dataset['Nome_Assinatura'].str.replace(' ', '', regex=False) + '_' +
            dataset['Ano_Lancamento'].astype(str) + '_' +
            dataset['CPU'].astype(str).str.replace(' ', '', regex=False) + '_' +
            dataset['RAM'].astype(str) + 'GB'
        )
        
        # Remove duplicatas
        dataset.drop_duplicates(subset=['ID_UNICO_CONFIG'], inplace=True)
        
        return dataset


# ==================== EXECUÇÃO PRINCIPAL ====================

if __name__ == "__main__":
    # Configuração de paths (mantida do código original)
    try:
        caminho_script = Path(__file__).resolve().parent
        caminho_raiz_projeto = caminho_script.parent.parent
        sys.path.append(str(caminho_raiz_projeto))
        from config import DIRETORIO_CSV_DATASET_COLETADOS, DIRETORIO_CSV_DATASET_FINAL
    except:
        print("Usando paths simulados")
        DIRETORIO_CSV_DATASET_COLETADOS = Path('data/coletados')
        DIRETORIO_CSV_DATASET_FINAL = Path('data/final')
    
    # Lista de arquivos e mapeamentos
    arquivos_e_mapeamentos = [
        (DIRETORIO_CSV_DATASET_COLETADOS / 'Brand Laptops Dataset - List of all brand new laptops - until 2024.csv',
         {'brand': 'Marca', 'Model': 'Modelo_Completo', 'ram_memory': 'RAM'}),
        (DIRETORIO_CSV_DATASET_COLETADOS / 'Gamming Laptop - Flipkart.csv',
         {'Laptop Name': 'Modelo_Completo'}),
        (DIRETORIO_CSV_DATASET_COLETADOS / 'Laptops Dataset - Predicting laptop prices based on specifications.csv',
         {'brand': 'Marca', 'model_name': 'Modelo_Completo', 'processor_name': 'CPU', 'ram(GB)': 'RAM'}),
        (DIRETORIO_CSV_DATASET_COLETADOS / 'Unveiling the Top Gaming Laptops - Demystifying Laptop Specifications.csv',
         {'Product': 'Modelo_Completo', 'Processor': 'CPU', 'Ram': 'RAM'}),
        (DIRETORIO_CSV_DATASET_COLETADOS / 'modelos_gerado_AI.csv',
         {'marca': 'Marca', 'modelo': 'Modelo_Completo', 'ano': 'Ano_Lancamento'}),
    ]
    
    # Inicializa e processa
    config = ConfiguracaoProcessamento()
    processador = ProcessadorDatasetLaptops(config)
    
    dataset_final = processador.processar_dataset_completo(arquivos_e_mapeamentos)
    
    # Salva resultado
    output_path = DIRETORIO_CSV_DATASET_FINAL / 'dataset_laptops.csv'
    dataset_final.to_csv(output_path, index=False)
    
    print(f"\n✓ Processamento concluído!")
    print(f"✓ Dataset salvo em: {output_path}")
    print(f"✓ Total de registros: {len(dataset_final)}")
    
    # Demonstração
    modelos_acer_gamer = dataset_final[
        (dataset_final['Marca'] == 'ACER') & 
        (dataset_final['Tipo_Notebook'] == 'Gamer')
    ]['Nome_Assinatura'].unique()
    
    print(f"\n📊 Exemplo - Modelos Acer Gamer únicos: {len(modelos_acer_gamer)}")
    print(modelos_acer_gamer[:5])