# custom_evaluatorV5.py - versão corrigida
from deepeval.models.base_model import DeepEvalBaseLLM
from ollama import AsyncClient
import asyncio
import json
import re
from typing import Optional, Type
from pydantic import BaseModel

class OllamaEvaluator(DeepEvalBaseLLM):
    _global_semaphore = asyncio.Semaphore(1)

    def __init__(self, 
                 model_name: str = "qwen3:4b-instruct", 
                 prompt_version: Optional[str] = None,
                 temperature: float = 0.0):
        self.model_name = model_name
        self.prompt_version = prompt_version
        self.temperature = temperature
        self.async_client = AsyncClient()
        # Conteúdo real do sistema (copiado do seu V4)
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
            "Do not invent keys. Use only the standard keys."
        )

    def load_model(self):
        return self.model_name

    def _clean_json(self, content: str) -> dict:
        """Extrai e valida o primeiro JSON válido da string."""
        content = content.strip()
        content = re.sub(r'```json\s*|\s*```', '', content)
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if not match:
            raise ValueError("No JSON object found")
        json_str = match.group(0)
        # Remove vírgulas extras
        json_str = re.sub(r',\s*}', '}', json_str)
        json_str = re.sub(r',\s*\]', ']', json_str)
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            try:
                from json_repair import repair_json
                repaired = repair_json(json_str)
                return json.loads(repaired)
            except ImportError:
                raise

    async def a_generate(self, prompt: str, schema: Optional[Type[BaseModel]] = None) -> str:
        full_prompt = prompt
        if self.prompt_version:
            full_prompt += f"\n[INFO] Evaluating variant: {self.prompt_version}."

        async with OllamaEvaluator._global_semaphore:
            response = await self.async_client.chat(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": self.system_content},
                    {"role": "user", "content": full_prompt}
                ],
                format='json',
                options={"temperature": self.temperature}
            )
            raw = response['message']['content']
            data = self._clean_json(raw)
            # Não valida com schema aqui; retorna JSON string
            return json.dumps(data, ensure_ascii=False)

    def generate(self, prompt: str, schema: Optional[Type[BaseModel]] = None) -> str:
        return asyncio.run(self.a_generate(prompt, schema))

    def get_model_name(self) -> str:
        return f"Ollama {self.model_name} ({self.prompt_version})"