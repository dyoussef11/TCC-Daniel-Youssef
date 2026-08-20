from deepeval.models.base_model import DeepEvalBaseLLM
import ollama
import asyncio
import json
import re

class OllamaEvaluator(DeepEvalBaseLLM):
    def __init__(self, model_name="phi3.5:latest"):
        self.model_name = model_name
        # Prompt do Sistema consolidado para o papel de Auditoria Técnica
        self.system_content = (
            "Act as a Senior Hardware RAG Auditor. Provide deep technical justification.\n\n"
            "STRICT RULES:\n"
            "1. REASONING DEPTH: In the 'reason' fields, explicitly mention which hardware model, SKU, or date "
            "caused the score. Explain WHY the answer is faithful or unfaithful based on the provided Evidence.\n"
            "2. TEMPORAL AUDIT: If there is a mismatch between 2024 internal knowledge and 2025/2026 Evidence, "
            "detail this conflict in the reasoning.\n"
            "3. TAG NEUTRALITY: Ignore [RAG]/[INTERNAL] tags for Relevancy, but use them to judge Faithfulness.\n"
            "4. OUTPUT FORMAT: Return ONLY JSON: {\"score\": float, \"reason\": \"Detailed global analysis\", "
            "\"verdicts\": [{\"verdict\": \"yes/no/idk\", \"reason\": \"Specific evidence-based reason\"}]}.\n"
            "5. NO VAGUENESS: Avoid phrases like 'good alignment'. Use 'The RAM spec matches the 2021 context' instead."
        )

    def load_model(self):
        return self.model_name

    def _clean_response(self, content: str) -> str:
        """
        Limpa e repara a saída do modelo para garantir conformidade com JSON/Pydantic.
        """
        content = content.strip()
        # Remove blocos de código Markdown
        content = re.sub(r'```json\s*|\s*```', '', content)
        
        # Localiza o objeto JSON principal
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            content = match.group(0)
        
        # Normaliza quebras de linha que quebram o parser
        content = content.replace('\n', ' ').replace('\r', '')

        # REPARO DE VERDITO: Força 'yes', 'no' ou 'idk' puro eliminando justificativas internas às aspas
        content = re.sub(r'("verdict":\s*)"(yes|no|idk)[^"]*"', r'\1"\2"', content, flags=re.IGNORECASE)
        
        return content

    async def a_generate(self, prompt: str, max_retries: int = 2) -> str:
        tentativa = 0
        feedback_erro = ""

        while tentativa <= max_retries:
            prompt_final = prompt if tentativa == 0 else (
                f"{prompt}\n\n[SYSTEM WARNING]: Previous response invalid JSON. "
                f"Error: {feedback_erro}. Return ONLY valid JSON."
            )
            
            try:
                response = await asyncio.to_thread(
                    ollama.chat,
                    model="qwen3:4b-instruct",  # Mais rápido que phi3.5
                    messages=[
                        {"role": "system", "content": self.system_content},
                        {"role": "user", "content": prompt_final}
                    ],
                    format='json',
                    options={
                        "temperature": 0,
                        # "num_thread": 8,  # REDUZIDO de 12 para 8
                        "num_thread": 4,  # REDUZIDO de 8 para 4
                        "num_gpu": 20,    # NOVO: força uso da GPU
                    },
                    keep_alive=0
                )
                
                raw_content = response['message']['content']
                cleaned_content = self._clean_response(raw_content)
                json.loads(cleaned_content)
                return cleaned_content

            except (json.JSONDecodeError, Exception) as e:
                tentativa += 1
                feedback_erro = str(e)
                if tentativa > max_retries:
                    return json.dumps({
                        "score": 0.0,
                        "reason": f"JSON generation failed: {feedback_erro}",
                        "verdicts": []
                    })

    def generate(self, prompt: str) -> str:
        """Versão síncrona (fallback)."""
        return asyncio.run(self.a_generate(prompt))

    def get_model_name(self):
        return f"Ollama {self.model_name}"