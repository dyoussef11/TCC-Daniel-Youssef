"""
RAG Temporal V9 - Compacto (Versão Corrigida)
Sistema de RAG com consciência temporal, fallback inteligente e SAÍDA LIMPA.
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
    """Configurações centralizadas do RAG Temporal."""
    
    def __init__(self, variant_name: str = "V9_HYBRID_MIXED_AUDITOR"):
        # Modelo e dimensões
        self.embedding_dimension: int = 1024
        self.current_model: str = "phi3.5:latest"
        self.embedding_model: str = "bge-m3:latest"
        
        # Busca
        self.search_top_k: int = 50
        self.similarity_threshold: float = 1.2
        self.max_context_chars: int = 2000
        
        # Temporalidade adaptativa
        self.yearly_penalty_rate: float = 0.04
        self.old_doc_threshold_years: float = 2.0
        self.recency_threshold: int = 3
        self.low_coverage_penalty_multiplier: float = 0.3
        self.fallback_semantic_threshold: float = 1.15
        self.max_fallback_docs: int = 5
        self.max_results_returned: int = 5
        
        # Expansão de query
        self.use_expansion: bool = True
        self.max_synonym_terms: int = 5
        
        # Modelo
        self.temperature: float = 0.0
        self.top_p: float = 0.9
        
        # Variante e prompts
        self.variant_name: str = variant_name
        self.prompts_dir: Optional[Path] = None
        
        # Logging
        self.verbose: bool = True

        

    def log(self, message: str) -> None:
        if self.verbose:
            print(message)


# ============================================================================
# CACHE DE EMBEDDINGS
# ============================================================================

class EmbeddingCache:
    """Cache LRU para embeddings de queries."""
    
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
        if not self.cache_dir:
            return
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
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
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
    """Carrega documentos JSON com suporte a streaming."""
    
    def __init__(self):
        self.documents: List[Dict] = []
        self.stats = {"total_loaded": 0, "with_vectors": 0, "with_metadata": 0, "with_dates": 0, "errors": 0}
    
    def load_documents(self, json_path: Union[str, Path]) -> List[Dict]:
        try:
            path = Path(json_path)
            if not path.exists():
                raise FileNotFoundError(f"Arquivo não encontrado: {json_path}")
            self.documents = []
            self.stats = self._get_initial_stats()
            with open(path, 'rb') as f:
                for item in ijson.items(f, 'item'):
                    processed = self._process_document(item)
                    if processed:
                        self.documents.append(processed)
                        self.stats["total_loaded"] += 1
            print(f"✅ Base carregada: {len(self.documents)} documentos")
            print(f"   📊 Stats: {self.stats['total_loaded']} docs | {self.stats['with_vectors']} vectors | {self.stats['with_dates']} dates")
            return self.documents
        except Exception as e:
            print(f"❌ Erro ao carregar base: {e}")
            return []
    
    def _process_document(self, doc: Dict) -> Optional[Dict]:
        try:
            processed = doc.copy()
            if 'vector' in processed:
                self.stats["with_vectors"] += 1
            if 'metadata' not in processed:
                processed['metadata'] = {}
            else:
                self.stats["with_metadata"] += 1
            if 'date_iso' in processed:
                processed['date_iso'] = processed['date_iso'][:10]
                self.stats["with_dates"] += 1
            else:
                processed['date_iso'] = '2024-01-01'
            if 'id' not in processed:
                processed['id'] = hash(processed.get('original_text', '')) % 1000000
            return processed
        except Exception:
            self.stats["errors"] += 1
            return None
    
    def _get_initial_stats(self) -> Dict:
        return {"total_loaded": 0, "with_vectors": 0, "with_metadata": 0, "with_dates": 0, "errors": 0}
    
    def get_document_by_id(self, doc_id: int) -> Optional[Dict]:
        for doc in self.documents:
            if doc.get('id') == doc_id:
                return doc
        return None

    def load_from_precomputed(self, base_path: Path) -> List[Dict]:
        """Carrega metadados do .meta.json (ignora o JSON gigante)."""
        meta_path = base_path.with_suffix('.meta.json')
        if not meta_path.exists():
            raise FileNotFoundError(f"Arquivo .meta.json não encontrado: {meta_path}")
        
        with open(meta_path, 'r', encoding='utf-8') as f:
            self.documents = json.load(f)
        
        self.stats["total_loaded"] = len(self.documents)
        print(f"✅ Metadados carregados: {len(self.documents)} documentos (via .meta.json)")
        return self.documents


# ============================================================================
# EMBEDDING MANAGER
# ============================================================================

class EmbeddingManager:
    """Gerencia a criação de embeddings usando Ollama em CPU."""
    
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
                print(f"✅ Conexão com {self.model} (CPU) estabelecida - dimensão: {self.dimension}")
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
                print(f"⚠️ Erro de NaN no embedding para texto: '{text[:50]}...'")
                dim = self.dimension if self.dimension else 1024
                return np.zeros(dim, dtype=np.float32)
            raise
    
    def compute_embeddings_batch(self, texts: List[str]) -> np.ndarray:
        embeddings = [self.compute_embedding(text) for text in texts]
        return np.array(embeddings)


# ============================================================================
# FAISS MANAGER
# ============================================================================

class FAISSManager:
    """Gerencia índice FAISS para busca vetorial."""
    
    def __init__(self, dimension: int = 1024):
        self.dimension = dimension
        self.index: Optional[faiss.IndexFlatL2] = None
        self.stats = {"total_vectors": 0, "last_search_time": 0, "searches_performed": 0}
    
    def build_index(self, documents: List[Dict]) -> None:
        if not documents:
            print("⚠️ Nenhum documento para indexar")
            return
        vectors = self._extract_vectors(documents)
        if vectors is None or len(vectors) == 0:
            print("⚠️ Nenhum vetor válido encontrado")
            return
        self.index = faiss.IndexFlatL2(self.dimension)
        self.index.add(vectors)
        self.stats["total_vectors"] = self.index.ntotal
        print(f"✅ Index FAISS criado com {self.index.ntotal} vetores (dimensão {self.dimension})")
    
    def _extract_vectors(self, documents: List[Dict]) -> Optional[np.ndarray]:
        vectors = []
        for doc in documents:
            if 'vector' in doc:
                vec = np.array(doc['vector'], dtype=np.float32)
                if len(vec) == self.dimension:
                    vectors.append(vec)
        return np.array(vectors).astype('float32') if vectors else None
    
    def search(self, query_vector: np.ndarray, k: int = 20) -> List[Tuple[int, float]]:
        import time
        if self.index is None:
            return []
        start_time = time.time()
        if query_vector.ndim == 1:
            query_vector = query_vector.reshape(1, -1)
        distances, indices = self.index.search(query_vector, k)
        results = [(int(idx), float(distances[0][i])) for i, idx in enumerate(indices[0]) if idx != -1]
        self.stats["searches_performed"] += 1
        self.stats["last_search_time"] = time.time() - start_time
        return results
    
    def get_index_stats(self) -> Dict:
        stats = self.stats.copy()
        if self.index:
            stats.update({"index_size": self.index.ntotal, "dimension": self.index.d})
        return stats

    def load_index(self, index_path: Path) -> bool:
        if index_path.exists():
            self.index = faiss.read_index(str(index_path))
            self.stats["total_vectors"] = self.index.ntotal
            print(f"✅ Índice FAISS carregado de {index_path} ({self.index.ntotal} vetores)")
            return True
        return False


# ============================================================================
# TEMPORAL SCORER
# ============================================================================

class TemporalScorer:
    """Aplica penalidade temporal adaptativa."""
    
    def __init__(self, yearly_penalty_rate: float = 0.03, recency_threshold: int = 3,
                 low_coverage_multiplier: float = 0.3):
        self.yearly_penalty_rate = yearly_penalty_rate
        self.recency_threshold = recency_threshold
        self.low_coverage_multiplier = low_coverage_multiplier
    
    def calculate_temporal_gap(self, doc_date: str, ref_date: datetime) -> float:
        try:
            doc_dt = datetime.strptime(doc_date[:10], "%Y-%m-%d")
            return (ref_date - doc_dt).days / 365.25
        except (ValueError, IndexError):
            return 0.0
    
    def calculate_domain_recency(self, doc_model: str, ref_date: datetime, all_docs: List[Dict]) -> float:
        if not doc_model:
            return 1.0
        recent_count = 0
        for other in all_docs:
            other_model = other.get('metadata', {}).get('model', '')
            if other_model == doc_model:
                other_date = other.get('date_iso', '2024-01-01')[:10]
                try:
                    other_dt = datetime.strptime(other_date, "%Y-%m-%d")
                    if other_dt > ref_date:
                        recent_count += 1
                except ValueError:
                    pass
        recency_ratio = min(recent_count / self.recency_threshold, 1.0)
        return max(self.low_coverage_multiplier, recency_ratio)
    
    def score_document(self, semantic_score: float, temporal_gap: float, recency_multiplier: float) -> Tuple[float, float, str]:
        if temporal_gap <= 0:
            return semantic_score, 0.0, "future_or_current"
        base_penalty = 1.0 + (temporal_gap * self.yearly_penalty_rate)
        final_penalty = 1.0 + (base_penalty - 1.0) * recency_multiplier
        final_score = semantic_score * final_penalty
        return final_score, final_penalty - 1.0, f"old_gap_{temporal_gap:.1f}y"
    
    def get_penalty_stats(self, scored_results: List[Dict]) -> Dict:
        if not scored_results:
            return {"avg_penalty": 0, "max_penalty": 0, "docs_with_penalty": 0}
        penalties = [r.get('penalty_applied', 0) for r in scored_results]
        return {
            "avg_penalty": round(sum(penalties) / len(penalties), 4),
            "max_penalty": round(max(penalties), 4),
            "docs_with_penalty": sum(1 for p in penalties if p > 0),
            "total_docs": len(scored_results)
        }


# ============================================================================
# FALLBACK SEARCHER
# ============================================================================

class FallbackSearcher:
    def __init__(self, similarity_threshold: float = 1.2, max_fallback_docs: int = 3, old_doc_threshold_years: float = 2.0):
        self.similarity_threshold = similarity_threshold
        self.max_fallback_docs = max_fallback_docs
        self.old_doc_threshold_years = old_doc_threshold_years
    
    def should_activate(self, scored_results: List[Dict]) -> bool:
        if not scored_results:
            return False
        best_doc_age = scored_results[0].get('temporal_gap', 0)
        recent_docs_count = sum(1 for r in scored_results if r.get('temporal_gap', 0) < 0.5)
        return best_doc_age > self.old_doc_threshold_years and recent_docs_count < 2
    
    def semantic_only_search(self, query_vector: np.ndarray, index, all_docs: List[Dict],
                            ref_date: datetime, existing_ids: Set[int]) -> List[Dict]:
        k_search = self.max_fallback_docs * 3
        distances, indices = index.search(query_vector, k=k_search)
        fallback_results = []
        for i, idx in enumerate(indices[0]):
            if idx == -1:
                continue
            doc = all_docs[idx]
            doc_id = doc.get('id', idx)
            if doc_id in existing_ids:
                continue
            semantic_score = distances[0][i]
            if semantic_score < self.similarity_threshold * 1.1:
                doc_date = doc.get('date_iso', '2024-01-01')[:10]
                temporal_gap = self._calculate_gap(doc_date, ref_date)
                fallback_results.append({
                    'doc': doc,
                    'semantic_score': semantic_score,
                    'final_score': semantic_score * 1.05,
                    'temporal_gap': temporal_gap,
                    'temporal_status': "fallback_no_penalty",
                    'penalty_applied': 0.05,
                    'date': doc_date
                })
        fallback_results.sort(key=lambda x: x['semantic_score'])
        return fallback_results[:self.max_fallback_docs]
    
    def _calculate_gap(self, doc_date: str, ref_date: datetime) -> float:
        try:
            doc_dt = datetime.strptime(doc_date[:10], "%Y-%m-%d")
            return (ref_date - doc_dt).days / 365.25
        except (ValueError, IndexError):
            return 0.0


# ============================================================================
# QUERY EXPANDER (SKU Detection)
# ============================================================================

class QueryExpander:
    def __init__(self, hierarchical_path: Optional[Path] = None, flat_dict_path: Optional[Path] = None,
                 max_terms: int = 5, variant: str = "temporal"):
        self.max_terms = max_terms
        self.variant = variant
        self.hierarchical = {}
        self.flat_dict = {}
        if hierarchical_path and hierarchical_path.exists():
            self._load_hierarchical(hierarchical_path)
        if flat_dict_path and flat_dict_path.exists():
            self._load_flat(flat_dict_path)
    
    def _load_hierarchical(self, path: Path) -> None:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                self.hierarchical = json.load(f)
            print(f"✅ Dicionário hierárquico carregado: {len(self.hierarchical)} marcas")
        except Exception as e:
            print(f"⚠️ Erro ao carregar dicionário hierárquico: {e}")
    
    def _load_flat(self, path: Path) -> None:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                self.flat_dict = json.load(f)
            print(f"✅ Dicionário flat carregado: {len(self.flat_dict)} entradas")
        except Exception as e:
            print(f"⚠️ Erro ao carregar dicionário flat: {e}")
    
    def has_specific_sku(self, query: str) -> bool:
        query_lower = query.lower()
        known_skus = [
            '15ach6', '15ach6h', '15iah7', '15arp8', '15imh6', '15ith6', '15irx9',
            'an515-56', 'an515-57', 'an515-58', 'an515-46', 'an515-47',
            'g7 7588', 'g7 7590', 'g15 5510', 'g15 5520', 'xps 15 9500',
            'fx507', 'fa507', 'gv301', 'gz301',
            'victus 15-fa', 'victus 16-d', 'omen 16-wf',
        ]
        for sku in known_skus:
            if sku in query_lower:
                print(f"   🔒 SKU conhecido detectado: {sku}")
                return True
        sku_patterns = [
            r'[A-Z]{2,3}[-]?\d{3}[-]?\d{2,4}',
            r'\d{2,4}[A-Z]{2,4}',
            r'[A-Z]{2,3}\s\d{3}\s\d{4}',
            r'[a-z]{3,4}\d{4}',
        ]
        for pattern in sku_patterns:
            if re.search(pattern, query, re.IGNORECASE):
                print(f"   🔒 SKU detectado pelo padrão")
                return True
        return False
    
    def expand_query(self, query: str) -> str:
        if self.has_specific_sku(query):
            print(f"   🚫 SKU detectado - expansão CANCELADA")
            return query
        return query


# ============================================================================
# PROMPT MANAGER (CORRIGIDO - CARREGA DO JSON)
# ============================================================================

class PromptManager:
    """Gerencia prompts do sistema RAG carregando do arquivo JSON."""
    
    def __init__(self, variant_name: str = "V9_HYBRID_MIXED_AUDITOR", prompts_path: Optional[Path] = None):
        self.variant_name = variant_name
        self.prompts_path = prompts_path
        self.prompt_data = None
        self._load_prompt_variant()
    
    def _load_prompt_variant(self):
        """Carrega a variante específica do arquivo JSON."""
        if self.prompts_path is None:
            # Caminho padrão - ajuste conforme sua estrutura de diretórios
            from core.paths import VALIDACAO_CONFIG
            self.prompts_path = VALIDACAO_CONFIG / 'prompt_rag_temporal_hybrid_V9.json'
        
        if not self.prompts_path.exists():
            print(f"⚠️ Arquivo de prompts não encontrado em {self.prompts_path}. Usando fallback hardcoded.")
            self._fallback_prompt()
            return
        
        try:
            with open(self.prompts_path, 'r', encoding='utf-8') as f:
                all_prompts = json.load(f)
            if self.variant_name in all_prompts:
                self.prompt_data = all_prompts[self.variant_name]
                print(f"✅ Prompt carregado: {self.variant_name}")
            else:
                print(f"⚠️ Variante {self.variant_name} não encontrada. Usando fallback.")
                self._fallback_prompt()
        except Exception as e:
            print(f"⚠️ Erro ao carregar prompts: {e}. Usando fallback.")
            self._fallback_prompt()
    
    def _fallback_prompt(self):
        """Prompt de fallback que garante saída limpa."""
        self.prompt_data = {
            "system_role": "You are a Technical Support Specialist. Use context and internal knowledge, but answer cleanly.",
            "constraints": [
                "For SPECIFIC SKU: use context if available; if not, say information unavailable.",
                "For SERIES query (no SKU): ask for specific model number.",
                "Do NOT include any tags, AUDIT blocks, or special formatting."
            ],
            "prompt_template": "CONTEXT:\n{context}\n\nQUERY:\n{query}\n\nREFERENCE DATE: {ref_date}\n\nRESPONSE:"
        }
    
    def build_system_prompt(self) -> str:
        if not self.prompt_data:
            return "You are a helpful technical assistant. Answer cleanly and concisely."
        system_role = self.prompt_data.get("system_role", "")
        constraints = self.prompt_data.get("constraints", [])
        prompt_parts = [system_role]
        if constraints:
            prompt_parts.append("\nRULES:\n" + "\n".join(f"- {c}" for c in constraints))
        # NÃO adicione mais nada aqui
        return "\n".join(prompt_parts)
    
    def build_user_prompt(self, context: str, query: str, ref_date: str) -> str:
        """Constrói o user prompt usando template do JSON."""
        template = self.prompt_data.get("prompt_template", "CONTEXT:\n{context}\n\nQUERY:\n{query}\n\nRESPONSE:")
        return template.format(context=context, query=query, ref_date=ref_date)


# ============================================================================
# CONTEXT BUILDER
# ============================================================================

class ContextBuilder:
    def __init__(self, max_chars: int = 2000):
        self.max_chars = max_chars
    
    def build_context(self, scored_results: List[Dict]) -> str:
        context_parts = []
        for i, result in enumerate(scored_results[:5]):
            doc = result['doc']
            metadata = doc.get('metadata', {})
            title = metadata.get('title') or metadata.get('model') or f"Source_{i}"
            date = result.get('date', 'Unknown')
            text = doc.get('original_text', '')[:self.max_chars]
            header = f"[[ID_{i} | DATE: {date} | TITLE: {title}]]"
            context_parts.append(f"{header}\n{text}")
        return "\n\n".join(context_parts)


# ============================================================================
# SEARCH PIPELINE
# ============================================================================

class SearchPipeline:
    def __init__(self, faiss_manager, data_loader, temporal_scorer, fallback_searcher, config):
        self.faiss_manager = faiss_manager
        self.data_loader = data_loader
        self.temporal_scorer = temporal_scorer
        self.fallback_searcher = fallback_searcher
        self.config = config
    
    async def execute(self, query_vector: np.ndarray, query: str, ref_dt: datetime,
                     expanded_query: str) -> List[Dict]:
        search_results = self.faiss_manager.search(query_vector, k=self.config.search_top_k)
        scored_results = self._apply_temporal_scoring(search_results, ref_dt)
        final_results = await self._apply_fallback_if_needed(scored_results, query_vector, ref_dt)
        return final_results
    
    def _apply_temporal_scoring(self, search_results: List[Tuple], ref_dt: datetime) -> List[Dict]:
        scored_results = []
        for idx, distance in search_results:
            doc = self.data_loader.documents[idx]
            metadata = doc.get('metadata', {})
            if metadata.get('priorizacao_recentes', False):
                doc_date = metadata.get('data_processamento', doc.get('date_iso', '2024-01-01'))
            else:
                doc_date = metadata.get('data_post_original', doc.get('date_iso', '2024-01-01'))
            temporal_gap = self.temporal_scorer.calculate_temporal_gap(doc_date, ref_dt)
            recency_multiplier = 1.0
            final_score, penalty, status = self.temporal_scorer.score_document(distance, temporal_gap, recency_multiplier)
            scored_results.append({
                'doc': doc,
                'idx': idx,
                'semantic_score': distance,
                'final_score': final_score,
                'temporal_gap': temporal_gap,
                'temporal_status': status,
                'penalty_applied': penalty,
                'date': doc_date
            })
        scored_results.sort(key=lambda x: x['final_score'])
        return scored_results
    
    async def _apply_fallback_if_needed(self, scored_results: List[Dict], query_vector: np.ndarray,
                                       ref_dt: datetime) -> List[Dict]:
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
                return merged[:self.config.max_results_returned]
        return scored_results[:self.config.max_results_returned]


# ============================================================================
# RAG ENGINE PRINCIPAL (CORRIGIDO - SEM AUDITORIA NA SAÍDA)
# ============================================================================

class SpecialistTimeAwareRAG:
    """
    Engine RAG com consciência temporal e fallback inteligente.
    SAÍDA LIMPA: sem tags, sem blocos AUDIT:, sem ANSWER:.
    """
    _semaphore = asyncio.Semaphore(1) 

    # def __init__(self, json_path: Union[str, Path], variant_name: str = "V9_HYBRID_MIXED_AUDITOR",
    #             embedding_cache=None, use_expansion: bool = True):
        
    #     print(f"--- 🧠 RAG ENGINE ATIVADA (Variante: {variant_name}) ---")
    #     self.config = RAGConfig(variant_name)
    #     self.config.use_expansion = use_expansion
    #     print(f"   Temporal config: 4.0%/year penalty, fallback after 2.0y")
        
    #     self.cache_manager = embedding_cache
    #     self.embedding_manager = EmbeddingManager(model=self.config.embedding_model)
        
    #     self.data_loader = DataLoader()
        
    #     self.faiss_manager = FAISSManager(dimension=self.config.embedding_dimension)
    #     if self.data_loader.documents:
    #         self.faiss_manager.build_index(self.data_loader.documents)
        
    #     self.temporal_scorer = TemporalScorer(
    #         yearly_penalty_rate=self.config.yearly_penalty_rate,
    #         recency_threshold=self.config.recency_threshold,
    #         low_coverage_multiplier=self.config.low_coverage_penalty_multiplier
    #     )
    #     self.fallback_searcher = FallbackSearcher(
    #         similarity_threshold=self.config.similarity_threshold,
    #         max_fallback_docs=self.config.max_fallback_docs,
    #         old_doc_threshold_years=self.config.old_doc_threshold_years
    #     )
    #     self.query_expander = QueryExpander(variant="temporal", max_terms=self.config.max_synonym_terms)
        
    #     # PromptManager agora carrega do JSON e garante saída limpa
    #     self.prompt_manager = PromptManager(variant_name=variant_name)
        
    #     self.context_builder = ContextBuilder(max_chars=self.config.max_context_chars)
        
    #     self.search_pipeline = SearchPipeline(
    #         faiss_manager=self.faiss_manager,
    #         data_loader=self.data_loader,
    #         temporal_scorer=self.temporal_scorer,
    #         fallback_searcher=self.fallback_searcher,
    #         config=self.config
    #     )
        
    #     print(f"✅ Sistema inicializado com {len(self.data_loader.documents)} documentos")

    #     self.data_loader = DataLoader()
    #     base_path = Path(json_path)
        
    #     # Tenta carregar pelo índice FAISS + metadados (rápido)
    #     index_path = base_path.with_suffix('.faiss')
    #     if index_path.exists() and self.faiss_manager.load_index(index_path):
    #         # Carrega só os metadados (leves)
    #         self.base_dados = self.data_loader.load_from_precomputed(base_path)
    #     else:
    #         # Fallback: carrega o JSON completo e reconstrói o índice
    #         print("⚠️ Índice FAISS não encontrado. Recriando a partir do JSON...")
    #         self.data_loader.load_documents(json_path)
    #         self.base_dados = self.data_loader.documents
    #         self.faiss_manager.build_index(self.base_dados)


    def __init__(self, json_path: Union[str, Path], variant_name: str = "V9_HYBRID_MIXED_AUDITOR",
                 embedding_cache=None, use_expansion: bool = True):
        
        print(f"--- 🧠 RAG ENGINE ATIVADA (Variante: {variant_name}) ---")
        self.config = RAGConfig(variant_name)
        self.config.use_expansion = use_expansion
        print(f"   Temporal config: 4.0%/year penalty, fallback after 2.0y")
        
        self.cache_manager = embedding_cache
        self.embedding_manager = EmbeddingManager(model=self.config.embedding_model)
        
        # DataLoader e FAISSManager (ainda sem dados)
        self.data_loader = DataLoader()
        self.faiss_manager = FAISSManager(dimension=self.config.embedding_dimension)
        
        base_path = Path(json_path)
        index_path = base_path.with_suffix('.faiss')
        if index_path.exists() and self.faiss_manager.load_index(index_path):
            # Carrega metadados (popula self.data_loader.documents)
            self.base_dados = self.data_loader.load_from_precomputed(base_path)
        else:
            print("⚠️ Índice FAISS não encontrado. Recriando a partir do JSON...")
            self.data_loader.load_documents(json_path)
            self.base_dados = self.data_loader.documents
            self.faiss_manager.build_index(self.base_dados)
        
        # Agora self.data_loader.documents está populado
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
        self.prompt_manager = PromptManager(variant_name=variant_name)
        self.context_builder = ContextBuilder(max_chars=self.config.max_context_chars)
        
        self.search_pipeline = SearchPipeline(
            faiss_manager=self.faiss_manager,
            data_loader=self.data_loader,      # agora com documentos
            temporal_scorer=self.temporal_scorer,
            fallback_searcher=self.fallback_searcher,
            config=self.config
        )
        
        print(f"✅ Sistema inicializado com {len(self.data_loader.documents)} documentos")

        # Os demais componentes (temporal_scorer, fallback, etc.) não dependem do carregamento,
        # mas o search_pipeline precisa do data_loader e faiss_manager – já estão prontos.
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
        
        expanded_query = query
        if self.config.use_expansion:
            expanded_query = self.query_expander.expand_query(query)
        
        query_vector = await self._get_embedding(expanded_query)
        final_results = await self.search_pipeline.execute(
            query_vector=query_vector, query=query, ref_dt=ref_dt, expanded_query=expanded_query
        )
        context_str = self.context_builder.build_context(final_results)
        
        # Geração da resposta com prompt limpo
        response = await self._generate_response(context_str, query, ref_date)
        
        # Não há mais auditoria para extrair; a resposta já é limpa
        clean_answer = response.strip()
        
        # Opcional: gerar auditoria interna (não visível) a partir dos metadados da busca
        audit_trail = self._build_internal_audit(final_results, expanded_query, ref_dt)
        
        result = self._build_result(clean_answer, audit_trail, final_results, expanded_query, ref_dt)
        gc.collect()
        return result
    
    async def _generate_response(self, context_str: str, query: str, ref_date: str) -> str:
        sys_prompt = self.prompt_manager.build_system_prompt()
        user_content = self.prompt_manager.build_user_prompt(context_str, query, ref_date)
        
        response = await asyncio.to_thread(
            ollama.chat,
            model=self.config.current_model,
            messages=[
                {'role': 'system', 'content': sys_prompt},
                {'role': 'user', 'content': user_content}
            ],
            options={"temperature": self.config.temperature, "top_p": self.config.top_p},
            keep_alive=0
        )
        return response['message']['content']
    
    def _build_internal_audit(self, final_results: List[Dict], expanded_query: str, ref_dt: datetime) -> str:
        """Gera um registro de auditoria interno (não visível ao usuário) para depuração."""
        if not final_results:
            return "No documents retrieved."
        best = final_results[0]
        return f"Best doc: {best['doc'].get('metadata',{}).get('title','Unknown')} | Gap: {best['temporal_gap']:.2f}y | Score: {best['final_score']:.3f}"
    
    def _build_result(self, clean_answer: str, audit_trail: str, final_results: List[Dict],
                     expanded_query: str, ref_dt: datetime) -> Dict:
        return {
            "answer": clean_answer,
            "audit_trail": audit_trail,   # interno, não usado pelo avaliador
            "titles": [r['doc'].get('metadata', {}).get('title', 'Unknown') for r in final_results[:5]],
            "sources": [r['doc'].get('original_text', '') for r in final_results[:5]],
            "retrieved_metadata": [r['doc'].get('metadata', {}) for r in final_results[:5]],
            "normalized_query": expanded_query,
            "diagnostic": {
                "num_documents_retrieved": len(final_results),
                "cache_used": self.cache_manager is not None,
                "best_temporal_gap_years": round(final_results[0]['temporal_gap'], 2) if final_results else 0,
                **self.temporal_scorer.get_penalty_stats(final_results)
            }
        }