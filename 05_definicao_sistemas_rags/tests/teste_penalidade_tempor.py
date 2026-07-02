#!/usr/bin/env python3
"""
test_temporal_retriever.py

Testa APENAS o recuperador (retriever) do RAG Temporal V9:
- Embedding da consulta
- Busca FAISS
- Re-rank com penalidade temporal
- Fallback (quando configurado)
- Avaliação contra o dataset (data esperada, presença de documento correto, etc.)

Sem chamadas ao modelo de linguagem (ollama.chat).
Uso:
    python test_temporal_retriever.py
"""

import asyncio
import csv
import json
import sys
import numpy as np
import faiss
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from collections import defaultdict

# Adicionar diretórios ao path
from core.paths import VALIDACAO_SCRIPT, AVALIACAO_SCRIPT
for p in [VALIDACAO_SCRIPT, AVALIACAO_SCRIPT]:
    if p not in sys.path:
        sys.path.append(str(p))

# Importar módulos do RAG
from RAG_Temporal_V9_3 import (
    RAGConfig,
    EmbeddingManager,
    DataLoader,
    FAISSManager,
    TemporalScorer,
    FallbackSearcher,
    QueryExpander,
    SearchPipeline,
)
from dataset_avaliacaoV4 import get_temporal_tests, get_behavioral_tests, TEST_SUITE


# ============================================================================
# CONFIGURAÇÃO
# ============================================================================

BASE_PATH = Path("04_vetorizacao/data/base_conhecimento_multilingueV9.meta.json")
OUTPUT_CSV = Path("05_definicao_sistemas_rags/tests/resultados_temporais_penalidade/resultados_retriever_temporal.csv")

# Parâmetros a testar (produto cartesiano)
PENALTY_RATES = [0.01,0.02,0.03, 0.04, 0.05, 0.06,0.07,0.08,0.09,0.10]
OLD_THRESHOLDS = [1.0, 2.0, 3.0,4.0, 5.0]

# Seleção de testes
TEST_SELECTION = "temporal"  # "temporal", "behavioral", "all"
TEST_IDS_FILTER = None       # ex: ["TC_TEMP_ABS_001"]


# ============================================================================
# FUNÇÕES AUXILIARES
# ============================================================================

def load_tests():
    if TEST_SELECTION == "temporal":
        tests = get_temporal_tests()
    elif TEST_SELECTION == "behavioral":
        tests = get_behavioral_tests()
    else:
        tests = TEST_SUITE
    if TEST_IDS_FILTER:
        tests = [t for t in tests if t.get("id") in TEST_IDS_FILTER]
    return tests


def get_base_name(path: Path) -> str:
    """Retorna o nome base do arquivo sem extensões (ex: 'base' de 'base.meta.json')."""
    return path.name.split('.')[0]


def evaluate_retrieval(docs_retrieved: List[Dict], test: Dict, config: Dict) -> Dict:
    """
    Avalia a recuperação com base nos metadados dos documentos e na data esperada.
    """
    eval_result = {
        "passed": False,
        "reason": "",
        "fallback_activated": False,
        "best_doc_date": None,
        "best_doc_gap": None,
        "best_semantic": None,
        "best_final": None,
        "penalty_applied": None,
        "num_docs": len(docs_retrieved),
        "docs_info": []
    }

    if not docs_retrieved:
        eval_result["reason"] = "Nenhum documento recuperado"
        return eval_result

    best = docs_retrieved[0]
    eval_result["best_doc_date"] = best.get("date", "Unknown")
    eval_result["best_doc_gap"] = best.get("temporal_gap", 0.0)
    eval_result["best_semantic"] = best.get("semantic_score", 0.0)
    eval_result["best_final"] = best.get("final_score", 0.0)
    eval_result["penalty_applied"] = best.get("penalty_applied", 0.0)
    eval_result["fallback_activated"] = "fallback" in best.get("temporal_status", "")

    for i, r in enumerate(docs_retrieved[:5]):
        eval_result["docs_info"].append({
            "rank": i+1,
            "title": r["doc"].get("metadata", {}).get("title", "Unknown"),
            "date": r.get("date", "Unknown"),
            "gap": r.get("temporal_gap", 0.0),
            "semantic": r.get("semantic_score", 0.0),
            "final": r.get("final_score", 0.0),
            "penalty": r.get("penalty_applied", 0.0),
            "status": r.get("temporal_status", ""),
        })

    expected = test.get("expected_behavior", "")
    required = test.get("required_patterns", [])
    forbidden = test.get("forbidden_patterns", [])

    # Avaliação baseada no expected_behavior
    if "should_use_doc_from_2024_or_later" in expected:
        try:
            doc_year = int(eval_result["best_doc_date"][:4]) if eval_result["best_doc_date"] != "Unknown" else 0
            if doc_year >= 2024:
                eval_result["passed"] = True
                eval_result["reason"] = f"Documento mais recente ({eval_result['best_doc_date']}) usado."
            else:
                eval_result["reason"] = f"Documento antigo ({eval_result['best_doc_date']}), esperado >=2024."
        except:
            eval_result["reason"] = f"Data inválida: {eval_result['best_doc_date']}"

    elif "should_use_doc_from_2023" in expected:
        try:
            doc_year = int(eval_result["best_doc_date"][:4])
            if doc_year == 2023:
                eval_result["passed"] = True
                eval_result["reason"] = "Documento de 2023 usado."
            else:
                eval_result["reason"] = f"Documento de {doc_year}, esperado 2023."
        except:
            eval_result["reason"] = f"Data inválida: {eval_result['best_doc_date']}"

    elif "should_use_doc_from_2025_or_later" in expected:
        try:
            doc_year = int(eval_result["best_doc_date"][:4])
            if doc_year >= 2025:
                eval_result["passed"] = True
                eval_result["reason"] = f"Documento mais recente ({eval_result['best_doc_date']}) usado."
            else:
                eval_result["reason"] = f"Documento antigo ({eval_result['best_doc_date']}), esperado >=2025."
        except:
            eval_result["reason"] = f"Data inválida: {eval_result['best_doc_date']}"

    elif "should_admit_unknown_future" in expected or "should_admit_unavailability" in expected:
        if eval_result["num_docs"] == 0:
            eval_result["passed"] = True
            eval_result["reason"] = "Nenhum documento recuperado (esperado para futuro)."
        else:
            try:
                doc_year = int(eval_result["best_doc_date"][:4])
                if doc_year >= 2026:
                    eval_result["reason"] = f"Recuperou documento futuro ({doc_year}), mas esperava nenhum."
                else:
                    eval_result["passed"] = True
                    eval_result["reason"] = f"Recuperou documento de {doc_year} (não futuro)."
            except:
                eval_result["reason"] = f"Data inválida: {eval_result['best_doc_date']}"

    elif "should_use_most_recent_doc" in expected:
        if eval_result["best_doc_gap"] <= 1.0:
            eval_result["passed"] = True
            eval_result["reason"] = f"Documento recente (gap {eval_result['best_doc_gap']:.2f}y)."
        else:
            eval_result["reason"] = f"Documento antigo (gap {eval_result['best_doc_gap']:.2f}y)."

    elif "should_count_slots_correctly" in expected:
        title = eval_result["docs_info"][0]["title"].lower() if eval_result["docs_info"] else ""
        if "2" in title or "two" in title:
            eval_result["passed"] = True
            eval_result["reason"] = "Documento com indicação de 2 slots."
        else:
            eval_result["reason"] = "Documento não indica claramente 2 slots."

    elif "should_identify_correct_last_model" in expected:
        correct_models = [p for p in required if p.startswith("AN") or p.startswith("G") or p.startswith("Legion")]
        if correct_models:
            found = False
            for info in eval_result["docs_info"]:
                title = info["title"]
                for m in correct_models:
                    if m in title:
                        found = True
                        break
                if found:
                    break
            if found:
                eval_result["passed"] = True
                eval_result["reason"] = f"Modelo correto encontrado: {correct_models}"
            else:
                eval_result["reason"] = f"Modelo esperado não encontrado: {correct_models}"
        else:
            eval_result["reason"] = "Sem modelo esperado definido."

    else:
        eval_result["passed"] = True
        eval_result["reason"] = "Comportamento não especificado, assumido como pass (recuperou docs)."

    return eval_result


# ============================================================================
# RETRIEVER TESTER (CORRIGIDO)
# ============================================================================

class RetrieverTester:
    """Testa o retriever sem gerar resposta, com carregamento correto do índice."""

    def __init__(self, base_path: Path, variant_name: str = "V9_HYBRID_MIXED_AUDITOR"):
        self.config = RAGConfig(variant_name)
        self.embedding_manager = EmbeddingManager(model=self.config.embedding_model)
        self.data_loader = DataLoader()

        # Determinar nome base (sem extensões)
        base_name = get_base_name(base_path)
        base_dir = base_path.parent
        self.meta_path = base_dir / f"{base_name}.meta.json"
        self.index_path = base_dir / f"{base_name}.faiss"
        self.npy_path = base_dir / f"{base_name}.npy"
        self.base_no_ext = base_dir / base_name  # sem extensão

        print(f"📂 Base: {base_name}")
        print(f"   Meta: {self.meta_path}")
        print(f"   Índice: {self.index_path}")
        print(f"   Vetores: {self.npy_path}")

        # Carregar metadados: passamos o caminho base sem extensão
        if self.meta_path.exists():
            self.base_docs = self.data_loader.load_from_precomputed(self.base_no_ext)
        else:
            raise FileNotFoundError(f"Arquivo .meta.json não encontrado em {self.meta_path}")

        if not self.base_docs:
            raise RuntimeError("Falha ao carregar metadados.")

        # Inicializar FAISS manager
        self.faiss_manager = FAISSManager(dimension=self.config.embedding_dimension)
        self._load_or_build_index()

        # Inicializar outros componentes
        self.temporal_scorer = TemporalScorer(
            yearly_penalty_rate=self.config.yearly_penalty_rate,
            recency_threshold=self.config.recency_threshold,
            low_coverage_multiplier=self.config.low_coverage_penalty_multiplier
        )
        self.fallback_searcher = FallbackSearcher(
            similarity_threshold=self.config.similarity_threshold,
            max_fallback_docs=self.config.max_fallback_docs,
            old_doc_threshold_years=self.config.old_doc_threshold_years
        )
        self.query_expander = QueryExpander(variant="temporal", max_terms=self.config.max_synonym_terms)
        self.search_pipeline = SearchPipeline(
            faiss_manager=self.faiss_manager,
            data_loader=self.data_loader,
            temporal_scorer=self.temporal_scorer,
            fallback_searcher=self.fallback_searcher,
            config=self.config
        )

    def _load_or_build_index(self):
        """Tenta carregar índice FAISS; se falhar, tenta construir a partir do .npy."""
        if self.index_path.exists():
            print(f"🔍 Tentando carregar índice existente: {self.index_path}")
            if self.faiss_manager.load_index(self.index_path):
                print(f"✅ Índice FAISS carregado com {self.faiss_manager.index.ntotal} vetores.")
                return
            else:
                print("⚠️ Falha ao carregar índice. Tentando recriar...")
        else:
            print("⚠️ Índice FAISS não encontrado.")

        if self.npy_path.exists():
            print(f"📥 Carregando vetores de {self.npy_path}")
            vectors = np.load(self.npy_path)
            if vectors.shape[0] != len(self.base_docs):
                print(f"⚠️ Número de vetores ({vectors.shape[0]}) != documentos ({len(self.base_docs)}). Ajustando...")
                if vectors.shape[0] > len(self.base_docs):
                    vectors = vectors[:len(self.base_docs)]
                else:
                    print(f"⚠️ Apenas {vectors.shape[0]} vetores disponíveis para {len(self.base_docs)} documentos.")
            if vectors.shape[1] != self.config.embedding_dimension:
                print(f"⚠️ Dimensão dos vetores ({vectors.shape[1]}) != esperada ({self.config.embedding_dimension}).")
                self.config.embedding_dimension = vectors.shape[1]
            self.faiss_manager.index = faiss.IndexFlatL2(self.config.embedding_dimension)
            self.faiss_manager.index.add(vectors.astype('float32'))
            self.faiss_manager.stats["total_vectors"] = self.faiss_manager.index.ntotal
            print(f"✅ Índice FAISS construído a partir do .npy com {self.faiss_manager.index.ntotal} vetores.")
        else:
            raise RuntimeError("Nenhum vetor disponível (falta .npy e .faiss).")

    def update_params(self, yearly_penalty_rate: float, old_doc_threshold_years: float):
        self.config.yearly_penalty_rate = yearly_penalty_rate
        self.config.old_doc_threshold_years = old_doc_threshold_years
        self.temporal_scorer.yearly_penalty_rate = yearly_penalty_rate
        self.fallback_searcher.old_doc_threshold_years = old_doc_threshold_years

    async def retrieve(self, query: str, ref_date: str) -> List[Dict]:
        """Executa apenas a busca e retorna os resultados ranqueados."""
        ref_dt = datetime.strptime(ref_date, "%Y-%m-%d")
        expanded_query = self.query_expander.expand_query(query) if self.config.use_expansion else query
        query_vector = await asyncio.to_thread(self.embedding_manager.compute_embedding, expanded_query)
        scored_results = await self.search_pipeline.execute(
            query_vector=query_vector,
            query=query,
            ref_dt=ref_dt,
            expanded_query=expanded_query
        )
        return scored_results


# ============================================================================
# FUNÇÃO PRINCIPAL
# ============================================================================

async def main():
    print("🧪 Teste de Retriever Temporal (sem LLM)")
    print(f"Base: {BASE_PATH}")
    tests = load_tests()
    print(f"Testes: {len(tests)}")

    if not tests:
        print("Nenhum teste selecionado.")
        return

    # Criar diretório de saída se não existir
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)

    # Inicializar o tester
    tester = RetrieverTester(BASE_PATH)

    all_results = []

    for pr in PENALTY_RATES:
        for th in OLD_THRESHOLDS:
            print(f"\n⚙️ Config: penalty_rate={pr}, threshold={th}y")
            tester.update_params(pr, th)

            for test in tests:
                test_id = test.get("id", "unknown")
                query = test["input"]
                ref_date = test.get("reference_date", "2026-06-23")
                print(f"  Executando {test_id}...", end=" ", flush=True)

                try:
                    docs = await tester.retrieve(query, ref_date)
                except Exception as e:
                    print(f"❌ ERRO: {e}")
                    docs = []

                eval_res = evaluate_retrieval(docs, test, {
                    "yearly_penalty_rate": pr,
                    "old_doc_threshold_years": th
                })

                record = {
                    "test_id": test_id,
                    "config_penalty_rate": pr,
                    "config_threshold": th,
                    "ref_date": ref_date,
                    "query": query,
                    "expected_behavior": test.get("expected_behavior", ""),
                    "passed": eval_res["passed"],
                    "reason": eval_res["reason"],
                    "best_doc_date": eval_res["best_doc_date"],
                    "best_doc_gap": eval_res["best_doc_gap"],
                    "best_semantic": eval_res["best_semantic"],
                    "best_final": eval_res["best_final"],
                    "penalty_applied": eval_res["penalty_applied"],
                    "num_docs": eval_res["num_docs"],
                    "fallback_activated": eval_res["fallback_activated"],
                    "top_docs_json": json.dumps(eval_res["docs_info"], ensure_ascii=False),
                }
                all_results.append(record)

                status = "✅ PASS" if eval_res["passed"] else "❌ FAIL"
                print(f"{status} ({eval_res['reason'][:60]})")

    # Salvar CSV
    print(f"\n📝 Salvando relatório em {OUTPUT_CSV}")
    fieldnames = [
        "test_id", "config_penalty_rate", "config_threshold", "ref_date",
        "query", "expected_behavior", "passed", "reason",
        "best_doc_date", "best_doc_gap", "best_semantic", "best_final",
        "penalty_applied", "num_docs", "fallback_activated", "top_docs_json"
    ]
    with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for rec in all_results:
            writer.writerow(rec)

    # Estatísticas
    total = len(all_results)
    passed = sum(1 for r in all_results if r["passed"])
    print(f"\n📊 Resumo: {passed}/{total} passaram ({passed/total*100:.1f}%)")

    by_config = defaultdict(lambda: {"total": 0, "pass": 0})
    for r in all_results:
        key = (r["config_penalty_rate"], r["config_threshold"])
        by_config[key]["total"] += 1
        if r["passed"]:
            by_config[key]["pass"] += 1

    print("\nDesempenho por configuração:")
    for (pr, th), stats in sorted(by_config.items()):
        pct = stats["pass"] / stats["total"] * 100 if stats["total"] else 0
        print(f"  penalty_rate={pr}, threshold={th}y: {stats['pass']}/{stats['total']} ({pct:.1f}%)")


if __name__ == "__main__":
    if not BASE_PATH.exists():
        print(f"❌ Base não encontrada: {BASE_PATH}")
        sys.exit(1)
    asyncio.run(main())