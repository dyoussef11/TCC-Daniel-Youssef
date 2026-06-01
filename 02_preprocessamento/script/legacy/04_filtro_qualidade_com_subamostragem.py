
import os
import json
import pandas as pd
import random
from concurrent.futures import ProcessPoolExecutor
from tqdm import tqdm
from functools import partial
from core.paths import PREPROCESSAMENTO_DATA

# Configurações de Caminho
CAMINHO_METRICAS = PREPROCESSAMENTO_DATA / "Contagem_AnaliseV2" / "prevalencia_com_comentarios.csv"
CAMINHO_INPUT_JSON = PREPROCESSAMENTO_DATA / "Dados_Consolidados_Por_ModeloV2"
CAMINHO_SAIDA_FINAL = PREPROCESSAMENTO_DATA / "Dados_Final_ThresholdV2"

def processar_arquivo(nome_arquivo, modelos_eleitos, max_posts):
    """
    Função worker que processa um único arquivo JSON.
    """
    caminho_entrada = CAMINHO_INPUT_JSON / nome_arquivo
    caminho_saida = CAMINHO_SAIDA_FINAL / nome_arquivo

    try:
        with open(caminho_entrada, 'r', encoding='utf-8') as f:
            dados = json.load(f)
        
        # Verifica se o modelo do arquivo está na lista de aprovados
        if dados.get('modelo_busca_utilizado') in modelos_eleitos:
            posts = dados.get('posts', [])
            
            # Realiza a amostragem (downsampling) para eficiência
            if len(posts) > max_posts:
                posts = random.sample(posts, max_posts)
            
            dados['posts'] = posts
            
            # Salva o arquivo filtrado/amostrado
            with open(caminho_saida, 'w', encoding='utf-8') as f:
                json.dump(dados, f, indent=4, ensure_ascii=False)
            return True
    except Exception:
        return False
    return False

def executar_corte_final_otimizado():
    MAX_POSTS = 50 # Teto para poupar a GTX 1050 Ti
    
    if not CAMINHO_SAIDA_FINAL.exists(): 
        CAMINHO_SAIDA_FINAL.mkdir(parents=True)
    
    # 1. Carrega métricas e identifica modelos aprovados (Rápido)
    df = pd.read_csv(CAMINHO_METRICAS, sep=';')
    aprovados = df[(df['posts_unicos'] >= 20) & 
                   (df['densidade_tecnica'] >= 3.0) & 
                   (df['temas_cobertos'] >= 3)]

    # Transformar em 'set' para busca O(1) extremamente rápida
    modelos_eleitos = set(aprovados['modelo'].unique().tolist())
    
    # 2. Listar todos os arquivos JSON da pasta de entrada
    arquivos = [f for f in os.listdir(CAMINHO_INPUT_JSON) if f.endswith('.json')]
    
    # 3. Configurar a função com argumentos fixos usando partial
    worker_com_parametros = partial(
        processar_arquivo, 
        modelos_eleitos=modelos_eleitos, 
        max_posts=MAX_POSTS
    )

    print(f"🚀 Iniciando processamento paralelo: {len(arquivos)} arquivos...")
    print(f"📊 Threshold: Densidade >= 3.0 | Modelos Aprovados: {len(modelos_eleitos)}")

    # 4. Execução Paralela com Barra de Progresso
    with ProcessPoolExecutor() as executor:
        # O map distribui os arquivos entre os processos
        # list() é necessário para consumir o generator e ativar a tqdm
        list(tqdm(
            executor.map(worker_com_parametros, arquivos), 
            total=len(arquivos), 
            desc="Filtrando e Amostrando"
        ))

    print(f"\n✅ Concluído! Os arquivos aprovados estão em: {CAMINHO_SAIDA_FINAL}")

if __name__ == "__main__":
    executar_corte_final_otimizado()