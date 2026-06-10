"""
RAG Temporal V9 - Equalizado com V1 (apenas diferença temporal)
Formato de saída: limpo, sem blocos AUDIT, sem tags [RAG:...]
Regras comportamentais: idênticas ao V1 (SKU lock, série, fallback transparente)
"""

import asyncio
import faiss
import gc
import ijson
import json
import numpy as np
import ollama
import re
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any, Set, Union

# ============================================================================
# CONFIGURAÇÃO
# ============================================================================

class RAGConfig:
    def __init__(self):
        self.embedding_dimension: int = 1024
        self.current_model: str = "phi3.5:latest"
        self.embedding_model: str = "bge-m3:latest"
        self.search_top_k: int = 20
        self.similarity_threshold: float = 1.2
        self.max_context_chars: int = 2000
        
        # Parâmetros temporais
        self.yearly_penalty_rate: float = 0.04      # 4% de penalidade por ano
        self.old_doc_threshold_years: float = 2.0   # >2 anos ativa fallback
        self.recency_threshold: int = 3
        self.low_coverage_penalty_multiplier: float = 0.3
        self.fallback_semantic_threshold: float = 1.15
        self.max_fallback_docs: int = 3
        self.max_results_returned: int = 8
        
        # Expansão
        self.use_expansion: bool = True
        self.max_synonym_terms: int = 5
        
        # Geração
        self.temperature: float = 0.0
        self.top_p: float = 0.9
        
        self.verbose: bool = True

    def log(self, message: str) -> None:
        if self.verbose:
            print(message)


# ============================================================================
# CACHE
# ============================================================================

class EmbeddingCache:
    def __init__(self, cache_dir: Optional[Path] = None, max_size: int = 1000):
        self.cache_dir = cache_dir
        self.max_size = max_size
        self._cache: Dict[str, np.ndarray] = {}
        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)
            self._load_existing()

    def _get_key(self, query: str) -> str:
        import hashlib
        return hashlib.md5(query.encode()).hexdigest()

    def _load_existing(self) -> None:
        for path in self.cache_dir.glob("*.pkl"):
            if len(self._cache) >= self.max_size:
                break
            try:
                import pickle
                with open(path, 'rb') as f:
                    self._cache[path.stem] = pickle.load(f)
            except:
                pass

    def get(self, query: str) -> Optional[np.ndarray]:
        key = self._get_key(query)
        return self._cache.get(key)

    def set(self, query: str, embedding: np.ndarray) -> None:
        key = self._get_key(query)
        if len(self._cache) >= self.max_size:
            oldest = next(iter(self._cache))
            del self._cache[oldest]
            if self.cache_dir:
                (self.cache_dir / f"{oldest}.pkl").unlink(missing_ok=True)
        self._cache[key] = embedding.copy()
        if self.cache_dir:
            import pickle
            with open(self.cache_dir / f"{key}.pkl", 'wb') as f:
                pickle.dump(embedding, f)

    def stats(self) -> Dict:
        return {"size": len(self._cache), "max_size": self.max_size}


# ============================================================================
# DATA LOADER
# ============================================================================

class DataLoader:
    def __init__(self):
        self.documents: List[Dict] = []
        self.stats = {"total_loaded": 0, "with_vectors": 0, "with_dates": 0, "errors": 0}

    def load_documents(self, json_path: Union[str, Path]) -> List[Dict]:
        path = Path(json_path)
        if not path.exists():
            raise FileNotFoundError(f"Arquivo não encontrado: {json_path}")

        self.documents = []
        self.stats = {k: 0 for k in self.stats}

        with open(path, 'rb') as f:
            for item in ijson.items(f, 'item'):
                processed = self._process_document(item)
                if processed:
                    self.documents.append(processed)
                    self.stats["total_loaded"] += 1

        print(f"✅ Base carregada: {len(self.documents)} documentos")
        print(f"   📊 Stats: {self.stats['total_loaded']} docs | {self.stats['with_vectors']} vectors | {self.stats['with_dates']} dates")
        return self.documents

    def _process_document(self, doc: Dict) -> Optional[Dict]:
        try:
            processed = doc.copy()
            if 'vector' in processed:
                self.stats["with_vectors"] += 1
            if 'date_iso' in processed:
                processed['date_iso'] = processed['date_iso'][:10]
                self.stats["with_dates"] += 1
            else:
                processed['date_iso'] = '2024-01-01'
            if 'id' not in processed:
                processed['id'] = hash(processed.get('original_text', '')) % 1000000
            if 'metadata' not in processed:
                processed['metadata'] = {}
            return processed
        except Exception:
            self.stats["errors"] += 1
            return None

    def get_document_by_id(self, doc_id: int) -> Optional[Dict]:
        for doc in self.documents:
            if doc.get('id') == doc_id:
                return doc
        return None


# ============================================================================
# EMBEDDING MANAGER
# ============================================================================

class EmbeddingManager:
    def __init__(self, model: str = "bge-m3:latest", host: str = "http://localhost:11434"):
        self.model = model
        self.host = host
        self.dimension: Optional[int] = None
        self.client = ollama.Client(host=self.host)
        self._test_connection()

    def _test_connection(self) -> None:
        try:
            test_result = self.client.embeddings(model=self.model, prompt="test")
            if 'embedding' in test_result:
                self.dimension = len(test_result['embedding'])
                print(f"✅ Conexão com {self.model} - dimensão: {self.dimension}")
        except Exception as e:
            print(f"⚠️ {self.model} pode não estar disponível: {e}")
            self.dimension = 1024

    def compute_embedding(self, text: str) -> np.ndarray:
        if not text or not text.strip():
            text = " "
        try:
            result = self.client.embeddings(model=self.model, prompt=text)
            return np.array(result['embedding'], dtype=np.float32)
        except ollama.ResponseError as e:
            if "NaN" in str(e):
                print(f"⚠️ NaN detectado para texto: '{text[:50]}...'")
                return np.zeros(self.dimension if self.dimension else 1024, dtype=np.float32)
            raise


# ============================================================================
# FAISS MANAGER
# ============================================================================

class FAISSManager:
    def __init__(self, dimension: int = 1024):
        self.dimension = dimension
        self.index: Optional[faiss.IndexFlatL2] = None
        self.stats = {"total_vectors": 0, "searches_performed": 0}

    def build_index(self, documents: List[Dict]) -> None:
        if not documents:
            return
        vectors = self._extract_vectors(documents)
        if vectors is None or len(vectors) == 0:
            print("⚠️ Nenhum vetor válido")
            return
        self.index = faiss.IndexFlatL2(self.dimension)
        self.index.add(vectors)
        self.stats["total_vectors"] = self.index.ntotal
        print(f"✅ Índice FAISS criado com {self.index.ntotal} vetores")

    def _extract_vectors(self, documents: List[Dict]) -> Optional[np.ndarray]:
        vectors = []
        for doc in documents:
            if 'vector' in doc:
                vec = np.array(doc['vector'], dtype=np.float32)
                if len(vec) == self.dimension:
                    vectors.append(vec)
        return np.array(vectors).astype('float32') if vectors else None

    def search(self, query_vector: np.ndarray, k: int = 20) -> List[Tuple[int, float]]:
        if self.index is None:
            return []
        if query_vector.ndim == 1:
            query_vector = query_vector.reshape(1, -1)
        distances, indices = self.index.search(query_vector, k)
        results = [(int(idx), float(distances[0][i])) for i, idx in enumerate(indices[0]) if idx != -1]
        self.stats["searches_performed"] += 1
        return results


# ============================================================================
# TEMPORAL SCORER (interna, não aparece na resposta)
# ============================================================================

class TemporalScorer:
    def __init__(self, yearly_penalty_rate: float = 0.04, recency_threshold: int = 3,
                 low_coverage_multiplier: float = 0.3):
        self.yearly_penalty_rate = yearly_penalty_rate

    def calculate_temporal_gap(self, doc_date: str, ref_date: datetime) -> float:
        try:
            doc_dt = datetime.strptime(doc_date[:10], "%Y-%m-%d")
            return (ref_date - doc_dt).days / 365.25
        except:
            return 0.0

    def score_document(self, semantic_score: float, temporal_gap: float) -> float:
        """Aplica penalidade: score final = semantic_score * (1 + gap * taxa)"""
        if temporal_gap <= 0:
            return semantic_score
        penalty = 1.0 + (temporal_gap * self.yearly_penalty_rate)
        return semantic_score * penalty


# ============================================================================
# FALLBACK SEARCHER (semântico quando todos docs são antigos)
# ============================================================================

class FallbackSearcher:
    def __init__(self, old_doc_threshold_years: float = 2.0, max_fallback_docs: int = 3):
        self.old_doc_threshold_years = old_doc_threshold_years
        self.max_fallback_docs = max_fallback_docs

    def should_activate(self, scored_results: List[Dict]) -> bool:
        if not scored_results:
            return False
        best_gap = scored_results[0].get('temporal_gap', 0)
        recent_count = sum(1 for r in scored_results if r.get('temporal_gap', 0) < 0.5)
        return best_gap > self.old_doc_threshold_years and recent_count < 2

    def semantic_only_search(self, query_vector: np.ndarray, index, all_docs: List[Dict],
                             ref_date: datetime, existing_ids: Set[int]) -> List[Dict]:
        k = self.max_fallback_docs * 3
        distances, indices = index.search(query_vector, k=k)
        fallback = []
        for i, idx in enumerate(indices[0]):
            if idx == -1 or idx in existing_ids:
                continue
            doc = all_docs[idx]
            semantic_score = distances[0][i]
            if semantic_score < 1.3:  # tolerância maior
                doc_date = doc.get('date_iso', '2024-01-01')[:10]
                gap = self._calculate_gap(doc_date, ref_date)
                fallback.append({
                    'doc': doc,
                    'idx': idx,
                    'semantic_score': semantic_score,
                    'final_score': semantic_score * 0.95,  # pequeno bônus para fallback
                    'temporal_gap': gap,
                    'date': doc_date
                })
        fallback.sort(key=lambda x: x['semantic_score'])
        return fallback[:self.max_fallback_docs]

    def _calculate_gap(self, doc_date: str, ref_date: datetime) -> float:
        try:
            doc_dt = datetime.strptime(doc_date[:10], "%Y-%m-%d")
            return (ref_date - doc_dt).days / 365.25
        except:
            return 0.0


# ============================================================================
# CONTEXT BUILDER (sem tags, formato limpo)
# ============================================================================

class ContextBuilder:
    def __init__(self, max_chars: int = 2000):
        self.max_chars = max_chars

    def build_context(self, scored_results: List[Dict]) -> str:
        context_parts = []
        for i, res in enumerate(scored_results[:5]):
            doc = res['doc']
            text = doc.get('original_text', '')[:self.max_chars]
            # Sem tags, apenas o texto
            context_parts.append(text)
        return "\n\n".join(context_parts)


# ============================================================================
# QUERY EXPANDER (SKU detection – igual ao V1)
# ============================================================================

class QueryExpander:
    def __init__(self):
        self.known_skus = [
            '15ach6', '15ach6h', '15iah7', '15arp8', '15imh6', '15ith6', '15irx9',
            'an515-56', 'an515-57', 'an515-58', 'an515-46', 'an515-47',
            'g7 7588', 'g7 7590', 'g15 5510', 'g15 5520', 'xps 15 9500',
            'fx507', 'fa507', 'gv301', 'gz301', 'victus 15-fa', 'victus 16-d', 'omen 16-wf'
        ]
        self.sku_pattern = re.compile(r'[A-Z]{2,3}[-]?\d{3}[-]?\d{2,4}|\d{2,4}[A-Z]{2,4}|[A-Z]{2,3}\s\d{3}\s\d{4}', re.IGNORECASE)

    def has_specific_sku(self, query: str) -> bool:
        query_lower = query.lower()
        for sku in self.known_skus:
            if sku in query_lower:
                return True
        if self.sku_pattern.search(query):
            return True
        return False

    def expand_query(self, query: str) -> str:
        # Expansão simplificada - apenas retorna a query original se não houver SKU
        if self.has_specific_sku(query):
            return query
        return query  # Poderia adicionar sinônimos, mas mantemos simples


# ============================================================================
# SYSTEM PROMPT (idêntico ao V1 – sem auditoria, sem tags)
# ============================================================================

SYSTEM_PROMPT_V1_EQUAL = """You are a technical support assistant. You have access to EXTERNAL context (retrieved documents) and your INTERNAL knowledge. You may combine both sources to provide the best answer.

RULES:
1. CLASSIFY the user query as: SPECIFIC_SKU, GENERAL_TECH, COMPARISON, or SERIES.

2. SPECIFIC_SKU (SKU mentioned in query):
   - You MAY use EXTERNAL context if available.
   - If EXTERNAL context has direct info → use it (prefer it for specs).
   - If EXTERNAL context is missing or incomplete → you MAY use INTERNAL knowledge, but you MUST clearly state that external documentation was not found.
   - Example: "No external documentation found for [SKU]. Based on general knowledge, typical specs are..."
   - NEVER present INTERNAL knowledge as official documentation.

3. GENERAL_TECH (no SKU, concepts, troubleshooting):
   - You may freely use EXTERNAL + INTERNAL knowledge.

4. COMPARISON (two SKUs):
   - Use EXTERNAL context for each SKU if available.
   - If one or both SKUs lack external docs, you may use INTERNAL knowledge but must indicate which part is from internal knowledge.

5. SERIES (product line without SKU, e.g., "Nitro 5", "Dell G15 series"):
   - DO NOT answer the technical question with specs.
   - MUST ask: "Could you provide the specific model number (SKU)?"

6. INTERNAL KNOWLEDGE RULES:
   - ALLOWED: general concepts, typical configurations, industry standards, troubleshooting.
   - FORBIDDEN: Inventing specs for a SKU without any basis.

7. WHEN EXTERNAL CONTEXT IS MISSING: State that clearly before providing internal knowledge (except for SERIES queries).

8. FORMAT: Write a clean, natural, customer-facing response. DO NOT use any tags like [RAG], [INTERNAL], or audit sections. DO NOT include block headers like "AUDIT:" or "ANSWER:". Just provide the answer directly."""


# ============================================================================
# RAG ENGINE PRINCIPAL (com temporalidade, mas saída limpa)
# ============================================================================

class SpecialistTimeAwareRAGEqual:
    def __init__(self, json_path: Union[str, Path], embedding_cache=None, use_expansion: bool = True):
        print(f"--- 🧠 RAG TEMPORAL EQUALIZADO (V9_EQUAL) ---")
        self.config = RAGConfig()
        self.config.use_expansion = use_expansion

        self.cache_manager = embedding_cache
        self.embedding_manager = EmbeddingManager(model=self.config.embedding_model)
        self.data_loader = DataLoader()
        self.data_loader.load_documents(json_path)

        self.faiss_manager = FAISSManager(dimension=self.config.embedding_dimension)
        if self.data_loader.documents:
            self.faiss_manager.build_index(self.data_loader.documents)

        self.temporal_scorer = TemporalScorer(yearly_penalty_rate=self.config.yearly_penalty_rate)
        self.fallback_searcher = FallbackSearcher(
            old_doc_threshold_years=self.config.old_doc_threshold_years,
            max_fallback_docs=self.config.max_fallback_docs
        )
        self.query_expander = QueryExpander()
        self.context_builder = ContextBuilder(max_chars=self.config.max_context_chars)

        print(f"✅ Sistema inicializado com {len(self.data_loader.documents)} documentos")
        print(f"   Temporal: {self.config.yearly_penalty_rate*100}%/year penalty, fallback after {self.config.old_doc_threshold_years}y")

    async def _get_embedding(self, query: str) -> np.ndarray:
        if self.cache_manager:
            cached = self.cache_manager.get(query)
            if cached is not None:
                return cached
            embedding = await asyncio.to_thread(self.embedding_manager.compute_embedding, query)
            self.cache_manager.set(query, embedding)
            return embedding
        return await asyncio.to_thread(self.embedding_manager.compute_embedding, query)

    async def search(self, query: str, ref_date: str = "2026-03-23") -> Dict:
        print(f"🔍 Processando: {query[:60]}...")
        ref_dt = datetime.strptime(ref_date, "%Y-%m-%d")

        # Expansão (igual ao V1)
        expanded_query = self.query_expander.expand_query(query) if self.config.use_expansion else query

        # Embedding
        query_vector = await self._get_embedding(expanded_query)

        # 1. Busca inicial
        search_results = self.faiss_manager.search(query_vector, k=self.config.search_top_k)

        # 2. Aplica penalidade temporal
        scored_results = []
        for idx, semantic_dist in search_results:
            doc = self.data_loader.documents[idx]
            doc_date = doc.get('date_iso', '2024-01-01')[:10]
            gap = self.temporal_scorer.calculate_temporal_gap(doc_date, ref_dt)
            final_score = self.temporal_scorer.score_document(semantic_dist, gap)
            scored_results.append({
                'doc': doc,
                'idx': idx,
                'semantic_score': semantic_dist,
                'final_score': final_score,
                'temporal_gap': gap,
                'date': doc_date
            })
        scored_results.sort(key=lambda x: x['final_score'])

        # 3. Fallback se necessário (temporal adaptativo)
        if self.fallback_searcher.should_activate(scored_results):
            self.config.log("🔄 Ativando fallback sem penalidade temporal...")
            existing_ids = {r['idx'] for r in scored_results}
            fallback_results = self.fallback_searcher.semantic_only_search(
                query_vector.reshape(1, -1), self.faiss_manager.index,
                self.data_loader.documents, ref_dt, existing_ids
            )
            if fallback_results:
                merged = scored_results[:4]
                for fb in fallback_results:
                    if len(merged) >= self.config.max_results_returned:
                        break
                    merged.append(fb)
                merged.sort(key=lambda x: x['final_score'])
                final_results = merged[:self.config.max_results_returned]
            else:
                final_results = scored_results[:self.config.max_results_returned]
        else:
            final_results = scored_results[:self.config.max_results_returned]

        # 4. Construção de contexto limpo (sem tags)
        context_str = self.context_builder.build_context(final_results)

        # 5. Geração da resposta com prompt igual ao V1
        user_content = f"CONTEXT:\n{context_str}\n\nUSER_QUERY:\n{query}\n\nRESPONSE:"

        response = await asyncio.to_thread(
            ollama.chat,
            model=self.config.current_model,
            messages=[
                {'role': 'system', 'content': SYSTEM_PROMPT_V1_EQUAL},
                {'role': 'user', 'content': user_content}
            ],
            options={"temperature": self.config.temperature, "top_p": self.config.top_p},
            keep_alive=0
        )

        answer = response['message']['content'].strip()

        # Remove qualquer "ANSWER:" residual que o modelo possa erroneamente incluir
        if answer.lower().startswith("answer:"):
            answer = answer[7:].strip()

        gc.collect()

        return {
            "answer": answer,
            "sources": [r['doc'].get('original_text', '') for r in final_results[:5]],
            "titles": [r['doc'].get('metadata', {}).get('title', 'Unknown') for r in final_results[:5]],
            "normalized_query": expanded_query,
            "diagnostic": {
                "num_documents_retrieved": len(final_results),
                "best_temporal_gap_years": round(final_results[0]['temporal_gap'], 2) if final_results else 0,
                "fallback_used": self.fallback_searcher.should_activate(scored_results)
            }
        }