import pandas as pd
from pathlib import Path
import sys
from core.paths import DATASET_KAGGLE, DATASET_GAMER 

# 1. Configurar caminhos
caminho_entrada = DATASET_KAGGLE
caminho_saida = DATASET_GAMER / "dataset_filtrados_colunas"
caminho_saida.mkdir(parents=True, exist_ok=True)

# 2. Listar arquivos
arquivos_csv = sorted(list(caminho_entrada.glob("*.csv")))

if not arquivos_csv:
    print(f"❌ Nenhum arquivo CSV encontrado.")
    sys.exit()

print(f"\n📂 Foram encontrados {len(arquivos_csv)} arquivos.")

# 3. Loop Interativo
for i, caminho_arq in enumerate(arquivos_csv, 1):
    nome_saida = caminho_saida / caminho_arq.name
    
    if nome_saida.exists():
        print(f"⏩ [{i}/{len(arquivos_csv)}] Pulando: {caminho_arq.name} (Já existe)")
        continue

    print(f"\n" + "="*85)
    print(f"ARQUIVO ({i}/{len(arquivos_csv)}): {caminho_arq.name}")
    print("="*85)

    try:
        # Carrega apenas a primeira linha para amostra
        try:
            df_sample = pd.read_csv(caminho_arq, nrows=1)
        except UnicodeDecodeError:
            df_sample = pd.read_csv(caminho_arq, nrows=1, encoding='latin1')
        
        colunas = df_sample.columns.tolist()
        # Pega a primeira linha de dados como exemplo (se existir)
        amostra = df_sample.iloc[0].to_dict() if not df_sample.empty else {}

        # --- NOVA VISUALIZAÇÃO MELHORADA ---
        print(f"{'ID':<5} | {'NOME DA COLUNA':<35} | {'EXEMPLO DE VALOR'}")
        print("-" * 85)
        
        for idx, col in enumerate(colunas):
            valor = str(amostra.get(col, "N/A"))
            # Limita o tamanho do texto do valor para não quebrar o layout
            valor_curto = (valor[:40] + '..') if len(valor) > 40 else valor
            print(f"[{idx:2}] | {col:<35} | {valor_curto}")

        print("-" * 85)
        print("Digite os números separados por vírgula | [p] Pular | [s] Sair")
        entrada = input(f"Seleção: ").strip().lower()

        if entrada == 's': break
        if entrada in ['p', '']: continue

        # Processamento e Salvamento
        indices = [int(x.strip()) for x in entrada.split(',')]
        colunas_escolhidas = [colunas[idx] for idx in indices]

        try:
            df_full = pd.read_csv(caminho_arq)
        except UnicodeDecodeError:
            df_full = pd.read_csv(caminho_arq, encoding='latin1')

        df_filtrado = df_full[colunas_escolhidas].copy()
        df_filtrado.to_csv(nome_saida, index=False)
        
        print(f"✅ Salvo: {nome_saida.name} ({len(colunas_escolhidas)} colunas)")

    except Exception as e:
        print(f"❌ Erro: {e}")
        continue

print(f"\n✨ Processamento finalizado!")