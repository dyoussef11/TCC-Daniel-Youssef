# custom_chat_ollama_json.py
import json
import re
import asyncio
from typing import List, Optional
from langchain_ollama import ChatOllama
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from ollama import AsyncClient

class ChatOllamaJson(ChatOllama):
    def __init__(self, **kwargs):
        # Initialize the base Pydantic model normally
        super().__init__(**kwargs)
        # Store the async client without triggering Pydantic field validation
        object.__setattr__(self, '_json_async_client', AsyncClient(host=self.base_url))

    @property
    def _async_client(self):
        return self._json_async_client

    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager = None,
        **kwargs
    ) -> ChatResult:
        # Convert LangChain messages to Ollama format
        ollama_messages = []
        for msg in messages:
            if isinstance(msg, HumanMessage):
                role = "user"
            elif isinstance(msg, AIMessage):
                role = "assistant"
            elif isinstance(msg, SystemMessage):
                role = "system"
            else:
                continue
            ollama_messages.append({"role": role, "content": msg.content})

        # Build options (temperature, stop, etc.)
        options = {"temperature": self.temperature}
        if stop:
            options["stop"] = stop

        # Call Ollama with **forced JSON format**
        response = await self._async_client.chat(
        model=self.model,
        messages=ollama_messages,
        format='json',
        options=options
    )
        raw = response['message']['content']

        # Limpeza agressiva
        raw = re.sub(r'[\x00-\x1f\x7f]', '', raw)          # remove controles
        raw = re.sub(r',\s*}', '}', raw)                   # vírgula antes de }
        raw = re.sub(r',\s*]', ']', raw)                   # vírgula antes de ]
        raw = re.sub(r'([{,])\s*([a-zA-Z0-9_]+)\s*:', r'\1"\2":', raw)  # adiciona aspas em keys sem aspas

        # Tenta parsear com diferentes estratégias
        parsed = None
        for strategy in [
            lambda: json.loads(raw),
            lambda: json.loads(raw, strict=False),
            lambda: json.loads(re.search(r'\{.*\}', raw, re.DOTALL).group(0)),
            lambda: eval(raw)   # perigoso, mas pode funcionar em JSON simples
        ]:
            try:
                parsed = strategy()
                break
            except:
                continue

        if parsed is None:
            # Fallback: retorna um JSON vazio (RAGAS pode lidar mal, mas evita crash)
            parsed = {"error": "failed_to_parse", "raw": raw[:200]}

        content_str = json.dumps(parsed, ensure_ascii=False)
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=content_str))])