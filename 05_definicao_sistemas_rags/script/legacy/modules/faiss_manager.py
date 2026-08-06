"""
faiss_manager.py
Gerenciamento do índice FAISS para busca vetorial.
"""

import faiss
import numpy as np
from typing import List, Dict, Tuple, Optional

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