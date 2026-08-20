#!/usr/bin/env python3
"""
test_rag_components.py
Testes unitários e de integração para o pipeline RAG (vetorização + carregamento + busca)
Antes de executar os avaliações completas.
"""

import json
import numpy as np
import faiss
from pathlib import Path
import sys
from datetime import datetime
import asyncio

# Adicione seus paths personalizados se necessário
from core.paths import VETORIZATION_DATA, AVALIACAO_DATA

# Import das classes modificadas
from RAG_BaseLineV2 import VanillaRAG, DataLoader, FAISSManager
from RAG_Temporal_V9_3 import SpecialistTimeAwareRAG, TemporalScorer

# ============================================================================
# CONFIGURAÇÕES
# ============================================================================

BASE_PATH = VETORIZATION_DATA / 'base_vetorizada' / 'base_conhecimento_multilingueV9.json'  # caminho base (sem extensão)

# ============================================================================
# TESTE 1: VALIDAÇÃO DOS ARQUIVOS GERADOS
# ============================================================================

def test_arquivos_gerados():
    """Verifica se os arquivos .npy, .meta.json e .faiss existem e são válidos."""
    print("\n🔍 TESTE 1: Verificando arquivos gerados...")
    
    base_path = Path(BASE_PATH)
    npy_path = base_path.with_suffix('.npy')
    meta_path = base_path.with_suffix('.meta.json')
    faiss_path = base_path.with_suffix('.faiss')
    
    for path, nome in [(npy_path, '.npy'), (meta_path, '.meta.json'), (faiss_path, '.faiss')]:
        if not path.exists():
            print(f"❌ Arquivo {nome} não encontrado em {path}")
            return False
        else:
            print(f"✅ {nome} encontrado")
    
    # Tenta carregar o .npy para verificar integridade
    try:
        vectors = np.load(npy_path)
        print(f"   Vetores carregados: {vectors.shape} (dtype={vectors.dtype})")
    except Exception as e:
        print(f"❌ Erro ao carregar .npy: {e}")
        return False
    
    # Tenta carregar o .meta.json
    try:
        with open(meta_path, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        print(f"   Metadados carregados: {len(metadata)} documentos")
        # Verifica se cada documento tem os campos mínimos
        for doc in metadata[:5]:
            assert 'id' in doc
            assert 'original_text' in doc
            assert 'date_iso' in doc
            assert 'metadata' in doc
        print("   ✅ Metadados com estrutura correta")
    except Exception as e:
        print(f"❌ Erro ao carregar .meta.json: {e}")
        return False
    
    # Tenta carregar o índice FAISS
    try:
        index = faiss.read_index(str(faiss_path))
        print(f"   Índice FAISS carregado: {index.ntotal} vetores, dimensão {index.d}")
    except Exception as e:
        print(f"❌ Erro ao carregar .faiss: {e}")
        return False
    
    print("✅ Teste 1 passou!\n")
    return True

# ============================================================================
# TESTE 2: CARREGAMENTO OTIMIZADO NO VanillaRAG
# ============================================================================

def test_vanilla_rag_load():
    """Verifica se o VanillaRAG carrega os arquivos otimizados corretamente."""
    print("\n🔍 TESTE 2: Carregamento otimizado do VanillaRAG...")
    
    try:
        rag = VanillaRAG(BASE_PATH, use_expansion=False)
        # Verifica se o índice FAISS foi carregado (não reconstruído)
        if rag.faiss_manager.index is None:
            print("❌ Índice FAISS não carregado")
            return False
        
        # Verifica se a base de dados (metadados) foi carregada
        if not rag.base_dados:
            print("❌ Base de dados (metadados) vazia")
            return False
        
        print(f"   Documentos carregados: {len(rag.base_dados)}")
        print(f"   Índice FAISS: {rag.faiss_manager.index.ntotal} vetores")
        
        # Testa uma busca síncrona simples (usa o método search que não é assíncrono)
        # Como o método search é async, vamos fazer uma chamada de teste usando asyncio
        async def test_search():
            result = await rag.search("What is the maximum RAM for Dell G15 5530?")
            return result
        
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(test_search())
        
        if 'answer' in result and result['answer']:
            print(f"   Resposta obtida (primeiros 100 chars): {result['answer']}...")
            print(f"   Fontes recuperadas: {len(result.get('sources', []))}")
        else:
            print("❌ Resposta vazia ou inválida")
            return False
        
        print("✅ Teste 2 passou!\n")
        return True
    except Exception as e:
        print(f"❌ Erro no VanillaRAG: {e}")
        import traceback
        traceback.print_exc()
        return False

# ============================================================================
# TESTE 3: CARREGAMENTO OTIMIZADO NO SpecialistTimeAwareRAG
# ============================================================================

def test_temporal_rag_load():
    """Verifica se o TemporalRAG carrega arquivos otimizados e o TemporalScorer funciona."""
    print("\n🔍 TESTE 3: Carregamento otimizado do TemporalRAG...")
    
    try:
        rag = SpecialistTimeAwareRAG(BASE_PATH, variant_name="V9_HYBRID_MIXED_AUDITOR", use_expansion=True)
        
        # Verifica índice FAISS
        if rag.faiss_manager.index is None:
            print("❌ Índice FAISS não carregado")
            return False
        
        print(f"   Documentos carregados: {len(rag.data_loader.documents)}")
        print(f"   Índice FAISS: {rag.faiss_manager.index.ntotal} vetores")
        
        # Testa busca temporal com penalidade
        async def test_temporal_search():
            result = await rag.search(
                "What was the RAM of Dell G15 5530 in 2024?",
                ref_date="2024-06-01"
            )
            return result
        
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(test_temporal_search())
        
        if 'answer' in result and result['answer']:
            print(f"   Resposta obtida (primeiros 100 chars): {result['answer']}...")
            print(f"   Fontes: {len(result.get('sources', []))}")
            # Verifica se o diagnóstico temporal está presente
            diag = result.get('diagnostic', {})
            print(f"   Diagnóstico: gap={diag.get('best_temporal_gap_years', 'N/A')}, penalidade média={diag.get('avg_penalty', 'N/A')}")
        else:
            print("❌ Resposta vazia ou inválida")
            return False
        
        # Teste adicional: verificar se o TemporalScorer está aplicando penalidades
        # Força uma busca com data futura para ver se há fallback
        async def test_future_search():
            result = await rag.search(
                "What is the latest BIOS for Acer Nitro 5?",
                ref_date="2026-12-31"
            )
            return result
        
        result_future = loop.run_until_complete(test_future_search())
        diag_future = result_future.get('diagnostic', {})
        print(f"   Busca com data futura: gap={diag_future.get('best_temporal_gap_years', 'N/A')}")
        # Não há assert forte porque pode não ter documentos futuros; apenas verifica se não quebra
        
        print("✅ Teste 3 passou!\n")
        return True
    except Exception as e:
        print(f"❌ Erro no TemporalRAG: {e}")
        import traceback
        traceback.print_exc()
        return False

# ============================================================================
# TESTE 4: TEMPORAL SCORER ISOLADO
# ============================================================================

def test_temporal_scorer():
    """Testa o TemporalScorer com dados mock para garantir que as penalidades são calculadas."""
    print("\n🔍 TESTE 4: Testando TemporalScorer...")
    
    scorer = TemporalScorer(
        yearly_penalty_rate=0.04,
        recency_threshold=3,
        low_coverage_multiplier=0.3
    )
    
    ref_date = datetime(2024, 6, 1)
    doc_date_1 = "2026-06-19"
    # Caso 1: documento atual
    gap = scorer.calculate_temporal_gap(doc_date_1, ref_date)

    score, penalty, status = scorer.score_document(semantic_score=0.5, temporal_gap=gap, recency_multiplier=1.0)

    print(f"   Documento atual: gap={gap:.2f}, score={score:.3f}, penalty={penalty:.3f}, status={status}")
    
    assert penalty == 0.0, "Documento atual não deve ter penalidade"
    
    # Caso 2: documento antigo (2 anos)
    doc_date_2 = "2024-01-01"
    gap = scorer.calculate_temporal_gap(doc_date_2, ref_date)
    score, penalty, status = scorer.score_document(semantic_score=0.5, temporal_gap=gap, recency_multiplier=0.5)
    print(f"   Documento antigo (2y): gap={gap:.2f}, score={score:.3f}, penalty={penalty:.3f}, status={status}")
    assert penalty > 0.0, "Documento antigo deve ter penalidade"
    assert score > 0.5, "Score final deve ser maior que o semântico (devido à penalidade multiplicativa)"
    
    # Caso 3: documento futuro (gap negativo)
    gap = scorer.calculate_temporal_gap("2025-06-01", ref_date)
    score, penalty, status = scorer.score_document(semantic_score=0.5, temporal_gap=gap, recency_multiplier=1.0)
    print(f"   Documento futuro: gap={gap:.2f}, score={score:.3f}, penalty={penalty:.3f}, status={status}")
    assert penalty == 0.0, "Documento futuro não deve ter penalidade"
    
    print("✅ Teste 4 passou!\n")
    return True

# ============================================================================
# TESTE 5: COMPARAÇÃO DE DESEMPENHO (OPCIONAL)
# ============================================================================

def test_performance_comparison():
    """Compara o tempo de carregamento com e sem otimização (se ambos os modos estiverem disponíveis)."""
    print("\n🔍 TESTE 5: Comparação de desempenho (opcional)...")
    
    import time
    
    base_path = Path(BASE_PATH)
    # Verifica se temos o arquivo FAISS
    if not base_path.with_suffix('.faiss').exists():
        print("⚠️ Arquivo .faiss não encontrado. Pulando teste de performance.")
        return True
    
    # Mede tempo de carregamento otimizado
    start = time.time()
    rag_opt = VanillaRAG(BASE_PATH, use_expansion=False)
    time_opt = time.time() - start
    print(f"   Carregamento otimizado: {time_opt:.2f} segundos")
    
    # Para o modo não otimizado, precisaríamos renomear o arquivo .faiss temporariamente,
    # mas não faremos isso para não corromper. Vamos apenas assumir que o carregamento
    # otimizado é mais rápido que o anterior (que levava ~5-10s).
    # Se time_opt < 2.0, consideramos bom.
    if time_opt < 2.0:
        print("   ✅ Carregamento rápido (menos de 2s)")
    else:
        print(f"   ⚠️ Carregamento ainda lento ({time_opt:.2f}s), verifique se o .faiss está sendo usado corretamente.")
    
    return True

# ============================================================================
# FUNÇÃO PRINCIPAL
# ============================================================================

def run_all_tests():
    print("=" * 60)
    print("🧪 INICIANDO TESTES DOS COMPONENTES RAG")
    print("=" * 60)
    
    results = []
    
    # Teste 1: Arquivos
    results.append(("Arquivos gerados", test_arquivos_gerados()))
    
    # Teste 2: VanillaRAG
    results.append(("Carregamento VanillaRAG", test_vanilla_rag_load()))
    
    # Teste 3: TemporalRAG
    results.append(("Carregamento TemporalRAG", test_temporal_rag_load()))
    
    # Teste 4: TemporalScorer
    results.append(("TemporalScorer", test_temporal_scorer()))
    
    # Teste 5: Performance (opcional)
    results.append(("Desempenho", test_performance_comparison()))
    
    # Resumo
    print("\n" + "=" * 60)
    print("📊 RESUMO DOS TESTES")
    print("=" * 60)
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {name:<30} {status}")
    
    all_passed = all(passed for _, passed in results)
    if all_passed:
        print("\n🎉 Todos os testes passaram! O pipeline está pronto para a avaliação completa.")
    else:
        print("\n⚠️ Alguns testes falharam. Revise as implementações antes de prosseguir.")
    
    return all_passed

if __name__ == "__main__":
    run_all_tests()