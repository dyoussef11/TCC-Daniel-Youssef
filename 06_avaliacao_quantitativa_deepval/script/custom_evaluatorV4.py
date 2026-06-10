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
        "OUTPUT INSTRUCTION: Return valid JSON with a 'verdict' of 'yes' (pass), 'no' (fail), or 'idk' (cannot determine)."
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
            # Dentro de _clean_response, após carregar o JSON em 'parsed'

            if "verdicts" in parsed and isinstance(parsed["verdicts"], list):
                for item in parsed["verdicts"]:
                    if isinstance(item, dict):
                        # Correção de várias grafias erradas da chave "verdict"
                        wrong_keys = ["ver- dict", "verdicts", "veredict", "veritecture", "veredicto"]
                        for wrong in wrong_keys:
                            if wrong in item:
                                item["verdict"] = item.pop(wrong)
                                break   # usa a primeira que encontrar
                        
                        # Se ainda não tem "verdict", talvez o item seja o próprio veredicto
                        if "verdict" not in item and len(item) == 1:
                            # Pega a primeira chave/valor e assume que é o veredicto
                            key, val = next(iter(item.items()))
                            item["verdict"] = val
                            del item[key]
                        
                        # Normalização do valor para yes/no/idk
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