# ollama_base_ragas_llm.py
import json
import re
from typing import Any, List, Optional
from langchain_core.callbacks import Callbacks
from ragas.llms.base import BaseRagasLLM
from ragas.llms import LLMResult, Generation
import ollama

class OllamaBaseRagasLLM(BaseRagasLLM):
    def __init__(self, model: str, base_url: Optional[str] = None, temperature: float = 0.0):
        self.model = model
        self.base_url = base_url or "http://localhost:11434"
        self.temperature = temperature
        self.client = ollama.Client(host=self.base_url)

    async def _agenerate(
        self,
        prompts: List[str],
        n: int = 1,
        temperature: float = None,
        stop: Optional[List[str]] = None,
        callbacks: Callbacks = None,
        **kwargs: Any
    ) -> LLMResult:
        generations = []
        for prompt in prompts:
            response = self.client.chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                format='json',
                options={"temperature": temperature or self.temperature, "stop": stop}
            )
            raw = response['message']['content']
            generations.append([Generation(text=raw)])
        return LLMResult(generations=generations)

    def generate(
        self,
        prompts: List[str],
        n: int = 1,
        temperature: float = None,
        stop: Optional[List[str]] = None,
        callbacks: Callbacks = None,
        **kwargs: Any
    ) -> LLMResult:
        # Para compatibilidade síncrona, chama o assíncrono (simplificado)
        import asyncio
        return asyncio.run(self._agenerate(prompts, n, temperature, stop, callbacks, **kwargs))

    def get_num_tokens(self, text: str) -> int:
        return len(text.split())