"""
prompt_manager.py
Gerenciamento de prompts do sistema.
"""

import json
from pathlib import Path
from typing import Dict, Optional

class PromptManager:
    """
    Carrega e gerencia prompts do sistema RAG.
    """
    
    def __init__(self, variant_name: str = "V9_HYBRID_AUDITOR", 
                 prompts_dir: Optional[Path] = None):
        self.variant_name = variant_name
        self.prompts_dir = prompts_dir or Path("config")
        
        # Prompts carregados
        self.prompts: Dict = {}
        
        # Prompt padrão caso arquivo não exista
        self.default_prompts = {
            "system_role": "You are a technical specialist assistant.",
            "constraints": [
                "Answer only based on the provided context",
                "Be concise and technical",
                "Do not hallucinate or infer specifications not present in the context"
            ]
        }
        
        # Carrega prompts
        self._load_prompts()
    
    def _load_prompts(self) -> None:
        """Carrega prompts do arquivo JSON."""
        prompt_file = self.prompts_dir / 'prompt_rag_temporal_hybrid_V9.json'
        
        try:
            with open(prompt_file, 'r', encoding='utf-8') as f:
                all_prompts = json.load(f)
                
                if self.variant_name in all_prompts:
                    self.prompts = all_prompts[self.variant_name]
                    print(f"✅ Prompts carregados para variante: {self.variant_name}")
                else:
                    print(f"⚠️ Variante '{self.variant_name}' não encontrada, usando padrão")
                    self.prompts = self.default_prompts
                    
        except FileNotFoundError:
            print(f"⚠️ Arquivo de prompt não encontrado: {prompt_file}")
            self.prompts = self.default_prompts
        except json.JSONDecodeError as e:
            print(f"❌ Erro ao decodificar JSON: {e}")
            self.prompts = self.default_prompts
    
    def build_system_prompt(self, include_temporal: bool = True) -> str:
        """
        Constrói prompt do sistema.
        
        Args:
            include_temporal: Se inclui instruções temporais
            
        Returns:
            str: Prompt do sistema formatado
        """
        variant = self.prompts
        
        # Role do sistema
        system_role = variant.get('system_role', self.default_prompts['system_role'])
        
        # Constraints
        constraints = variant.get('constraints', self.default_prompts['constraints'])
        constraints_text = "\n".join(f"- {c}" for c in constraints)
        
        # Constrói prompt base
        prompt = f"""{system_role}

CRITICAL RULES:
{constraints_text}"""
        
        # Adiciona instruções temporais se solicitado
        if include_temporal:
            prompt += """

TEMPORAL AWARENESS:
- Some documents may be older than the reference date. This is noted in the context.
- If the only available information is from older documents, use it but note the age.
- Do not hallucinate or infer specifications not present in the context."""
        
        # Adiciona formato de saída
        prompt += """

MANDATORY OUTPUT FORMAT:
AUDIT: [List source IDs used with dates. Note if any documents were older than reference date]
ANSWER: [Clean technical response]"""
        
        return prompt
    
    def build_user_prompt(self, context: str, query: str, 
                         ref_date: str = "2026-03-23") -> str:
        """
        Constrói prompt do usuário.
        
        Args:
            context: Contexto dos documentos
            query: Query do usuário
            ref_date: Data de referência
            
        Returns:
            str: Prompt do usuário
        """
        return f"""CONTEXT:
{context}

QUERY: {query}

REFERENCE DATE: {ref_date}

Generate your response following the exact format specified."""
    
    def get_constraints_list(self) -> list:
        """
        Retorna lista de constraints.
        
        Returns:
            list: Constraints
        """
        return self.prompts.get('constraints', self.default_prompts['constraints'])
    
    def get_system_role(self) -> str:
        """
        Retorna role do sistema.
        
        Returns:
            str: Role do sistema
        """
        return self.prompts.get('system_role', self.default_prompts['system_role'])
    
    def reload_prompts(self, variant_name: Optional[str] = None) -> None:
        """
        Recarrega prompts (útil para hot-reload).
        
        Args:
            variant_name: Nova variante (opcional)
        """
        if variant_name:
            self.variant_name = variant_name
        
        self._load_prompts()