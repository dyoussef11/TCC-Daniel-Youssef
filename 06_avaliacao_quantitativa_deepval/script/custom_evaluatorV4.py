"""
custom_evaluatorV4.py - Avaliador leve para DeepEval (sem instructor)
Com suporte a timeout e fallback em caso de falha.
"""

from deepeval.models.base_model import DeepEvalBaseLLM
from ollama import AsyncClient, Client
from pydantic import BaseModel, ValidationError
from typing import Optional, Type, Any, Union, get_origin
import asyncio
import json
import re
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OllamaEvaluator(DeepEvalBaseLLM):
    _semaphore = asyncio.Semaphore(3)  # Permite até 3 chamadas simultâneas

    def __init__(self, model_name: str = "qwen3:4b-instruct", 
                 prompt_version: Optional[str] = None,
                 timeout: int = 120):  # timeout padrão de 120 segundos
        self.model_name = model_name
        self.prompt_version = prompt_version
        self.timeout = timeout

        # Clientes com timeout explícito
        self.sync_client = Client(host="http://localhost:11434", timeout=timeout)
        self.async_client = AsyncClient(host="http://localhost:11434", timeout=timeout)

        self.system_content = (
            "Act as a Senior Hardware RAG Auditor evaluating responses based on MIXED KNOWLEDGE guidelines.\n\n"
            "CRITICAL RULES:\n"
            "1. For a SPECIFIC SKU query with missing external documentation, the response MUST explicitly state "
            "   that no external documentation was found before providing fallback information.\n"
            "2. For a SERIES query (product line without SKU), the response MUST NOT provide specifications. "
            "   It MUST ask for the specific SKU.\n"
            "3. For a COMPARISON query with missing data on one or both SKUs, the response may use fallback but must indicate.\n"
            "4. The response MUST be clean and natural, without any tags like [RAG], [INTERNAL], without 'AUDIT:' or 'ANSWER:' blocks.\n\n"
            "You will be asked to produce a structured JSON output that follows a specific schema. "
            "- CHRONOLOGICAL ANCHOR: The current year is 2026. The response must not invent dates or future specs unless present in the retrieved context."
            "Return ONLY valid JSON with the required fields. Do not add extra text."
        )

    def load_model(self):
        return self.model_name

    def get_model_name(self) -> str:
        return f"ollama/{self.model_name} ({self.prompt_version})"

    def _clean_json(self, raw: str) -> dict:
        raw = raw.strip()
        raw = re.sub(r'```json\s*|\s*```', '', raw)
        start = raw.find('{')
        end = raw.rfind('}')
        if start != -1 and end != -1:
            raw = raw[start:end+1]
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            try:
                from json_repair import repair_json
                repaired = repair_json(raw)
                return json.loads(repaired)
            except ImportError:
                return {}
            except:
                return {}

    def _get_fallback_response(self, schema: Optional[Type[BaseModel]] = None):
        """Retorna um objeto vazio do schema ou uma string de erro."""
        if schema is None:
            return "[TIMEOUT] Falha na geração da resposta."
        default = {}
        for name, field in schema.model_fields.items():
            annotation = field.annotation
            origin = get_origin(annotation)
            if origin is list or annotation is list:
                default[name] = []
            elif origin is dict or annotation is dict:
                default[name] = {}
            elif annotation is str:
                default[name] = ""
            elif annotation is int:
                default[name] = 0
            elif annotation is float:
                default[name] = 0.0
            elif annotation is bool:
                default[name] = False
            else:
                try:
                    default[name] = field.default_factory() if field.default_factory else None
                except:
                    default[name] = None
        return schema.model_validate(default)

    def generate(self, prompt: str, schema: Optional[Type[BaseModel]] = None) -> Union[BaseModel, str]:
        """Versão síncrona (usada pelo DeepEval em algumas métricas)."""
        try:
            if schema is None:
                response = self.sync_client.chat(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": self.system_content},
                        {"role": "user", "content": prompt}
                    ],
                    options={"temperature": 0.0}
                )
                return response['message']['content']

            for attempt in range(2):  # máximo 2 tentativas
                response = self.sync_client.chat(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": self.system_content},
                        {"role": "user", "content": f"{prompt}\n\nRespond with a valid JSON object matching:\n{schema.model_json_schema()}"}
                    ],
                    options={"temperature": 0.0}
                )
                data = self._clean_json(response['message']['content'])
                if data:
                    try:
                        return schema.model_validate(data)
                    except ValidationError:
                        continue
            return self._get_fallback_response(schema)
        except Exception as e:
            logger.error(f"Erro na geração síncrona: {e}")
            return self._get_fallback_response(schema)

    async def a_generate(self, prompt: str, schema: Optional[Type[BaseModel]] = None) -> Union[BaseModel, str]:
        """Versão assíncrona com timeout e semáforo."""
        async with OllamaEvaluator._semaphore:
            try:
                if schema is None:
                    response = await asyncio.wait_for(
                        self.async_client.chat(
                            model=self.model_name,
                            messages=[
                                {"role": "system", "content": self.system_content},
                                {"role": "user", "content": prompt}
                            ],
                            options={"temperature": 0.0}
                        ),
                        timeout=self.timeout
                    )
                    return response['message']['content']

                for attempt in range(2):
                    try:
                        response = await asyncio.wait_for(
                            self.async_client.chat(
                                model=self.model_name,
                                messages=[
                                    {"role": "system", "content": self.system_content},
                                    {"role": "user", "content": f"{prompt}\n\nRespond with a valid JSON object matching:\n{schema.model_json_schema()}"}
                                ],
                                options={"temperature": 0.0}
                            ),
                            timeout=self.timeout
                        )
                        data = self._clean_json(response['message']['content'])
                        if data:
                            try:
                                return schema.model_validate(data)
                            except ValidationError:
                                continue
                    except asyncio.TimeoutError:
                        logger.warning(f"Timeout na tentativa {attempt+1} para {self.model_name}")
                        continue
                # Fallback após falhas
                return self._get_fallback_response(schema)
            except Exception as e:
                logger.error(f"Erro na geração assíncrona: {e}")
                return self._get_fallback_response(schema)