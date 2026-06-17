#!/usr/bin/env python3
"""
precompute_cacheV2.py - Pré‑computa embeddings para todas as queries do dataset.
Usa cliente direto do Ollama (CPU) e carrega as classes de cache do avaliador
via importlib.util (suporta nomes com ponto).
"""

import asyncio
import os
import sys
from pathlib import Path
from tqdm import tqdm
import numpy as np
from ollama import Client, ResponseError

# -----------------------------------------------------------------------------
# Carrega dinamicamente o módulo do avaliador (mesma pasta)
# -----------------------------------------------------------------------------
AVALIADOR_PATH = Path(__file__).parent / "evaluate_deepval_unified_comparative_Repete_N_Modelos_10Vezes.py"
if not AVALIADOR_PATH.exists():
    # Tenta a versão V8.1 se existir
    AVALIADOR_PATH = Path(__file__).parent / "evaluate_deepval_unified_comparative_V8.1.py"

if not AVALIADOR_PATH.exists():
    print(f"❌ Arquivo do avaliador não encontrado.")
    sys.exit(1)

import importlib.util
spec = importlib.util.spec_from_file_location("evaluator_module", AVALIADOR_PATH)
evaluator_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluator_module)

EvalConfig = evaluator_module.EvalConfig
EmbeddingCache = evaluator_module.EmbeddingCache

# -----------------------------------------------------------------------------
# Carrega o dataset de testes (mesma pasta)
# -----------------------------------------------------------------------------
DATASET_PATH = Path(__file__).parent / "dataset_avaliacaoV4.py"
if not DATASET_PATH.exists():
    print(f"❌ Arquivo do dataset não encontrado: {DATASET_PATH}")
    sys.exit(1)

spec_ds = importlib.util.spec_from_file_location("dataset_module", DATASET_PATH)
dataset_module = importlib.util.module_from_spec(spec_ds)
spec_ds.loader.exec_module(dataset_module)
TEST_SUITE = dataset_module.TEST_SUITE

print(f"✅ Dataset carregado: {len(TEST_SUITE)} casos de teste.")

# -----------------------------------------------------------------------------
# Função de sanitização aprimorada
# -----------------------------------------------------------------------------
def _sanitize_query(q: str) -> str:
    """
    Limpa a query para evitar NaN no BGE-M3.
    Remove palavras problemáticas, isola SKUs e elimina números soltos.
    """
    import re
    
    # 1. Remove palavras que podem causar ambiguidade (comparativos, superlativos, conectivos)
    remove_words = r'\b(same|identical|equal|maximum|minimum|default|standard|typical|compare|comparison|versus|vs\.?|and slots as|slots as|have|has|does|did|what|which|when|where|why|how|is|are|was|were|for|with|without|from|to|of|the|a|an)\b'
    q_clean = re.sub(remove_words, ' ', q, flags=re.IGNORECASE)
    
    # 2. Substitui padrões de SKU conhecidos (ex: G15 5520 → G15 model 5520)
    # Inclui marcas comuns do seu dataset
    sku_patterns = [
        (r'(G15|Nitro 5|Legion 5|Dell G15|Dell G16|HP Victus|HP Omen|ASUS TUF|ROG Zephyrus|MSI Katana|MSI Sword|Lenovo LOQ|Acer Predator)\s+(\d{4})', r'\1 model \2'),
        (r'([A-Z]+\d+)-(\d+)', r'\1 model \2'),  # AN515-58 → AN515 model 58
        (r'(RTX|GTX|AMD|Intel)\s+(\d{4})', r'\1 model \2')
    ]
    for pattern, repl in sku_patterns:
        q_clean = re.sub(pattern, repl, q_clean, flags=re.IGNORECASE)
    
    # 3. Remove números isolados (ex: 2024, 2025, 32GB, 512GB, etc.)
    # Mas preserva números que fazem parte de modelos (já substituídos)
    q_clean = re.sub(r'\b\d+\b', '', q_clean)
    
    # 4. Remove múltiplos espaços e espaços no início/fim
    q_clean = re.sub(r'\s+', ' ', q_clean).strip()
    
    # 5. Se a string ficou vazia, usa fallback
    if not q_clean:
        q_clean = "hardware specification query"
    
    return q_clean

# -----------------------------------------------------------------------------
# Função principal de aquecimento (versão direta, sem RAG)
# -----------------------------------------------------------------------------
async def warmup_cache_direct():
    """Gera embeddings usando cliente Ollama (CPU) e armazena no cache."""
    config = EvalConfig()
    cache = EmbeddingCache(config.cache_dir, config.embedding_cache_size)

    print(f"🚀 Iniciando aquecimento de cache para {len(TEST_SUITE)} perguntas...")
    print(f"📍 Local do cache: {config.cache_dir}")

    # Força uso da CPU para evitar conflitos com GPU
    original_cuda = os.environ.get('CUDA_VISIBLE_DEVICES')
    os.environ['CUDA_VISIBLE_DEVICES'] = '-1'
    os.environ['OLLAMA_NUM_GPU'] = '0'

    client = Client(host="http://localhost:11434")

    # Restaura variáveis após criar o cliente
    if original_cuda is not None:
        os.environ['CUDA_VISIBLE_DEVICES'] = original_cuda
    else:
        os.environ.pop('CUDA_VISIBLE_DEVICES', None)
    os.environ.pop('OLLAMA_NUM_GPU', None)

    print("✅ Cliente BGE-M3 (CPU) inicializado")

    hits = 0
    new_embeddings = 0
    errors = 0
    dimension = 1024  # dimensão esperada para bge-m3

    for case in tqdm(TEST_SUITE, desc="Processando queries"):
        query = case["input"]

        # Verifica se já está em cache
        if cache.get(query) is not None:
            hits += 1
            continue

        # Sanitização para evitar NaN
        sanitized = _sanitize_query(query)

        # Gera embedding via thread separada
        try:
            result = await asyncio.to_thread(
                client.embeddings,
                model="bge-m3:latest",
                prompt=sanitized
            )
            embedding = np.array(result['embedding'], dtype=np.float32)

            # Verifica e corrige NaN
            if np.isnan(embedding).any():
                print(f"\n⚠️ NaN detectado para: {query[:50]}... substituindo por zeros.")
                embedding = np.nan_to_num(embedding, nan=0.0)

            cache.set(query, embedding)
            new_embeddings += 1

        except ResponseError as e:
            # Erro específico do Ollama (ex: NaN)
            print(f"\n❌ Erro do Ollama para: {query[:50]}... | {e}")
            # Cria embedding de fallback (zeros)
            fallback_embedding = np.zeros(dimension, dtype=np.float32)
            cache.set(query, fallback_embedding)
            new_embeddings += 1
            errors += 1

        except Exception as e:
            print(f"\n❌ Erro inesperado para: {query[:50]}... | {e}")
            fallback_embedding = np.zeros(dimension, dtype=np.float32)
            cache.set(query, fallback_embedding)
            new_embeddings += 1
            errors += 1

    # Estatísticas finais (usando contagem de arquivos no diretório)
    import pickle
    cache_files = list(Path(config.cache_dir).glob("*.pkl"))
    total_in_dir = len(cache_files)

    print("\n" + "=" * 50)
    print("✅ AQUECIMENTO CONCLUÍDO")
    print(f"   - Já estavam no cache: {hits}")
    print(f"   - Novos embeddings gerados: {new_embeddings}")
    print(f"   - Total disponível (no cache): {hits + new_embeddings}")
    print(f"   - Arquivos no diretório: {total_in_dir}")
    print(f"   - Erros (substituídos por zeros): {errors}")
    print("=" * 50)

# -----------------------------------------------------------------------------
# Opção extra: verificar o conteúdo do cache
# -----------------------------------------------------------------------------
async def verify_cache():
    config = EvalConfig()
    cache = EmbeddingCache(config.cache_dir, config.embedding_cache_size)
    # stats não existe; vamos listar manualmente
    import pickle
    cache_dir = config.cache_dir
    files = list(cache_dir.glob("*.pkl"))
    print(f"\n🔍 Verificando cache...")
    print(f"   Diretório: {cache_dir}")
    print(f"   Arquivos no disco: {len(files)}")
    if files:
        sample = files[0]
        try:
            with open(sample, 'rb') as f:
                emb = pickle.load(f)
            print(f"   Exemplo: {sample.name} → dimensão {len(emb)}")
        except Exception as e:
            print(f"   Erro ao ler exemplo: {e}")

# -----------------------------------------------------------------------------
# Ponto de entrada
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("🔧 SCRIPT DE AQUECIMENTO DE CACHE (versão direta)")
    print("=" * 60)

    print("\nOpções:")
    print("1 - Gerar/atualizar cache (recomendado)")
    print("2 - Verificar cache existente")
    choice = input("\nEscolha (1/2): ").strip()

    if choice == "2":
        asyncio.run(verify_cache())
    else:
        asyncio.run(warmup_cache_direct())