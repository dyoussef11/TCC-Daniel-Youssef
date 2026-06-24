"""utils/helpers.py - Funções utilitárias auxiliares"""

import re
import time
import asyncio
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from contextlib import asynccontextmanager


def extract_sku_from_query(query: str) -> Optional[str]:
    """
    Extrai SKU de uma query usando padrões comuns.
    
    Args:
        query: String da query do usuário
        
    Returns:
        SKU encontrado ou None
    """
    patterns = [
        r'[A-Z]{2,3}[-]?\d{3}[-]?\d{2,4}',  # AN515-56, G7-7588
        r'[A-Z]{2,3}\s\d{3}\s\d{4}',         # G7 7588
        r'[A-Z]{2,3}\d{3}[A-Z]?\d{2,4}',     # 15ACH6
    ]
    
    for pattern in patterns:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            return match.group(0)
    return None


def detect_query_type(query: str) -> Dict:
    """
    Detecta o tipo de query para aplicar regras comportamentais.
    
    Args:
        query: String da query do usuário
        
    Returns:
        Dict com tipo e metadados
    """
    query_lower = query.lower()
    
    # Lista de palavras-chave para perguntas técnicas gerais
    general_keywords = [
        'why does', 'how to', 'what is', 'explain', 'difference between',
        'thermal throttl', 'overheating', 'cooling', 'temperature',
        'battery', 'performance', 'upgrade', 'maintenance',
        'troubleshooting', 'problem', 'issue', 'fix', 'repair'
    ]
    
    # 1. Detectar pergunta técnica GERAL
    if not extract_sku_from_query(query):
        for keyword in general_keywords:
            if keyword in query_lower:
                return {"type": "general_tech", "reason": "General technical concept"}
    
    # 2. Detectar comparação
    comparison_patterns = [
        r'(\w+[-]\d+).*same as.*(\w+[-]\d+)',
        r'compare.*(\w+[-]\d+).*(\w+[-]\d+)',
    ]
    for pattern in comparison_patterns:
        match = re.search(pattern, query_lower)
        if match:
            return {
                "type": "comparison",
                "sku1": match.group(1),
                "sku2": match.group(2)
            }
    
    # 3. Detectar série genérica
    series_keywords = ['nitro 5', 'legion 5', 'predator', 'g7', 'xps', 'pavilion']
    for keyword in series_keywords:
        if keyword in query_lower and not extract_sku_from_query(query):
            return {"type": "generic_series", "series": keyword}
    
    # 4. Detectar SKU específico
    sku = extract_sku_from_query(query)
    if sku:
        return {"type": "specific_sku", "sku": sku}
    
    return {"type": "unknown"}


def calculate_improvement(v1_score: float, v9_score: float) -> Dict:
    """
    Calcula melhoria percentual entre V1 e V9.
    
    Args:
        v1_score: Score do V1 (baseline)
        v9_score: Score do V9 (novo)
        
    Returns:
        Dict com diferença absoluta e percentual
    """
    delta = v9_score - v1_score
    delta_pct = (delta / v1_score * 100) if v1_score > 0 else 0
    
    return {
        "absolute": delta,
        "percentage": delta_pct,
        "improved": delta > 0,
        "status": "improved" if delta > 0.05 else "degraded" if delta < -0.05 else "similar"
    }


def format_duration(seconds: float) -> str:
    """
    Formata duração em segundos para string legível.
    
    Args:
        seconds: Segundos totais
        
    Returns:
        String formatada (ex: "1h 23m 45s")
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    
    parts = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if secs > 0 or not parts:
        parts.append(f"{secs}s")
    
    return " ".join(parts)


def safe_truncate(text: str, max_length: int = 500, suffix: str = "...") -> str:
    """
    Trunca texto de forma segura (quebra em palavras).
    
    Args:
        text: Texto original
        max_length: Tamanho máximo
        suffix: Sufixo para indicar truncamento
        
    Returns:
        Texto truncado
    """
    if len(text) <= max_length:
        return text
    
    truncated = text[:max_length]
    last_space = truncated.rfind(' ')
    if last_space > 0:
        truncated = truncated[:last_space]
    
    return truncated + suffix


def extract_brand_from_sku(sku: str) -> Optional[str]:
    """
    Tenta extrair marca de um SKU.
    
    Args:
        sku: Código SKU
        
    Returns:
        Nome da marca ou None
    """
    sku_lower = sku.lower()
    
    brand_patterns = {
        "Acer": ["nitro", "predator", "aspire", "an515", "ph315"],
        "Dell": ["g7", "xps", "latitude", "inspiron"],
        "Lenovo": ["legion", "thinkpad", "yoga", "ideapad"],
        "HP": ["pavilion", "envy", "spectre", "omen"],
        "Asus": ["rog", "tuf", "zenbook", "vivobook"],
        "MSI": ["gf", "gp", "ge", "gs", "stealth"]
    }
    
    for brand, patterns in brand_patterns.items():
        for pattern in patterns:
            if pattern in sku_lower:
                return brand
    
    return None


class Timer:
    """Context manager para medir tempo de execução"""
    
    def __init__(self, name: str = "Operation"):
        self.name = name
        self.start_time = None
        self.end_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, *args):
        self.end_time = time.time()
        elapsed = self.end_time - self.start_time
        print(f"⏱️ {self.name} took {format_duration(elapsed)}")
    
    @property
    def elapsed(self) -> float:
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return 0.0


@asynccontextmanager
async def async_timer(name: str = "Async Operation"):
    """Versão assíncrona do Timer"""
    start = time.time()
    yield
    elapsed = time.time() - start
    print(f"⏱️ {name} took {format_duration(elapsed)}")


def merge_dicts(*dicts: Dict) -> Dict:
    """Mescla múltiplos dicionários (últimos sobrescrevem anteriores)"""
    result = {}
    for d in dicts:
        result.update(d)
    return result


def chunk_list(lst: List, chunk_size: int) -> List[List]:
    """Divide uma lista em chunks menores"""
    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]


def normalize_score(score: float, min_val: float = 0.0, max_val: float = 1.0) -> float:
    """Normaliza um score entre min e max"""
    return max(min_val, min(max_val, score))