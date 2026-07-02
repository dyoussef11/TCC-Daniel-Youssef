#!/usr/bin/env python3
"""
buscar_na_base_vetorizada_ollama.py
Busca semântica usando o modelo BGE-M3 via Ollama (mesmo usado na vetorização).
Requer Ollama rodando localmente (http://localhost:11434).
"""

import json
import numpy as np
import faiss
import requests
from pathlib import Path
from typing import List, Dict, Tuple

# ============================================================================
# CONFIGURAÇÃO DOS CAMINHOS
# ============================================================================
BASE_DIR = Path("04_vetorizacao/data")
META_PATH = BASE_DIR / "base_conhecimento_multilingueV9.meta.json"
FAISS_PATH = BASE_DIR / "base_conhecimento_multilingueV9.faiss"

# OLLAMA_URL = "http://localhost:11434"
OLLAMA_URL = "http://localhost:11434/api/embeddings"
MODEL_NAME = "bge-m3:latest"

# ============================================================================
# CARREGAMENTO DOS DADOS
# ============================================================================

def carregar_metadados() -> List[Dict]:
    if not META_PATH.exists():
        raise FileNotFoundError(f"❌ Metadados não encontrados: {META_PATH}")
    with open(META_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

def carregar_indice_faiss() -> faiss.Index:
    if not FAISS_PATH.exists():
        raise FileNotFoundError(f"❌ Índice FAISS não encontrado: {FAISS_PATH}")
    return faiss.read_index(str(FAISS_PATH))

def gerar_embedding_ollama(texto: str) -> np.ndarray:
    """
    Envia o texto para o Ollama e retorna o embedding como array numpy float32.
    """
    payload = {
        "model": MODEL_NAME,
        "prompt": texto
    }
    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        embedding = data.get("embedding")
        if embedding is None:
            raise ValueError("Resposta do Ollama sem campo 'embedding'")
        return np.array(embedding, dtype=np.float32)
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Erro ao chamar Ollama: {e}")

# ============================================================================
# FUNÇÃO DE BUSCA
# ============================================================================

def buscar(
    query: str,
    index: faiss.Index,
    metadados: List[Dict],
    top_k: int = 5
) -> List[Tuple[float, Dict]]:
    """
    Busca os top_k posts mais similares à query.
    """
    # 1. Obtém embedding da query via Ollama
    query_vec = gerar_embedding_ollama(query)
    query_vec = query_vec.reshape(1, -1)  # FAISS espera (n, dim)

    # 2. Busca no índice
    distances, indices = index.search(query_vec, top_k)

    # 3. Monta resultados
    resultados = []
    for i, idx in enumerate(indices[0]):
        if idx == -1:
            continue
        distancia = distances[0][i]
        meta = metadados[idx]
        resultados.append((distancia, meta))
    return resultados

# ============================================================================
# EXIBIÇÃO
# ============================================================================

def exibir_resultados(resultados: List[Tuple[float, Dict]], query: str):
    print("\n" + "=" * 80)
    print(f"🔍 RESULTADOS DA BUSCA PARA: \"{query}\"")
    print("=" * 80)

    if not resultados:
        print("Nenhum resultado encontrado.")
        return

    for rank, (distancia, meta_registro) in enumerate(resultados, start=1):
        meta = meta_registro.get('metadata', {})
        registro_id = meta_registro.get('id', 'ID Desconhecido')
        data_original = meta.get('data_post_original', 'Data não informada')
        modelo = meta.get('model', 'Modelo não informado')
        summary = meta.get('summary', 'Sem resumo')
        fault = meta.get('fault', 'Sem falha detectada')
        solucoes = meta.get('solutions', [])
        if isinstance(solucoes, list):
            solucoes_str = "; ".join(solucoes[:2])
        else:
            solucoes_str = str(solucoes)

        texto_original = meta_registro.get('original_text', '')
        preview = texto_original[:400].replace('\n', ' ') + ("..." if len(texto_original) > 400 else "")

        print(f"\n📌 RESULTADO #{rank} (Distância L2: {distancia:.4f} — quanto menor, mais similar)")
        print(f"   🏷️  ID do Post   : {registro_id}")
        print(f"   📅 Data Original: {data_original}")
        print(f"   💻 Modelo       : {modelo}")
        print(f"   📝 Resumo       : {summary}")
        print(f"   ⚠️  Falha        : {fault}")
        print(f"   🛠️  Soluções     : {solucoes_str}")
        print(f"   📄 Preview do texto embedado: {preview}")
        print("   " + "-" * 60)

# ============================================================================
# EXECUÇÃO PRINCIPAL
# ============================================================================

def main():
    try:
        metadados = carregar_metadados()
        index = carregar_indice_faiss()
        print(f"✅ Base carregada: {len(metadados)} registros.")
        print(f"📐 Dimensão dos vetores: {index.d}")

        # query_teste = "Compare battery life of Lenovo Legion 5 15ACH6 vs HP Victus 16-e0055dx"
        query_teste = "HP Victus 16-e0055dx"


        print(f"\n⏳ Buscando por: \"{query_teste}\"...")

        resultados = buscar(query_teste, index, metadados, top_k=5)
        exibir_resultados(resultados, query_teste)

    except FileNotFoundError as e:
        print(e)
        print("⚠️ Verifique se os arquivos .faiss e .meta.json estão no caminho correto.")
    except Exception as e:
        print(f"❌ Erro inesperado: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()