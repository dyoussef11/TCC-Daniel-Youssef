from typing import Dict, List

from datetime import datetime
from pathlib import Path
from typing import Union
from core.paths import VALIDACAO_CONFIG

import numpy as np
from functools import lru_cache
from typing import Dict, Optional, Any
import asyncio

import re
from typing import Dict

from datetime import datetime
from typing import Dict, List, Tuple, Optional

from datetime import datetime
from typing import Dict, List, Tuple, Optional
import numpy as np

import gc
from pathlib import Path
from datetime import datetime
from typing import Dict, Union, Optional, List, Tuple
import numpy as np
import ollama
import asyncio
from core.paths import VALIDACAO_CONFIG
from modules.config import RAGConfig
from modules.cache_manager import CacheManager
from modules.embeddings import EmbeddingManager
from modules.data_loader import DataLoader
from modules.faiss_manager import FAISSManager
from modules.context_builder import ContextBuilder
from modules.temporal_scoring import TemporalScorer
from modules.fallback_search import FallbackSearcher
from modules.search_pipeline import SearchPipeline
from modules.query_expansion import QueryExpander
from modules.prompt_manager import PromptManager
from modules.auditor import ResponseAuditor

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import json
from pathlib import Path
from typing import Dict, Optional

import numpy as np
from datetime import datetime
from typing import Dict, List, Set, Optional

import faiss
import numpy as np
from typing import List, Dict, Tuple, Optional

import os
import numpy as np
from ollama import Client
from typing import Optional

import json
import ijson
from pathlib import Path
from typing import Dict, List, Union, Iterator



"""
data_loader.py
Sistema de carregamento de documentos com suporte a streaming.
"""


class DataLoader:
    """
    Carrega documentos JSON com suporte a streaming para arquivos grandes.
    """
    
    def __init__(self):
        self.documents: List[Dict] = []
        self.stats = {
            "total_loaded": 0,
            "with_vectors": 0,
            "with_metadata": 0,
            "with_dates": 0,
            "errors": 0
        }
    
    def load_documents(self, json_path: Union[str, Path]) -> List[Dict]:
        """
        Carrega documentos do arquivo JSON.
        
        Args:
            json_path: Caminho para o arquivo JSON
            
        Returns:
            List[Dict]: Lista de documentos carregados
        """
        try:
            path = Path(json_path)
            
            if not path.exists():
                raise FileNotFoundError(f"Arquivo não encontrado: {json_path}")
            
            # Usa streaming para arquivos grandes
            self.documents = []
            self.stats = self._get_initial_stats()
            
            with open(path, 'rb') as f:
                for item in ijson.items(f, 'item'):
                    processed = self._process_document(item)
                    if processed:
                        self.documents.append(processed)
                        self.stats["total_loaded"] += 1
            
            print(f"✅ Base carregada: {len(self.documents)} documentos")
            self._print_stats()
            
            return self.documents
            
        except Exception as e:
            print(f"❌ Erro ao carregar base: {e}")
            self.documents = []
            return []
    
    def _process_document(self, doc: Dict) -> Dict:
        """
        Processa e valida um documento.
        
        Args:
            doc: Documento bruto
            
        Returns:
            Dict: Documento processado
        """
        try:
            processed = doc.copy()
            
            # Garante campos obrigatórios
            if 'vector' in processed:
                self.stats["with_vectors"] += 1
            
            # Extrai metadata se ausente
            if 'metadata' not in processed:
                processed['metadata'] = self._extract_metadata(doc)
            else:
                self.stats["with_metadata"] += 1
            
            # Formata data
            if 'date_iso' in processed:
                processed['date_iso'] = processed['date_iso'][:10]
                self.stats["with_dates"] += 1
            else:
                processed['date_iso'] = '2024-01-01'
            
            # Garante ID único
            if 'id' not in processed:
                processed['id'] = hash(processed.get('original_text', '')) % 1000000
            
            return processed
            
        except Exception as e:
            self.stats["errors"] += 1
            print(f"⚠️ Erro ao processar documento: {e}")
            return None
    
    def _extract_metadata(self, doc: Dict) -> Dict:
        """
        Extrai metadata do documento se não estruturada.
        
        Args:
            doc: Documento
            
        Returns:
            Dict: Metadata extraída
        """
        metadata = {}
        
        # Tenta extrair campos comuns
        for key in ['title', 'model', 'brand', 'category']:
            if key in doc:
                metadata[key] = doc[key]
        
        # Se tiver texto, usa primeiras palavras como título
        if 'original_text' in doc and 'title' not in metadata:
            text = doc['original_text']
            metadata['title'] = text[:100].strip()
        
        return metadata
    
    def _get_initial_stats(self) -> Dict:
        """Retorna estatísticas iniciais zeradas."""
        return {
            "total_loaded": 0,
            "with_vectors": 0,
            "with_metadata": 0,
            "with_dates": 0,
            "errors": 0
        }
    
    def _print_stats(self) -> None:
        """Imprime estatísticas de carregamento."""
        s = self.stats
        print(f"   📊 Stats: {s['total_loaded']} docs | "
              f"{s['with_vectors']} vectors | "
              f"{s['with_metadata']} metadata | "
              f"{s['with_dates']} dates | "
              f"{s['errors']} errors")
    
    def get_document_by_id(self, doc_id: int) -> Dict:
        """
        Busca documento por ID.
        
        Args:
            doc_id: ID do documento
            
        Returns:
            Dict: Documento encontrado ou None
        """
        for doc in self.documents:
            if doc.get('id') == doc_id:
                return doc
        return None
    
    def filter_by_metadata(self, key: str, value: str) -> List[Dict]:
        """
        Filtra documentos por campo de metadata.
        
        Args:
            key: Chave de metadata
            value: Valor a filtrar
            
        Returns:
            List[Dict]: Documentos filtrados
        """
        return [
            doc for doc in self.documents
            if doc.get('metadata', {}).get(key, '').lower() == value.lower()
        ]
    
    def get_date_range(self) -> tuple:
        """
        Retorna range de datas dos documentos.
        
        Returns:
            tuple: (data_min, data_max)
        """
        dates = []
        for doc in self.documents:
            if 'date_iso' in doc:
                dates.append(doc['date_iso'])
        
        if dates:
            return min(dates), max(dates)
        return None, None

"""
embeddings.py
Gerenciamento de embeddings via Ollama (CPU).
"""


class EmbeddingManager:
    """Gerencia a criação de embeddings usando Ollama."""
    
    def __init__(self, model: str = "bge-m3:latest", host: str = "http://localhost:11434"):
        self.model = model
        self.host = host
        self.dimension: Optional[int] = None
        self._init_client()
    
    def _init_client(self) -> None:
        """Inicializa cliente forçando CPU."""
        # Backup das configurações atuais
        self._original_cuda = os.environ.get('CUDA_VISIBLE_DEVICES')
        self._original_num_gpu = os.environ.get('OLLAMA_NUM_GPU')
        
        # Força CPU
        os.environ['CUDA_VISIBLE_DEVICES'] = '-1'
        os.environ['OLLAMA_NUM_GPU'] = '0'
        
        self.client = Client(host=self.host)
        
        # Restaura configurações
        self._restore_env()
        
        # Testa conexão
        self._test_connection()
    
    def _restore_env(self) -> None:
        """Restaura variáveis de ambiente originais."""
        if self._original_cuda is not None:
            os.environ['CUDA_VISIBLE_DEVICES'] = self._original_cuda
        else:
            os.environ.pop('CUDA_VISIBLE_DEVICES', None)
        
        if self._original_num_gpu is not None:
            os.environ['OLLAMA_NUM_GPU'] = self._original_num_gpu
        else:
            os.environ.pop('OLLAMA_NUM_GPU', None)
    
    def _test_connection(self) -> None:
        """Testa a conexão com o modelo."""
        try:
            test_result = self.client.embeddings(model=self.model, prompt="test")
            if 'embedding' in test_result:
                self.dimension = len(test_result['embedding'])
                print(f"✅ Conexão com {self.model} (CPU) estabelecida - dimensão: {self.dimension}")
        except Exception as e:
            print(f"⚠️ {self.model} pode não estar disponível: {e}")
            self.dimension = 1024  # Fallback
    
    def compute_embedding(self, text: str) -> np.ndarray:
        """
        Computa embedding para um texto.
        
        Args:
            text: Texto para gerar embedding
            
        Returns:
            np.ndarray: Vetor de embedding
        """
        result = self.client.embeddings(
            model=self.model,
            prompt=text
        )
        return np.array(result['embedding'], dtype=np.float32)
    
    def compute_embeddings_batch(self, texts: list) -> np.ndarray:
        """
        Computa embeddings para múltiplos textos.
        
        Args:
            texts: Lista de textos
            
        Returns:
            np.ndarray: Matriz de embeddings
        """
        embeddings = []
        for text in texts:
            emb = self.compute_embedding(text)
            embeddings.append(emb)
        return np.array(embeddings)

"""
faiss_manager.py
Gerenciamento do índice FAISS para busca vetorial.
"""


class FAISSManager:
    """
    Gerencia índice FAISS para busca eficiente de embeddings.
    """
    
    def __init__(self, dimension: int = 1024):
        self.dimension = dimension
        self.index: Optional[faiss.IndexFlatL2] = None
        self.stats = {
            "total_vectors": 0,
            "last_search_time": 0,
            "searches_performed": 0
        }
    
    def build_index(self, documents: List[Dict]) -> None:
        """
        Constrói índice FAISS a partir de documentos.
        
        Args:
            documents: Lista de documentos com vetores
        """
        if not documents:
            print("⚠️ Nenhum documento para indexar")
            return
        
        # Extrai vetores
        vectors = self._extract_vectors(documents)
        
        if vectors is None or len(vectors) == 0:
            print("⚠️ Nenhum vetor válido encontrado")
            return
        
        # Cria índice
        self.index = faiss.IndexFlatL2(self.dimension)
        
        # Adiciona vetores
        self.index.add(vectors)
        
        self.stats["total_vectors"] = self.index.ntotal
        print(f"✅ Index FAISS criado com {self.index.ntotal} vetores (dimensão {self.dimension})")
    
    def _extract_vectors(self, documents: List[Dict]) -> np.ndarray:
        """
        Extrai e valida vetores dos documentos.
        
        Args:
            documents: Lista de documentos
            
        Returns:
            np.ndarray: Matriz de vetores
        """
        vectors = []
        
        for doc in documents:
            if 'vector' in doc:
                vec = np.array(doc['vector'], dtype=np.float32)
                
                # Valida dimensão
                if len(vec) == self.dimension:
                    vectors.append(vec)
                else:
                    print(f"⚠️ Vetor com dimensão inválida: {len(vec)} (esperado {self.dimension})")
        
        if vectors:
            return np.array(vectors).astype('float32')
        return None
    
    def search(self, query_vector: np.ndarray, k: int = 20) -> List[Tuple[int, float]]:
        """
        Busca os k vizinhos mais próximos.
        
        Args:
            query_vector: Vetor de consulta
            k: Número de resultados
            
        Returns:
            List[Tuple[int, float]]: Lista de (índice, distância)
        """
        import time
        
        if self.index is None:
            print("❌ Índice FAISS não inicializado")
            return []
        
        start_time = time.time()
        
        # Garante shape correto
        if query_vector.ndim == 1:
            query_vector = query_vector.reshape(1, -1)
        
        # Busca
        distances, indices = self.index.search(query_vector, k)
        
        # Formata resultados
        results = []
        for i, idx in enumerate(indices[0]):
            if idx != -1:
                results.append((idx, float(distances[0][i])))
        
        # Atualiza stats
        self.stats["searches_performed"] += 1
        self.stats["last_search_time"] = time.time() - start_time
        
        return results
    
    def get_nearest_neighbors(self, query_vector: np.ndarray, 
                             threshold: Optional[float] = None) -> List[Tuple[int, float]]:
        """
        Busca vizinhos com threshold opcional de distância.
        
        Args:
            query_vector: Vetor de consulta
            threshold: Distância máxima (opcional)
            
        Returns:
            List[Tuple[int, float]]: Vizinhos filtrados
        """
        results = self.search(query_vector, k=50)  # Busca mais resultados
        
        if threshold:
            results = [(idx, dist) for idx, dist in results if dist <= threshold]
        
        return results
    
    def get_index_stats(self) -> Dict:
        """
        Retorna estatísticas do índice.
        
        Returns:
            Dict: Estatísticas
        """
        stats = self.stats.copy()
        
        if self.index:
            stats.update({
                "index_size": self.index.ntotal,
                "dimension": self.index.d,
                "memory_usage_mb": self.index.ntotal * self.index.d * 4 / (1024 * 1024)
            })
        
        return stats
    
    def save_index(self, path: str) -> None:
        """
        Salva índice em disco.
        
        Args:
            path: Caminho para salvar
        """
        if self.index:
            faiss.write_index(self.index, path)
            print(f"✅ Índice salvo em: {path}")
    
    def load_index(self, path: str) -> None:
        """
        Carrega índice do disco.
        
        Args:
            path: Caminho do arquivo
        """
        try:
            self.index = faiss.read_index(path)
            self.stats["total_vectors"] = self.index.ntotal
            print(f"✅ Índice carregado: {self.index.ntotal} vetores")
        except Exception as e:
            print(f"❌ Erro ao carregar índice: {e}")

"""
fallback_search.py
Mecanismo de fallback sem penalidade temporal.
"""


class FallbackSearcher:
    """Executa busca sem penalidade temporal para documentos antigos."""
    
    def __init__(self, similarity_threshold: float = 1.2,
                 max_fallback_docs: int = 3,
                 old_doc_threshold_years: float = 2.0):
        self.similarity_threshold = similarity_threshold
        self.max_fallback_docs = max_fallback_docs
        self.old_doc_threshold_years = old_doc_threshold_years
    
    def should_activate(self, scored_results: List[Dict]) -> bool:
        """
        Verifica se o fallback deve ser ativado.
        
        Critérios:
        1. Melhor documento é muito antigo (> threshold)
        2. Poucos documentos recentes (< 2)
        
        Args:
            scored_results: Resultados com score temporal
            
        Returns:
            bool: True se deve ativar fallback
        """
        if not scored_results:
            return False
        
        best_doc_age = scored_results[0].get('temporal_gap', 0)
        recent_docs_count = sum(1 for r in scored_results if r.get('temporal_gap', 0) < 0.5)
        
        return (best_doc_age > self.old_doc_threshold_years and 
                recent_docs_count < 2)
    
    async def semantic_only_search(self, query_vector: np.ndarray, 
                                   index, all_docs: List[Dict],
                                   ref_date: datetime,
                                   existing_ids: Set[int]) -> List[Dict]:
        """
        Busca adicional ignorando penalidade temporal.
        
        Args:
            query_vector: Vetor da query
            index: Índice FAISS
            all_docs: Todos os documentos
            ref_date: Data de referência
            existing_ids: IDs já selecionados
            
        Returns:
            List[Dict]: Resultados do fallback
        """
        # Busca mais ampla
        k_search = self.max_fallback_docs * 3
        distances, indices = index.search(query_vector, k=k_search)
        
        fallback_results = []
        
        for i, idx in enumerate(indices[0]):
            if idx == -1:
                continue
            
            doc = all_docs[idx]
            doc_id = doc.get('id', idx)
            
            # Evita duplicatas
            if doc_id in existing_ids:
                continue
            
            semantic_score = distances[0][i]
            
            # Score máximo para aceitar no fallback (ligeiramente mais relaxado)
            if semantic_score < self.similarity_threshold * 1.1:
                doc_date = doc.get('date_iso', '2024-01-01')[:10]
                temporal_gap = self._calculate_gap(doc_date, ref_date)
                
                fallback_results.append({
                    'doc': doc,
                    'semantic_score': semantic_score,
                    'final_score': semantic_score * 1.05,  # Penalidade simbólica
                    'temporal_gap': temporal_gap,
                    'temporal_status': "fallback_no_penalty",
                    'penalty_applied': 0.05,
                    'date': doc_date
                })
        
        # Ordena por score semântico
        fallback_results.sort(key=lambda x: x['semantic_score'])
        
        return fallback_results[:self.max_fallback_docs]
    
    def _calculate_gap(self, doc_date: str, ref_date: datetime) -> float:
        """Calcula gap temporal."""
        try:
            doc_dt = datetime.strptime(doc_date[:10], "%Y-%m-%d")
            return (ref_date - doc_dt).days / 365.25
        except (ValueError, IndexError):
            return 0.0

"""
prompt_manager.py - CORRIGIDO
Gerenciamento de prompts do sistema RAG - USA A ESTRUTURA COMPLETA DO JSON.
"""


class PromptManager:
    """
    Carrega e gerencia prompts do sistema RAG.
    Agora usa TODA a estrutura do JSON, incluindo:
    - core_principles
    - constraints
    - audit_pipeline
    - output_format
    - brand_patterns
    - prompt_template
    """
    
    def __init__(self, variant_name: str = "V9_HYBRID_AUDITOR", 
                 prompts_dir: Optional[Path] = None):
        self.variant_name = variant_name
        self.prompts_dir = prompts_dir or Path("config")
        
        # Estrutura completa carregada do JSON
        self.prompts: Dict = {}
        self.system_role: str = ""
        self.core_principles: list = []
        self.constraints: list = []
        self.audit_pipeline: list = []
        self.output_format: Dict = {}
        self.brand_patterns: Dict = {}
        self.prompt_template: str = ""
        
        # Carrega tudo
        self._load_prompts()
    
    def _load_prompts(self) -> None:
        """Carrega TODOS os campos do JSON."""
        prompt_file = self.prompts_dir / 'prompt_rag_temporal_hybrid_V9.json'
        
        try:
            with open(prompt_file, 'r', encoding='utf-8') as f:
                all_prompts = json.load(f)
                
                if self.variant_name in all_prompts:
                    variant = all_prompts[self.variant_name]
                    
                    # Carrega TODOS os campos
                    self.system_role = variant.get('system_role', '')
                    self.core_principles = variant.get('core_principles', [])
                    self.constraints = variant.get('constraints', [])
                    self.audit_pipeline = variant.get('audit_pipeline', [])
                    self.output_format = variant.get('output_format', {})
                    self.brand_patterns = variant.get('brand_patterns', {})
                    self.prompt_template = variant.get('prompt_template', '')
                    self.examples = variant.get('examples', {})
                    
                    print(f"✅ Prompts carregados para variante: {self.variant_name}")
                    print(f"   - {len(self.core_principles)} core principles")
                    print(f"   - {len(self.constraints)} constraints")
                    print(f"   - {len(self.audit_pipeline)} audit steps")
                    print(f"   - {len(self.examples)} examples loaded")
                else:
                    print(f"⚠️ Variante '{self.variant_name}' não encontrada")
                    
        except FileNotFoundError:
            print(f"⚠️ Arquivo de prompt não encontrado: {prompt_file}")
        except json.JSONDecodeError as e:
            print(f"❌ Erro ao decodificar JSON: {e}")
    
    def build_system_prompt(self) -> str:
        """
        Constrói o system prompt COMPLETO usando TODOS os campos do JSON.
        """
        parts = []
        
        # 1. System Role
        if self.system_role:
            parts.append(self.system_role)
        
        # 2. Core Principles
        if self.core_principles:
            parts.append("\nCORE PRINCIPLES:")
            for principle in self.core_principles:
                parts.append(f"- {principle}")
        
        # 3. Constraints
        if self.constraints:
            parts.append("\nCRITICAL RULES:")
            for constraint in self.constraints:
                if isinstance(constraint, str):
                    parts.append(f"- {constraint}")
                elif isinstance(constraint, dict):
                    # Para constraints aninhadas
                    for key, value in constraint.items():
                        parts.append(f"- {key}: {value}")
        
        # 4. Audit Pipeline
        if self.audit_pipeline:
            parts.append("\nAUDIT PROCEDURE:")
            for step in self.audit_pipeline:
                parts.append(step)
        
        # 5. Output Format
        if self.output_format:
            parts.append("\nMANDATORY OUTPUT FORMAT:")
            if 'audit' in self.output_format:
                parts.append(f"Audit format: {self.output_format['audit']}")
            if 'answer' in self.output_format:
                parts.append(f"Answer format: {self.output_format['answer']}")
        
        # 6. Brand Patterns (como referência, não para inferência)
        if self.brand_patterns and 'note' in self.brand_patterns:
            parts.append(f"\nBRAND PATTERNS (identification only): {self.brand_patterns['note']}")
        
        return "\n".join(parts)
    
    def build_user_prompt(self, context: str, query: str, 
                         ref_date: str = "2026-04-28") -> str:
        """
        Constrói o user prompt usando o TEMPLATE do JSON.
        AGORA USA o prompt_template definido no JSON!
        """
        # Se temos um template no JSON, usa ele
        if self.prompt_template:
            # Substitui as variáveis no template
            prompt = self.prompt_template.replace('{context}', context)
            prompt = prompt.replace('{query}', query)
            prompt = prompt.replace('{ref_date}', ref_date)
            return prompt
        
        # Fallback se não houver template
        return f"""=== TECHNICAL CONTEXT ===
            {context}

            === USER QUERY ===
            {query}

            === REFERENCE DATE ===
            {ref_date}

            === INSTRUCTIONS ===
            1. Extract the exact model/SKU from the user's query.
            2. Check if this EXACT SKU exists in the context above.
            3. If the EXACT SKU is NOT in the context, respond that information is unavailable.
            4. DO NOT infer specifications from different models, even same brand.
            5. Output format: AUDIT: [...] then ANSWER: [...] 
            (without any [RAG] or [INTERNAL] tags in ANSWER)

            === RESPONSE ==="""
    
    # prompt_manager.py - SUBSTITUA O MÉTODO get_examples_for_few_shot

    def get_examples_for_few_shot(self) -> str:
        """
        Retorna exemplos formatados para few-shot learning.
        CORRIGIDO: Agora mostra exemplos COMPLETOS (query + expected_answer)
        """
        if not hasattr(self, 'examples') or not self.examples:
            return ""
        
        examples_text = "\n=== EXAMPLES OF CORRECT BEHAVIOR ===\n"
        examples_text += "Follow these EXACT patterns:\n\n"
        
        # Exemplo 1: SKU não encontrado - deve dizer que não tem dados
        if 'sku_not_found_acer' in self.examples:
            ex = self.examples['sku_not_found_acer']
            examples_text += f"""Example 1 (SKU not found):
    Query: "{ex.get('query', '')}"
    Expected Answer: "{ex.get('expected_answer', '')}"
    Expected Audit: "{ex.get('expected_audit', '')}"
    """
        
        # Exemplo 2: Pergunta sobre série sem SKU - deve PEDIR SKU
        examples_text += """
    Example 2 (Generic series - ASK FOR SKU):
    Query: "Does the Nitro 5 have Thunderbolt 4?"
    Expected Answer: "To provide accurate specifications, I need the complete model number (SKU). Could you please provide the full model number (e.g., AN515-56, AN515-57)?"
    Expected Audit: "AUDIT: [SKU: None] | [STATUS: missing] | [CROSS-CHECK: asked_for_SKU]"

    Example 3 (Comparison without data - CANNOT COMPARE):
    Query: "Does AN515-56 have same Thunderbolt as AN515-57?"
    Expected Answer: "I cannot compare these models because I lack complete data for one or both SKUs. I only provide comparisons when both specifications are verified in my database."
    Expected Audit: "AUDIT: [SKU: AN515-56, AN515-57] | [STATUS: missing_second_model] | [CROSS-CHECK: comparison_refused]"

    Example 4 (Specific model not in DB - ADMIT UNAVAILABILITY):
    Query: "What is the maximum RAM for Acer AN515-56?"
    Expected Answer: "Information for the Acer AN515-56 model is not available in the documentation provided for this specific SKU. No inference from similar models is permitted."
    Expected Audit: "AUDIT: [SKU: AN515-56] | [STATUS: not_found] | [SOURCES: none] | [CROSS-CHECK: no_inference]"
    """
    
        return examples_text
    
    def get_audit_format_instructions(self) -> str:
        """
        Retorna instruções específicas para o formato de auditoria.
        """
        if self.output_format and 'audit' in self.output_format:
            return f"""AUDIT FORMAT REQUIREMENTS:
        Your AUDIT section MUST follow this exact format:
        {self.output_format['audit']}

        Components:
        - SKU: The exact model identifier from the query
        - STATUS: 'found' if SKU in context, 'not_found' if not
        - SOURCES: Document IDs from context or INTERNAL concepts
        - CROSS-CHECK: Always include 'no_inference_detected' or explain any inference"""
        return ""
    
    def get_sku_validation_rules(self) -> str:
        """
        Extrai regras de validação de SKU dos constraints e principles.
        """
        rules = []
        
        # Procura regras específicas de SKU
        for constraint in self.constraints:
            if isinstance(constraint, str) and ('SKU' in constraint or 'model' in constraint.lower()):
                rules.append(constraint)
        
        return "\n".join(rules) if rules else ""

# query_expansion.py - VERSÃO CORRIGIDA COM SKU DETECTION



class QueryExpander:
    """
    Expande queries usando dicionário hierárquico.
    Só expande queries SEM SKU específico.
    """
    
    def __init__(self, 
                 hierarchical_path: Optional[Path] = None,
                 flat_dict_path: Optional[Path] = None,
                 max_terms: int = 5,
                 variant: str = "vanilla"):
        
        self.max_terms = max_terms
        self.variant = variant  # 'vanilla' ou 'temporal'
        
        # Carrega dicionário hierárquico
        self.hierarchical = {}
        if hierarchical_path:
            self._load_hierarchical(hierarchical_path)
        
        # Fallback para flat (se necessário)
        self.flat_dict = {}
        if flat_dict_path:
            self._load_flat(flat_dict_path)
    
    def _load_hierarchical(self, path: Path) -> None:
        """Carrega dicionário hierárquico."""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                self.hierarchical = json.load(f)
            print(f"✅ Dicionário hierárquico carregado: {len(self.hierarchical)} marcas")
        except Exception as e:
            print(f"⚠️ Erro ao carregar dicionário hierárquico: {e}")
    
    def _load_flat(self, path: Path) -> None:
        """Carrega dicionário flat (fallback)."""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                self.flat_dict = json.load(f)
            print(f"✅ Dicionário flat carregado: {len(self.flat_dict)} entradas")
        except Exception as e:
            print(f"⚠️ Erro ao carregar dicionário flat: {e}")
    
    def has_exact_sku(self, query: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Verifica se a query já contém um SKU específico.
        Retorna (tem_sku, sku, marca)
        """
        query_lower = query.lower()
        
        # ⭐ 1. Primeiro: padrões de SKU específico (com números)
        sku_patterns = [
            r'[A-Z]{2,3}[-]?\d{3}[-]?\d{2,4}',     # AN515-56, AN515-57-7447
            r'\d{2,4}[A-Z]{2,4}',                   # 15ACH6, 15IRX9
            r'[A-Z]{2,3}\s\d{3}\s\d{4}',            # G7 7588, XPS 15 9500
            r'[a-z]+\s\d{1,2}[a-z]?\s?\d{4}[a-z]?', # Legion 5 15ACH6
            r'[a-z]{3,4}\d{4}',                     # fa5075, gv301
            r'82[a-z0-9]{4}',                       # 82k2022xin (Lenovo)
            r'83[a-z0-9]{4}',                       # 83jj000din (Lenovo)
            r'g7\s*7588',                           # G7 7588
            r'xps\s*15\s*9500',                     # XPS 15 9500
        ]
        
        for pattern in sku_patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                sku = match.group(0)
                # Verifica se parece um SKU real (tem números)
                if re.search(r'\d', sku):
                    print(f"   🔍 SKU detectado pelo padrão '{pattern}': {sku}")
                    return True, sku, None
        
        # ⭐ 2. Verifica termos que são claramente SKUs (NÃO genéricos)
        non_generic_terms = [
            '15ach6', '15ach6h', '15iah7', '15arp8', '15imh6', '15ith6',  # Lenovo
            'an515-56', 'an515-57', 'an515-58', 'an515-46', 'an515-47',    # Acer
            'g7 7588', 'g7 7590', 'g15 5510', 'g15 5520',                   # Dell
            'fa5075', 'fx507', 'gv301', 'gz301',                             # ASUS
            'victus 15-fa', 'victus 16-d',                                   # HP
        ]
        
        for term in non_generic_terms:
            if term in query_lower:
                print(f"   🔍 SKU detectado (termo específico): {term}")
                return True, term.upper(), None
        
        return False, None, None
    
    # query_expansion.py - Adicione este método

    def has_specific_sku(self, query: str) -> bool:
        """
        Verifica se a query contém um SKU específico.
        Retorna True se encontrar qualquer padrão de SKU.
        """
        query_lower = query.lower()
        
        # Lista de SKUs conhecidos (para detecção rápida)
        known_skus = [
            # Lenovo Legion
            '15ach6', '15ach6h', '15iah7', '15arp8', '15imh6', '15ith6',
            '15irx9', '15irx10', '15iax10', '16irx9', '16irx8',
            
            # Acer Nitro
            'an515-56', 'an515-57', 'an515-58', 'an515-46', 'an515-47',
            'an515-45', 'an515-51',
            
            # Dell
            'g7 7588', 'g7 7590', 'g15 5510', 'g15 5511', 'g15 5515',
            'g15 5520', 'g15 5525', 'g15 5530', 'xps 15 9500', 'xps 15 9520',
            
            # ASUS
            'fx507', 'fa507', 'gv301', 'gz301', 'ga402', 'gu603',
            
            # HP
            'victus 15-fa', 'victus 16-d', 'omen 16-wf',
        ]
        
        for sku in known_skus:
            if sku in query_lower:
                print(f"   🔒 SKU conhecido detectado: {sku}")
                return True
        
        # Padrões regex para SKU
        sku_patterns = [
            r'[A-Z]{2,3}[-]?\d{3}[-]?\d{2,4}',     # AN515-56, AN515-57-7447
            r'\d{2,4}[A-Z]{2,4}',                   # 15ACH6, 16IRX9
            r'[A-Z]{2,3}\s\d{3}\s\d{4}',            # G7 7588, XPS 15 9500
            r'[a-z]+\s\d{1,2}[a-z]?\s?\d{4}[a-z]?', # Legion 5 15ACH6
            r'[a-z]{3,4}\d{4}',                     # fa5075, gv301
            r'82[a-z0-9]{4}',                       # 82k2022xin (Lenovo)
            r'83[a-z0-9]{4}',                       # 83jj000din (Lenovo)
            r'g7\s*7588',                           # G7 7588
            r'xps\s*15\s*9500',                     # XPS 15 9500
            r'pavilion\s*15-ec\d{4}',               # Pavilion 15-ec9999
        ]
        
        for pattern in sku_patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                sku = match.group(0)
                print(f"   🔒 SKU detectado pelo padrão: {sku}")
                return True
        
        # Verifica se a query tem padrão de "modelo + número" (ex: "Nitro 5" não é SKU)
        # Mas "Nitro 5 AN515-56" tem SKU
        if re.search(r'[A-Z]{2,3}\d{3}', query, re.IGNORECASE):
            print(f"   🔒 Padrão de SKU detectado (letras+números)")
            return True
        
        return False
    
    def get_synonyms_for_expansion(self, brand: str, family: str, subfamily: str) -> List[str]:
        """
        Retorna sinônimos para expansão (APENAS termos GENÉRICOS).
        """
        synonyms = []
        
        # ⭐ Mapeamento manual para termos genéricos (recomendado)
        manual_synonyms = {
            ('acer', 'nitro', '5'): [
                'acer nitro 5',
                'nitro 5 gaming',
                'acer nitro series'
            ],
            ('acer', 'nitro', 'base'): [
                'acer nitro',
                'nitro gaming'
            ],
            ('dell', 'g_series', '15'): [
                'dell g15',
                'dell g series 15',
                'g15 gaming laptop'
            ],
            ('dell', 'g_series', 'base'): [
                'dell g series',
                'g series gaming'
            ],
            ('lenovo', 'legion', '5'): [
                'lenovo legion 5',
                'legion 5 gaming',
                'lenovo legion series'
            ],
            ('lenovo', 'legion', 'base'): [
                'lenovo legion',
                'legion gaming'
            ],
            ('hp', 'victus', '15'): [
                'hp victus 15',
                'victus 15 gaming'
            ],
            ('hp', 'victus', 'base'): [
                'hp victus',
                'victus gaming'
            ],
            ('asus', 'tuf', 'f15'): [
                'asus tuf f15',
                'tuf gaming f15'
            ],
            ('asus', 'tuf', 'a15'): [
                'asus tuf a15',
                'tuf gaming a15'
            ],
            ('asus', 'tuf', 'base'): [
                'asus tuf',
                'tuf gaming'
            ],
            ('msi', 'thin', 'base'): [
                'msi thin',
                'thin gaming'
            ],
            ('msi', 'katana', 'base'): [
                'msi katana',
                'katana gaming'
            ],
        }
        
        key = (brand, family, subfamily)
        if key in manual_synonyms:
            return manual_synonyms[key][:self.max_terms]
        
        # Busca no dicionário hierárquico (com filtro rigoroso)
        if brand in self.hierarchical:
            if family in self.hierarchical[brand]:
                if subfamily in self.hierarchical[brand][family]:
                    items = self.hierarchical[brand][family][subfamily]
                    
                    for item in items:
                        # ⭐ SÓ ADICIONA se NÃO parecer um SKU específico
                        if self._is_generic_term(item):
                            if item not in synonyms and item != subfamily:
                                synonyms.append(item)
        
        # Remove duplicatas e limita
        synonyms = list(dict.fromkeys(synonyms))[:self.max_terms]
        
        return synonyms

    def _is_generic_term(self, term: str) -> bool:
        """Verifica se um termo é genérico (não é SKU específico)."""
        term_lower = term.lower()
        
        # ⭐ Termos que são claramente SKUs específicos (com números e hífens)
        if re.search(r'[a-z]{2,3}[-]?\d{3}[-]?\d{2,4}', term_lower):
            return False
        
        if re.search(r'\d{4}[a-z]{2,4}', term_lower):  # 15ACH6
            return False
        
        if re.search(r'[a-z]{3}\d{4}', term_lower):    # fa5075
            return False
        
        if re.search(r'82[a-z0-9]{4}', term_lower):    # 82k2022xin
            return False
        
        # ⭐ Termos genéricos permitidos
        generic_terms = [
            'acer nitro 5', 'nitro 5 gaming', 'acer nitro',
            'lenovo legion 5', 'legion 5 gaming', 'lenovo legion',
            'dell g15', 'g15 gaming', 'dell g series',
            'asus tuf', 'tuf gaming', 'asus tuf f15', 'asus tuf a15',
            'hp victus', 'victus gaming', 'hp victus 15',
            'msi thin', 'thin gaming', 'msi katana', 'katana gaming',
            'nitro 5', 'legion 5', 'victus 15', 'omen 16'
        ]
        
        if term_lower in generic_terms:
            return True
        
        # Termos muito curtos ou genéricos
        if len(term.split()) <= 3 and not re.search(r'\d', term):
            return True
        
        return False

    def extract_brand_and_family(self, query: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Extrai marca, família e subfamília da query para expansão.
        """
        query_lower = query.lower()
        
        # ⭐ Verificações manuais prioritárias (resolvem conflitos)
        manual_mappings = [
            (r'acer.*nitro', 'acer', 'nitro', '5'),
            (r'nitro 5(?!.*acer)', 'acer', 'nitro', '5'),
            (r'lenovo.*legion', 'lenovo', 'legion', '5'),
            (r'legion 5(?!.*lenovo)', 'lenovo', 'legion', '5'),
            (r'hp.*victus', 'hp', 'victus', '15'),
            (r'victus(?!.*hp)', 'hp', 'victus', '15'),
            (r'dell.*g7', 'dell', 'g_series', '15'),
            (r'g7\s*7588', 'dell', 'g_series', '15'),
            (r'asus.*tuf', 'asus', 'tuf', 'base'),
            (r'tuf(?!.*asus)', 'asus', 'tuf', 'base'),
            (r'msi.*thin', 'msi', 'thin', 'base'),
            (r'msi.*katana', 'msi', 'katana', 'base'),
        ]
        
        for pattern, brand, family, subfamily in manual_mappings:
            if re.search(pattern, query_lower):
                return brand, family, subfamily
        
        # ⭐ Busca no dicionário hierárquico
        brand_priority = ['acer', 'lenovo', 'asus', 'dell', 'hp', 'msi']
        
        for brand in brand_priority:
            if brand in self.hierarchical:
                for family, subfamilies in self.hierarchical[brand].items():
                    family_readable = family.replace('_', ' ')
                    
                    if family_readable in query_lower:
                        for subfamily_name, items in subfamilies.items():
                            subfamily_readable = subfamily_name.replace('_', ' ')
                            if subfamily_readable in query_lower and subfamily_readable != 'base':
                                return brand, family, subfamily_name
        
        # ⭐ Tenta detectar apenas pela marca
        for brand in brand_priority:
            if brand in query_lower:
                # Marca detectada, mas família não - retorna genérico
                if brand == 'acer':
                    return brand, 'nitro', '5'
                elif brand == 'lenovo':
                    return brand, 'legion', '5'
                elif brand == 'dell':
                    return brand, 'g_series', '15'
                elif brand == 'hp':
                    return brand, 'victus', '15'
                elif brand == 'asus':
                    return brand, 'tuf', 'base'
        
        return None, None, None
    
    def expand_query(self, query: str) -> str:
        """
        Expande query usando dicionário hierárquico.
        ⭐ Só expande se NÃO houver SKU específico!
        """
        # ⭐ VERIFICAÇÃO FORTE: Se tem SKU, NÃO expande
        if self.has_specific_sku(query):
            print(f"   🚫 SKU detectado - expansão CANCELADA")
            return query
        
        # Para V9 (temporal), verifica também números
        if self.variant == "temporal":
            # Verifica se a query tem padrão de modelo com números
            if re.search(r'\b[A-Za-z]*\d{3,}[A-Za-z]*\b', query):
                print(f"   🚫 Padrão de modelo detectado - expansão CANCELADA")
                return query
        
        # Extrai marca e família para expansão
        brand, family, subfamily = self.extract_brand_and_family(query)
        
        if not brand or not family:
            return query
        
        # Obtém sinônimos da mesma subfamília
        synonyms = self.get_synonyms_for_expansion(brand, family, subfamily)
        
        if not synonyms:
            return query
        
        # Constrói query expandida
        new_terms = []
        query_lower = query.lower()
        
        for term in synonyms:
            term_lower = term.lower()
            if term_lower not in query_lower and len(term) >= 3:
                # ⭐ Verifica se o termo não contém SKU
                if not self.has_specific_sku(term):
                    new_terms.append(term)
        
        new_terms = new_terms[:self.max_terms]
        
        if new_terms:
            expanded = f"{query} {' '.join(new_terms)}"
            print(f"   🔧 Expansão: +{len(new_terms)} termos")
            print(f"   📝 Termos adicionados: {new_terms}")
            return expanded
        
        return query
    
    def debug_query(self, query: str) -> Dict:
        """Debug: mostra o que seria adicionado."""
        has_sku, sku, brand = self.has_exact_sku(query)
        
        if has_sku:
            return {
                "query": query,
                "has_sku": True,
                "sku": sku,
                "brand": brand,
                "will_expand": False,
                "reason": f"SKU específico detectado: {sku}"
            }
        
        # Verifica se tem números
        if self.variant == "temporal" and re.search(r'\d{3,}', query):
            return {
                "query": query,
                "has_sku": True,
                "sku": "números detectados",
                "brand": None,
                "will_expand": False,
                "reason": "Números detectados na query (possível SKU)"
            }
        
        brand, family, subfamily = self.extract_brand_and_family(query)
        
        if not brand or not family:
            return {
                "query": query,
                "has_sku": False,
                "brand": brand,
                "family": family,
                "will_expand": False,
                "reason": "Família não identificada"
            }
        
        synonyms = self.get_synonyms_for_expansion(brand, family, subfamily)
        
        return {
            "query": query,
            "has_sku": False,
            "brand": brand,
            "family": family,
            "subfamily": subfamily,
            "will_expand": len(synonyms) > 0,
            "synonyms": synonyms[:self.max_terms],
            "expanded": self.expand_query(query) if synonyms else query
        }

"""
rag_engine.py
Classe principal do RAG Temporal - versão reduzida.
"""










class SpecialistTimeAwareRAG:
    """
    Engine RAG com Auditoria Silenciosa e Normalização por Sinônimos.
    Aplica penalidade temporal adaptativa com fallback inteligente.
    """
    
    def __init__(self, json_path: Union[str, Path], 
                variant_name: str = "V9_HYBRID_AUDITOR",
                embedding_cache=None, 
                use_expansion: bool = True):
        
        # Inicializa configurações
        self.config = RAGConfig(variant_name)
        self.config.use_expansion = use_expansion
        
        print(f"--- 🧠 RAG ENGINE ATIVADA (Variante: {variant_name}) ---")
        print(f"   Temporal config: {self.config.yearly_penalty_rate*100}%/year penalty, "
            f"fallback after {self.config.old_doc_threshold_years}y")
        
        # Inicializa componentes
        self._init_components(json_path, embedding_cache)
        
        # Pipeline de busca
        self.search_pipeline = SearchPipeline(
            faiss_manager=self.faiss_manager,
            data_loader=self.data_loader,
            temporal_scorer=self.temporal_scorer,
            fallback_searcher=self.fallback_searcher,
            context_builder=self.context_builder,
            config=self.config
        )
        
        print(f"✅ Sistema inicializado com {len(self.data_loader.documents)} documentos")
    
    def _init_components(self, json_path: Union[str, Path], embedding_cache) -> None:
        """Inicializa todos os componentes do sistema."""
        
        # Gerenciador de cache
        self.cache_manager = CacheManager(external_cache=embedding_cache)
        
        # Gerenciador de embeddings
        self.embedding_manager = EmbeddingManager(
            model=self.config.embedding_model
        )
        
        # Carregamento de dados
        self.data_loader = DataLoader()
        self.data_loader.load_documents(json_path)
        
        # Gerenciador FAISS
        self.faiss_manager = FAISSManager(
            dimension=self.config.embedding_dimension
        )
        
        if self.data_loader.documents:
            self.faiss_manager.build_index(self.data_loader.documents)
        
        # Expansão de query
        hierarchical_dict_path = VALIDACAO_CONFIG / 'dictionary_synonyms_hierarchical_v4.json'
        flat_dict_path = VALIDACAO_CONFIG / 'dictionary_synonyms_flat_v9.json'

        self.query_expander = QueryExpander(
            hierarchical_path=hierarchical_dict_path,
            flat_dict_path=flat_dict_path,
            max_terms=self.config.max_synonym_terms,
            variant="temporal"
        )
        
        # Sistema de scoring temporal
        self.temporal_scorer = TemporalScorer(
            yearly_penalty_rate=self.config.yearly_penalty_rate,
            recency_threshold=self.config.recency_threshold,
            low_coverage_multiplier=self.config.low_coverage_penalty_multiplier
        )
        
        # Sistema de fallback
        self.fallback_searcher = FallbackSearcher(
            similarity_threshold=self.config.similarity_threshold,
            max_fallback_docs=self.config.max_fallback_docs,
            old_doc_threshold_years=self.config.old_doc_threshold_years
        )
        
        # Gerenciador de prompts
        self.prompt_manager = PromptManager(
            variant_name=self.config.variant_name,
            prompts_dir=self.config.prompts_dir
        )
        
        # Auditor de resposta
        self.auditor = ResponseAuditor()
        
        # Construtor de contexto
        self.context_builder = ContextBuilder(
            max_chars=self.config.max_context_chars
        )
    
    async def _get_embedding(self, query: str) -> np.ndarray:
        """Obtém embedding com cache."""
        return await self.cache_manager.get_embedding(
            query, 
            self.embedding_manager.compute_embedding
        )
    
    async def search(self, query: str, ref_date: str = "2026-03-23") -> Dict:
        """
        Executa busca RAG completa.
        O comportamento é controlado APENAS pelo prompt system.
        """
        print(f"🔍 Processando: {query[:60]}...")
        ref_dt = datetime.strptime(ref_date, "%Y-%m-%d")
        
        # 1. Expansão de query
        expanded_query = query
        if self.config.use_expansion:
            expanded_query = self.query_expander.expand_query(query)
            if expanded_query != query:
                print(f"📝 Query expandida: {expanded_query[:80]}...")
        
        # 2. Embedding
        query_vector = await self._get_embedding(expanded_query)
        
        # 3. Busca via pipeline
        final_results = await self.search_pipeline.execute(
            query_vector=query_vector,
            query=query,
            ref_dt=ref_dt,
            expanded_query=expanded_query
        )
        
        # 4. Construção de contexto
        context_str = self.context_builder.build_context(final_results)
        
        # 5. Geração de resposta
        response = await self._generate_response(context_str, query, ref_date)
        
        # 6. Extração de auditoria
        audited_response = self.auditor.extract_audit(response)
        
        # 7. Montagem do resultado
        result = self._build_result(
            audited_response, final_results, expanded_query, 
            ref_dt, []
        )
        
        self._cleanup()
        return result
    
    async def _generate_response(self, context_str: str, query: str, 
                        ref_date: str) -> str:
        """Gera resposta usando prompt do JSON."""
        
        sys_prompt = self.prompt_manager.build_system_prompt()
        
        few_shot = self.prompt_manager.get_examples_for_few_shot()
        if few_shot:
            sys_prompt += "\n" + few_shot
        
        audit_format = self.prompt_manager.get_audit_format_instructions()
        if audit_format:
            sys_prompt += "\n" + audit_format
        
        user_content = self.prompt_manager.build_user_prompt(
            context_str, query, ref_date
        )
        
        response = await asyncio.to_thread(
            ollama.chat,
            model=self.config.current_model,
            messages=[
                {'role': 'system', 'content': sys_prompt},
                {'role': 'user', 'content': user_content}
            ],
            options={
                "temperature": self.config.temperature, 
                "top_p": self.config.top_p
            },
            keep_alive=0
        )
        
        return response['message']['content']
    
    def _build_result(self, audited_response: Dict, final_results: List[Dict],
                     expanded_query: str, ref_dt: datetime,
                     scored_results: List[Dict]) -> Dict:
        """Constrói o dicionário de resultado final."""
        
        penalty_stats = self.temporal_scorer.get_penalty_stats(final_results)
        
        fallback_used = False
        if hasattr(self.fallback_searcher, 'should_activate'):
            fallback_used = self.fallback_searcher.should_activate([])
        
        return {
            "answer": audited_response["clean_answer"],
            "audit_trail": audited_response["audit_log"],
            "titles": [r['doc'].get('metadata', {}).get('title', 'Unknown') 
                      for r in final_results],
            "sources": [r['doc'].get('original_text', '') for r in final_results],
            "retrieved_metadata": [r['doc'].get('metadata', {}) for r in final_results],
            "normalized_query": expanded_query,
            "diagnostic": {
                "num_documents_retrieved": len(final_results),
                "cpu_embeddings": True,
                "cache_used": self.cache_manager.external_cache is not None,
                "fallback_used": fallback_used,
                "best_temporal_gap_years": round(final_results[0]['temporal_gap'], 2) if final_results else 0,
                "recent_docs_count": sum(1 for r in final_results if r.get('temporal_gap', 0) < 0.5),
                **penalty_stats
            }
        }
    
    def _cleanup(self) -> None:
        """Limpeza de memória."""
        gc.collect()

"""
search_pipeline.py
Pipeline de busca do RAG Temporal.
"""




class SearchPipeline:
    """
    Gerencia o pipeline de busca: FAISS → temporal scoring → fallback → merge.
    """
    
    def __init__(self, faiss_manager, data_loader, temporal_scorer,
                 fallback_searcher, context_builder, config):
        self.faiss_manager = faiss_manager
        self.data_loader = data_loader
        self.temporal_scorer = temporal_scorer
        self.fallback_searcher = fallback_searcher
        self.context_builder = context_builder
        self.config = config
    
    async def execute(self, query_vector: np.ndarray, query: str,
                     ref_dt: datetime, expanded_query: str) -> List[Dict]:
        """
        Executa o pipeline completo de busca.
        
        Args:
            query_vector: Vetor da query
            query: Query original
            ref_dt: Data de referência
            expanded_query: Query expandida (pode ser igual à original)
            
        Returns:
            Lista de resultados finais (já com contexto)
        """
        # 1. Busca FAISS
        search_results = self.faiss_manager.search(
            query_vector, 
            k=self.config.search_top_k
        )
        
        # 2. Scoring temporal
        scored_results = self._apply_temporal_scoring(
            search_results, ref_dt, query_vector
        )
        
        # 3. Fallback se necessário
        final_results = await self._apply_fallback_if_needed(
            scored_results, query_vector, ref_dt
        )
        
        return final_results
    
    def _apply_temporal_scoring(self, search_results: List[Tuple], 
                                ref_dt: datetime, 
                                query_vector: np.ndarray) -> List[Dict]:
        """Aplica scoring temporal nos resultados."""
        domain_recency_cache = {}
        scored_results = []
        
        for idx, distance in search_results:
            doc = self.data_loader.documents[idx]
            doc_id = doc.get('id', idx)
            doc_date = doc.get('date_iso', '2024-01-01')[:10]
            
            # Gap temporal
            temporal_gap = self.temporal_scorer.calculate_temporal_gap(doc_date, ref_dt)
            
            # Recência do domínio (cacheada)
            if doc_id not in domain_recency_cache:
                model = doc.get('metadata', {}).get('model', '')
                domain_recency_cache[doc_id] = self.temporal_scorer.calculate_domain_recency(
                    model, ref_dt, self.data_loader.documents
                )
            
            recency_multiplier = domain_recency_cache[doc_id]
            
            # Score final
            final_score, penalty, status = self.temporal_scorer.score_document(
                distance, temporal_gap, recency_multiplier
            )
            
            scored_results.append({
                'doc': doc,
                'idx': idx,
                'semantic_score': distance,
                'final_score': final_score,
                'temporal_gap': temporal_gap,
                'temporal_status': status,
                'penalty_applied': penalty,
                'recency_multiplier': recency_multiplier,
                'date': doc_date
            })
        
        # Ordena por score final
        scored_results.sort(key=lambda x: x['final_score'])
        
        return scored_results
    
    async def _apply_fallback_if_needed(self, scored_results: List[Dict],
                                       query_vector: np.ndarray,
                                       ref_dt: datetime) -> List[Dict]:
        """Aplica fallback se necessário."""
        
        if self.fallback_searcher.should_activate(scored_results):
            self.config.log("🔄 Ativando fallback sem penalidade temporal...")
            
            existing_ids = {r['idx'] for r in scored_results}
            
            fallback_results = await self.fallback_searcher.semantic_only_search(
                query_vector.reshape(1, -1),
                self.faiss_manager.index,
                self.data_loader.documents,
                ref_dt,
                existing_ids
            )
            
            if fallback_results:
                return self._merge_results(scored_results, fallback_results)
        
        # Sem fallback, retorna top resultados
        return scored_results[:self.config.max_results_returned]
    
    def _merge_results(self, primary: List[Dict], fallback: List[Dict]) -> List[Dict]:
        """Mescla resultados primários e fallback."""
        existing_ids = {r['doc'].get('id', r['idx']) for r in primary}
        merged = primary[:4]  # Top 4 do primário
        
        for fb in fallback:
            if len(merged) >= self.config.max_results_returned:
                break
            
            fb_id = fb['doc'].get('id', hash(fb.get('date', '')))
            if fb_id not in existing_ids:
                merged.append(fb)
                existing_ids.add(fb_id)
        
        merged.sort(key=lambda x: x['final_score'])
        return merged[:self.config.max_results_returned]

"""
temporal_scoring.py
Sistema de penalidade temporal adaptativa.
"""


class TemporalScorer:
    """Aplica penalidade temporal adaptativa baseada em idade e cobertura do domínio."""
    
    def __init__(self, yearly_penalty_rate: float = 0.03,
                 recency_threshold: int = 3,
                 low_coverage_multiplier: float = 0.3):
        self.yearly_penalty_rate = yearly_penalty_rate
        self.recency_threshold = recency_threshold
        self.low_coverage_multiplier = low_coverage_multiplier
        
    def calculate_temporal_gap(self, doc_date: str, ref_date: datetime) -> float:
        """
        Calcula o gap temporal em anos.
        
        Args:
            doc_date: Data do documento (YYYY-MM-DD)
            ref_date: Data de referência
            
        Returns:
            float: Gap em anos
        """
        try:
            doc_dt = datetime.strptime(doc_date[:10], "%Y-%m-%d")
            return (ref_date - doc_dt).days / 365.25
        except (ValueError, IndexError):
            return 0.0
    
    def calculate_domain_recency(self, doc_model: str, ref_date: datetime, 
                                 all_docs: List[Dict]) -> float:
        """
        Calcula o fator de recência do domínio.
        
        Quanto mais documentos recentes, MAIOR o multiplicador (mais penalidade).
        Domínios com pouca cobertura recebem penalidade reduzida.
        
        Args:
            doc_model: Modelo do documento
            ref_date: Data de referência
            all_docs: Todos os documentos para contar recência
            
        Returns:
            float: Multiplicador de penalidade (0.3 a 1.0)
        """
        if not doc_model:
            return 1.0  # Sem modelo, penalidade padrão
        
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
        
        # Mais documentos recentes = maior penalidade para os antigos
        recency_ratio = min(recent_count / self.recency_threshold, 1.0)
        
        # Multiplicador: mínimo = low_coverage, máximo = 1.0
        return max(self.low_coverage_multiplier, recency_ratio)
    
    def score_document(self, semantic_score: float, temporal_gap: float, 
                      recency_multiplier: float) -> Tuple[float, float, str]:
        """
        Calcula o score final de um documento.
        
        Args:
            semantic_score: Score de similaridade semântica
            temporal_gap: Gap temporal em anos
            recency_multiplier: Multiplicador baseado na cobertura do domínio
            
        Returns:
            Tuple[float, float, str]: (final_score, penalty_applied, status)
        """
        if temporal_gap <= 0:
            # Documento futuro ou mesma data
            return semantic_score, 0.0, "future_or_current"
        
        # Cálculo da penalidade
        base_penalty = 1.0 + (temporal_gap * self.yearly_penalty_rate)
        final_penalty = 1.0 + (base_penalty - 1.0) * recency_multiplier
        final_score = semantic_score * final_penalty
        
        penalty_applied = final_penalty - 1.0
        status = f"old_gap_{temporal_gap:.1f}y_penalty_{final_penalty:.2f}"
        
        return final_score, penalty_applied, status
    
    def get_penalty_stats(self, scored_results: List[Dict]) -> Dict:
        """
        Calcula estatísticas de penalidade dos resultados.
        
        Args:
            scored_results: Lista de resultados pontuados
            
        Returns:
            Dict: Estatísticas de penalidade
        """
        if not scored_results:
            return {"avg_penalty": 0, "max_penalty": 0, "docs_with_penalty": 0}
        
        penalties = [r.get('penalty_applied', 0) for r in scored_results]
        docs_with_penalty = sum(1 for p in penalties if p > 0)
        
        return {
            "avg_penalty": round(sum(penalties) / len(penalties), 4),
            "max_penalty": round(max(penalties), 4),
            "docs_with_penalty": docs_with_penalty,
            "total_docs": len(scored_results)
        }

"""
auditor.py
Sistema de extração e validação de auditoria das respostas.
"""


class ResponseAuditor:
    """
    Extrai e valida a auditoria das respostas do LLM.
    Separa a resposta em trilha de auditoria e resposta limpa.
    """
    
    def __init__(self):
        # Padrões regex para extração
        self.audit_pattern = re.compile(
            r"AUDIT:(.*?)(?=ANSWER:|$)", 
            re.DOTALL | re.IGNORECASE
        )
        self.answer_pattern = re.compile(
            r"ANSWER:(.*)", 
            re.DOTALL | re.IGNORECASE
        )
    
    def extract_audit(self, full_response: str) -> Dict[str, str]:
        """
        Extrai auditoria e resposta limpa do output do modelo.
        
        Args:
            full_response: Resposta completa do LLM
            
        Returns:
            Dict com 'audit_log' e 'clean_answer'
        """
        # Extrai seção AUDIT
        audit_match = self.audit_pattern.search(full_response)
        audit_log = audit_match.group(1).strip() if audit_match else "No audit log provided."
        
        # Extrai seção ANSWER
        answer_match = self.answer_pattern.search(full_response)
        clean_answer = answer_match.group(1).strip() if answer_match else full_response.strip()
        
        return {
            "audit_log": audit_log,
            "clean_answer": clean_answer
        }
    
    def validate_audit_format(self, audit_log: str) -> bool:
        """
        Valida se o formato da auditoria está correto.
        
        Args:
            audit_log: Log de auditoria extraído
            
        Returns:
            bool: True se formato é válido
        """
        # Verifica se contém IDs de fonte
        has_source_ids = bool(re.search(r'\[\[ID_\d+', audit_log))
        
        # Verifica se menciona datas
        has_dates = bool(re.search(r'DATE:', audit_log))
        
        # Verifica se menciona documentos antigos se aplicável
        has_old_docs_note = ("years old" in audit_log.lower() or 
                            "older than" in audit_log.lower())
        
        return has_source_ids and has_dates
    
    def add_temporal_diagnostic(self, audit_log: str, 
                               best_gap: float, 
                               fallback_used: bool) -> str:
        """
        Adiciona diagnóstico temporal à auditoria.
        
        Args:
            audit_log: Log de auditoria original
            best_gap: Melhor gap temporal em anos
            fallback_used: Se fallback foi usado
            
        Returns:
            str: Auditoria enriquecida com diagnóstico
        """
        diagnostic = f" [Temporal: best_gap={best_gap:.1f}y, fallback={'yes' if fallback_used else 'no'}]"
        return audit_log + diagnostic
    
    def extract_source_ids(self, audit_log: str) -> list:
        """
        Extrai IDs de fontes mencionadas na auditoria.
        
        Args:
            audit_log: Log de auditoria
            
        Returns:
            list: Lista de IDs extraídos
        """
        pattern = r'\[\[ID_(\d+)'
        matches = re.findall(pattern, audit_log)
        return [int(m) for m in matches]
    
    def extract_dates_from_audit(self, audit_log: str) -> list:
        """
        Extrai datas mencionadas na auditoria.
        
        Args:
            audit_log: Log de auditoria
            
        Returns:
            list: Lista de datas (YYYY-MM-DD)
        """
        pattern = r'DATE:\s*(\d{4}-\d{2}-\d{2})'
        matches = re.findall(pattern, audit_log)
        return matches

"""
cache_manager.py
Gerenciamento de cache LRU interno e cache externo.
"""


class CacheManager:
    """Gerencia cache interno LRU e cache externo."""
    
    def __init__(self, external_cache: Any = None, maxsize: int = 200):
        self.external_cache = external_cache
        self._cache_func = lru_cache(maxsize=maxsize)(self._compute_embedding)
        
    def _compute_embedding(self, query: str) -> np.ndarray:
        """
        Método placeholder para ser sobrescrito.
        O decorador @lru_cache será aplicado na subclasse.
        """
        raise NotImplementedError("Subclasses devem implementar _compute_embedding")
    
    async def get_embedding(self, query: str, compute_func) -> np.ndarray:
        """
        Obtém embedding com prioridade para cache externo.
        
        Args:
            query: Texto da query
            compute_func: Função para computar embedding se não estiver em cache
        """
        # 1. Verifica cache externo
        if self.external_cache:
            cached = self.external_cache.get(query)
            if cached is not None:
                return cached
        
        # 2. Verifica cache interno / computa
        embedding = await asyncio.to_thread(compute_func, query)
        
        # 3. Salva no cache externo
        if self.external_cache:
            self.external_cache.set(query, embedding)
        
        return embedding
    
    def get_stats(self) -> Dict:
        """Retorna estatísticas dos caches."""
        stats = {
            "internal_hits": 0,
            "internal_misses": 0,
            "internal_currsize": 0,
            "external_cache_size": 0
        }
        
        if hasattr(self._cache_func, 'cache_info'):
            cache_info = self._cache_func.cache_info()
            stats.update({
                "internal_hits": cache_info.hits,
                "internal_misses": cache_info.misses,
                "internal_currsize": cache_info.currsize
            })
        
        if self.external_cache:
            external_stats = self.external_cache.stats()
            stats["external_cache_size"] = external_stats.get('size', 0)
        
        return stats
    
    def clear(self) -> None:
        """Limpa o cache interno."""
        if hasattr(self._cache_func, 'cache_clear'):
            self._cache_func.cache_clear()

"""
config.py
Configurações centralizadas do RAG Temporal.
"""



class RAGConfig:
    """Configurações do RAG Engine."""
    
    def __init__(self, variant_name: str = "V9_HYBRID_AUDITOR"):
        # Modelo e dimensões
        self.embedding_dimension: int = 1024
        self.current_model: str = "phi3.5:latest"
        self.embedding_model: str = "bge-m3:latest"
        
        # Busca
        self.search_top_k: int = 20
        self.similarity_threshold: float = 1.2
        self.max_context_chars: int = 2000
        
        # Temporalidade adaptativa
        self.yearly_penalty_rate: float = 0.03
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
        self.prompts_dir: Path = VALIDACAO_CONFIG
        # self.prompts_dir: Path = Path(__file__).parent.parent / 'core' / 'paths'
        
        # Logging
        self.verbose: bool = True

    def log(self, message: str) -> None:
        """Log condicional baseado em verbose."""
        if self.verbose:
            print(message)

"""
context_builder.py
Construtor de contexto para o LLM a partir dos resultados da busca.
"""


class ContextBuilder:
    """
    Constrói o contexto formatado para envio ao LLM.
    Inclui informações temporais e metadados relevantes.
    """
    
    def __init__(self, max_chars: int = 2000):
        self.max_chars = max_chars
    
    def build_context(self, scored_results: List[Dict]) -> str:
        """
        Constrói string de contexto formatada.
        
        Args:
            scored_results: Lista de resultados pontuados
            
        Returns:
            str: Contexto formatado para o LLM
        """
        context_parts = []
        
        for i, result in enumerate(scored_results):
            doc = result['doc']
            context_part = self._build_document_context(i, result)
            context_parts.append(context_part)
        
        return "\n\n".join(context_parts)
    
    def _build_document_context(self, index: int, result: Dict) -> str:
        """
        Constrói o contexto para um único documento.
        
        Args:
            index: Índice do documento
            result: Resultado pontuado
            
        Returns:
            str: Contexto do documento formatado
        """
        doc = result['doc']
        metadata = doc.get('metadata', {})
        
        # Informações do documento
        title = metadata.get('title') or metadata.get('model') or f"Source_{index}"
        date = result.get('date', 'Unknown')
        text = doc.get('original_text', '')
        
        # Trunca texto se necessário
        if len(text) > self.max_chars:
            text = text[:self.max_chars] + "..."
        
        # Adiciona indicador de idade
        age_indicator = self._get_age_indicator(result.get('temporal_gap', 0))
        
        # Adiciona status temporal
        temporal_note = self._get_temporal_note(result)
        
        # Constrói cabeçalho
        header = f"[[ID_{index} | DATE: {date}{age_indicator} | TITLE: {title}]]"
        
        # Adiciona notas temporais se necessário
        if temporal_note:
            header += f"\n{temporal_note}"
        
        return f"{header}\n{text}"
    
    def _get_age_indicator(self, temporal_gap: float) -> str:
        """
        Gera indicador de idade do documento.
        
        Args:
            temporal_gap: Gap temporal em anos
            
        Returns:
            str: Indicador de idade
        """
        if temporal_gap > 5:
            return f" [VERY OLD: {temporal_gap:.1f} years]"
        elif temporal_gap > 2:
            return f" [OLD: {temporal_gap:.1f} years]"
        elif temporal_gap > 1:
            return f" [NOTE: This document is {temporal_gap:.1f} years old]"
        elif temporal_gap > 0.5:
            return f" [Slightly dated: {temporal_gap:.1f} years]"
        else:
            return ""
    
    def _get_temporal_note(self, result: Dict) -> str:
        """
        Gera nota temporal baseada no status.
        
        Args:
            result: Resultado pontuado
            
        Returns:
            str: Nota temporal
        """
        status = result.get('temporal_status', '')
        
        if "fallback" in status:
            return "⚠️ FALLBACK: This document retrieved without temporal penalty"
        elif "future" in status:
            return "ℹ️ This document is from the future relative to reference date"
        elif result.get('penalty_applied', 0) > 0.3:
            penalty_pct = result['penalty_applied'] * 100
            return f"📅 Note: Temporal penalty of {penalty_pct:.0f}% applied"
        
        return ""
    
    def build_compact_context(self, scored_results: List[Dict], 
                             max_docs: int = 5) -> str:
        """
        Constrói versão compacta do contexto.
        
        Args:
            scored_results: Resultados pontuados
            max_docs: Número máximo de documentos
            
        Returns:
            str: Contexto compacto
        """
        # Seleciona apenas os melhores documentos
        top_results = scored_results[:max_docs]
        
        # Reduz tamanho máximo por documento
        original_max = self.max_chars
        self.max_chars = min(self.max_chars, 1500)
        
        context = self.build_context(top_results)
        
        # Restaura configuração original
        self.max_chars = original_max
        
        return context
