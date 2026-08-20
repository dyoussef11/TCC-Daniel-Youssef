"""
custom_evaluatorV3.py - Evaluator adaptado para as Regras MIXED com AsyncClient Nativo e Auto-Correção
"""

from deepeval.models.base_model import DeepEvalBaseLLM
from ollama import AsyncClient
import asyncio
import json
import re
from typing import Optional


class OllamaEvaluator(DeepEvalBaseLLM):
    # SEMÁFORO GLOBAL: Garante concorrência máxima de exatamente 1 chamada por vez no Ollama.
    _global_semaphore = asyncio.Semaphore(1)

    def __init__(self, model_name: str = "qwen3:4b-instruct", prompt_version: Optional[str] = None):
        self.model_name = model_name
        self.prompt_version = prompt_version
        self.async_client = AsyncClient()

        # Sistema de auditoria atualizado para a variante MIXED do segundo prompt
        self.system_content = (
            "Act as a Senior Hardware RAG Auditor evaluate responses based on MIXED KNOWLEDGE guidelines.\n\n"
            
            "CRITICAL MIXED RULES:\n"
            "1. FALLBACK IS PERMITTED: For SPECIFIC SKU queries, if EXTERNAL context (RAG) is missing or incomplete, "
            "   the model IS ALLOWED to use INTERNAL training knowledge to fill gaps. This is now considered FAITHFUL.\n"
            "2. DISCLAIMER CONSTRAINT: For a specific SKU fallback to be faithful, the model MUST explicitly state "
            "   that external documentation was not found (e.g., 'No external documentation found for...').\n"
            "3. SERIES QUERIES: For product lines without SKU (e.g., 'Nitro 5'), the model is strictly FORBIDDEN "
            "   from giving specs. It MUST request the specific SKU. Answering with specs here is UNFAITHFUL.\n"
            "4. AUDIT TAGS: V9 MUST include an AUDIT section tagging [RAG:id] or [INTERNAL:domain:YYYY]. "
            "   V1 MUST NOT contain any audit block, tags, or special formatting; it must be completely clean.\n\n"
            
            "CRITICAL OUTPUT INSTRUCTION:\n"
            "You MUST strictly output valid JSON matching the exact schema properties required by DeepEval's prompt.\n"
            "If the schema asks for a 'verdict' property, its value MUST be exactly one of: 'yes', 'no', or 'idk'. "
            "Never use variations like 'id', 'maybe', or empty objects. Adhere strictly to the requested schema keys."
        )

    def load_model(self):
        return self.model_name

    def _clean_response(self, content: str) -> str:
        """Limpa blocos de código markdown e corrige anomalias comuns do Pydantic."""
        content = content.strip()
        content = re.sub(r'```json\s*|\s*```', '', content)
        
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            content = match.group(0)
            
        try:
            # Força correção de sanidade sintática antes de enviar ao core do DeepEval
            parsed = json.loads(content)
            
            # 1. Corrige problemas de listagem de vereditos
            if "verdicts" in parsed and isinstance(parsed["verdicts"], list):
                for item in parsed["verdicts"]:
                    if isinstance(item, dict):
                        # Se o modelo gerou chaves corrompidas por hífens
                        if "ver- dict" in item:
                            item["verdict"] = item.pop("ver- dict")
                        
                        # Se o modelo gerou a chave no plural em sub-objetos por engano
                        if "verdicts" in item:
                            item["verdict"] = item.pop("verdicts")
                            
                        # Correção do seu erro atual: se gerou 'id' ou quebras, normaliza para 'idk'
                        if "verdict" in item:
                            val = str(item["verdict"]).strip().lower()
                            if val not in ["yes", "no", "idk"]:
                                item["verdict"] = "idk"
                                
            # 2. Garante compatibilidade retroativa para estruturas simples de veredito único
            if "verdict" in parsed:
                val = str(parsed["verdict"]).strip().lower()
                if val not in ["yes", "no", "idk"]:
                    parsed["verdict"] = "idk"
                    
            return json.dumps(parsed, ensure_ascii=False)
        except Exception:
            # Se o JSON estiver completamente quebrado, deixa o fluxo seguir para o fallback nativo
            return content

    async def a_generate(self, prompt: str) -> str:
        version_hint = f"\n[INFO] Evaluating variant: {self.prompt_version}. "
        if self.prompt_version == "V9":
            version_hint += "Expect MANDATORY 'AUDIT:' block with source tags. ANSWER block must be clean."
        else:
            version_hint += "Expect NO tags, NO audit block, NO special formatting. Pure clean answer."

        full_prompt = prompt + version_hint

        # Trava o hardware em uma fila estrita de 1 por vez usando async real
        async with OllamaEvaluator._global_semaphore:
            response = await self.async_client.chat(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": self.system_content},
                    {"role": "user", "content": full_prompt}
                ],
                format='json',
                options={
                    "temperature": 0.0,
                }
            )
            raw_content = response['message']['content']
            return self._clean_response(raw_content)

    def generate(self, prompt: str) -> str:
        return asyncio.run(self.a_generate(prompt))

    def get_model_name(self) -> str:
        return f"Ollama {self.model_name} ({self.prompt_version})"