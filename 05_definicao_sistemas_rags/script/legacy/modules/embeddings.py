"""
embeddings.py
Gerenciamento de embeddings via Ollama (CPU).
"""

import os
import numpy as np
from ollama import Client
from typing import Optional

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