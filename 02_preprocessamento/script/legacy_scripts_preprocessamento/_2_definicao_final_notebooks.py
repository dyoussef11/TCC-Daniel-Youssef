import os
import shutil
from pathlib import Path
from core.paths import PREPROCESSAMENTO_DATA

# ============================================
# CONFIGURAÇÕES DE CAMINHOS
# ============================================
PASTA_ORIGEM = PREPROCESSAMENTO_DATA / "Dados_Limpos_IniciaisV8"
PASTA_FINAL = PREPROCESSAMENTO_DATA / "Dados_Final_Threshold_V13"
ARQUIVO_LISTA = PREPROCESSAMENTO_DATA / "analise_estatisticaV3" / "lista_amostra_selecionada.txt"

def preparar_dataset_final():
    # 1. Cria a pasta de destino se não existir
    if not os.path.exists(PASTA_FINAL):
        os.makedirs(PASTA_FINAL)
        print(f"📁 Pasta criada: {PASTA_FINAL}")

    # 2. Lê a lista de arquivos selecionados
    if not os.path.exists(ARQUIVO_LISTA):
        print(f"❌ Erro: Arquivo {ARQUIVO_LISTA} não encontrado!")
        return

    with open(ARQUIVO_LISTA, 'r', encoding='utf-8') as f:
        arquivos_selecionados = [linha.strip() for linha in f if linha.strip()]

    print(f"📋 Lendo lista com {len(arquivos_selecionados)} arquivos...")

    # 3. Copia os arquivos
    contagem = 0
    erros = 0

    for nome_arquivo in arquivos_selecionados:
        caminho_origem = PASTA_ORIGEM / nome_arquivo
        caminho_destino = PASTA_FINAL / nome_arquivo

        if os.path.exists(caminho_origem):
            try:
                # Usamos copy2 para preservar metadados do arquivo
                shutil.copy2(caminho_origem, caminho_destino)
                contagem += 1
            except Exception as e:
                print(f"⚠️ Erro ao copiar {nome_arquivo}: {e}")
                erros += 1
        else:
            print(f"❓ Arquivo não encontrado na origem: {nome_arquivo}")
            erros += 1

    print(f"\n{'='*40}")
    print(f"✅ Processo concluído!")
    print(f"🚀 Arquivos movidos com sucesso: {contagem}")
    if erros > 0:
        print(f"❌ Falhas encontradas: {erros}")
    print(f"📂 Localização final: {PASTA_FINAL}")
    print(f"{'='*40}")

if __name__ == "__main__":
    preparar_dataset_final()