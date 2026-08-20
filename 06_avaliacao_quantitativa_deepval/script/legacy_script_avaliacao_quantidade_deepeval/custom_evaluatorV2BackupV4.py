from deepeval.models.base_model import DeepEvalBaseLLM
import ollama
import asyncio
import json
import re

class OllamaEvaluator(DeepEvalBaseLLM):
    def __init__(self, model_name="qwen3:4b-instruct", prompt_version=None):
        """
        prompt_version: 'V9' ou 'V1' (opcional). Se None, tenta detectar.
        """
        self.model_name = model_name
        self.prompt_version = prompt_version

        # Sistema de avaliação adaptado para o cenário híbrido (RAG + interno)
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
        """Extrai a query original do prompt de avaliação"""
        # Procura por padrões comuns no prompt
        patterns = [
            r'Input:\s*(.+?)(?=\n|$)',
            r'Question:\s*(.+?)(?=\n|$)',
            r'Query:\s*(.+?)(?=\n|$)',
            r'"input":\s*"(.+?)"',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, prompt, re.IGNORECASE | re.DOTALL)
            if match:
                return match.group(1).strip()
        
        # Fallback: pega as primeiras linhas
        lines = prompt.split('\n')
        for line in lines[:20]:
            if '?' in line and len(line) > 10:
                return line.strip()
        
        return ""

    def _extract_answer_from_prompt(self, prompt: str) -> str:
        """Extrai a resposta (actual output) do prompt de avaliação"""
        patterns = [
            r'Actual Output:\s*(.+?)(?=\n\n|\n[A-Z]|$)',
            r'Answer:\s*(.+?)(?=\n\n|\n[A-Z]|$)',
            r'Response:\s*(.+?)(?=\n\n|\n[A-Z]|$)',
            r'"actual_output":\s*"(.+?)"',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, prompt, re.IGNORECASE | re.DOTALL)
            if match:
                return match.group(1).strip()
        
        return ""

    def _clean_response(self, content: str) -> str:
        content = content.strip()
        content = re.sub(r'```json\s*|\s*```', '', content)
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
            if 'reason' not in parsed:
                parsed['reason'] = 'No reason provided'
            
            content = json.dumps(parsed)
            
        except json.JSONDecodeError:
            # Fallback: criar estrutura válida
            content = json.dumps({
                "score": 0.0,
                "reason": f"Failed to parse evaluator output: {content}",
                "verdicts": [{"verdict": "idk", "reason": "Parse error"}]
            })
        
        return content

    def _detect_numerical_speculation(self, query: str, answer: str) -> str:
        """
        Detecta se a resposta contém especulação numérica para SKU específico.
        Retorna um aviso para o avaliador.
        """
        # Detecta se é query de SKU específico
        sku_pattern = r'[A-Z]{2,3}[-]?\d{3}[-]?\d{2,4}'
        has_sku = bool(re.search(sku_pattern, query, re.IGNORECASE))
        
        if not has_sku:
            return ""
        
        # Padrões de especulação numérica
        speculation_patterns = [
            r'\d+\s*GB',           # "32GB", "8GB"
            r'\d+\s*MHz',          # "3200MHz"
            r'\d+\s*Gbps',         # "40Gbps"
            r'\d+\s*cores?',       # "8 cores"
            r'\d+\.?\d*\s*GHz',    # "2.5GHz"
            r'between\s+\d+\s+and\s+\d+',  # "between 8 and 32"
            r'ranging\s+from\s+\d+\s+to\s+\d+',  # "ranging from 8 to 32"
            r'typically\s+\d+',     # "typically 16"
            r'usually\s+\d+',       # "usually 8"
            r'around\s+\d+',        # "around 16"
            r'approximately\s+\d+', # "approximately 32"
        ]
        
        found_patterns = []
        for pattern in speculation_patterns:
            if re.search(pattern, answer, re.IGNORECASE):
                found_patterns.append(pattern)
        
        if found_patterns:
            return f"\n[WARNING] This is a SPECIFIC SKU query but the answer contains numerical speculation: {', '.join(found_patterns[:3])}. According to rules, numerical specs without external documentation are UNFAITHFUL."
        
        return ""

    async def a_generate(self, prompt: str, max_retries: int = 2) -> str:
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
        query = self._extract_query_from_prompt(prompt)
        answer = self._extract_answer_from_prompt(prompt)
        speculation_warning = self._detect_numerical_speculation(query, answer)

        full_prompt = prompt + version_hint + speculation_warning

        while tentativa <= max_retries:
            prompt_final = full_prompt if tentativa == 0 else (
                f"{full_prompt}\n\n[SYSTEM WARNING]: Previous response invalid JSON. "
                f"Error: {feedback_erro}. Return ONLY valid JSON."
            )
            
            try:
                response = await asyncio.to_thread(
                    ollama.chat,
                    model="qwen3:4b-instruct",
                    messages=[
                        {"role": "system", "content": self.system_content},
                        {"role": "user", "content": prompt_final}
                    ],
                    format='json',
                    options={
                        "temperature": 0,
                        "num_thread": 4,
                        "num_gpu": 20,
                    },
                    keep_alive="5m"
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
        return asyncio.run(self.a_generate(prompt))

    def get_model_name(self):
        return f"Ollama {self.model_name}"