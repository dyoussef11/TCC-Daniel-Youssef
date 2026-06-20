"""
custom_evaluatorV4.py - Avaliador leve para DeepEval (sem instructor)
"""

from deepeval.models.base_model import DeepEvalBaseLLM
from ollama import AsyncClient, Client
from pydantic import BaseModel, ValidationError
from typing import Optional, Type, Any, Union, get_origin
import asyncio
import json
import re

class OllamaEvaluator(DeepEvalBaseLLM):
    _semaphore = asyncio.Semaphore(1)

    def __init__(self, model_name: str = "qwen3:4b-instruct", prompt_version: Optional[str] = None):
        self.model_name = model_name
        self.prompt_version = prompt_version
        # Clientes simples (sem instructor)
        self.sync_client = Client(host="http://localhost:11434")
        self.async_client = AsyncClient(host="http://localhost:11434")

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
            "Return ONLY valid JSON with the required fields. Do not add extra text."
        )

    def load_model(self):
        return self.model_name

    def get_model_name(self) -> str:
        return f"ollama/{self.model_name} ({self.prompt_version})"

    def _clean_json(self, raw: str) -> dict:
        raw = raw.strip()
        # Remove code fences
        raw = re.sub(r'```json\s*|\s*```', '', raw)
        # Tenta encontrar o primeiro { e último }
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

    def generate(self, prompt: str, schema: Optional[Type[BaseModel]] = None) -> Union[BaseModel, str]:
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

        for attempt in range(3):
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
                except ValidationError as e:
                    print(f"⚠️ ValidationError (attempt {attempt+1}): {e}")
                    continue

        # Fallback seguro
        print("⚠️ Todas as tentativas de JSON falharam. Usando fallback.")
        try:
            # Tenta validar o default
            return schema.model_validate(self._build_default(schema))
        except ValidationError:
            # Se ainda falhar, cria uma instância com valores padrão (None ou vazios)
            return self._build_empty_instance(schema)

    def _build_default(self, schema: Type[BaseModel]) -> dict:
        """Constrói um dicionário com valores padrão para cada campo."""
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
                # Para outros tipos, tenta usar default_factory ou None
                try:
                    default[name] = field.default_factory() if field.default_factory else None
                except:
                    default[name] = None
        return default

    def _build_empty_instance(self, schema: Type[BaseModel]) -> BaseModel:
        """Cria uma instância vazia do schema, ignorando validações."""
        try:
            return schema()
        except Exception:
            # Se o modelo não tem __init__ sem argumentos, usa **kwargs com None
            empty = {name: None for name in schema.model_fields}
            return schema(**empty)

        
    async def a_generate(self, prompt: str, schema: Optional[Type[BaseModel]] = None) -> Union[BaseModel, str]:
        async with OllamaEvaluator._semaphore:
            if schema is None:
                response = await self.async_client.chat(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": self.system_content},
                        {"role": "user", "content": prompt}
                    ],
                    options={"temperature": 0.0}
                )
                return response['message']['content']

            for attempt in range(3):
                response = await self.async_client.chat(
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
            default = {}
        for name, field in schema.model_fields.items():
            annotation = field.annotation
            origin = get_origin(annotation)
            if origin is list or annotation is list:
                # Se for List[...], cria lista vazia
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
                # Para outros tipos complexos (ex.: nested models), tenta instanciar vazio
                try:
                    default[name] = field.default_factory() if field.default_factory else None
                except:
                    default[name] = None
        return schema.model_validate(default)