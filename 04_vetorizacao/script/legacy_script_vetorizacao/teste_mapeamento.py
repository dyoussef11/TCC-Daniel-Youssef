#!/usr/bin/env python3
"""
teste_mapeamento.py
Script para testar o mapeamento de nomes de modelos a partir do CSV e dos arquivos NER.
"""

import json
import pandas as pd
from pathlib import Path

from core.paths import DATASET_FINAL_CSV, NER_DATA

# ============================================================================
# CONFIGURAÇÕES
# ============================================================================

# Caminho do CSV com mapeamento
CAMINHO_CSV = Path(DATASET_FINAL_CSV /"dataset_laptops_UNICOS_V10.csv") 

# Diretório com arquivos NER (ajuste conforme sua estrutura)
DIR_NER = Path(NER_DATA / "Base_Conhecimento_ResumidaV13_VERIFICADA")  # ou o caminho correto

# ============================================================================
# FUNÇÕES DE MApeAMENTO
# ============================================================================

def carregar_mapeamento_por_modelo_limpo(csv_path: Path) -> dict:
    """Carrega CSV e retorna dicionário: modelo_limpo -> nome completo com marca."""
    if not csv_path.exists():
        print(f"⚠️ Arquivo CSV não encontrado em {csv_path}. Usando fallback.")
        return {}
    df = pd.read_csv(csv_path)
    mapa = {}
    for _, row in df.iterrows():
        modelo_limpo = str(row['modelo_limpo']).strip()
        marca = str(row['marca']).strip()
        if not modelo_limpo or modelo_limpo == 'nan':
            continue
        # Verifica se a marca já está presente no modelo_limpo
        if marca.lower() in modelo_limpo.lower():
            nome_completo = modelo_limpo
        else:
            nome_completo = f"{marca} {modelo_limpo}"
        # Remove múltiplos espaços
        nome_completo = ' '.join(nome_completo.split())
        mapa[modelo_limpo] = nome_completo
    return mapa

def obter_nome_modelo(modelo_original: str, modelo_generico: str, marca_arquivo: str,
                       mapa_por_modelo_limpo: dict) -> str:
    """
    Retorna o nome do modelo pronto para embedding.
    Prioridades:
      1. modelo_generico (se não for 'na' ou vazio) – já pode conter a marca
      2. mapa_por_modelo_limpo usando modelo_original como chave (caso coincida com modelo_limpo)
      3. modelo_original com marca_arquivo adicionada (se não contiver a marca)
      4. fallback: modelo_original limpo
    """
    # Se modelo_generico existe e não é 'na' ou vazio, usa ele
    if modelo_generico and modelo_generico.lower() != 'na':
        # Substitui underscores por espaços e capitaliza
        nome = modelo_generico.replace('_', ' ').title()
        # Se a marca do arquivo não estiver no nome, adiciona
        if marca_arquivo and marca_arquivo.lower() not in nome.lower():
            nome = f"{marca_arquivo.title()} {nome}"
        return ' '.join(nome.split())
    
    # Tenta mapear via modelo_original (que geralmente é igual ao modelo_limpo)
    if modelo_original in mapa_por_modelo_limpo:
        return mapa_por_modelo_limpo[modelo_original]
    
    # Fallback: usa modelo_original e adiciona a marca se necessário
    nome_base = modelo_original.replace('_', ' ').title()
    if marca_arquivo and marca_arquivo.lower() not in nome_base.lower():
        nome_base = f"{marca_arquivo.title()} {nome_base}"
    return ' '.join(nome_base.split())

# ============================================================================
# TESTE
# ============================================================================

def testar_mapeamento():
    print("=" * 70)
    print("🧪 TESTE DE MAPEAMENTO DE NOMES DE MODELOS")
    print("=" * 70)
    
    # Carrega o mapeamento
    mapa = carregar_mapeamento_por_modelo_limpo(CAMINHO_CSV)
    print(f"📊 Mapeamento carregado: {len(mapa)} entradas.")
    print("-" * 70)
    
    # Lista alguns modelos para teste (pega os primeiros 10 do CSV para demonstrar)
    print("📋 EXEMPLOS DO MAPEAMENTO (primeiros 10):")
    for i, (key, value) in enumerate(list(mapa.items())[:10]):
        print(f"  {i+1:2}. {key} -> {value}")
    print("-" * 70)
    
    # Agora testa com arquivos NER reais (se existirem)
    if DIR_NER.exists():
        arquivos = list(DIR_NER.glob("NER_*.json"))
        print(f"📁 Encontrados {len(arquivos)} arquivos NER em {DIR_NER}")
        # Pega alguns arquivos para teste (até 10)
        for arq in arquivos[:10]:
            try:
                with open(arq, 'r', encoding='utf-8') as f:
                    dados = json.load(f)
                modelo_original = dados.get('modelo_original', '')
                modelo_generico = dados.get('modelo_generico', '')
                # Extrai marca do nome do arquivo
                nome_arquivo = arq.stem
                partes = nome_arquivo.split('_')
                marca_arquivo = partes[1] if len(partes) > 1 else ''
                if marca_arquivo.lower() == 'na' and modelo_generico:
                    if '_' in modelo_generico:
                        marca_arquivo = modelo_generico.split('_')[0]
                
                nome_tratado = obter_nome_modelo(
                    modelo_original=modelo_original,
                    modelo_generico=modelo_generico,
                    marca_arquivo=marca_arquivo,
                    mapa_por_modelo_limpo=mapa
                )
                print(f"📄 Arquivo: {arq.name}")
                print(f"   modelo_original: {modelo_original}")
                print(f"   modelo_generico: {modelo_generico}")
                print(f"   marca_arquivo: {marca_arquivo}")
                print(f"   ✅ Nome tratado: {nome_tratado}")
                print("-" * 40)
            except Exception as e:
                print(f"❌ Erro ao processar {arq.name}: {e}")
    else:
        print("⚠️ Diretório NER não encontrado. Testando apenas com exemplos manuais.")
        # Testa alguns casos manuais conhecidos
        casos = [
            {"modelo_original": "g15_5530_15_2023", "modelo_generico": "", "marca_arquivo": "dell"},
            {"modelo_original": "15_fc0028au", "modelo_generico": "hp_fc0028au", "marca_arquivo": "hp"},
            {"modelo_original": "an515_58", "modelo_generico": "acer_nitro_5", "marca_arquivo": "acer"},
            {"modelo_original": "v15_g4", "modelo_generico": "lenovo_v15", "marca_arquivo": "lenovo"},
            {"modelo_original": "modelo_inexistente", "modelo_generico": "", "marca_arquivo": "marca_x"},
        ]
        for caso in casos:
            nome = obter_nome_modelo(
                modelo_original=caso["modelo_original"],
                modelo_generico=caso["modelo_generico"],
                marca_arquivo=caso["marca_arquivo"],
                mapa_por_modelo_limpo=mapa
            )
            print(f"Original: {caso['modelo_original']} -> Tratado: {nome}")
    
    print("\n✅ Teste concluído.")

if __name__ == "__main__":
    testar_mapeamento()