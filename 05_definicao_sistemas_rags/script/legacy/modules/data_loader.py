"""
data_loader.py
Sistema de carregamento de documentos com suporte a streaming.
"""

import json
import ijson
from pathlib import Path
from typing import Dict, List, Union, Iterator

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