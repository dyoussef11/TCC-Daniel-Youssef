"""
auditor.py
Sistema de extração e validação de auditoria das respostas.
"""

import re
from typing import Dict

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