# test_rag_temporal.py - VERSÃO CORRIGIDA
import asyncio
import signal
from contextlib import asynccontextmanager

from core.paths import VALIDACAO_SCRIPT, VETORIZATION_DATA
import sys
sys.path.append(str(VALIDACAO_SCRIPT))
from RAG_Temporal_V9 import SpecialistTimeAwareRAG

async def test_with_timeout(coro, timeout_seconds=30):
    """Executa uma corotina com timeout."""
    try:
        return await asyncio.wait_for(coro, timeout=timeout_seconds)
    except asyncio.TimeoutError:
        print(f"⚠️ Timeout após {timeout_seconds} segundos")
        return None

async def test():
    print("🚀 Inicializando RAG...")
    rag = SpecialistTimeAwareRAG(
        VETORIZATION_DATA / 'base_conhecimento_multilingueV7.json',
        variant_name="V9_HYBRID_AUDITOR"
    )
    
    tests = [
        # Teste 1: Pergunta genérica - deve pedir SKU
        ("Does the Nitro 5 have Thunderbolt 4?", "should_ask_for_sku"),
        
        # Teste 2: Comparação - deve admitir que não pode comparar
        ("Does AN515-56 have same Thunderbolt as AN515-57?", "should_admit_cannot_compare"),
        
        # Teste 3: SKU específico não encontrado - deve admitir indisponibilidade
        ("What is the maximum RAM for Acer AN515-56?", "should_admit_unavailability"),
    ]
    
    print("\n" + "=" * 60)
    
    for i, (query, expected) in enumerate(tests, 1):
        print(f"\n📝 Teste {i}: {query}")
        print(f"🎯 Esperado: {expected}")
        print("-" * 40)
        
        try:
            result = await test_with_timeout(rag.search(query, "2025-06-01"), timeout_seconds=45)
            
            if result is None:
                print("❌ TIMEOUT - Sistema não respondeu")
                continue
            
            print(f"✅ Resposta recebida ({len(result['answer'])} caracteres)")
            print(f"📄 Resposta: {result['answer'][:300]}...")
            print(f"📋 Audit: {result.get('audit_trail', '')[:200]}")
            
            # Verificação simples
            answer_lower = result['answer'].lower()
            
            if expected == "should_ask_for_sku":
                asks_for_sku = any(phrase in answer_lower for phrase in 
                                ['model number', 'sku', 'specific model', 'complete model'])
                if asks_for_sku:
                    print("✅ PASSOU: Pediu SKU")
                else:
                    print("❌ FALHOU: Não pediu SKU")
                    
            elif expected == "should_admit_cannot_compare":
                admits_cannot = any(phrase in answer_lower for phrase in 
                                ['cannot compare', 'lack complete data', 'missing data'])
                if admits_cannot:
                    print("✅ PASSOU: Admitiu que não pode comparar")
                else:
                    print("❌ FALHOU: Não admitiu limitação para comparação")
                    
            elif expected == "should_admit_unavailability":
                admits_unavail = any(phrase in answer_lower for phrase in 
                                    ['not available', 'no information', "don't have"])
                if admits_unavail:
                    print("✅ PASSOU: Admitiu indisponibilidade")
                else:
                    print("❌ FALHOU: Não admitiu indisponibilidade")
                    
        except Exception as e:
            print(f"❌ ERRO: {type(e).__name__}: {e}")
        
        print("-" * 60)
    
    print("\n" + "=" * 60)
    print("🏁 Testes concluídos")

if __name__ == "__main__":
    try:
        asyncio.run(test())
    except KeyboardInterrupt:
        print("\n⚠️ Teste interrompido pelo usuário")
    except Exception as e:
        print(f"\n❌ Erro fatal: {e}")