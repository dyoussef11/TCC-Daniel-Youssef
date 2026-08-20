#!/usr/bin/env python3
"""
buscar_por_perguntas_dataset.py
Para cada pergunta do dataset_avaliacaoV4, recupera os 5 documentos mais similares da base vetorizada.
Exibe distância L2, ID, data, modelo, sumário e preview do texto.
Salva os resultados em CSV e JSON na pasta 04_vetorizacao/tests/resultados_sematicos/
"""

import json
import sys
from pathlib import Path
from typing import List, Dict, Tuple
from datetime import datetime
import time

import numpy as np
import faiss
import requests
import pandas as pd

# Importa o dataset de perguntas
from core.paths import AVALIACAO_SCRIPT, VETORIZATION_DATA, VETORIZATION_TESTS
sys.path.append(str(AVALIACAO_SCRIPT))
from dataset_avaliacaoV4 import TEST_SUITE

# ============================================================================
# CONFIGURAÇÃO
# ============================================================================
META_PATH = VETORIZATION_DATA /'base_vetorizada' / "base_conhecimento_multilingueV9.meta.json"
FAISS_PATH = VETORIZATION_DATA /'base_vetorizada' / "base_conhecimento_multilingueV9.faiss"

OUTPUT_DIR = Path(VETORIZATION_TESTS / "resultados_sematicos")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

OLLAMA_URL = "http://localhost:11434/api/embeddings"
MODEL_NAME = "bge-m3:latest"
TOP_K = 5
SLEEP_BETWEEN_QUERIES = 0.5  # segundos para não sobrecarregar o Ollama

# ============================================================================
# CARREGAMENTO DA BASE
# ============================================================================

def carregar_metadados() -> List[Dict]:
    if not META_PATH.exists():
        raise FileNotFoundError(f"❌ Metadados não encontrados: {META_PATH}")
    with open(META_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

def carregar_indice() -> faiss.Index:
    if not FAISS_PATH.exists():
        raise FileNotFoundError(f"❌ Índice FAISS não encontrado: {FAISS_PATH}")
    return faiss.read_index(str(FAISS_PATH))

# ============================================================================
# EMBEDDING VIA OLLAMA
# ============================================================================

def gerar_embedding(texto: str) -> np.ndarray:
    payload = {"model": MODEL_NAME, "prompt": texto}
    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        embedding = data.get("embedding")
        if embedding is None:
            raise ValueError("Resposta sem campo 'embedding'")
        return np.array(embedding, dtype=np.float32)
    except Exception as e:
        raise RuntimeError(f"Erro ao gerar embedding: {e}")

# ============================================================================
# BUSCA
# ============================================================================

def buscar(query: str, index: faiss.Index, metadados: List[Dict], k: int = TOP_K) -> List[Tuple[float, Dict]]:
    vec = gerar_embedding(query)
    vec = vec.reshape(1, -1)
    distances, indices = index.search(vec, k)
    resultados = []
    for i, idx in enumerate(indices[0]):
        if idx == -1:
            continue
        distancia = float(distances[0][i])  # converter para float nativo
        meta = metadados[idx]
        resultados.append((distancia, meta))
    return resultados

# ============================================================================
# EXIBIÇÃO E SALVAMENTO
# ============================================================================

def processar_perguntas(perguntas: List[Dict], index: faiss.Index, metadados: List[Dict]) -> List[Dict]:
    """
    Para cada pergunta, faz a busca e retorna uma lista de dicionários com resultados.
    """
    registros = []
    total = len(perguntas)

    for i, tc in enumerate(perguntas, start=1):
        query = tc["input"]
        pergunta_id = tc.get("id", f"P_{i}")
        print(f"\n🔍 Processando {i}/{total}: {query[:60]}...")

        try:
            resultados = buscar(query, index, metadados, k=TOP_K)
            if not resultados:
                print("   ⚠️ Nenhum documento recuperado.")
                registros.append({
                    "pergunta_id": pergunta_id,
                    "pergunta": query,
                    "rank": None,
                    "distancia": None,
                    "doc_id": None,
                    "data_original": None,
                    "modelo": None,
                    "summary": None,
                    "preview": None,
                    "original_text": None,
                    "erro": "Nenhum documento encontrado"
                })
            else:
                for rank, (dist, meta_reg) in enumerate(resultados, start=1):
                    meta = meta_reg.get('metadata', {})
                    registros.append({
                        "pergunta_id": pergunta_id,
                        "pergunta": query,
                        "rank": rank,
                        "distancia": round(dist, 4),  # já é float
                        "doc_id": str(meta_reg.get('id', 'N/A')),
                        "data_original": str(meta.get('data_post_original', 'N/A')),
                        "modelo": str(meta.get('model', 'N/A')),
                        "summary": str(meta.get('summary', 'Sem resumo')),
                        "preview": str(meta_reg.get('original_text', '')[:300].replace('\n', ' ')),
                        "original_text": str(meta_reg.get('original_text', '')),
                        "erro": None
                    })
                print(f"   ✅ Recuperados {len(resultados)} documentos.")
        except Exception as e:
            print(f"   ❌ Erro: {e}")
            registros.append({
                "pergunta_id": pergunta_id,
                "pergunta": query,
                "rank": None,
                "distancia": None,
                "doc_id": None,
                "data_original": None,
                "modelo": None,
                "summary": None,
                "preview": None,
                "original_text": None,
                "erro": str(e)
            })

        # Pausa para não sobrecarregar
        if i < total:
            time.sleep(SLEEP_BETWEEN_QUERIES)

    return registros

def salvar_resultados(registros: List[Dict], output_dir: Path):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # 1. Salvar CSV (apenas campos principais)
    df = pd.DataFrame(registros)
    # Seleciona colunas para o CSV
    cols = ["pergunta_id", "pergunta", "rank", "distancia", "doc_id", "data_original", "modelo", "summary", "preview"]
    df_csv = df[cols].copy()
    csv_path = output_dir / f"resultados_busca_{timestamp}.csv"
    df_csv.to_csv(csv_path, index=False, encoding='utf-8-sig')
    print(f"✅ CSV salvo em: {csv_path}")

    # 2. Salvar JSON completo (inclui texto original)
    json_path = output_dir / f"resultados_busca_{timestamp}.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(registros, f, ensure_ascii=False, indent=2)
    print(f"✅ JSON salvo em: {json_path}")

    # 3. Gerar estatísticas resumidas em TXT
    txt_path = output_dir / f"resumo_busca_{timestamp}.txt"
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write("="*80 + "\n")
        f.write(f"RESUMO DA BUSCA SEMÂNTICA - {timestamp}\n")
        f.write("="*80 + "\n")
        f.write(f"Total de perguntas: {len(set(r['pergunta_id'] for r in registros))}\n")
        f.write(f"Total de registros (incluindo vazios): {len(registros)}\n")
        # Contar quantas perguntas tiveram pelo menos um resultado
        perguntas_com_resultado = set()
        for r in registros:
            if r['rank'] is not None and r['rank'] == 1:
                perguntas_com_resultado.add(r['pergunta_id'])
        f.write(f"Perguntas com pelo menos 1 documento recuperado: {len(perguntas_com_resultado)}\n")
        
        # Listar perguntas sem resultados
        ids_com_resultado = {r['pergunta_id'] for r in registros if r['rank'] is not None}
        all_ids = {r['pergunta_id'] for r in registros}
        sem_resultado = all_ids - ids_com_resultado
        if sem_resultado:
            f.write("\nPerguntas sem nenhum documento recuperado:\n")
            for pid in sem_resultado:
                pergunta = next((r['pergunta'] for r in registros if r['pergunta_id'] == pid), pid)
                f.write(f"  - {pid}: {pergunta}\n")
    print(f"✅ Resumo salvo em: {txt_path}")

# ============================================================================
# MAIN
# ============================================================================

def main():
    print("🚀 Carregando base vetorizada...")
    try:
        metadados = carregar_metadados()
        index = carregar_indice()
        print(f"✅ Base carregada: {len(metadados)} registros, dimensão {index.d}")
    except Exception as e:
        print(f"❌ Erro ao carregar base: {e}")
        return

    # Filtra apenas perguntas que têm o campo "input"
    perguntas = [tc for tc in TEST_SUITE if "input" in tc]
    total = len(perguntas)
    print(f"\n📋 Total de perguntas no dataset: {total}")

    registros = processar_perguntas(perguntas, index, metadados)

    # Salvar resultados
    salvar_resultados(registros, OUTPUT_DIR)

    print("\n✅ Busca concluída para todas as perguntas.")
    print(f"📂 Resultados salvos em: {OUTPUT_DIR}")

if __name__ == "__main__":
    main()