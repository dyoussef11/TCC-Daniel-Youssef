# expand_query_hierarchical.py
"""
Expansão de query usando o dicionário hierárquico flat.
"""

import json
import re
from pathlib import Path
from core.paths import VALIDACAO_CONFIG

DICT_PATH = VALIDACAO_CONFIG / 'dictionary_synonyms_flat_v3.json'


def expand_query(query: str, flat_dict: dict, max_terms: int = 5) -> tuple:
    """
    Expande a query usando correspondência de chaves do dicionário flat.
    Retorna (query_expandida, termos_adicionados)
    """
    query_lower = query.lower()
    
    # Encontra a melhor chave correspondente
    best_key = None
    best_match_len = 0
    
    for key in flat_dict.keys():
        if key in query_lower:
            if len(key) > best_match_len:
                best_match_len = len(key)
                best_key = key
    
    if not best_key:
        return query, []
    
    # Obtém os sinônimos
    synonyms = flat_dict[best_key]
    
    # Filtra termos que já estão na query
    new_terms = []
    for term in synonyms:
        term_lower = term.lower()
        if term_lower not in query_lower and len(term) >= 3:
            # Pula termos muito genéricos
            if term not in ['gaming', 'laptop', 'notebook', 'edition']:
                new_terms.append(term)
    
    if not new_terms:
        return query, []
    
    # Limita número de termos
    new_terms = new_terms[:max_terms]
    
    expanded = f"{query} {' '.join(new_terms)}"
    return expanded, new_terms


# Teste rápido
if __name__ == "__main__":
    with open(DICT_PATH, 'r') as f:
        flat_dict = json.load(f)
    
    test_queries = [
        "HP Victus 15",
        "victus 16",
        "TUF A15",
        "Legion Slim 7",
        "Predator Helios Neo 16",
        "ROG Flow X13",
        "ASUS TUF Gaming F15",
        "Dell XPS 15",
        "MSI Katana 15",
        "ROG Strix G15",
    ]
    
    print("=" * 60)
    print("🧪 TESTE DE EXPANSÃO HIERÁRQUICA")
    print("=" * 60)
    
    for query in test_queries:
        expanded, terms = expand_query(query, flat_dict)
        print(f"\n📝 Query: {query}")
        print(f"   Expandida: {expanded}")
        print(f"   Termos: {terms}")