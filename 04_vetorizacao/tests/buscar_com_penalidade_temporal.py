#!/usr/bin/env python3
"""
buscar_com_penalidade_temporal.py
Para cada pergunta do dataset_avaliacaoV4, recupera os documentos mais similares
aplicando penalidade temporal (prioriza documentos mais recentes).
Exibe distância original, penalizada, gap temporal e preview com modelo|summary|data.
Salva resultados em CSV e JSON.
"""

import json
import sys
from pathlib import Path
from typing import List, Dict, Tuple, Optional
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

OUTPUT_DIR = Path(VETORIZATION_TESTS / "resultados_semanticos_temporais")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

OLLAMA_URL = "http://localhost:11434/api/embeddings"
MODEL_NAME = "bge-m3:latest"
TOP_K = 10                     # buscar mais para depois reordenar
FINAL_K = 5                    # quantos retornar após penalidade
SLEEP_BETWEEN_QUERIES = 0.5

# Parâmetros da penalidade temporal (mesmos do RAG_Temporal_V9_3)
YEARLY_PENALTY_RATE = 0.04     # 4% ao ano
REFERENCE_DATE_DEFAULT = "2026-06-23"

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
# FUNÇÃO DE PENALIDADE TEMPORAL
# ============================================================================

def calcular_gap_temporal(doc_date: str, ref_date: datetime) -> float:
    """Retorna diferença em anos (positivo se documento é mais antigo)."""
    try:
        doc_dt = datetime.strptime(doc_date[:10], "%Y-%m-%d")
        return (ref_date - doc_dt).days / 365.25
    except (ValueError, IndexError):
        return 0.0

def aplicar_penalidade(semantic_distance: float, temporal_gap: float) -> Tuple[float, float]:
    """
    Retorna (distancia_penalizada, penalidade_aplicada).
    Penalidade = 1 + gap * YEARLY_PENALTY_RATE
    """
    if temporal_gap <= 0:
        return semantic_distance, 0.0
    penalidade = 1.0 + (temporal_gap * YEARLY_PENALTY_RATE)
    return semantic_distance * penalidade, penalidade - 1.0

# ============================================================================
# BUSCA COM REORDENAÇÃO TEMPORAL
# ============================================================================

def buscar_com_penalidade(query: str, ref_date: datetime,
                          index: faiss.Index, metadados: List[Dict],
                          top_k: int = TOP_K, final_k: int = FINAL_K) -> List[Dict]:
    """
    Recupera documentos, calcula distância penalizada e retorna os final_k melhores.
    Cada resultado é um dicionário com chaves:
      rank, distancia_original, distancia_penalizada, temporal_gap_years, penalty_applied,
      doc_id, data_original, modelo, summary, preview, data_post_original
    """
    vec = gerar_embedding(query)
    vec = vec.reshape(1, -1)
    distances, indices = index.search(vec, top_k)

    resultados = []
    for i, idx in enumerate(indices[0]):
        if idx == -1:
            continue
        distancia_orig = float(distances[0][i])
        meta_doc = metadados[idx]
        metadata = meta_doc.get('metadata', {})
        # Prioriza data_post_original, senão date_iso
        data_post = metadata.get('data_post_original', meta_doc.get('date_iso', '2024-01-01'))
        gap = calcular_gap_temporal(data_post, ref_date)
        dist_penal, penalty = aplicar_penalidade(distancia_orig, gap)

        modelo = metadata.get('model', 'N/A')
        summary = metadata.get('summary', 'Sem resumo')
        preview = f"{modelo} | {summary} | {data_post}"

        resultados.append({
            "distancia_original": round(distancia_orig, 4),
            "distancia_penalizada": round(dist_penal, 4),
            "temporal_gap_years": round(gap, 2),
            "penalty_applied": round(penalty, 4),
            "doc_id": str(meta_doc.get('id', 'N/A')),
            "data_original": str(meta_doc.get('date_iso', 'N/A')),
            "data_post_original": str(data_post),
            "modelo": modelo,
            "summary": summary,
            "preview": preview,
            "original_text": str(meta_doc.get('original_text', '')),
        })

    # Ordena pela distância penalizada (menor é melhor)
    resultados.sort(key=lambda x: x["distancia_penalizada"])
    # Retorna os final_k primeiros
    for rank, r in enumerate(resultados[:final_k], start=1):
        r["rank"] = rank
    return resultados[:final_k]

# ============================================================================
# PROCESSAMENTO PRINCIPAL
# ============================================================================

def processar_perguntas(perguntas: List[Dict], index: faiss.Index, metadados: List[Dict]) -> List[Dict]:
    registros = []
    total = len(perguntas)

    for i, tc in enumerate(perguntas, start=1):
        query = tc["input"]
        pergunta_id = tc.get("id", f"P_{i}")
        # Data de referência: usa a do dataset ou padrão
        ref_date_str = tc.get("reference_date", REFERENCE_DATE_DEFAULT)
        ref_date = datetime.strptime(ref_date_str, "%Y-%m-%d")
        print(f"\n🔍 {i}/{total}: {query[:60]}... (ref: {ref_date_str})")

        try:
            resultados = buscar_com_penalidade(query, ref_date, index, metadados)
            if not resultados:
                print("   ⚠️ Nenhum documento recuperado.")
                registros.append({
                    "pergunta_id": pergunta_id,
                    "pergunta": query,
                    "reference_date": ref_date_str,
                    "rank": None,
                    "distancia_original": None,
                    "distancia_penalizada": None,
                    "temporal_gap_years": None,
                    "penalty_applied": None,
                    "doc_id": None,
                    "data_original": None,
                    "data_post_original": None,
                    "modelo": None,
                    "summary": None,
                    "preview": None,
                    "original_text": None,
                    "erro": "Nenhum documento encontrado"
                })
            else:
                for r in resultados:
                    registros.append({
                        "pergunta_id": pergunta_id,
                        "pergunta": query,
                        "reference_date": ref_date_str,
                        "rank": r["rank"],
                        "distancia_original": r["distancia_original"],
                        "distancia_penalizada": r["distancia_penalizada"],
                        "temporal_gap_years": r["temporal_gap_years"],
                        "penalty_applied": r["penalty_applied"],
                        "doc_id": r["doc_id"],
                        "data_original": r["data_original"],
                        "data_post_original": r["data_post_original"],
                        "modelo": r["modelo"],
                        "summary": r["summary"],
                        "preview": r["preview"],
                        "original_text": r["original_text"],
                        "erro": None
                    })
                print(f"   ✅ Recuperados {len(resultados)} documentos (reordenados temporalmente).")
        except Exception as e:
            print(f"   ❌ Erro: {e}")
            registros.append({
                "pergunta_id": pergunta_id,
                "pergunta": query,
                "reference_date": ref_date_str,
                "rank": None,
                "distancia_original": None,
                "distancia_penalizada": None,
                "temporal_gap_years": None,
                "penalty_applied": None,
                "doc_id": None,
                "data_original": None,
                "data_post_original": None,
                "modelo": None,
                "summary": None,
                "preview": None,
                "original_text": None,
                "erro": str(e)
            })

        if i < total:
            time.sleep(SLEEP_BETWEEN_QUERIES)

    return registros

# ============================================================================
# SALVAMENTO
# ============================================================================

def salvar_resultados(registros: List[Dict], output_dir: Path):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    df = pd.DataFrame(registros)
    # Colunas para o CSV (ordem amigável)
    cols = [
        "pergunta_id", "pergunta", "reference_date",
        "rank", "distancia_original", "distancia_penalizada",
        "temporal_gap_years", "penalty_applied",
        "doc_id", "data_original", "data_post_original",
        "modelo", "summary", "preview", "erro"
    ]
    df_csv = df[cols].copy()
    csv_path = output_dir / f"resultados_busca_temporal_{timestamp}.csv"
    df_csv.to_csv(csv_path, index=False, encoding='utf-8-sig')
    print(f"✅ CSV salvo em: {csv_path}")

    # JSON completo (inclui original_text)
    json_path = output_dir / f"resultados_busca_temporal_{timestamp}.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(registros, f, ensure_ascii=False, indent=2)
    print(f"✅ JSON salvo em: {json_path}")

    # Resumo
    txt_path = output_dir / f"resumo_busca_temporal_{timestamp}.txt"
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write("="*80 + "\n")
        f.write(f"RESUMO DA BUSCA SEMÂNTICA COM PENALIDADE TEMPORAL - {timestamp}\n")
        f.write("="*80 + "\n")
        f.write(f"Total de perguntas: {len(set(r['pergunta_id'] for r in registros))}\n")
        f.write(f"Total de registros (incluindo vazios): {len(registros)}\n")
        perguntas_com_resultado = set()
        for r in registros:
            if r['rank'] is not None and r['rank'] == 1:
                perguntas_com_resultado.add(r['pergunta_id'])
        f.write(f"Perguntas com pelo menos 1 documento recuperado: {len(perguntas_com_resultado)}\n")
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

    perguntas = [tc for tc in TEST_SUITE if "input" in tc]
    print(f"\n📋 Total de perguntas no dataset: {len(perguntas)}")

    registros = processar_perguntas(perguntas, index, metadados)
    salvar_resultados(registros, OUTPUT_DIR)

    print("\n✅ Busca com penalidade temporal concluída.")
    print(f"📂 Resultados salvos em: {OUTPUT_DIR}")

if __name__ == "__main__":
    main()