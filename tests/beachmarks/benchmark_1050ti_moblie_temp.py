
import asyncio
import json
import time
import subprocess
import ijson
from datetime import datetime, timedelta
from pathlib import Path
from openai import AsyncOpenAI
from tqdm import tqdm

# --- 1. CONFIGURAÇÃO DE CAMINHOS ---
from core.paths import NER_DATA, NER_RULES, PREPROCESSAMENTO_DATA 

RULES_PATH = NER_RULES / 'hardware_patterns.json'
CAMINHO_ENTRADA_JSON = PREPROCESSAMENTO_DATA / 'reddit_notebook_dados_limpos.json'
DIR_BENCHMARK_SAIDA = NER_DATA / 'benchmarks_qwen_real'
DIR_BENCHMARK_SAIDA.mkdir(exist_ok=True)

# --- 2. SERVIÇOS TÉCNICOS ---
class HardwareService:
    @staticmethod
    def get_gpu_temp():
        try:
            cmd = ["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"]
            res = subprocess.check_output(cmd).decode().strip()
            return int(res)
        except: return 0

class HardwareExtractor:
    def __init__(self, rules_path: Path):
        with open(rules_path, 'r', encoding='utf-8') as f:
            self.patterns = json.load(f)

    def get_hints(self, text: str) -> str:
        text_lower = text.lower() if text else ""
        found = []
        descriptions = {"cpu": "CPU", "gpu": "GPU", "ram": "RAM", "temp": "Heat", "model": "Model"}
        for category, pattern in self.patterns.items():
            match = re.search(pattern, text_lower)
            if match:
                desc = descriptions.get(category.lower(), "HW")
                found.append(f"[{category.upper()} ({desc}): {match.group(0).strip()}]")
        return " | ".join(found)

class AIAgent:
    def __init__(self, model: str = "qwen3:4b-instruct"):  
        self.client = AsyncOpenAI(base_url='http://localhost:11434/v1', api_key='ollama')
        self.model = model

    async def analyze(self, system_prompt: str, user_content: str):
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_content}],
                response_format={"type": "json_object"},
                temperature=0.1,
                timeout=240 # Aumentado para o benchmark real
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            return {"error": str(e)}

# --- 3. ORQUESTRADOR DE BENCHMARK REAL ---
class RealScenarioBenchmark:
    def __init__(self, temp_limit, posts_to_test=15):
        self.extractor = HardwareExtractor(RULES_PATH)
        self.ai = AIAgent()
        self.temp_limit = temp_limit
        self.posts_to_test = posts_to_test
        self.cooling_events = 0
        self.total_chars_processed = 0

    async def run(self):
        print(f"\n🔥 Iniciando Teste Real: Limite {self.temp_limit}°C | Alvo: {self.posts_to_test} posts")
        start_time = time.time()
        processed = 0
        
        # Prompt Robusto para o teste ser fiel à produção
        prompt_sys = """
        You are an Expert Hardware Systems Engineer specializing in laptop architecture and troubleshooting.
        GOAL: Analyze a technical discussion from Reddit to extract diagnostic insights.
        
        TASK GUIDELINES:
        1. IDENTIFY: Detect specific hardware components (CPU, GPU, RAM, Model) mentioned.
        2. DIAGNOSE: Differentiate between software bugs (drivers/OS) and physical hardware failures.
        3. INTENT CLASSIFICATION: Technical Problem | Purchase | Upgrade | Discussion | Other.
        
        JSON STRUCTURE:
        {
            "summary": "Technical overview (max 280 chars).",
            "intent": "Classification",
            "detected_fault": "Heat/Thermal | Driver/Software | Component Failure | Human Error | None",
            "suggested_solution": "Actionable technical fix."
        }
        """

        with tqdm(total=self.posts_to_test, desc=f"Limit {self.temp_limit}°C") as pbar:
            with open(CAMINHO_ENTRADA_JSON, 'rb') as f:
                objetos = ijson.items(f, 'item')
                for item in objetos:
                    if processed >= self.posts_to_test: break
                    
                    for post in item.get('posts', []):
                        if processed >= self.posts_to_test: break
                        
                        # Monitoramento Térmico
                        temp = HardwareService.get_gpu_temp()
                        if temp >= self.temp_limit:
                            self.cooling_events += 1
                            pbar.set_description(f"🌡️ Cooling ({temp}°C)")
                            await asyncio.sleep(15)
                        
                        # Processamento Real (Contexto Longo)
                        titulo = post.get('titulo_limpo', '')
                        corpo = post.get('conteudo_texto_limpo', '')
                        comentarios = "\n".join([c.get('conteudo_limpo', '') for c in post.get('comentarios', [])[:15]])
                        hw_hints = self.extractor.get_hints(f"{titulo} {corpo} {comentarios}")
                        
                        user_content = f"HINTS: {hw_hints}\nTITLE: {titulo}\nPOST: {corpo}\nCOMMENTS: {comentarios}"
                        self.total_chars_processed += len(user_content)
                        
                        # Chamada Real à IA
                        await self.ai.analyze(prompt_sys, user_content)
                        
                        processed += 1
                        pbar.update(1)
                        pbar.set_postfix(GPU=f"{HardwareService.get_gpu_temp()}°C", Chars=f"{len(user_content)}")

        total_time_min = (time.time() - start_time) / 60
        return {
            "temp_limit": self.temp_limit,
            "ppm": round(processed / total_time_min, 2),
            "pausas": self.cooling_events,
            "tempo_total": round(total_time_min, 2),
            "media_chars_por_post": round(self.total_chars_processed / processed, 0)
        }

import re # Adicionado para o HardwareExtractor

async def main():
    # Testaremos apenas os pontos críticos baseados no seu benchmark anterior
    # 78°C (equilíbrio), 80°C (máxima performance) e 82°C (limite de segurança mobile)
    temperaturas = [78, 80, 82]
    resultados = []

    print("🛠️ BENCHMARK DE CENÁRIO REAL - QWEN-4B + CONTEXTO LONGO")
    print("="*60)

    for t in temperaturas:
        tester = RealScenarioBenchmark(temp_limit=t, posts_to_test=10) # 10 posts por bateria
        res = await tester.run()
        resultados.append(res)
        await asyncio.sleep(40) # Descanso maior para estabilizar a temp

    # Relatório Final
    print("\n" + "📊 RESULTADOS DO CENÁRIO DE PRODUÇÃO".center(60))
    print("-" * 60)
    print(f"{'Limite (°C)':<12} | {'Posts/Min':<10} | {'Pausas':<10} | {'Média Chars':<12}")
    for r in resultados:
        print(f"{r['temp_limit']:<12} | {r['ppm']:<10} | {r['pausas']:<10} | {r['media_chars_por_post']:<12}")
    
    melhor = max(resultados, key=lambda x: x['ppm'])
    print("-" * 60)
    print(f"💡 RECOMENDAÇÃO: Use {melhor['temp_limit']}°C para processamento real.")

if __name__ == "__main__":
    asyncio.run(main())