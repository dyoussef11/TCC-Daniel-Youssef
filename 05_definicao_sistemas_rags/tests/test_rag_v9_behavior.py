"""
test_rag_v9_behavior.py
Testa o comportamento do RAG V9 com SKU Lock e proibição de inferência serial.
"""

import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List

# Configuração do caminho
sys.path.append(str(Path(__file__).parent.parent.parent))

from core.paths import AVALIACAO_SCRIPT, VETORIZATION_DATA, AVALIACAO_DATA, VALIDACAO_SCRIPT
sys.path.append(str(VALIDACAO_SCRIPT))
sys.path.append(str(AVALIACAO_SCRIPT))

from RAG_Temporal_V8_CPUMode_CacheReady import SpecialistTimeAwareRAG
from evaluate_rag_deepeval_TemporalVSNãoTemporalV7_CacheReady import EmbeddingCache


class RAGBehaviorTester:
    """
    Testa comportamentos específicos do RAG V9:
    - SKU Lock (não inferir entre modelos)
    - Proibição de inferência serial
    - Uso correto de conhecimento interno
    - Admissão de falta de dados
    """
    
    def __init__(self):
        self.base_path = VETORIZATION_DATA / 'base_conhecimento_multilingueV7.json'
        self.cache = EmbeddingCache(AVALIACAO_DATA / "cache", max_size=1000)
        self.rag = None
        self.results = []
    
    async def initialize(self):
        """Inicializa o RAG com o prompt V9."""
        print("\n" + "=" * 80)
        print("🔧 INICIALIZANDO RAG V9 PARA TESTES")
        print("=" * 80)
        
        self.rag = SpecialistTimeAwareRAG(
            self.base_path,
            variant_name="V9_HYBRID_AUDITOR",  # Usando V9
            embedding_cache=self.cache
        )
        
        # Configurações otimizadas (da sua análise)
        self.rag.current_model = "phi3.5:latest"
        self.rag.temperature = 0.0
        self.rag.search_top_k = 10
        self.rag.similarity_threshold = 1.2
        
        print("\n✅ RAG V9 inicializado com configurações otimizadas:")
        print(f"   Modelo: {self.rag.current_model}")
        print(f"   Temperatura: {self.rag.temperature}")
        print(f"   Top-K: {self.rag.search_top_k}")
        print(f"   Threshold: {self.rag.similarity_threshold}")
    
    async def test_sku_lock_acer(self):
        """Testa SKU Lock para Acer - NÃO deve inferir de AN515-57 para AN515-56."""
        print("\n" + "=" * 80)
        print("📝 TESTE 1: SKU LOCK - ACER")
        print("=" * 80)
        
        query = "What is the maximum RAM capacity for the Acer Nitro 5 AN515-56?"
        ref_date = "2025-06-01"
        
        print(f"\n🔍 Query: {query}")
        print(f"📅 Data referência: {ref_date}")
        print("\n⚠️ EXPECTATIVA: Deve dizer que informação não está disponível")
        print("   (NÃO deve inferir do AN515-57 ou AN515-58)")
        
        result = await self.rag.search(query, ref_date)
        
        self._print_result(result)
        self._analyze_sku_compliance(result, "AN515-56")
        
        return result
    
    async def test_sku_lock_dell(self):
        """Testa SKU Lock para Dell - NÃO deve inferir entre modelos G7."""
        print("\n" + "=" * 80)
        print("📝 TESTE 2: SKU LOCK - DELL")
        print("=" * 80)
        
        query = "What processor does the Dell G7 7588 have?"
        ref_date = "2025-06-01"
        
        print(f"\n🔍 Query: {query}")
        print(f"📅 Data referência: {ref_date}")
        print("\n⚠️ EXPECTATIVA: Deve dizer que informação não está disponível")
        print("   (NÃO deve inferir do G7 7590 ou outros Dells)")
        
        result = await self.rag.search(query, ref_date)
        
        self._print_result(result)
        self._analyze_sku_compliance(result, "G7 7588")
        
        return result
    
    async def test_no_series_inference(self):
        """Testa proibição de inferência serial - NÃO deve usar dados de série."""
        print("\n" + "=" * 80)
        print("📝 TESTE 3: PROIBIÇÃO DE INFERÊNCIA SERIAL")
        print("=" * 80)
        
        query = "Does the Nitro 5 have Thunderbolt 4?"
        ref_date = "2025-06-01"
        
        print(f"\n🔍 Query: {query}")
        print(f"📅 Data referência: {ref_date}")
        print("\n⚠️ EXPECTATIVA: Deve pedir modelo específico")
        print("   (NÃO deve responder de forma genérica sobre a série Nitro 5)")
        
        result = await self.rag.search(query, ref_date)
        
        self._print_result(result)
        
        # Verifica se pediu modelo específico
        answer_lower = result["answer"].lower()
        if any(phrase in answer_lower for phrase in ["specific model", "exact sku", "which model", "an515"]):
            print("\n✅ PASS: Modelo pediu especificação do SKU")
        else:
            print("\n❌ FAIL: Resposta genérica sem pedir SKU específico")
        
        return result
    
    async def test_internal_knowledge_usage(self):
        """Testa uso correto de conhecimento interno - APENAS para conceitos gerais."""
        print("\n" + "=" * 80)
        print("📝 TESTE 4: CONHECIMENTO INTERNO (Apenas conceitos gerais)")
        print("=" * 80)
        
        query = "Why does my laptop thermal throttle during gaming?"
        ref_date = "2025-06-01"
        
        print(f"\n🔍 Query: {query}")
        print(f"📅 Data referência: {ref_date}")
        print("\n⚠️ EXPECTATIVA: Deve explicar conceito geral de thermal throttling")
        print("   (NÃO deve dar especificações de nenhum modelo)")
        
        result = await self.rag.search(query, ref_date)
        
        self._print_result(result)
        
        # Verifica se usou conhecimento interno (explicação geral)
        answer_lower = result["answer"].lower()
        if any(phrase in answer_lower for phrase in ["throttling", "temperature", "cooling", "thermal"]):
            print("\n✅ PASS: Forneceu explicação conceitual")
        else:
            print("\n⚠️ WARN: Resposta pode não ter explicado o conceito")
        
        return result
    
    async def test_missing_data_admission(self):
        """Testa admissão de falta de dados - NÃO deve inventar."""
        print("\n" + "=" * 80)
        print("📝 TESTE 5: ADMISSÃO DE FALTA DE DADOS")
        print("=" * 80)
        
        query = "What is the BIOS version for Lenovo Legion 5 15ACH6?"
        ref_date = "2025-06-01"
        
        print(f"\n🔍 Query: {query}")
        print(f"📅 Data referência: {ref_date}")
        print("\n⚠️ EXPECTATIVA: Deve admitir que informação não está disponível")
        print("   (NÃO deve inventar um número de versão)")
        
        result = await self.rag.search(query, ref_date)
        
        self._print_result(result)
        
        # Verifica se admitiu falta de dados
        answer_lower = result["answer"].lower()
        if any(phrase in answer_lower for phrase in ["not available", "unavailable", "not found", "no information"]):
            print("\n✅ PASS: Admitiu falta de dados")
        else:
            print("\n❌ FAIL: Pode ter inventado informação")
        
        return result
    
    async def test_sku_mismatch_honesty(self):
        """Testa honestidade em SKU mismatch - NÃO deve inferir."""
        print("\n" + "=" * 80)
        print("📝 TESTE 6: HONESTIDADE EM SKU MISMATCH")
        print("=" * 80)
        
        query = "Does the AN515-56 have the same Thunderbolt port as the AN515-57?"
        ref_date = "2025-06-01"
        
        print(f"\n🔍 Query: {query}")
        print(f"📅 Data referência: {ref_date}")
        print("\n⚠️ EXPECTATIVA: Deve dizer que não tem dados para comparação")
        print("   (NÃO deve afirmar que são iguais ou diferentes sem evidência)")
        
        result = await self.rag.search(query, ref_date)
        
        self._print_result(result)
        
        # Verifica honestidade
        answer_lower = result["answer"].lower()
        if "not available" in answer_lower or "cannot compare" in answer_lower or "insufficient" in answer_lower:
            print("\n✅ PASS: Honesto sobre falta de dados para comparação")
        else:
            print("\n⚠️ CHECK: Verificar se não inferiu comparação")
        
        return result
    
    async def test_temporal_awareness(self):
        """Testa consciência temporal - deve saber que 2026 é futuro."""
        print("\n" + "=" * 80)
        print("📝 TESTE 7: CONSCIÊNCIA TEMPORAL")
        print("=" * 80)
        
        query = "What is the latest stable BIOS version for Helios Neo 16 as of 2026?"
        ref_date = "2026-01-01"
        
        print(f"\n🔍 Query: {query}")
        print(f"📅 Data referência: {ref_date}")
        print("\n⚠️ EXPECTATIVA: Deve reconhecer que 2026 é futuro ou ainda não documentado")
        
        result = await self.rag.search(query, ref_date)
        
        self._print_result(result)
        
        return result
    
    def _print_result(self, result: Dict):
        """Imprime o resultado de forma organizada."""
        print("\n" + "-" * 40)
        print("📤 RESPOSTA DO RAG:")
        print("-" * 40)
        print(f"\n📋 AUDIT TRAIL:\n{result['audit_trail'][:500]}")
        print(f"\n💬 ANSWER:\n{result['answer'][:500]}")
        print(f"\n📚 SOURCES USADAS: {len(result['sources'])} documentos")
        if result['titles']:
            print(f"   Títulos: {result['titles'][:3]}")
    
    def _analyze_sku_compliance(self, result: Dict, expected_sku: str):
        """Analisa se o RAG respeitou o SKU Lock."""
        answer = result["answer"].lower()
        
        # Padrões que indicam inferência proibida
        inference_patterns = [
            "similar model",
            "based on the", 
            "typically found",
            "usually",
            "in general",
            "other models",
            "similar sku",
            "series"
        ]
        
        found_inference = [p for p in inference_patterns if p in answer]
        
        if found_inference:
            print(f"\n⚠️ INFERÊNCIA DETECTADA: {found_inference}")
            print("   O RAG pode estar violando SKU Lock")
        else:
            print(f"\n✅ SKU Lock respeitado para {expected_sku}")
        
        # Verifica se admitiu falta de dados
        if any(p in answer for p in ["not available", "unavailable", "not found", "no information"]):
            print("   ✅ Admitiu falta de dados corretamente")
        else:
            print("   ⚠️ Pode não ter admitido falta de dados")
    
    async def run_all_tests(self):
        """Executa todos os testes."""
        await self.initialize()
        
        test_results = {}
        
        # Lista de testes
        tests = [
            ("SKU Lock Acer", self.test_sku_lock_acer),
            ("SKU Lock Dell", self.test_sku_lock_dell),
            ("Proibição Inferência Serial", self.test_no_series_inference),
            ("Conhecimento Interno", self.test_internal_knowledge_usage),
            ("Admissão Falta Dados", self.test_missing_data_admission),
            ("Honestidade SKU Mismatch", self.test_sku_mismatch_honesty),
            ("Consciência Temporal", self.test_temporal_awareness),
        ]
        
        for name, test_func in tests:
            print("\n" + "🧪" * 40)
            print(f"INICIANDO TESTE: {name}")
            print("🧪" * 40)
            
            try:
                result = await test_func()
                test_results[name] = {
                    "status": "completed",
                    "audit": result.get("audit_trail", "")[:200],
                    "answer_preview": result.get("answer", "")[:200]
                }
            except Exception as e:
                print(f"\n❌ ERRO no teste {name}: {e}")
                test_results[name] = {"status": "failed", "error": str(e)}
            
            # Pequena pausa entre testes
            await asyncio.sleep(2)
        
        # Sumário final
        self._print_summary(test_results)
    
    def _print_summary(self, test_results: Dict):
        """Imprime sumário dos testes."""
        print("\n" + "=" * 80)
        print("📊 SUMÁRIO DOS TESTES RAG V9")
        print("=" * 80)
        
        for name, result in test_results.items():
            status = result.get("status", "unknown")
            if status == "completed":
                print(f"\n✅ {name}: OK")
                print(f"   Answer preview: {result['answer_preview'][:100]}...")
            else:
                print(f"\n❌ {name}: FALHOU - {result.get('error', 'unknown')}")
        
        print("\n" + "=" * 80)
        print("💡 RECOMENDAÇÕES FINAIS")
        print("=" * 80)
        print("""
        1. Verifique se o RAG está admitindo falta de dados (SKU_NOT_FOUND)
        2. Confirme que não há inferência entre modelos diferentes
        3. Valide que conhecimento interno só é usado para conceitos gerais
        4. Teste com marcas diferentes (Dell, Lenovo, HP)
        5. Ajuste o prompt V9 se necessário baseado nos resultados
        """)


async def quick_test():
    """Teste rápido para verificar o prompt V9 com uma query."""
    print("\n" + "=" * 80)
    print("⚡ TESTE RÁPIDO - VERIFICANDO PROMPT V9")
    print("=" * 80)
    
    cache = EmbeddingCache(AVALIACAO_DATA / "cache", max_size=1000)
    
    rag = SpecialistTimeAwareRAG(
        VETORIZATION_DATA / 'base_conhecimento_multilingueV7.json',
        variant_name="V9_HYBRID_AUDITOR",
        embedding_cache=cache
    )
    
    # Configurações otimizadas
    rag.current_model = "phi3.5:latest"
    rag.temperature = 0.0
    rag.search_top_k = 10
    rag.similarity_threshold = 1.2
    
    queries = [
        ("What is the maximum RAM for Acer Nitro 5 AN515-56?", "2025-06-01"),
        ("Does Dell G7 7588 support Thunderbolt 4?", "2025-06-01"),
        ("What processor does Lenovo Legion 5 have?", "2025-06-01"),
    ]
    
    for query, ref_date in queries:
        print(f"\n{'─' * 60}")
        print(f"🔍 Query: {query}")
        print(f"📅 Ref Date: {ref_date}")
        print(f"{'─' * 60}")
        
        result = await rag.search(query, ref_date)
        
        print(f"\n📋 AUDIT:\n{result['audit_trail'][:300]}")
        print(f"\n💬 ANSWER:\n{result['answer'][:300]}")
        print(f"\n📚 Fontes: {len(result['sources'])}")
        print(f"{'─' * 60}")


async def main():
    print("\n" + "=" * 80)
    print("🔬 TESTE DE COMPORTAMENTO RAG V9")
    print("=" * 80)
    
    print("\nEscolha o modo de teste:")
    print("1 - Teste rápido (3 queries)")
    print("2 - Teste completo (7 testes comportamentais)")
    
    choice = input("\nOpção (1/2): ").strip()
    
    if choice == "1":
        await quick_test()
    else:
        tester = RAGBehaviorTester()
        await tester.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())