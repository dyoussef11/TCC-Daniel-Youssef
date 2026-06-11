"""
custom_evaluatorV4.py - Evaluator compatível com DeepEval, utilizando instructor
no modo JSON para evitar tool calls múltiplas.
"""

from deepeval.models.base_model import DeepEvalBaseLLM
from ollama import AsyncClient, Client
import instructor
from pydantic import BaseModel, ValidationError
from typing import Optional, Type, Any, Union
import asyncio
import json

class OllamaEvaluator(DeepEvalBaseLLM):
    _global_semaphore = asyncio.Semaphore(1)

    def __init__(self, model_name: str = "qwen3:4b-instruct", prompt_version: Optional[str] = None):
        self.model_name = model_name
        self.prompt_version = prompt_version

        # --- CRIA CLIENTES INSTRUCTOR COM MODO JSON EXPLÍCITO ---
        # O modo JSON força o modelo a retornar apenas JSON válido, sem tool calls.
        # Isso resolve o erro "multiple tool calls".
        self.client = instructor.from_provider(
            f"ollama/{self.model_name}",
            mode=instructor.Mode.JSON
        )
        self.async_client = instructor.from_provider(
            f"ollama/{self.model_name}",
            async_client=True,
            mode=instructor.Mode.JSON
        )

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
            "You will be asked to produce a structured JSON output that follows a specific schema. "
            "Do not invent your own schema – you must comply exactly with the schema provided via the 'response_model' parameter."
        )

    def load_model(self):
        return self.model_name

    def get_model_name(self) -> str:
        return f"ollama/{self.model_name} ({self.prompt_version})"

    def generate(self, prompt: str, schema: Optional[Type[BaseModel]] = None) -> Union[BaseModel, str]:
        if schema is None:
            # Resposta simples (string)
            raw_client = Client(host="http://localhost:11434")
            response = raw_client.chat(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": self.system_content},
                    {"role": "user", "content": prompt}
                ],
                options={"temperature": 0.0}
            )
            return response['message']['content']

        # Tenta gerar com validação Pydantic
        try:
            resp = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": self.system_content},
                    {"role": "user", "content": prompt}
                ],
                response_model=schema,
                temperature=0.0,
                max_retries=2
            )
            return resp
        except Exception as e:
            print(f"⚠️ Erro ao gerar saída estruturada: {e}")
            # --- FALLBACK ROBUSTO: cria uma instância com campos padrão ---
            # Tenta obter os nomes dos campos obrigatórios e preencher com valores vazios
            try:
                # Se o schema tem fields, cria um dicionário com valores padrão
                default_values = {}
                for field_name, field_info in schema.model_fields.items():
                    if field_info.annotation == list:
                        default_values[field_name] = []
                    elif field_info.annotation == str:
                        default_values[field_name] = ""
                    else:
                        # Para outros tipos, usa None
                        default_values[field_name] = None
                return schema.model_validate(default_values)
            except:
                # Último recurso: retorna uma instância vazia (pode causar erro, mas evita quebra completa)
                return schema.model_construct()

    async def a_generate(self, prompt: str, schema: Optional[Type[BaseModel]] = None) -> Union[BaseModel, str]:
        async with OllamaEvaluator._global_semaphore:
            if schema is None:
                raw_client = AsyncClient(host="http://localhost:11434")
                response = await raw_client.chat(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": self.system_content},
                        {"role": "user", "content": prompt}
                    ],
                    options={"temperature": 0.0}
                )
                return response['message']['content']

            try:
                resp = await self.async_client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": self.system_content},
                        {"role": "user", "content": prompt}
                    ],
                    response_model=schema,
                    temperature=0.0,
                    max_retries=2
                )
                return resp
            except Exception as e:
                print(f"⚠️ Erro async ao gerar saída estruturada: {e}")
                # Mesmo fallback robusto
                try:
                    default_values = {}
                    for field_name, field_info in schema.model_fields.items():
                        if field_info.annotation == list:
                            default_values[field_name] = []
                        elif field_info.annotation == str:
                            default_values[field_name] = ""
                        else:
                            default_values[field_name] = None
                    return schema.model_validate(default_values)
                except:
                    return schema.model_construct()