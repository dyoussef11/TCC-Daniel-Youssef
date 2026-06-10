"""
custom_evaluatorV3.py - Evaluator adaptado para as Regras MIXED com Semáforo de Hardware
"""

from deepeval.models.base_model import DeepEvalBaseLLM
import ollama
import asyncio
from typing import Optional


class OllamaEvaluator(DeepEvalBaseLLM):
    # SEMÁFORO GLOBAL: Garante concorrência máxima de 1 chamada por vez no Ollama,
    # impedindo que o DeepEval dispare requisições simultâneas para a mesma métrica.
    _global_semaphore = asyncio.Semaphore(1)

    def __init__(self, model_name: str = "qwen3.5:9b", prompt_version: Optional[str] = None):
        self.model_name = model_name
        self.prompt_version = prompt_version

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
            
            "OUTPUT FORMAT (Strict JSON only):\n"
            "{\n"
            "  \"score\": float (0.0 to 1.0),\n"
            "  \"reason\": \"Detailed analysis of fallback transparency, query type compliance, and source tags\"\n"
            "}"
        )

    def load_model(self):
        return self.model_name

    async def a_generate(self, prompt: str) -> str:
        version_hint = f"\n[INFO] Evaluating variant: {self.prompt_version}. "
        if self.prompt_version == "V9":
            version_hint += "Expect MANDATORY 'AUDIT:' block with source tags. ANSWER block must be clean."
        else:
            version_hint += "Expect NO tags, NO audit block, NO special formatting. Pure clean answer."

        full_prompt = prompt + version_hint

        # Trava o barramento físico aqui para impedir execuções simultâneas do Qwen 9B
        async with OllamaEvaluator._global_semaphore:
            response = await asyncio.to_thread(
                ollama.chat,
                model=self.model_name,
                messages=[
                    {"role": "system", "content": self.system_content},
                    {"role": "user", "content": full_prompt}
                ],
                format='json',
                options={
                    "temperature": 0.0,
                    "num_thread": 4,
                    "num_gpu": 20,
                },
                keep_alive="5m"
            )
            return response['message']['content']

    def generate(self, prompt: str) -> str:
        return asyncio.run(self.a_generate(prompt))

    def get_model_name(self) -> str:
        return f"Ollama {self.model_name} ({self.prompt_version})"