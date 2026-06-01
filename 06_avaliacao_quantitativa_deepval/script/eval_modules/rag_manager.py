"""core/rag_manager.py - Gerencia ambas as versões do RAG"""

from pathlib import Path
from typing import Optional

from RAG_BaseLine import VanillaRAG
from RAG_Temporal_V9_3 import SpecialistTimeAwareRAG


class ComparativeRAGManager:
    """Gerencia V1 (Vanilla) e V9 (Temporal) com carregamento lazy"""
    
    def __init__(self, base_path: Path, config, embedding_cache=None):
        self.base_path = base_path
        self.config = config
        self.embedding_cache = embedding_cache
        self._vanilla: Optional[VanillaRAG] = None
        self._temporal: Optional[SpecialistTimeAwareRAG] = None
    
    @property
    def vanilla(self) -> VanillaRAG:
        if self._vanilla is None:
            print("🔄 Carregando RAG Vanilla (V1 - SEM expansão)...")
            self._vanilla = VanillaRAG(
                self.base_path,
                embedding_cache=self.embedding_cache,
                use_expansion=self.config.vanilla_use_expansion
            )
        return self._vanilla
    
    @property
    def temporal(self) -> SpecialistTimeAwareRAG:
        if self._temporal is None:
            print("🔄 Carregando RAG Temporal (V9 - COM expansão)...")
            self._temporal = SpecialistTimeAwareRAG(
                self.base_path,
                variant_name=self.config.temporal_variant,
                embedding_cache=self.embedding_cache,
                use_expansion=self.config.temporal_use_expansion
            )
            self._temporal.current_model = self.config.model_name
            self._temporal.temperature = self.config.temperature
            self._temporal.search_top_k = self.config.search_top_k
        return self._temporal
    
    # No rag_manager.py, adicione logs para debug

    async def search_both(self, query: str, ref_date: str) -> tuple:
        """Executa busca em ambas as versões em paralelo"""
        import asyncio
        
        print(f"\n{'='*60}")
        print(f"🔍 QUERY: {query}")
        print(f"📅 REF_DATE: {ref_date}")
        print(f"{'='*60}")
        
        v1_task = self.vanilla.search(query)
        v9_task = self.temporal.search(query, ref_date)
        
        results = await asyncio.gather(v1_task, v9_task)
        
        # ⭐ Log da resposta do V9 para diagnóstico
        print(f"\n📊 V9 RESPONSE PREVIEW: {results[1]['answer']}...")
        print(f"📋 V9 AUDIT: {results[1].get('audit_trail', 'N/A')}")
        
        return results[0], results[1]