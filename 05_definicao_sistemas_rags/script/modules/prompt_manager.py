"""
prompt_manager.py - CORRIGIDO
Gerenciamento de prompts do sistema RAG - USA A ESTRUTURA COMPLETA DO JSON.
"""

import json
from pathlib import Path
from typing import Dict, Optional

class PromptManager:
    """
    Carrega e gerencia prompts do sistema RAG.
    Agora usa TODA a estrutura do JSON, incluindo:
    - core_principles
    - constraints
    - audit_pipeline
    - output_format
    - brand_patterns
    - prompt_template
    """
    
    def __init__(self, variant_name: str = "V9_HYBRID_AUDITOR", 
                 prompts_dir: Optional[Path] = None):
        self.variant_name = variant_name
        self.prompts_dir = prompts_dir or Path("config")
        
        # Estrutura completa carregada do JSON
        self.prompts: Dict = {}
        self.system_role: str = ""
        self.core_principles: list = []
        self.constraints: list = []
        self.audit_pipeline: list = []
        self.output_format: Dict = {}
        self.brand_patterns: Dict = {}
        self.prompt_template: str = ""
        
        # Carrega tudo
        self._load_prompts()
    
    def _load_prompts(self) -> None:
        """Carrega TODOS os campos do JSON."""
        prompt_file = self.prompts_dir / 'prompt_rag_temporal_hybrid_V9.json'
        
        try:
            with open(prompt_file, 'r', encoding='utf-8') as f:
                all_prompts = json.load(f)
                
                if self.variant_name in all_prompts:
                    variant = all_prompts[self.variant_name]
                    
                    # Carrega TODOS os campos
                    self.system_role = variant.get('system_role', '')
                    self.core_principles = variant.get('core_principles', [])
                    self.constraints = variant.get('constraints', [])
                    self.audit_pipeline = variant.get('audit_pipeline', [])
                    self.output_format = variant.get('output_format', {})
                    self.brand_patterns = variant.get('brand_patterns', {})
                    self.prompt_template = variant.get('prompt_template', '')
                    self.examples = variant.get('examples', {})
                    
                    print(f"✅ Prompts carregados para variante: {self.variant_name}")
                    print(f"   - {len(self.core_principles)} core principles")
                    print(f"   - {len(self.constraints)} constraints")
                    print(f"   - {len(self.audit_pipeline)} audit steps")
                    print(f"   - {len(self.examples)} examples loaded")
                else:
                    print(f"⚠️ Variante '{self.variant_name}' não encontrada")
                    
        except FileNotFoundError:
            print(f"⚠️ Arquivo de prompt não encontrado: {prompt_file}")
        except json.JSONDecodeError as e:
            print(f"❌ Erro ao decodificar JSON: {e}")
    
    def build_system_prompt(self) -> str:
        """
        Constrói o system prompt COMPLETO usando TODOS os campos do JSON.
        """
        parts = []
        
        # 1. System Role
        if self.system_role:
            parts.append(self.system_role)
        
        # 2. Core Principles
        if self.core_principles:
            parts.append("\nCORE PRINCIPLES:")
            for principle in self.core_principles:
                parts.append(f"- {principle}")
        
        # 3. Constraints
        if self.constraints:
            parts.append("\nCRITICAL RULES:")
            for constraint in self.constraints:
                if isinstance(constraint, str):
                    parts.append(f"- {constraint}")
                elif isinstance(constraint, dict):
                    # Para constraints aninhadas
                    for key, value in constraint.items():
                        parts.append(f"- {key}: {value}")
        
        # 4. Audit Pipeline
        if self.audit_pipeline:
            parts.append("\nAUDIT PROCEDURE:")
            for step in self.audit_pipeline:
                parts.append(step)
        
        # 5. Output Format
        if self.output_format:
            parts.append("\nMANDATORY OUTPUT FORMAT:")
            if 'audit' in self.output_format:
                parts.append(f"Audit format: {self.output_format['audit']}")
            if 'answer' in self.output_format:
                parts.append(f"Answer format: {self.output_format['answer']}")
        
        # 6. Brand Patterns (como referência, não para inferência)
        if self.brand_patterns and 'note' in self.brand_patterns:
            parts.append(f"\nBRAND PATTERNS (identification only): {self.brand_patterns['note']}")
        
        return "\n".join(parts)
    
    def build_user_prompt(self, context: str, query: str, 
                         ref_date: str = "2026-04-28") -> str:
        """
        Constrói o user prompt usando o TEMPLATE do JSON.
        AGORA USA o prompt_template definido no JSON!
        """
        # Se temos um template no JSON, usa ele
        if self.prompt_template:
            # Substitui as variáveis no template
            prompt = self.prompt_template.replace('{context}', context)
            prompt = prompt.replace('{query}', query)
            prompt = prompt.replace('{ref_date}', ref_date)
            return prompt
        
        # Fallback se não houver template
        return f"""=== TECHNICAL CONTEXT ===
            {context}

            === USER QUERY ===
            {query}

            === REFERENCE DATE ===
            {ref_date}

            === INSTRUCTIONS ===
            1. Extract the exact model/SKU from the user's query.
            2. Check if this EXACT SKU exists in the context above.
            3. If the EXACT SKU is NOT in the context, respond that information is unavailable.
            4. DO NOT infer specifications from different models, even same brand.
            5. Output format: AUDIT: [...] then ANSWER: [...] 
            (without any [RAG] or [INTERNAL] tags in ANSWER)

            === RESPONSE ==="""
    
    # prompt_manager.py - SUBSTITUA O MÉTODO get_examples_for_few_shot

    def get_examples_for_few_shot(self) -> str:
        """
        Retorna exemplos formatados para few-shot learning.
        CORRIGIDO: Agora mostra exemplos COMPLETOS (query + expected_answer)
        """
        if not hasattr(self, 'examples') or not self.examples:
            return ""
        
        examples_text = "\n=== EXAMPLES OF CORRECT BEHAVIOR ===\n"
        examples_text += "Follow these EXACT patterns:\n\n"
        
        # Exemplo 1: SKU não encontrado - deve dizer que não tem dados
        if 'sku_not_found_acer' in self.examples:
            ex = self.examples['sku_not_found_acer']
            examples_text += f"""Example 1 (SKU not found):
    Query: "{ex.get('query', '')}"
    Expected Answer: "{ex.get('expected_answer', '')}"
    Expected Audit: "{ex.get('expected_audit', '')}"
    """
        
        # Exemplo 2: Pergunta sobre série sem SKU - deve PEDIR SKU
        examples_text += """
    Example 2 (Generic series - ASK FOR SKU):
    Query: "Does the Nitro 5 have Thunderbolt 4?"
    Expected Answer: "To provide accurate specifications, I need the complete model number (SKU). Could you please provide the full model number (e.g., AN515-56, AN515-57)?"
    Expected Audit: "AUDIT: [SKU: None] | [STATUS: missing] | [CROSS-CHECK: asked_for_SKU]"

    Example 3 (Comparison without data - CANNOT COMPARE):
    Query: "Does AN515-56 have same Thunderbolt as AN515-57?"
    Expected Answer: "I cannot compare these models because I lack complete data for one or both SKUs. I only provide comparisons when both specifications are verified in my database."
    Expected Audit: "AUDIT: [SKU: AN515-56, AN515-57] | [STATUS: missing_second_model] | [CROSS-CHECK: comparison_refused]"

    Example 4 (Specific model not in DB - ADMIT UNAVAILABILITY):
    Query: "What is the maximum RAM for Acer AN515-56?"
    Expected Answer: "Information for the Acer AN515-56 model is not available in the documentation provided for this specific SKU. No inference from similar models is permitted."
    Expected Audit: "AUDIT: [SKU: AN515-56] | [STATUS: not_found] | [SOURCES: none] | [CROSS-CHECK: no_inference]"
    """
    
        return examples_text
    
    def get_audit_format_instructions(self) -> str:
        """
        Retorna instruções específicas para o formato de auditoria.
        """
        if self.output_format and 'audit' in self.output_format:
            return f"""AUDIT FORMAT REQUIREMENTS:
        Your AUDIT section MUST follow this exact format:
        {self.output_format['audit']}

        Components:
        - SKU: The exact model identifier from the query
        - STATUS: 'found' if SKU in context, 'not_found' if not
        - SOURCES: Document IDs from context or INTERNAL concepts
        - CROSS-CHECK: Always include 'no_inference_detected' or explain any inference"""
        return ""
    
    def get_sku_validation_rules(self) -> str:
        """
        Extrai regras de validação de SKU dos constraints e principles.
        """
        rules = []
        
        # Procura regras específicas de SKU
        for constraint in self.constraints:
            if isinstance(constraint, str) and ('SKU' in constraint or 'model' in constraint.lower()):
                rules.append(constraint)
        
        return "\n".join(rules) if rules else ""