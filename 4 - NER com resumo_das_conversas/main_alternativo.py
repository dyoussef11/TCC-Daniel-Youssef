import asyncio
import json
import re
import sys
import html
import time  # Novo: para controle de log
from pathlib import Path
from openai import AsyncOpenAI
from tqdm.asyncio import tqdm

# --- 1. BOOTSTRAP DE CAMINHO ---
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.paths import NER_DATA, NER_RULES, PREPROCESSAMENTO_DATA 

RULES_PATH = NER_RULES / 'hardware_patterns.json'
CAMINHO_ENTRADA_JSON = PREPROCESSAMENTO_DATA / 'reddit_notebook_dados_limpos.json'
CAMINHO_SAIDA_JSON = NER_DATA / 'reddit_dados_com_resumo_llama_aprimorado_ingles.json'
DIR_CHECKPOINTS = NER_DATA / 'checkpoints_ia'

# --- 2. SERVIÇO DE LIMPEZA (REDUZIDO POIS JÁ FOI LIMPO) ---
class TextCleanerService:
    @staticmethod
    def limpar(texto):
        if not texto: return ""
        # Apenas uma limpeza leve caso venha algo bruto
        texto = html.unescape(str(texto))
        return ' '.join(texto.split()).lower()

# --- 3. SERVIÇO DE EXTRAÇÃO (REGEX) ---
class HardwareExtractor:
    def __init__(self, rules_path: Path):
        if not rules_path.exists():
            raise FileNotFoundError(f"Dicionário não encontrado em: {rules_path}")
        with open(rules_path, 'r', encoding='utf-8') as f:
            self.patterns = json.load(f)

    def get_hints(self, text: str) -> str:
        if not text: return ""
        text_lower = text.lower()
        found = []
        for category, pattern in self.patterns.items():
            matches = re.finditer(pattern, text_lower)
            uniques = set(m.group(0).strip() for m in matches)
            if uniques:
                found.append(f"{category.upper()}: {', '.join(uniques)}")
        return " | ".join(found)

# --- 4. AGENTE DE IA (OTIMIZADO PARA GTX 1050 TI) ---
class AIAgent:
    def __init__(self, model: str = "llama3.2:1b", limit: int = 1): 
        self.client = AsyncOpenAI(base_url='http://localhost:11434/v1', api_key='ollama')
        self.model = model
        self.semaphore = asyncio.Semaphore(limit)

    async def analyze(self, system_prompt: str, user_content: str):
        async with self.semaphore:
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.0,
                    timeout=45.0 
                )
                return json.loads(response.choices[0].message.content)
            except Exception as e:
                return {"error": f"IA_FAIL: {str(e)}"}

# --- 5. ORQUESTRADOR COM LOGS E ESTRATÉGIA B ---
class RedditProcessor:
    def __init__(self):
        self.cleaner = TextCleanerService()
        self.extractor = HardwareExtractor(RULES_PATH)
        self.ai = AIAgent()
        self.start_time = None
        self.processed_count = 0
        DIR_CHECKPOINTS.mkdir(parents=True, exist_ok=True)

    async def process_post(self, post, pbar):
        post_id = post.get('id', 'unknown')
        checkpoint_path = DIR_CHECKPOINTS / f"{post_id}.json"

        if checkpoint_path.exists():
            try:
                with open(checkpoint_path, 'r', encoding='utf-8') as f:
                    post['analise_ia'] = json.load(f)
                self.processed_count += 1
                pbar.update(1)
                return
            except: pass

        # 1. Recupera textos limpos
        titulo = post.get('titulo_limpo', '')
        raw_corpo = post.get('conteudo_texto_limpo', '')

        # 2. ESTRATÉGIA B: Smart Windowing (Início + Fim)
        # Mantemos o prompt pequeno para a GPU não engasgar
        LIMITE_JANELA = 1200
        if len(raw_corpo) > LIMITE_JANELA:
            corpo = raw_corpo[:800] + "\n[...]\n" + raw_corpo[-400:]
        else:
            corpo = raw_corpo
        
        # 3. Dicas de Hardware (Varridura completa via Regex - Texto Original)
        hw_hints = self.extractor.get_hints(f"{titulo} {raw_corpo}")
        
        prompt_sys = """
        You are a strict technical JSON data extractor. Output MUST be in English.
        Return ONLY valid JSON:
        {
            "summary": "1-sentence summary.",
            "intent": "Problem/Purchase/Upgrade/Discussion/Other",
            "components": {"CPU": "model", "GPU": "model", "RAM": "size/type", "MOBO": "model", "POWER": "model", "DISK": "size/type", "MODEL": "laptop model"},
            "suggested_solution": "brief advice"
        }
        """
        
        user_content = f"HINTS: {hw_hints}\nTITLE: {titulo}\nCONTENT: {corpo}"
        analysis = await self.ai.analyze(prompt_sys, user_content)
        post['analise_ia'] = analysis
        
        # Salva Checkpoint
        with open(checkpoint_path, 'w', encoding='utf-8') as f:
            json.dump(analysis, f, ensure_ascii=False)
        
        # Atualiza métricas de velocidade
        self.processed_count += 1
        elapsed = time.time() - self.start_time
        ipm = (self.processed_count / elapsed) * 60  # Itens por Minuto
        
        pbar.set_postfix(IPM=f"{ipm:.2f}", GPU="1050Ti")
        pbar.update(1)

    async def run(self):
        if not CAMINHO_ENTRADA_JSON.exists():
            print(f"❌ Erro: Entrada não encontrada em {CAMINHO_ENTRADA_JSON}")
            return

        with open(CAMINHO_ENTRADA_JSON, 'r', encoding='utf-8') as f:
            data = json.load(f)

        queue = [post for item in data if 'posts' in item for post in item['posts']]
        
        print(f"🚀 Iniciando extração de {len(queue)} posts...")
        self.start_time = time.time() # Inicia o cronômetro
        
        with tqdm(total=len(queue), desc="🤖 NER & AI Processing") as pbar:
            tasks = [self.process_post(p, pbar) for p in queue]
            await asyncio.gather(*tasks)

        with open(CAMINHO_SAIDA_JSON, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

if __name__ == "__main__":
    processor = RedditProcessor()
    asyncio.run(processor.run())
    print(f"\n✨ Processo concluído! Arquivo salvo em NER_DATA.")