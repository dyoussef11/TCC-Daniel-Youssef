"""
context_builder.py
Construtor de contexto para o LLM a partir dos resultados da busca.
"""

from typing import Dict, List

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