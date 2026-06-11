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
        "Act as a Senior Hardware RAG Auditor evaluating responses based on MIXED KNOWLEDGE guidelines.\n\n"
        "CRITICAL RULES (apply equally to all responses):\n"
        "1. For a SPECIFIC SKU query, if external documentation is missing, the response MUST explicitly state "
        "   that no external documentation was found before providing fallback information.\n"
        "2. For a SERIES query (product line without SKU, e.g., 'Nitro 5'), the response MUST NOT provide specifications. "
        "   It MUST ask for the specific SKU.\n"
        "3. For a COMPARISON query with missing data on one or both SKUs, the response may use fallback but must indicate.\n"
        "4. The response MUST be clean and natural, without any tags like [RAG], [INTERNAL], without 'AUDIT:' or 'ANSWER:' blocks, "
        "   and without any special formatting.\n\n"
        "OUTPUT INSTRUCTION: Return **valid JSON** using **exactly** the key names required by the evaluation. "
        "For single verdict: use 'verdict'. For list of verdicts: use 'verdicts'. For truths: use 'truths'. "
        "Do not invent keys like 'ver-than', 'veredict', 'veritect'. Use only the standard keys."
    )

    def load_model(self):
        return self.model_name

    def _clean_response(self, content: str) -> str:
        """Remove markdown e extrai o primeiro JSON válido. Nunca modifica as chaves."""
        content = content.strip()
        # Remove blocos de código markdown
        content = re.sub(r'```json\s*|\s*```', '', content)
        
        # Tenta encontrar o primeiro objeto JSON válido
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            content = match.group(0)
        
        # Valida se é um JSON (sem modificar)
        try:
            parsed = json.loads(content)
            # Retorna o JSON original, com as mesmas chaves que o modelo gerou
            return json.dumps(parsed, ensure_ascii=False)
        except json.JSONDecodeError:
            # Se não for JSON válido, retorna o conteúdo bruto (o DeepEval tentará extrair)
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