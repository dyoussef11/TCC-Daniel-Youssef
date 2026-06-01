"""
custom_evaluatorV2Backup.py - Evaluator para DeepEval com regras aprimoradas
Versão 3.0 - Com detecção de especulação numérica e regras corrigidas para SKU
"""

from deepeval.models.base_model import DeepEvalBaseLLM
import ollama
import asyncio
import json
import re
from typing import Optional


class OllamaEvaluator(DeepEvalBaseLLM):
    """
    Avaliador LLM para métricas DeepEval com regras específicas para:
    - Distinção entre queries com/sem SKU
    - Detecção de especulação numérica
    - Avaliação correta do STATUS not_found
    """
    
    def __init__(self, model_name: str = "qwen3:4b-instruct", prompt_version: Optional[str] = None):
        """
        Args:
            model_name: Nome do modelo Ollama a ser usado
            prompt_version: 'V9' ou 'V1' - usado para adaptar regras de avaliação
        """
        self.model_name = model_name
        self.prompt_version = prompt_version

        # Sistema de avaliação aprimorado - Versão 3.0
        self.system_content = (
            "Act as a Senior Hardware RAG Auditor. Your job is to evaluate responses that may combine "
            "EXTERNAL context (retrieved documents) and INTERNAL knowledge.\n\n"

            "STRICT RULES:\n"
            "1. ALLOWED KNOWLEDGE MIX: Both external and internal knowledge are permitted. "
            "   However, for SPECIFIC SKU queries, if the answer uses internal knowledge but the external context "
            "   contains contradictory or more recent official specs, the answer is UNFAITHFUL.\n\n"

            "2. FALLBACK RULE (MODIFIED - MORE RESTRICTIVE):\n"
            "   - If external context has NO information about a SPECIFIC SKU, the model:\n"
            "     ✅ MAY explain general concepts about the product series (e.g., 'Nitro 5 series typically uses DDR4')\n"
            "     ✅ MAY describe known limitations or common characteristics\n"
            "     ❌ MAY NOT provide specific numeric specifications (e.g., RAM capacity, clock speeds, slot counts)\n"
            "     ❌ MAY NOT estimate or extrapolate specs from other models\n"
            "     ❌ MAY NOT say 'typically supports X-Y range'\n"
            "     ✅ MUST explicitly state that the exact specification is not available\n"
            "   - This is considered FAITHFUL ONLY if the model provides NO numeric/quantitative speculation.\n"
            "   - PENALTY: Any numeric speculation for specific SKU without external context reduces Faithfulness to ≤0.3.\n\n"

            "3. STATUS EVALUATION (CRITICAL FIX):\n"
            "   - 'STATUS: not_found' is CORRECT when the SPECIFIC INFORMATION requested (e.g., RAM capacity, "
            "     processor model, BIOS version) is absent from the retrieval context, even if the SKU appears "
            "     elsewhere discussing other topics (battery, thermal issues, hardware faults).\n"
            "   - 'STATUS: found' should be used ONLY when the exact requested information is present.\n"
            "   - Do NOT penalize 'not_found' simply because the SKU is mentioned elsewhere for unrelated reasons.\n"
            "   - Example: If query asks for 'maximum RAM' and context mentions SKU but only discusses battery problems, "
            "     'STATUS: not_found' is CORRECT and should score 1.0 for faithfulness on that claim.\n\n"

            "4. SERIES QUERIES (no SKU): If the model answers with specific specs instead of asking for SKU, "
            "   that is UNFAITHFUL to the instruction (even if internal knowledge is correct).\n\n"

            "5. TEMPORAL AUDIT: Internal knowledge <= 2024. External context may be up to current date (2025/2026). "
            "   If a conflict exists, the model should prefer external context for SKU specs. Otherwise mark as unfaithful.\n\n"

            "6. AUDIT SECTION (only for V9): The response includes an 'AUDIT:' block with source tags like [RAG:doc_id] "
            "   or [INTERNAL:concept:YYYY]. Evaluate whether these tags accurately reflect the actual sources used in "
            "   the 'ANSWER:' block. If tags are missing or incorrect, reduce faithfulness score.\n\n"

            "7. FOR V1 (no AUDIT): The response has no tags. Judge faithfulness solely by comparing the answer content "
            "   to the external context + plausible internal knowledge (given cutoff). Assume good faith but penalize "
            "   hallucinations not supported by either source.\n\n"

            "8. SPECIFIC SKU QUERIES - SPECIAL HANDLING:\n"
            "   A query is considered 'SPECIFIC SKU' if it contains a model number like AN515-56, G7 7588, 15ACH6, etc.\n"
            "   For such queries:\n"
            "   - Providing a numeric range (e.g., '8GB to 32GB') without explicit external documentation = UNFAITHFUL\n"
            "   - Providing a specific value (e.g., '32GB') without external documentation = UNFAITHFUL\n"
            "   - Saying 'not available' or 'no information found' = FAITHFUL\n"
            "   - Explaining that specs vary by configuration = FAITHFUL (if no numbers given)\n\n"

            "9. SCORING GUIDELINES:\n"
            "   - Faithfulness 0.0-0.3: Contains invented numeric specs, hallucinated SKUs, or contradictions\n"
            "   - Faithfulness 0.4-0.7: Partially correct but has minor issues or missing source attribution\n"
            "   - Faithfulness 0.8-1.0: Fully aligned with context, no hallucinations, proper disclaimers\n"
            "   - For SPECIFIC SKU queries without context: 'not_found' = 1.0, numeric speculation = ≤0.3\n\n"

            "OUTPUT FORMAT (JSON only):\n"
            "{\n"
            "  \"score\": float (0.0 to 1.0),\n"
            "  \"reason\": \"Detailed global analysis covering source usage, temporal consistency, and any rule violations\",\n"
            "  \"verdicts\": [\n"
            "    {\"verdict\": \"yes/no/idk\", \"reason\": \"Specific evidence‑based reason for each claim\"}\n"
            "  ]\n"
            "}\n\n"

            "ADDITIONAL INSTRUCTIONS:\n"
            "- For 'verdict', 'yes' means faithful, 'no' means unfaithful, 'idk' means cannot determine.\n"
            "- In 'reason', mention the exact SKU, document ID (if any), and whether the answer used internal fallback correctly.\n"
            "- If the query is a SERIES query and the answer asks for SKU, that is 'yes' (faithful to rules).\n"
            "- Do not penalize the absence of AUDIT tags in V1; only evaluate content.\n"
            "- Return ONLY valid JSON. No markdown, no extra text."
        )

    def load_model(self):
        return self.model_name

    def _extract_query_from_prompt(self, prompt: str) -> str:
        """
        Extrai a query original do prompt de avaliação.
        Suporta múltiplos formatos de prompt.
        """
        patterns = [
            r'Input:\s*(.+?)(?=\n|$)',
            r'Question:\s*(.+?)(?=\n|$)',
            r'Query:\s*(.+?)(?=\n|$)',
            r'user_query:\s*(.+?)(?=\n|$)',
            r'QUERY:\s*(.+?)(?=\n|$)',
            r'"input":\s*"(.+?)"',
            r'"query":\s*"(.+?)"',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, prompt, re.IGNORECASE | re.DOTALL)
            if match:
                query = match.group(1).strip()
                # Remove caracteres de escape comuns
                query = query.replace('\\n', ' ').replace('\\"', '"')
                if len(query) > 5:  # Query válida tem pelo menos 5 caracteres
                    return query
        
        # Fallback: pega a primeira linha que parece uma pergunta
        lines = prompt.split('\n')
        for line in lines[:30]:
            line = line.strip()
            if '?' in line and len(line) > 10 and len(line) < 500:
                # Evita pegar linhas que são respostas
                if not any(skip in line.lower() for skip in ['answer:', 'response:', 'output:']):
                    return line
        
        # Último fallback
        return ""

    def _extract_answer_from_prompt(self, prompt: str) -> str:
        """
        Extrai a resposta (actual output) do prompt de avaliação.
        Suporta múltiplos formatos de prompt.
        """
        patterns = [
            r'Actual Output:\s*(.+?)(?=\n\n|\n[A-Z]|$)',
            r'Answer:\s*(.+?)(?=\n\n|\n[A-Z]|$)',
            r'Response:\s*(.+?)(?=\n\n|\n[A-Z]|$)',
            r'RESPONSE:\s*(.+?)(?=\n\n|---|\n\[|$)',
            r'"actual_output":\s*"(.+?)"',
            r'"answer":\s*"(.+?)"',
            r'--- V\d \(.*\) ---\nRESPONSE:\n(.+?)(?=\n\n---|\n\[|$)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, prompt, re.IGNORECASE | re.DOTALL)
            if match:
                answer = match.group(1).strip()
                # Remove caracteres de escape comuns
                answer = answer.replace('\\n', '\n').replace('\\"', '"')
                if len(answer) > 10:  # Resposta válida tem pelo menos 10 caracteres
                    return answer[:2000]  # Limita para não sobrecarregar
        
        return ""

    def _detect_numerical_speculation(self, query: str, answer: str) -> str:
        """
        Detecta se a resposta contém especulação numérica para SKU específico.
        Retorna um aviso SEVERO para o avaliador.
        
        Args:
            query: Query do usuário
            answer: Resposta do modelo
            
        Returns:
            String com aviso ou string vazia
        """
        # Detecta se é query de SKU específico
        sku_pattern = r'[A-Z]{2,3}[-]?\d{3}[-]?\d{2,4}'
        has_sku = bool(re.search(sku_pattern, query, re.IGNORECASE))
        
        if not has_sku:
            return ""
        
        # Padrões de especulação numérica (com descrições)
        speculation_patterns = [
            (r'\d+\s*GB', 'RAM capacity speculation'),
            (r'\d+\s*MB', 'memory speculation'),
            (r'\d+\s*TB', 'storage speculation'),
            (r'\d+\s*MHz', 'clock speed speculation'),
            (r'\d+\s*GHz', 'frequency speculation'),
            (r'\d+\s*Gbps', 'bandwidth speculation'),
            (r'\d+\s*cores?', 'core count speculation'),
            (r'\d+\.?\d*\s*GHz', 'frequency speculation'),
            (r'between\s+\d+\s+and\s+\d+', 'range speculation'),
            (r'ranging\s+from\s+\d+\s+to\s+\d+', 'range speculation'),
            (r'typically\s+\d+', 'typical value speculation'),
            (r'usually\s+\d+', 'usual value speculation'),
            (r'around\s+\d+', 'approximate speculation'),
            (r'approximately\s+\d+', 'approximate speculation'),
            (r'up to \d+', 'maximum speculation'),
            (r'as low as \d+', 'minimum speculation'),
            (r'\d+%', 'percentage speculation'),
        ]
        
        found_patterns = []
        for pattern, description in speculation_patterns:
            if re.search(pattern, answer, re.IGNORECASE):
                found_patterns.append(description)
        
        if found_patterns:
            return (f"\n[CRITICAL WARNING] This is a SPECIFIC SKU query but the answer contains "
                    f"numerical speculation: {', '.join(found_patterns[:3])}. "
                    f"According to Rule 8, numerical specs without external documentation are UNFAITHFUL "
                    f"and should receive a score ≤0.3.")
        
        return ""

    def _clean_response(self, content: str) -> str:
        """
        Limpa e valida a resposta JSON do modelo.
        Garante estrutura mínima e campos obrigatórios.
        """
        content = content.strip()
        # Remove markdown code blocks
        content = re.sub(r'```json\s*|\s*```', '', content)
        
        # Extrai o primeiro JSON válido encontrado
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            content = match.group(0)
        
        # Garantir estrutura mínima
        try:
            parsed = json.loads(content)
            
            # Garantir campos obrigatórios
            if 'verdicts' not in parsed:
                parsed['verdicts'] = []
            
            # Garantir que cada verdict tenha os campos obrigatórios
            for v in parsed.get('verdicts', []):
                if 'verdict' not in v:
                    v['verdict'] = 'idk'
                if 'reason' not in v:
                    v['reason'] = 'No reason provided'
            
            # Garantir score
            if 'score' not in parsed:
                parsed['score'] = 0.5
            if not isinstance(parsed['score'], (int, float)):
                parsed['score'] = 0.0
            parsed['score'] = max(0.0, min(1.0, float(parsed['score'])))
            
            # Garantir reason
            if 'reason' not in parsed:
                parsed['reason'] = 'No reason provided'
            
            content = json.dumps(parsed, ensure_ascii=False)
            
        except json.JSONDecodeError as e:
            # Fallback: criar estrutura válida
            content = json.dumps({
                "score": 0.0,
                "reason": f"Failed to parse evaluator output: {str(e)[:200]} - Raw: {content[:200]}",
                "verdicts": [{"verdict": "idk", "reason": "Parse error"}]
            }, ensure_ascii=False)
        
        return content

    async def a_generate(self, prompt: str, max_retries: int = 2) -> str:
        """
        Gera avaliação de forma assíncrona com retry em caso de falha.
        
        Args:
            prompt: Prompt de avaliação
            max_retries: Número máximo de tentativas
            
        Returns:
            String JSON com a avaliação
        """
        tentativa = 0
        feedback_erro = ""

        # Se a versão do prompt foi passada, adiciona uma dica para o avaliador
        version_hint = ""
        if self.prompt_version:
            version_hint = f"\n[INFO] The answer comes from prompt version: {self.prompt_version}. "
            if self.prompt_version == "V9":
                version_hint += "It MUST contain an AUDIT block. Evaluate tag correctness."
            else:
                version_hint += "It has NO AUDIT block. Evaluate only answer content."
        else:
            version_hint = "\n[INFO] No prompt version specified. Auto-detect by presence of 'AUDIT:'."
        
        # Extrai query e answer do prompt para detecção de especulação
        try:
            query = self._extract_query_from_prompt(prompt)
            answer = self._extract_answer_from_prompt(prompt)
            speculation_warning = self._detect_numerical_speculation(query, answer)
        except Exception as e:
            # Se falhar na extração, continua sem o warning
            speculation_warning = f"\n[WARNING] Could not extract query/answer for speculation detection: {str(e)[:100]}"

        full_prompt = prompt + version_hint + speculation_warning

        while tentativa <= max_retries:
            prompt_final = full_prompt if tentativa == 0 else (
                f"{full_prompt}\n\n[SYSTEM WARNING]: Previous response invalid JSON. "
                f"Error: {feedback_erro}. Return ONLY valid JSON."
            )
            
            try:
                response = await asyncio.to_thread(
                    ollama.chat,
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": self.system_content},
                        {"role": "user", "content": prompt_final}
                    ],
                    format='json',
                    options={
                        "temperature": 0.0,
                        "num_thread": 4,
                        "num_gpu": 20,
                    },
                    keep_alive="5m"
                )
                
                raw_content = response['message']['content']
                cleaned_content = self._clean_response(raw_content)
                # Valida se é JSON válido
                json.loads(cleaned_content)
                return cleaned_content

            except json.JSONDecodeError as e:
                tentativa += 1
                feedback_erro = str(e)
                if tentativa > max_retries:
                    return json.dumps({
                        "score": 0.0,
                        "reason": f"JSON generation failed after {max_retries} retries: {feedback_erro}",
                        "verdicts": [{"verdict": "idk", "reason": "JSON parse error"}]
                    }, ensure_ascii=False)
                    
            except Exception as e:
                tentativa += 1
                feedback_erro = str(e)
                if tentativa > max_retries:
                    return json.dumps({
                        "score": 0.0,
                        "reason": f"Generation failed after {max_retries} retries: {feedback_erro}",
                        "verdicts": [{"verdict": "idk", "reason": "Generation error"}]
                    }, ensure_ascii=False)

    def generate(self, prompt: str) -> str:
        """Versão síncrona do a_generate"""
        return asyncio.run(self.a_generate(prompt))

    def get_model_name(self) -> str:
        """Retorna o nome do modelo para debug"""
        return f"Ollama {self.model_name} (v{self.prompt_version if self.prompt_version else 'auto'})"


# Função factory para criar avaliadores facilmente
def create_evaluator(version: str = "V1", model_name: str = "qwen3:4b-instruct") -> OllamaEvaluator:
    """
    Factory function para criar avaliadores consistentes.
    
    Args:
        version: 'V1' ou 'V9'
        model_name: Nome do modelo Ollama
        
    Returns:
        OllamaEvaluator configurado
    """
    return OllamaEvaluator(model_name=model_name, prompt_version=version)