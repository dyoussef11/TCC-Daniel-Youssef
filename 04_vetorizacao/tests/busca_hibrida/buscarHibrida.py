#!/usr/bin/env python3
"""
buscar.py - Busca híbrida (densa + esparsa) na base vetorial gerada com BGE-M3
Uso:
    python buscar.py --consulta "texto" [--peso_denso 0.6] [--peso_esparso 0.4] [--k 5] [--saida resultados.json]
"""

import json
import sys
import argparse
from pathlib import Path

import numpy as np
import faiss
from ollama import Client
from rank_bm25 import BM25Okapi

from core.paths import VETORIZATION_DATA

# =============================================================================
# CONFIGURAÇÕES PADRÃO (podem ser sobrescritas por argumentos)
# =============================================================================
CONSULTA = "What was the maximum RAM capacity of the Dell G15 5530 in March 2024?"
K_RESULTADOS = 5
MODELO_EMBEDDING = "bge-m3:latest"
PESO_DENSO = 0.6
PESO_ESPARSO = 0.4
CAMINHO_BASE = VETORIZATION_DATA / "base_conhecimento_multilingueV9"
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
    corpus = [meta['original_text'].lower().split() for meta in metadados]
    bm25 = BM25Okapi(corpus)
    return bm25

def buscar_bm25(bm25, consulta: str, k: int):
    tokens = consulta.lower().split()
    scores = bm25.get_scores(tokens)
    top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
    return [(idx, scores[idx]) for idx in top_indices]

def combinar_resultados(resultados_densos, resultados_esparsos, k, peso_denso, peso_esparso):
    scores_finais = {}
    for r in resultados_densos:
        idx = r['id']
        scores_finais[idx] = peso_denso * r['similaridade']
    if resultados_esparsos:
        max_score = max(score for _, score in resultados_esparsos)
        if max_score > 0:
            for idx, score in resultados_esparsos:
                norm_score = score / max_score
                if idx in scores_finais:
                    scores_finais[idx] += peso_esparso * norm_score
                else:
                    scores_finais[idx] = peso_esparso * norm_score
    ids_ordenados = sorted(scores_finais.keys(), key=lambda idx: scores_finais[idx], reverse=True)
    return ids_ordenados[:k]

def main():
    parser = argparse.ArgumentParser(description="Busca híbrida com BGE-M3 + BM25")
    parser.add_argument('--consulta', type=str, default=CONSULTA,
                        help='Consulta a ser buscada')
    parser.add_argument('--peso_denso', type=float, default=PESO_DENSO,
                        help='Peso da busca densa (FAISS)')
    parser.add_argument('--peso_esparso', type=float, default=PESO_ESPARSO,
                        help='Peso da busca esparsa (BM25)')
    parser.add_argument('--k', type=int, default=K_RESULTADOS,
                        help='Número de resultados a retornar')
    parser.add_argument('--saida', type=str, default=None,
                        help='Arquivo JSON para salvar os resultados (opcional)')
    parser.add_argument('--quiet', action='store_true',
                        help='Não exibe saída no console (útil para testes)')
    args = parser.parse_args()

    # Força a saída padrão para UTF-8 no Windows
    if sys.platform == 'win32':
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

    # Sobrescreve configurações
    consulta = args.consulta
    k = args.k
    peso_denso = args.peso_denso
    peso_esparso = args.peso_esparso
    saida = args.saida
    quiet = args.quiet

    if not quiet:
        print(f"🔍 Buscando por: '{consulta}'")
        print(f"   Pesos: denso={peso_denso}, esparso={peso_esparso}")

    try:
        index, metadados = carregar_base(CAMINHO_BASE)
    except Exception as e:
        print(f"❌ Erro ao carregar base: {e}")
        sys.exit(1)

    if not quiet:
        print("🔄 Construindo índice BM25...")
    bm25 = construir_bm25_index(metadados)
    if not quiet:
        print("✅ Índice BM25 construído.")

    # Busca densa
    k_denso = k * 2
    emb_consulta = obter_embedding(consulta, MODELO_EMBEDDING)
    distancias, indices = index.search(emb_consulta, k_denso)

    resultados_densos = []
    for dist, idx in zip(distancias[0], indices[0]):
        if idx == -1:
            continue
        similaridade = 1 / (1 + float(dist))
        resultados_densos.append({
            'id': idx,
            'distancia': float(dist),
            'similaridade': similaridade,
            'metadata': metadados[idx]
        })

    # Busca esparsa
    k_esparso = k * 2
    resultados_esparsos = buscar_bm25(bm25, consulta, k_esparso)

    # Combinação
    ids_finais = combinar_resultados(resultados_densos, resultados_esparsos, k, peso_denso, peso_esparso)

    # Montagem dos resultados finais
    resultados_finais = []
    for idx in ids_finais:
        meta = metadados[idx]
        denso = next((r for r in resultados_densos if r['id'] == idx), None)
        if denso:
            similaridade = denso['similaridade']
            distancia = denso['distancia']
        else:
            similaridade = 0.0
            distancia = float('inf')
        resultados_finais.append({
            'id': meta.get('id', str(idx)),
            'distancia': distancia,
            'similaridade': similaridade,
            'texto': meta['original_text'][:200] + "...",
            'metadata': meta['metadata'],
            # 'data_post_original': meta['data_post_original']
            
        })

    # Se pediu para salvar, grava JSON
    if saida:
        with open(saida, 'w', encoding='utf-8') as f:
            json.dump(resultados_finais, f, ensure_ascii=False, indent=2)
        if not quiet:
            print(f"✅ Resultados salvos em {saida}")

    # Se não for quiet, exibe na tela
    if not quiet:
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