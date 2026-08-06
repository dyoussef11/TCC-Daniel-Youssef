"""
query_expansion.py
Expansão de queries usando dicionário de sinônimos.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional

# query_expansion.py - MODIFICAR

class QueryExpander:
    def __init__(self, synonym_dict: Optional[Dict] = None, 
                flat_dict_path: Optional[Path] = None,
                max_terms: int = 5,
                variant: str = "vanilla"):  # ⭐ NOVO: vanilla ou temporal
        self.synonym_dict = synonym_dict or {}
        self.flat_dict_path = flat_dict_path
        self.max_terms = max_terms
        self.variant = variant  # 'vanilla' ou 'temporal'
        self._flat_dict: Optional[Dict] = None
        
        if flat_dict_path:
            self._load_flat_dict()
    
    def _load_flat_dict(self) -> None:
        """Carrega o dicionário apropriado baseado na variante."""
        if self.variant == "temporal":
            # Usa dicionário V9 (sem SKUs específicos)
            dict_path = self.flat_dict_path.parent / 'dictionary_synonyms_flat_v9.json'
        else:
            # Usa dicionário original
            dict_path = self.flat_dict_path
        
        try:
            with open(dict_path, 'r', encoding='utf-8') as f:
                self._flat_dict = json.load(f)
            print(f"✅ Dicionário flat carregado: {len(self._flat_dict)} entradas")
            print(f"   (Variante: {self.variant})")
        except FileNotFoundError:
            print(f"⚠️ Dicionário não encontrado: {dict_path}")
            self._flat_dict = {}
            self._flat_dict = {}