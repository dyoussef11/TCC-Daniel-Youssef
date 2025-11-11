# 2_separate_datasets.py

import sys
from pathlib import Path
import re # Mantido por consistência, embora não seja usado
import pandas as pd
# Importa o módulo de detecção (Mantido por consistência)
from langdetect import detect, DetectorFactory 

# --- Configuração de Caminhos ---

# 1. Obtém o caminho absoluto da pasta do script atual.
caminho_script = Path(__file__).resolve().parent

# 2. Acessa a pasta raiz do projeto subindo dois níveis.
caminho_raiz_projeto = caminho_script.parent.parent

# 3. Adiciona o caminho da raiz ao caminho de busca do Python.
sys.path.append(str(caminho_raiz_projeto))

# Tenta importar as variáveis de configuração
try:
    from config import DIRETORIO_DADOS_LIMPEZA_DATASETS
except ImportError:
    print("Erro: Não foi possível importar diretórios de config.py.")
    sys.exit(1)


# Garante que a detecção de idioma seja consistente (Mantido por consistência)
DetectorFactory.seed = 0

# --- Funções de Pré-processamento e Detecção (Mantidas como "stubs") ---
# Embora não sejam estritamente usadas aqui, mantê-las garante 
# que o cabeçalho de imports e funções seja consistente e modular.

def is_pure_noise(text):
    """
    Verifica se o texto é composto apenas por nulos, strings vazias, 
    ou padrões puramente numéricos/de pontuação que indicam ruído.
    """
    if not isinstance(text, str):
        # Captura nulos (np.nan), que o pandas lê como float.
        return True
    
    # 1. Ruído de string vazia ou apenas espaços
    text_stripped = text.strip()
    if not text_stripped:
        return True
        
    # 2. Ruído puramente numérico ou de pontuação/separadores (como os números de ponto flutuante vistos)
    # ^[\d\s\.,/-]+$ -> Contém APENAS dígitos, espaços, ponto, vírgula, barra e traço
    if re.fullmatch(r'[\d\s\.,/-]+', text_stripped):
        return True
        
    # 3. Ruído de URLs que podem ter passado (se for só o texto de um link)
    if re.fullmatch(r'(http|www)\S*', text_stripped):
        return True

    return False

# --- Processamento Principal ---

def main_separation():
    print("--- 3. INICIANDO SEPARAÇÃO E REFINAMENTO DE DADOS ---")

    # Caminhos
    caminho_entrada_detectada = DIRETORIO_DADOS_LIMPEZA_DATASETS / 'respostas_com_lingua_detectada.csv'

    # Carregar o arquivo CSV com idioma detectado
    try:
        print(f"Carregando dados com idioma detectado de: {caminho_entrada_detectada}")
        df = pd.read_csv(caminho_entrada_detectada)
    except FileNotFoundError:
        print(f"Erro: Arquivo com idioma detectado não encontrado. Execute '2_detect_language.py' primeiro. Caminho: {caminho_entrada_detectada}")
        return

    # Proteção: Verifica se as colunas existem
    if 'language' not in df.columns or 'Conteudo_Comentario_Limpo' not in df.columns:
        print("Erro: As colunas 'language' e/ou 'Conteudo_Comentario_Limpo' não foram encontradas.")
        return

    print("\nIniciando separação e refinamento...")
    
    # Cria o diretório de destino
    DIRETORIO_DADOS_LIMPEZA_DATASETS.mkdir(parents=True, exist_ok=True)
    
    total_registros_filtrados = 0
    total_registros_salvos = 0

    for lang, group in df.groupby('language'):
        
        # --- REFINAMENTO APLICADO APENAS À CATEGORIA 'other' ---
        if lang == 'other':
            tamanho_original = len(group)
            
            # Aplica o filtro de ruído: is_pure_noise retorna True se for ruído
            # Usamos ~.apply() para manter os que NÃO são ruído.
            # Convertemos para string novamente para garantir que is_pure_noise funcione corretamente.
            group_refinado = group[~group['Conteudo_Comentario_Limpo'].astype(str).apply(is_pure_noise)].copy()
            
            tamanho_filtrado = len(group_refinado)
            registros_filtrados = tamanho_original - tamanho_filtrado
            total_registros_filtrados += registros_filtrados
            
            print(f"-> Refinamento 'other': {registros_filtrados} linhas de ruído removidas (Original: {tamanho_original}, Salvas: {tamanho_filtrado})")
            grupo_a_salvar = group_refinado
        else:
            grupo_a_salvar = group


        # Salva o DataFrame do grupo (refinado ou original)
        output_filename = DIRETORIO_DADOS_LIMPEZA_DATASETS / f'dataset_respostas_{lang}.csv'
        grupo_a_salvar.to_csv(output_filename, index=False)
        
        total_registros_salvos += len(grupo_a_salvar)
        print(f"-> Dados da categoria '{lang}' ({len(grupo_a_salvar)} linhas) salvos em '{output_filename.name}'")

    print("-" * 50)
    print("✅ Separação e Refinamento concluídos.")
    print(f"Total de registros de ruído removidos da categoria 'other': {total_registros_filtrados}")
    print(f"Total de registros salvos nos datasets finais: {total_registros_salvos}")
    print("-" * 50)

if __name__ == "__main__":
    main_separation()