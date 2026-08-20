import asyncio
from tqdm import tqdm
from core.paths import AVALIACAO_DATA
import sys
sys.path.append(str(AVALIACAO_DATA.parent / "05_definicao_sistemas_rags" / "script"))

from evaluate_rag_deepeval_TemporalVSNãoTemporalV7_CacheReady import EvalConfig, EmbeddingCache,RAGManager

from core.paths import AVALIACAO_DATA, VALIDACAO_SCRIPT
import sys
sys.path.append(str(VALIDACAO_SCRIPT))
from dataset_avaliacaoV3 import TEST_SUITE


async def warmup_cache():
    config = EvalConfig()
    cache = EmbeddingCache(config.cache_dir, config.embedding_cache_size)
    rag_manager = RAGManager(config.base_path)
    
    print(f"🚀 Iniciando aquecimento de cache para {len(TEST_SUITE)} perguntas...")
    print(f"📍 Local do cache: {config.cache_dir}")
    
    # Carrega o RAG para ter acesso ao método de embedding
    rag_engine = rag_manager.vanilla
    
    # ⭐ Verifica se o método _get_embedding existe
    if not hasattr(rag_engine, '_get_embedding'):
        print("❌ O RAG engine não possui o método '_get_embedding'")
        print("   Verifique se a classe VanillaRAG está corretamente herdando de SpecialistTimeAwareRAG")
        return
    
    hits = 0
    new_embeddings = 0
    
    for case in tqdm(TEST_SUITE, desc="Processando queries"):
        query = case["input"]
        
        # 1. Verifica se já existe no cache
        cached = cache.get(query)
        if cached is not None:
            hits += 1
            continue
            
        # 2. Se não existir, gera o embedding usando o método correto
        try:
            # ⭐ Usa o método assíncrono _get_embedding que já existe na classe
            embedding = await rag_engine._get_embedding(query)
            
            # Salva no cache (converte para numpy array se necessário)
            cache.set(query, embedding)
            new_embeddings += 1
            
            # Pequeno delay para não sobrecarregar
            await asyncio.sleep(0.01)
            
        except Exception as e:
            print(f"\n❌ Erro ao processar query: {query[:50]}... | Erro: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "="*50)
    print("✅ AQUECIMENTO CONCLUÍDO")
    print(f"   - Já estavam no cache: {hits}")
    print(f"   - Novos embeddings gerados: {new_embeddings}")
    print(f"   - Total agora disponível: {hits + new_embeddings}")
    print(f"   - Cache stats: {cache.stats()}")
    print("="*50)


async def warmup_cache_direct():
    """
    Versão alternativa que usa diretamente o cliente CPU do Ollama,
    sem depender do RAGManager.
    """
    import os
    from ollama import Client
    import numpy as np
    
    config = EvalConfig()
    cache = EmbeddingCache(config.cache_dir, config.embedding_cache_size)
    
    print(f"🚀 Iniciando aquecimento de cache (versão direta) para {len(TEST_SUITE)} perguntas...")
    print(f"📍 Local do cache: {config.cache_dir}")
    
    # Configura cliente CPU
    original_cuda = os.environ.get('CUDA_VISIBLE_DEVICES')
    os.environ['CUDA_VISIBLE_DEVICES'] = '-1'
    os.environ['OLLAMA_NUM_GPU'] = '0'
    
    cpu_client = Client()
    
    # Restaura após criar o cliente
    if original_cuda is not None:
        os.environ['CUDA_VISIBLE_DEVICES'] = original_cuda
    else:
        os.environ.pop('CUDA_VISIBLE_DEVICES', None)
    os.environ.pop('OLLAMA_NUM_GPU', None)
    
    print("✅ Cliente BGE-M3 (CPU) inicializado")
    
    hits = 0
    new_embeddings = 0
    
    for case in tqdm(TEST_SUITE, desc="Processando queries"):
        query = case["input"]
        
        # Verifica cache
        if cache.get(query) is not None:
            hits += 1
            continue
        
        # Gera embedding
        try:
            result = await asyncio.to_thread(
                cpu_client.embeddings,
                model="bge-m3:latest",
                prompt=query
            )
            embedding = np.array(result['embedding'], dtype=np.float32)
            cache.set(query, embedding)
            new_embeddings += 1
            
        except Exception as e:
            print(f"\n❌ Erro: {query[:50]}... | {e}")
    
    print("\n" + "="*50)
    print("✅ AQUECIMENTO CONCLUÍDO (versão direta)")
    print(f"   - Cache hits: {hits}")
    print(f"   - Novos embeddings: {new_embeddings}")
    print(f"   - Total: {hits + new_embeddings}")
    print("="*50)


async def verify_cache():
    """Verifica o conteúdo do cache."""
    config = EvalConfig()
    cache = EmbeddingCache(config.cache_dir, config.embedding_cache_size)
    
    print("\n🔍 Verificando cache...")
    stats = cache.stats()
    print(f"   Tamanho do cache: {stats['size']}")
    print(f"   Diretório: {stats['directory']}")
    
    # Lista alguns arquivos
    import pickle
    from pathlib import Path
    
    cache_files = list(Path(stats['directory']).glob("*.pkl"))
    print(f"   Arquivos no disco: {len(cache_files)}")
    
    if cache_files:
        print(f"\n   Primeiro arquivo: {cache_files[0].name}")
        try:
            with open(cache_files[0], 'rb') as f:
                embedding = pickle.load(f)
            print(f"   Dimensão do embedding: {len(embedding)}")
        except Exception as e:
            print(f"   Erro ao ler: {e}")


if __name__ == "__main__":
    import sys
    
    print("\n" + "="*60)
    print("🔧 SCRIPT DE AQUECIMENTO DE CACHE")
    print("="*60)
    
    print("\nOpções:")
    print("1 - Usar RAGManager (recomendado, após corrigir)")
    print("2 - Usar cliente direto (mais rápido, não carrega base)")
    print("3 - Verificar cache existente")
    
    choice = input("\nEscolha (1/2/3): ").strip()
    
    if choice == "3":
        asyncio.run(verify_cache())
    elif choice == "2":
        asyncio.run(warmup_cache_direct())
    else:
        asyncio.run(warmup_cache())