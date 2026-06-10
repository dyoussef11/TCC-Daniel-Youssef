"""
RAG Temporal V9 - Compacto
Sistema de RAG com consciência temporal, auditoria e fallback inteligente.
Versão unificada em um único arquivo.
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
        self.search_top_k: int = 20
        self.similarity_threshold: float = 1.2
        self.max_context_chars: int = 2000
        
        # Temporalidade adaptativa
        self.yearly_penalty_rate: float = 0.04
        self.old_doc_threshold_years: float = 2.0
        self.recency_threshold: int = 3
        self.low_coverage_penalty_multiplier: float = 0.3
        self.fallback_semantic_threshold: float = 1.15
        self.max_fallback_docs: int = 3
        self.max_results_returned: int = 8
        
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
        """Carrega caches existentes do disco."""
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
        """Carrega documentos do arquivo JSON."""
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
        """Processa e valida um documento."""
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
            
        except Exception as e:
            self.stats["errors"] += 1
            return None
    
    def _get_initial_stats(self) -> Dict:
        return {"total_loaded": 0, "with_vectors": 0, "with_metadata": 0, "with_dates": 0, "errors": 0}
    
    def get_document_by_id(self, doc_id: int) -> Optional[Dict]:
        for doc in self.documents:
            if doc.get('id') == doc_id:
                return doc
        return None


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
        """Testa a conexão com o modelo."""
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
            # Converte a lista retornada pelo Ollama em array NumPy
            return np.array(result['embedding'], dtype=np.float32)
        except ollama.ResponseError as e:
            if "NaN" in str(e):
                print(f"⚠️ Erro de NaN no embedding para texto: '{text[:50]}...'")
                # Retorna array de zeros com a dimensão correta
                dim = self.dimension if self.dimension else 1024
                return np.zeros(dim, dtype=np.float32)
            raise
    
    def compute_embeddings_batch(self, texts: List[str]) -> np.ndarray:
        """Computa embeddings para múltiplos textos."""
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
        """Constrói índice FAISS a partir de documentos."""
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
        """Extrai e valida vetores dos documentos."""
        vectors = []
        for doc in documents:
            if 'vector' in doc:
                vec = np.array(doc['vector'], dtype=np.float32)
                if len(vec) == self.dimension:
                    vectors.append(vec)
        
        return np.array(vectors).astype('float32') if vectors else None
    
    def search(self, query_vector: np.ndarray, k: int = 20) -> List[Tuple[int, float]]:
        """Busca os k vizinhos mais próximos."""
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
            stats.update({
                "index_size": self.index.ntotal,
                "dimension": self.index.d,
            })
        return stats


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
        """Calcula o gap temporal em anos."""
        try:
            doc_dt = datetime.strptime(doc_date[:10], "%Y-%m-%d")
            return (ref_date - doc_dt).days / 365.25
        except (ValueError, IndexError):
            return 0.0
    
    def calculate_domain_recency(self, doc_model: str, ref_date: datetime, all_docs: List[Dict]) -> float:
        """Calcula o fator de recência do domínio."""
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
        """Calcula o score final de um documento."""
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
    """Executa busca sem penalidade temporal para documentos antigos."""
    
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
        """Busca adicional ignorando penalidade temporal."""
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
    """Expande queries usando dicionário hierárquico. Só expande queries SEM SKU."""
    
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
        """Verifica se a query contém um SKU específico."""
        query_lower = query.lower()
        
        # Lista de SKUs conhecidos
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
        
        # Padrões regex para SKU
        sku_patterns = [
            r'[A-Z]{2,3}[-]?\d{3}[-]?\d{2,4}',     # AN515-56
            r'\d{2,4}[A-Z]{2,4}',                   # 15ACH6
            r'[A-Z]{2,3}\s\d{3}\s\d{4}',            # G7 7588
            r'[a-z]{3,4}\d{4}',                     # fa5075
        ]
        
        for pattern in sku_patterns:
            if re.search(pattern, query, re.IGNORECASE):
                print(f"   🔒 SKU detectado pelo padrão")
                return True
        
        return False
    
    def expand_query(self, query: str) -> str:
        """Expande query. Só expande se NÃO houver SKU específico."""
        if self.has_specific_sku(query):
            print(f"   🚫 SKU detectado - expansão CANCELADA")
            return query
        
        return query  # Expansão simplificada para este arquivo compacto


# ============================================================================
# PROMPT MANAGER
# ============================================================================

class PromptManager:
    """Gerencia prompts do sistema RAG."""
    
    def __init__(self, variant_name: str = "V9_HYBRID_MIXED_AUDITOR", prompts_dir: Optional[Path] = None):
        self.variant_name = variant_name
        self.system_role = ""
        self.core_principles = []
        self.constraints = []
        self.examples = {}
        self.output_format = {}
    
    def build_system_prompt(self) -> str:
        """Constrói o system prompt completo."""
        return """Act as a Senior Hardware RAG Auditor with Temporal Awareness.

CRITICAL RULES:
1. If the user asks about a SPECIFIC SKU (e.g., AN515-56, 15ACH6) and it's NOT in the context, you MUST say information is unavailable.
2. DO NOT infer specifications from different models, even from the same brand.
3. For generic series queries (e.g., "Nitro 5" without SKU), ASK for the specific model number.
4. Internal knowledge (pre-2024) can ONLY be used as fallback when explicitly stated.

OUTPUT FORMAT:
AUDIT: [SKU: xxx] | [STATUS: found/not_found] | [SOURCES: ...] | [CROSS-CHECK: ...]

ANSWER: [Your response here]"""
    
    def build_user_prompt(self, context: str, query: str, ref_date: str) -> str:
        """Constrói o user prompt usando template."""
        return f"""=== TECHNICAL CONTEXT ===
{context}

=== USER QUERY ===
{query}

=== REFERENCE DATE ===
{ref_date}

=== RESPONSE ===
AUDIT:"""


# ============================================================================
# RESPONSE AUDITOR
# ============================================================================

class ResponseAuditor:
    """Extrai e valida a auditoria das respostas."""
    
    def __init__(self):
        self.audit_pattern = re.compile(r"AUDIT:(.*?)(?=ANSWER:|$)", re.DOTALL | re.IGNORECASE)
        self.answer_pattern = re.compile(r"ANSWER:(.*)", re.DOTALL | re.IGNORECASE)
    
    def extract_audit(self, full_response: str) -> Dict[str, str]:
        """Extrai auditoria e resposta limpa."""
        audit_match = self.audit_pattern.search(full_response)
        audit_log = audit_match.group(1).strip() if audit_match else "No audit log provided."
        
        answer_match = self.answer_pattern.search(full_response)
        clean_answer = answer_match.group(1).strip() if answer_match else full_response.strip()
        
        return {"audit_log": audit_log, "clean_answer": clean_answer}


# ============================================================================
# CONTEXT BUILDER
# ============================================================================

class ContextBuilder:
    """Constrói o contexto formatado para envio ao LLM."""
    
    def __init__(self, max_chars: int = 2000):
        self.max_chars = max_chars
    
    def build_context(self, scored_results: List[Dict]) -> str:
        """Constrói string de contexto formatada."""
        context_parts = []
        
        for i, result in enumerate(scored_results[:5]):  # Limita a 5 docs
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
    """Gerencia o pipeline de busca."""
    
    def __init__(self, faiss_manager, data_loader, temporal_scorer, fallback_searcher, config):
        self.faiss_manager = faiss_manager
        self.data_loader = data_loader
        self.temporal_scorer = temporal_scorer
        self.fallback_searcher = fallback_searcher
        self.config = config
    
    async def execute(self, query_vector: np.ndarray, query: str, ref_dt: datetime,
                     expanded_query: str) -> List[Dict]:
        """Executa o pipeline completo de busca."""
        # Busca FAISS
        search_results = self.faiss_manager.search(query_vector, k=self.config.search_top_k)
        
        # Scoring temporal
        scored_results = self._apply_temporal_scoring(search_results, ref_dt)
        
        # Fallback se necessário
        final_results = await self._apply_fallback_if_needed(scored_results, query_vector, ref_dt)
        
        return final_results
    
    def _apply_temporal_scoring(self, search_results: List[Tuple], ref_dt: datetime) -> List[Dict]:
        """Aplica scoring temporal nos resultados."""
        scored_results = []
        
        for idx, distance in search_results:
            doc = self.data_loader.documents[idx]
            doc_date = doc.get('date_iso', '2024-01-01')[:10]
            
            temporal_gap = self.temporal_scorer.calculate_temporal_gap(doc_date, ref_dt)
            recency_multiplier = 1.0  # Simplificado para este arquivo compacto
            
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
        """Aplica fallback se necessário."""
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
# RAG ENGINE PRINCIPAL
# ============================================================================

class SpecialistTimeAwareRAG:
    """
    Engine RAG com Auditoria e Normalização por Sinônimos.
    Aplica penalidade temporal adaptativa com fallback inteligente.
    """
    
    def __init__(self, json_path: Union[str, Path], variant_name: str = "V9_HYBRID_MIXED_AUDITOR",
                 embedding_cache=None, use_expansion: bool = True):
        
        print(f"--- 🧠 RAG ENGINE ATIVADA (Variante: {variant_name}) ---")
        
        # Configuração
        self.config = RAGConfig(variant_name)
        self.config.use_expansion = use_expansion
        print(f"   Temporal config: 3.0%/year penalty, fallback after 2.0y")
        
        # Cache
        self.cache_manager = embedding_cache
        
        # Embeddings
        self.embedding_manager = EmbeddingManager(model=self.config.embedding_model)
        
        # Data Loader
        self.data_loader = DataLoader()
        self.data_loader.load_documents(json_path)
        
        # FAISS
        self.faiss_manager = FAISSManager(dimension=self.config.embedding_dimension)
        if self.data_loader.documents:
            self.faiss_manager.build_index(self.data_loader.documents)
        
        # Componentes
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
        self.auditor = ResponseAuditor()
        self.context_builder = ContextBuilder(max_chars=self.config.max_context_chars)
        
        # Pipeline
        self.search_pipeline = SearchPipeline(
            faiss_manager=self.faiss_manager,
            data_loader=self.data_loader,
            temporal_scorer=self.temporal_scorer,
            fallback_searcher=self.fallback_searcher,
            config=self.config
        )
        
        print(f"✅ Sistema inicializado com {len(self.data_loader.documents)} documentos")
    
    async def _get_embedding(self, query: str) -> np.ndarray:
        """Obtém embedding com cache."""
        if self.cache_manager:
            cached = self.cache_manager.get(query)
            if cached is not None:
                return cached
            
            embedding = await asyncio.to_thread(self.embedding_manager.compute_embedding, query)
            self.cache_manager.set(query, embedding)
            return embedding
        
        return await asyncio.to_thread(self.embedding_manager.compute_embedding, query)
    
    async def search(self, query: str, ref_date: str = "2026-03-23") -> Dict:
        """
        Executa busca RAG completa.
        """
        print(f"🔍 Processando: {query[:60]}...")
        ref_dt = datetime.strptime(ref_date, "%Y-%m-%d")
        
        # 1. Expansão de query (apenas se configurado)
        expanded_query = query
        if self.config.use_expansion:
            expanded_query = self.query_expander.expand_query(query)
        
        # 2. Embedding
        query_vector = await self._get_embedding(expanded_query)
        
        # 3. Busca via pipeline
        final_results = await self.search_pipeline.execute(
            query_vector=query_vector, query=query, ref_dt=ref_dt, expanded_query=expanded_query
        )
        
        # 4. Construção de contexto
        context_str = self.context_builder.build_context(final_results)
        
        # 5. Geração de resposta
        response = await self._generate_response(context_str, query, ref_date)
        
        # 6. Extração de auditoria
        audited_response = self.auditor.extract_audit(response)
        
        # 7. Montagem do resultado
        result = self._build_result(audited_response, final_results, expanded_query, ref_dt)
        
        gc.collect()
        return result
    
    async def _generate_response(self, context_str: str, query: str, ref_date: str) -> str:
        """Gera resposta usando prompt do JSON."""
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
    
    def _build_result(self, audited_response: Dict, final_results: List[Dict],
                     expanded_query: str, ref_dt: datetime) -> Dict:
        """Constrói o dicionário de resultado final."""
        return {
            "answer": audited_response["clean_answer"],
            "audit_trail": audited_response["audit_log"],
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