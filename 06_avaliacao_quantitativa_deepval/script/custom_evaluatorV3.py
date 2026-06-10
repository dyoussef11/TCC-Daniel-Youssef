"""
custom_evaluatorV3.py - Evaluator adaptado para as Regras MIXED com AsyncClient Nativo
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
            
            "OUTPUT FORMAT: You MUST strictly adhere to the JSON schema supplied by the user prompt. "
            "Generate your output inside valid JSON structures matching requested properties precisely."
        )

    def load_model(self):
        return self.model_name

    def _clean_response(self, content: str) -> str:
        """Limpa blocos de código markdown sem quebrar estruturas internas de propriedades."""
        content = content.strip()
        content = re.sub(r'```json\s*|\s*```', '', content)
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            content = match.group(0)
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