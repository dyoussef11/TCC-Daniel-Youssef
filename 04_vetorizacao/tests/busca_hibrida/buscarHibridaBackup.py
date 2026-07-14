#!/usr/bin/env python3
"""
buscar.py - Busca híbrida (densa + esparsa) na base vetorial gerada com BGE-M3
Uso: configure a variável CONSULTA abaixo e execute diretamente.
"""

import json
import sys
from pathlib import Path

import numpy as np
import faiss
from ollama import Client
from rank_bm25 import BM25Okapi

# =============================================================================
# CONFIGURAÇÕES (altere aqui a consulta e parâmetros)
# =============================================================================
CONSULTA = "What was the maximum RAM capacity of the Dell G15 5530 in March 2024?"   # <-- ALTERE AQUI A CONSULTA
K_RESULTADOS = 5
MODELO_EMBEDDING = "bge-m3:latest"

# Pesos para a fusão (ajuste conforme necessidade)
PESO_DENSO = 0.6
PESO_ESPARSO = 0.4

# Caminho base: assume que o script está em 04_vetorizacao/script/
# e os arquivos estão em 04_vetorizacao/data/
CAMINHO_BASE = Path(__file__).parent.parent / "data" / "base_conhecimento_multilingueV9"
# =============================================================================

def carregar_base(caminho_base: Path):
    faiss_path = caminho_base.with_suffix(".faiss")
    meta_path = caminho_base.with_suffix(".meta.json")

    if not faiss_path.exists():
        raise FileNotFoundError(f"Arquivo FAISS não encontrado: {faiss_path}")
    if not meta_path.exists():
        raise FileNotFoundError(f"Arquivo de metadados não encontrado: {meta_path}")

    index = faiss.read_index(str(faiss_path))
    with open(meta_path, 'r', encoding='utf-8') as f:
        metadados = json.load(f)

    print(f"✅ Base carregada: {index.ntotal} vetores, dimensão {index.d}")
    return index, metadados

def obter_embedding(consulta: str, modelo: str) -> np.ndarray:
    client = Client(host='http://localhost:11434')
    try:
        response = client.embeddings(model=modelo, prompt=consulta)
        embedding = np.array(response['embedding'], dtype=np.float32).reshape(1, -1)
        return embedding
    except Exception as e:
        print(f"❌ Erro ao obter embedding: {e}")
        sys.exit(1)

def construir_bm25_index(metadados):
    """
    Constrói um índice BM25 a partir do campo 'original_text' de cada metadado.
    Tokenização simples: minúsculas e split por espaços.
    """
    corpus = [meta['original_text'].lower().split() for meta in metadados]
    bm25 = BM25Okapi(corpus)
    return bm25

def buscar_bm25(bm25, consulta: str, k: int):
    """
    Retorna os k índices do corpus com maior pontuação BM25 para a consulta.
    """
    tokens = consulta.lower().split()
    scores = bm25.get_scores(tokens)
    # Obtém os índices dos k melhores
    top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
    return [(idx, scores[idx]) for idx in top_indices]

def combinar_resultados(resultados_densos, resultados_esparsos, k, peso_denso, peso_esparso):
    """
    Combina os resultados densos (lista de dicionários com 'id'=índice e 'similaridade')
    e esparsos (lista de tuplas (índice, score_bm25)) usando média ponderada normalizada.
    Retorna os k índices finais ordenados por pontuação combinada.
    """
    scores_finais = {}

    # 1. Adiciona contribuição densa (já normalizada)
    for r in resultados_densos:
        idx = r['id']  # índice no metadados
        scores_finais[idx] = peso_denso * r['similaridade']

    # 2. Adiciona contribuição esparsa (normaliza pelo máximo)
    if resultados_esparsos:
        max_score = max(score for _, score in resultados_esparsos)
        if max_score > 0:
            for idx, score in resultados_esparsos:
                norm_score = score / max_score
                if idx in scores_finais:
                    scores_finais[idx] += peso_esparso * norm_score
                else:
                    scores_finais[idx] = peso_esparso * norm_score

    # 3. Ordena e retorna os k melhores
    ids_ordenados = sorted(scores_finais.keys(), key=lambda idx: scores_finais[idx], reverse=True)
    return ids_ordenados[:k]

def main():
    print(f"🔍 Buscando por: '{CONSULTA}'")
    try:
        index, metadados = carregar_base(CAMINHO_BASE)
    except Exception as e:
        print(f"❌ Erro ao carregar base: {e}")
        sys.exit(1)

    # --- Construção do índice BM25 (esparso) ---
    print("🔄 Construindo índice BM25...")
    bm25 = construir_bm25_index(metadados)
    print("✅ Índice BM25 construído.")

    # --- 1. Busca densa (FAISS) ---
    # Buscar mais candidatos para ter material para a fusão
    k_denso = K_RESULTADOS * 2
    emb_consulta = obter_embedding(CONSULTA, MODELO_EMBEDDING)
    distancias, indices = index.search(emb_consulta, k_denso)

    resultados_densos = []
    for dist, idx in zip(distancias[0], indices[0]):
        if idx == -1:
            continue
        # Similaridade a partir da distância L2: 1/(1+dist)
        similaridade = 1 / (1 + float(dist))
        resultados_densos.append({
            'id': idx,  # índice no metadados
            'distancia': float(dist),
            'similaridade': similaridade,
            'metadata': metadados[idx]
        })

    # --- 2. Busca esparsa (BM25) ---
    k_esparso = K_RESULTADOS * 2
    resultados_esparsos = buscar_bm25(bm25, CONSULTA, k_esparso)

    # --- 3. Combinação híbrida ---
    ids_finais = combinar_resultados(
        resultados_densos,
        resultados_esparsos,
        K_RESULTADOS,
        PESO_DENSO,
        PESO_ESPARSO
    )

    # --- 4. Montagem dos resultados finais para exibição ---
    resultados_finais = []
    for idx in ids_finais:
        meta = metadados[idx]
        # Encontra a distância/similaridade densa (se existir)
        denso = next((r for r in resultados_densos if r['id'] == idx), None)
        if denso:
            similaridade = denso['similaridade']
            distancia = denso['distancia']
        else:
            similaridade = 0.0
            distancia = float('inf')

        resultados_finais.append({
            'id': meta.get('id', str(idx)),   # mantém o ID original se existir
            'distancia': distancia,
            'similaridade': similaridade,
            'texto': meta['original_text'][:200] + "...",
            'metadata': meta['metadata']
        })

    if not resultados_finais:
        print("Nenhum resultado encontrado.")
        return

    print(f"\n📋 Top {len(resultados_finais)} resultados (híbrido denso + BM25):\n")
    for i, r in enumerate(resultados_finais, 1):
        print(f"{i}. ID: {r['id']}")
        print(f"   Similaridade (densa): {r['similaridade']:.4f} (distância: {r['distancia']:.4f})")
        print(f"   Modelo: {r['metadata'].get('model', 'N/A')}")
        print(f"   Data: {r['metadata'].get('data_post_original', 'N/A')}")
        print(f"   Resumo: {r['metadata'].get('summary', '')[:100]}...")
        print(f"   Texto: {r['texto']}")
        print("-" * 60)

if __name__ == "__main__":
    main()