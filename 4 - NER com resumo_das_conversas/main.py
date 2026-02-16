
import asyncio
import json
import re
import sys
import html
from pathlib import Path
from openai import AsyncOpenAI
from tqdm.asyncio import tqdm

# --- BOOTSTRAP DE CAMINHO DO PROJETO ---
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.paths import (
    NER_DATA, 
    NER_RULES, 
    PREPROCESSAMENTO_DATA, 
)


# CORREÇÃO: PASTA_RESUMO_CONVERSAS_NER já é a pasta atual. Não duplique o nome.
RULES_PATH = NER_RULES / 'hardware_patterns.json'
CAMINHO_ENTRADA_JSON = PREPROCESSAMENTO_DATA / 'reddit_notebook_dados_limpos.json'
CAMINHO_SAIDA_JSON = NER_DATA / 'reddit_dados_com_resumo_llama_aprimorado_ingles.json'
DIR_CHECKPOINTS = NER_DATA / 'checkpoints_ia'

# --- 2. SERVIÇO DE LIMPEZA EXPANDIDA ---
class TextCleanerService:
    """Higienização robusta removendo emojis e ruídos do Reddit."""
    @staticmethod
    def limpar(texto):
        if texto is None: return ""
        if not isinstance(texto, str): return str(texto)
        try: texto = html.unescape(texto)
        except: pass
        # Remove placeholders de imagens e e-mails
        texto = re.sub(r'\*Processing img [^*]+\.\.\.\*', ' ', texto)
        texto = re.sub(r'\S+@\S+\.\S+', ' ', texto)
        # Remove menções e links Markdown (preserva o texto âncora)
        texto = re.sub(r'\b[ur]/[A-Za-z0-9_]+\b', ' ', texto)
        texto = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', texto)
        texto = re.sub(r'https?://\S+|www\.\S+', ' ', texto)
        # Remove Emojis (converte para ASCII ignorando símbolos)
        texto = texto.encode('ascii', 'ignore').decode('ascii')
        # Normalização de modelos técnicos
        texto = texto.replace('_', ' ').replace('|', ' ')
        texto = re.sub(r"[^\w\s.,!?\-']", ' ', texto)
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

# --- 4. AGENTE DE IA ---
class AIAgent:
    def __init__(self, model: str = "llama3.2:latest", limit: int = 1):
        # Aumentamos o timeout para evitar o erro de conexão em posts longos
        self.client = AsyncOpenAI(
            base_url='http://localhost:11434/v1', 
            api_key='ollama',

        )
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
                    temperature=0.0
                )
                return json.loads(response.choices[0].message.content)
            except Exception as e:
                return {"error": f"IA_FAIL: {str(e)}"}

# --- 5. ORQUESTRADOR ---
class RedditProcessor:
    def __init__(self):
        self.cleaner = TextCleanerService()
        self.extractor = HardwareExtractor(RULES_PATH)
        self.ai = AIAgent()
        DIR_CHECKPOINTS.mkdir(parents=True, exist_ok=True)

    async def process_post(self, post, pbar):
        post_id = post.get('id', 'unknown')
        checkpoint_path = DIR_CHECKPOINTS / f"{post_id}.json"

        if checkpoint_path.exists():
            try:
                with open(checkpoint_path, 'r', encoding='utf-8') as f:
                    post['analise_ia'] = json.load(f)
                pbar.update(1)
                return
            except: pass

        # Limpeza e Extração de Dicas (Hints)
        # titulo = self.cleaner.limpar(post.get('titulo_limpo', post.get('titulo', '')))
        # corpo = self.cleaner.limpar(post.get('conteudo_texto_limpo', post.get('conteudo_texto', '')))[:1200]

        # 1. Pega os dados que JÁ foram limpos pelo script anterior
        titulo = post.get('titulo_limpo', '')
        # 2. Pega o conteúdo limpo e apenas limita o tamanho para a IA
        # corpo = post.get('conteudo_texto_limpo', '')[:1200]
        corpo = post.get('conteudo_texto_limpo', '')[:2500]

        
        hw_hints = self.extractor.get_hints(f"{titulo} {corpo}")
        
        prompt_sys =  """
    You are a strict technical JSON data extractor. Output MUST be in English.
    All text output MUST be in English.

    ### HARDWARE EXTRACTION RULES (STRICT):
    1. SINGLE VALUE: Never return lists. If multiple models are mentioned, pick the most relevant one.
    2. BE SPECIFIC: Include model names (e.g., 'RTX 3060').
    3. CLEAN RAM/STORAGE: Capacity + Type only (e.g., '16GB DDR4', '1TB NVMe').
    4. NULL IF GENERIC: If not specified, use null.

    Return ONLY a valid JSON with this exact schema:
    {
        "summary": "1-sentence technical summary in English.",
        "intent": "One of: 'Technical Problem', 'Purchase', 'Upgrade', 'Discussion', 'Other'.",
        The components need to be like this dictionary "components" 
        "components": {
            "CPU": "Model or null", 
            "GPU": "Model or null", 
            "RAM": "Capacity/Type or null",
            "MOBO": "Model or null", 
            "POWER": "Model or null", 
            "DISK": "Capacity/Type or null",
            "MODEL": "Laptop model or null"
        },
        "suggested_solution": "Brief suggested solution in English or null."
    }
    """
        
        user_content = f"HINTS: {hw_hints}\nTITLE: {titulo}\nCONTENT: {corpo}"
        analysis = await self.ai.analyze(prompt_sys, user_content)
        post['analise_ia'] = analysis
        
        with open(checkpoint_path, 'w', encoding='utf-8') as f:
            json.dump(analysis, f, ensure_ascii=False)
        pbar.update(1)

    async def run(self):
        if not CAMINHO_ENTRADA_JSON.exists():
            print(f"❌ Erro: Entrada não encontrada em {CAMINHO_ENTRADA_JSON}")
            return

        with open(CAMINHO_ENTRADA_JSON, 'r', encoding='utf-8') as f:
            data = json.load(f)

        queue = [post for item in data if 'posts' in item for post in item['posts']]
        
        with tqdm(total=len(queue), desc="🤖 NER & AI Processing") as pbar:
            tasks = [self.process_post(p, pbar) for p in queue]
            await asyncio.gather(*tasks)

        with open(CAMINHO_SAIDA_JSON, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

if __name__ == "__main__":
    processor = RedditProcessor()
    asyncio.run(processor.run())
    print(f"\n✨ Processo concluído! Arquivo: {CAMINHO_SAIDA_JSON}")