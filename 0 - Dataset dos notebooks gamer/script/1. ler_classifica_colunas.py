import pandas as pd
import csv 
import sys
from pathlib import Path
import re
import numpy as np

# --- CONFIGURAÇÃO INICIAL (MANTIDA DO SEU CÓDIGO) ---

# Obtém o caminho absoluto da pasta do script atual.
caminho_script = Path(__file__).resolve().parent
caminho_raiz_projeto = caminho_script.parent.parent
sys.path.append(str(caminho_raiz_projeto))

from config import DIRETORIO_CSV_DATASET_COLETADOS, DIRETORIO_CSV_DATASET_FINAL

# Lista dos arquivos a serem processados
arquivos_csv = [
    DIRETORIO_CSV_DATASET_COLETADOS / 'Brand Laptops Dataset - List of all brand new laptops - until 2024.csv',
    DIRETORIO_CSV_DATASET_COLETADOS / 'Gamming Laptop - Flipkart.csv',
    DIRETORIO_CSV_DATASET_COLETADOS / 'Laptops Dataset - Predicting laptop prices based on specifications.csv',
    DIRETORIO_CSV_DATASET_COLETADOS / 'Unveiling the Top Gaming Laptops - Demystifying Laptop Specifications.csv',
    DIRETORIO_CSV_DATASET_COLETADOS / 'modelos_gerado_AI.csv',
]

# ----------------- INÍCIO DA LÓGICA DE PROCESSAMENTO -----------------

# Nomes padronizados para o dataset final
COLUNAS_PADRAO_ALVO = ['Marca', 'Modelo_Completo', 'CPU', 'GPU', 'Ano_Lancamento', 'RAM', 'Tipo_Notebook', 'Subtipo_Modelo']

# --- MAPEAMENTOS (Mantidos) ---
mapeamento_d2 = {'brand': 'Marca', 'Model': 'Modelo_Completo', 'ram_memory': 'RAM', 'processor_brand': 'CPU_Marca', 'processor_tier': 'CPU_Nivel', 'gpu_brand': 'GPU_Marca', 'gpu_type': 'GPU_Tipo',}
mapeamento_d4 = {'Laptop Name': 'Modelo_Completo',}
mapeamento_d5 = {'brand': 'Marca', 'model_name': 'Modelo_Completo', 'processor_name': 'CPU', 'graphics': 'GPU', 'ram(GB)': 'RAM',}
mapeamento_d1 = {'Product': 'Modelo_Completo', 'Processor': 'CPU', 'Ram': 'RAM',}
mapeamento_d3 = {'marca': 'Marca', 'modelo': 'Modelo_Completo', 'ano': 'Ano_Lancamento',}

lista_de_mapeamentos = [mapeamento_d2, mapeamento_d4, mapeamento_d5, mapeamento_d1, mapeamento_d3,]

dfs_a_concatenar = []

for idx, (caminho_arquivo, mapeamento) in enumerate(zip(arquivos_csv, lista_de_mapeamentos)):
    try:
        # 1. Carregar o DataFrame
        if caminho_arquivo.name == 'Unveiling the Top Gaming Laptops - Demystifying Laptop Specifications.csv':
            df = pd.read_csv(str(caminho_arquivo), encoding='latin1') 
        else:
            df = pd.read_csv(str(caminho_arquivo))
        
        # 2. Renomeação de colunas
        colunas_para_renomear = {
            col_original: col_padrao for col_original, col_padrao in mapeamento.items() if col_original in df.columns
        }
        df_renomeado = df.rename(columns=colunas_para_renomear)
        
        # 3. Tratamento Específico e Harmonização (Mantido o mesmo)
        if 'Marca' not in df_renomeado.columns and 'Modelo_Completo' in df_renomeado.columns:
            df_renomeado['Marca'] = df_renomeado['Modelo_Completo'].str.split().str[0]
        if idx == 0:
            df_renomeado['CPU'] = df_renomeado['CPU_Nivel'].astype(str).str.strip() + ' ' + df_renomeado['CPU_Marca'].astype(str).str.strip()
            df_renomeado['GPU'] = df_renomeado['GPU_Tipo'].astype(str).str.strip() + ' ' + df_renomeado['GPU_Marca'].astype(str).str.strip()
        elif idx == 1:
            cpu_pattern = r'(Intel Core i\d{1} \d{1,2}th Gen \d{3,}H[X]?|AMD Ryzen \d{1} Octa Core \d{3,}HS|AMD Ryzen \d{1} Quad Core \d{3,}HS|AMD Ryzen \d{1} Hexa Core \d{3,}H[S]?|Intel Core Ultra \d{1} \d{3}H|\d{1,2}th Gen Intel Core i\d|AMD Ryzen \d{1} Octa Core \d{4}H)'
            df_renomeado['CPU'] = df_renomeado['Modelo_Completo'].str.extract(cpu_pattern, flags=re.IGNORECASE)[0].fillna(pd.NA)
            ram_match = df_renomeado['Modelo_Completo'].str.extract(r'\(([\d\s]+GB)')[0]
            df_renomeado['RAM'] = ram_match.str.replace('GB', '', regex=False).str.strip().fillna(pd.NA)
            gpu_match = df_renomeado['Modelo_Completo'].str.extract(r'(\d+GB Graph)')
            df_renomeado['GPU'] = 'Dedicated ' + gpu_match[0].astype(str).str.replace('Graph', 'Graphics', regex=False).fillna(pd.NA)
        elif 'GPU' not in df_renomeado.columns:
            df_renomeado['GPU'] = pd.NA
        if 'RAM' in df_renomeado.columns:
             df_renomeado['RAM'] = df_renomeado['RAM'].astype(str).str.replace(r'[\?a-zA-Z\s]+', '', regex=True).str.replace(r'\.0$', '', regex=True).str.strip()
        else:
            df_renomeado['RAM'] = pd.NA
        if 'Ano_Lancamento' not in df_renomeado.columns:
             if 'Modelo_Completo' in df_renomeado.columns:
                 ano_extraido = df_renomeado['Modelo_Completo'].str.extract(r'\((\d{4})\)').fillna(0).astype(int)
                 df_renomeado['Ano_Lancamento'] = ano_extraido.where(ano_extraido != 0, pd.NA)
             else:
                 df_renomeado['Ano_Lancamento'] = pd.NA
                 
        # 4. Garantir todas as colunas padrão
        df_final = pd.DataFrame(columns=COLUNAS_PADRAO_ALVO)
        for col in COLUNAS_PADRAO_ALVO:
            if col in df_renomeado.columns:
                df_final[col] = df_renomeado[col]
            else:
                df_final[col] = pd.NA
        dfs_a_concatenar.append(df_final)

    except Exception as e:
        print(f"ERRO ao processar {caminho_arquivo.name}: {e}")

# --- CONCATENAÇÃO E ENGENHARIA DE RECURSOS ---

if dfs_a_concatenar:
    dataset_concatenado = pd.concat(dfs_a_concatenar, ignore_index=True)
    dataset_concatenado['Marca'] = dataset_concatenado['Marca'].astype(str).str.strip().str.upper()
    dataset_concatenado.replace(['NAN NAN', 'INTEGRATED NAN'], np.nan, inplace=True)
    dataset_concatenado.dropna(subset=['Modelo_Completo', 'Marca'], inplace=True)


    # 1. Função de Inferência do Ano (Mantida)
    def inferir_ano(row):
        if pd.notna(row['Ano_Lancamento']):
            return row['Ano_Lancamento']
            
        cpu = str(row['CPU']).upper()
        modelo = str(row['Modelo_Completo']).upper()
        gpu = str(row['GPU']).upper()
        
        if re.search(r'(14TH GEN|ULTRA \d|40[5-9]0|40[5-9]0 TI|40[5-9]0 MAX Q|8\d{3}HS|M4)', cpu) or 'RTX 40' in gpu or 'M4' in modelo: return 2024
        if re.search(r'(13TH GEN|7[579]\d{2}H[X]?|3080TI|M3)', cpu) or 'RTX 3080 TI' in gpu or 'M3' in modelo: return 2023
        if re.search(r'(12TH GEN|6[89]\d{2}H[S]?|30[5678]0|M2)', cpu) or 'RTX 30' in gpu or 'M2' in modelo: return 2022
        if re.search(r'(11TH GEN|5[68]\d{2}H[X]?|3050|3060|1650TI)', cpu) or 'RTX 3050' in gpu: return 2021
        if re.search(r'(10TH GEN|4\d{3}H|1650|1660|1650 MAX Q)', cpu) or 'GTX 1650' in gpu: return 2020
            
        return pd.NA

    dataset_concatenado['Ano_Lancamento'] = dataset_concatenado.apply(inferir_ano, axis=1)
    dataset_concatenado['Ano_Lancamento'] = pd.to_numeric(dataset_concatenado['Ano_Lancamento'], errors='coerce', downcast='integer').astype('Int64')

    # 2. Classificação Geral (Mantida)
    def classificar_tipo_notebook(row):
        modelo = str(row['Modelo_Completo']).upper()
        gpu = str(row['GPU']).upper()
        cpu = str(row['CPU']).upper()
        marca = str(row['Marca']).upper()
        
        gamer_keywords = ['GAMING', 'ROG', 'OMEN', 'PREDATOR', 'NITRO', 'LEGION', 'TUF', 'BLADE', 'AORUS', 'VICTUS']
        if any(kw in modelo for kw in gamer_keywords) or re.search(r'(RTX \d{4}|GTX 1650|RX 5500M|RX 6\d{3}M|RTX A\d{4}|DEDICATED \d+GB GRAPHICS)', gpu): return 'Gamer'
        if marca == 'APPLE': return 'Business/Premium (Apple)'
        if marca == 'LG' and 'GRAM' in modelo: return 'Business/Premium (Ultrafino)'
        if marca == 'MICROSOFT' and 'SURFACE' in modelo: return 'Business/Premium (Surface)'
        if marca in ['XIAOMI', 'REALME'] and ('PRO' in modelo or 'ULTRA' in modelo or 'BOOK SLIM' in modelo): return 'Performance/Geral'
        if marca in ['INFINIX', 'CHUWI', 'ULTIMUS', 'AVITA'] and 'ZERO' in modelo: return 'Performance/Geral'

        creator_keywords = ['CREATOR', 'PROART', 'STUDIO', 'XPS', 'ZBOOK', 'PRECISION', 'YOGA BOOK']
        if any(kw in modelo for kw in creator_keywords) or 'QUADRO' in gpu or 'RTX A' in gpu or ('CORE I9' in cpu and 'INTEGRATED' not in gpu): return 'Creator/Workstation'
        
        business_keywords = ['VOSTRO', 'LATITUDE', 'THINKPAD', 'PROBOOK', 'ELITEBOOK', 'SPECTRE', 'ZENBOOK']
        if any(kw in modelo for kw in business_keywords): return 'Business/Premium'

        if re.search(r'([I5|I7|R5|R7].*H[X]?|M\d|CORE ULTRA|RYZEN 7)', cpu): return 'Geral/Média Performance'
            
        return 'Geral/Baixa Performance'

    dataset_concatenado['Tipo_Notebook'] = dataset_concatenado.apply(classificar_tipo_notebook, axis=1)

    # 3. Classificação de Subtipo (Mantida)
    def classificar_subtipo(row):
        modelo = str(row['Modelo_Completo']).upper()
        marca = str(row['Marca']).upper()
        
        if 'ROG' in modelo:
            if 'ZEPHYRUS DUO' in modelo: return 'ROG Zephyrus Duo (Dual Screen)'
            if 'ZEPHYRUS G14' in modelo: return 'ROG Zephyrus G14 (Performance Compacta)'
            if 'ZEPHYRUS' in modelo: return 'ROG Zephyrus (Slim Performance)'
            if 'STRIX SCAR' in modelo: return 'ROG Strix SCAR (High-End Gaming)'
            if 'STRIX' in modelo: return 'ROG Strix (Gaming Performance)'
            if 'FLOW' in modelo: return 'ROG Flow (2-in-1 Gaming)'
            return 'ROG Geral'
        if 'TUF' in modelo: return 'TUF Gaming (Gaming Acessível)'
        if 'OMEN' in modelo: return 'HP Omen (Gaming)'
        if 'VICTUS' in modelo: return 'HP Victus (Gaming de Entrada)'
        if 'PREDATOR' in modelo: return 'Acer Predator (Gaming High-End)'
        if 'NITRO' in modelo: return 'Acer Nitro (Gaming Acessível)'
        if 'TITAN' in modelo or 'RAIDER' in modelo: return 'MSI High-End (Titan/Raider)'
        if 'KATANA' in modelo or 'SWORD' in modelo or 'PULSE' in modelo: return 'MSI Mid-Range (Katana/Pulse)'
        if 'THIN' in modelo: return 'MSI Thin (Gaming Slim/Entrada)'
        if 'LEGION PRO' in modelo: return 'Lenovo Legion Pro (High-End Gaming)'
        if 'LEGION' in modelo: return 'Lenovo Legion (Gaming Performance)'
        if 'LOQ' in modelo: return 'Lenovo LOQ (Gaming Acessível)'
        if 'ALIENWARE' in modelo: return 'Dell Alienware (Gaming Premium)'
        if 'DELL G' in modelo: return 'Dell G Series (Gaming)'
        if 'PROART' in modelo or 'CREATOR' in modelo or 'STUDIO' in modelo: return 'Creator/Estação de Trabalho'
        if 'XPS' in modelo: return 'Dell XPS (Premium/Creator)'
        if 'ZENBOOK' in modelo: return 'Asus Zenbook (Premium/Ultrafino)'
        if 'THINKPAD' in modelo or 'THINKBOOK' in modelo: return 'Lenovo ThinkPad/Book (Business/Durabilidade)'
        if 'SPECTRE' in modelo: return 'HP Spectre (Premium/2-in-1)'
        if 'LATITUDE' in modelo or 'VOSTRO' in modelo: return 'Dell Business (Latitude/Vostro)'
        if 'GRAM' in modelo and marca == 'LG': return 'LG Gram (Premium/Ultrafino)'
        if 'SURFACE' in modelo and marca == 'MICROSOFT': return 'Microsoft Surface (Premium/2-in-1)'
        if 'VIVOBOOK PRO' in modelo or 'PAVILION PLUS' in modelo: return 'Performance/Geral'
        if 'VIVOBOOK' in modelo or 'ASPIRE' in modelo or 'INSPIRON' in modelo: return 'Notebook Geral'
        if row['Tipo_Notebook'] in ['Performance/Geral', 'Geral/Média Performance']: return 'Série Geral de Performance'
        
        return 'Outros/Não Classificado'

    dataset_concatenado['Subtipo_Modelo'] = dataset_concatenado.apply(classificar_subtipo, axis=1)

    # 4. Criação do ID ÚNICO de Configuração (Base para a NOME_ASSINATURA)
    def extrair_serial_e_id_de_configuracao(row):
        modelo = str(row['Modelo_Completo']).upper()
        
        # Tenta extrair códigos de configuração alfanuméricos fortes
        match_code = re.search(r'([A-Z0-9]{4,7}[-\s]?[A-Z0-9]{4,8}[A-Z]{2,3})', modelo)
        if match_code:
            return match_code.group(1).replace('-', '').replace(' ', '')
            
        # Cria um ID de Fallback (Mantido do código anterior, mas agora usado como base)
        cpu_simples = re.search(r'(\d{2}TH GEN|RYZEN \d|CORE ULTRA \d|APPLE M\d)', str(row['CPU']).upper())
        cpu_id = cpu_simples.group(1).replace(' ', '') if cpu_simples else 'UNKNOWN_CPU'
        
        gpu_simples = re.search(r'(RTX \d{4}|GTX \d{4}|RX \d{4})', str(row['GPU']).upper())
        gpu_id = gpu_simples.group(1).replace(' ', '') if gpu_simples else 'INTEGRATED'
        
        ram_val = str(row['RAM']).split('.')[0] if pd.notna(row['RAM']) else 'NA'
        ano_val = str(row['Ano_Lancamento']) if pd.notna(row['Ano_Lancamento']) else 'NA'

        modelo_base = modelo.split('(')[0].split('-')[0].strip()
        
        return f"{modelo_base}_{ano_val}_{cpu_id}_{gpu_id}_{ram_val}GB"

    dataset_concatenado['ID_UNICO_CONFIG'] = dataset_concatenado.apply(extrair_serial_e_id_de_configuracao, axis=1)

    # 5. Criação da Coluna NOME_ASSINATURA (CORREÇÃO DE LÓGICA)
    def extrair_nome_assinatura(row):
        modelo = str(row['Modelo_Completo']).upper().strip()
        marca = str(row['Marca']).upper().strip()
        
        # PASSO 1: Remove a Marca e os parênteses (com todo o conteúdo dentro)
        modelo = re.sub(r'^{}\s+'.format(re.escape(marca)), '', modelo, count=1).strip()
        modelo = re.sub(r'\s*\([^)]*\)\s*', ' ', modelo).strip() # Remove (tudo o que estiver aqui)

        # PASSO 2: Remove a menção de "Laptop" e "Gaming" do início ou meio
        modelo = re.sub(r'^(GAMING|LAPTOP|NOTEBOOK|PC|WORKSTATION)\s*', '', modelo, flags=re.IGNORECASE).strip()
        modelo = re.sub(r'\s+(GAMING|LAPTOP|NOTEBOOK|PC|WORKSTATION)\s*$', '', modelo, flags=re.IGNORECASE).strip()

        # PASSO 3: Remove especificações de hardware (para garantir que nada tenha sobrado)
        # Processadores (Remoção total)
        modelo = re.sub(r'\b(I\d|R\d)\b.*H[X]?|\b(CORE|RYZEN|CELERON|PENTIUM|ATHLON).*', ' ', modelo).strip()
        # GPU, RAM, SSD, etc.
        modelo = re.sub(r'(\d+GB|\d+TB|SSD|HDD|RTX|GTX|RX|GEFORCE|RADEON|GRAPHICS|VRAM)', ' ', modelo).strip()
        
        # PASSO 4: Limpeza final de pontuação/espaços
        modelo = re.sub(r'[—_./]|[\s]*\b(\d+S|\d+U|\d+H)\b[\s]*', ' ', modelo).strip() # Limpa séries de CPU se não foram removidas
        modelo = re.sub(r'\s+', ' ', modelo).strip()

        # Se o resultado for uma string vazia, utiliza o Subtipo_Modelo
        return modelo if modelo else row['Subtipo_Modelo']


    dataset_concatenado['Nome_Assinatura'] = dataset_concatenado.apply(extrair_nome_assinatura, axis=1)

    # 6. Remoção de Duplicatas e Seleção Final
    dataset_concatenado.drop_duplicates(subset=['Marca', 'ID_UNICO_CONFIG'], inplace=True)
    
    COLUNAS_FINAL = ['Marca', 'Subtipo_Modelo', 'Modelo_Completo', 'Nome_Assinatura', 'ID_UNICO_CONFIG', 'Tipo_Notebook', 'Ano_Lancamento', 'CPU', 'GPU', 'RAM']
    dataset_final = dataset_concatenado[COLUNAS_FINAL]

    # Salvando o resultado final na pasta do projeto
    output_filename = 'dataset_laptops.csv'
    output_path = DIRETORIO_CSV_DATASET_FINAL / output_filename
    dataset_final.to_csv(output_path, index=False)
    
    print("\n--- Processamento COMPLETO Concluído ---")
    print(f"Dataset harmonizado e enriquecido salvo em: {output_path}")
    print(f"Total de registros únicos de configurações: {len(dataset_final)}")

else:
    print("Nenhum DataFrame foi processado para concatenação.")