import asyncio
import json
import re
import sys
from pathlib import Path
from openai import AsyncOpenAI
from tqdm.asyncio import tqdm

# --- 1. CONFIGURAÇÕES E CAMINHOS (MANTIDO CONFORME SOLICITADO) ---
caminho_script = Path(__file__).resolve().parent
caminho_raiz_projeto = caminho_script.parent.parent 
sys.path.append(str(caminho_raiz_projeto))

try:
    from config import DIRETORIO_DADOS_RESUMO_CONVERSAS, DIRETORIO_DADOS_PRE_PROCESSAMENTO
    # Se o config global existir, usamos a lógica de lá
    from config import PASTA_RESUMO_CONVERSAS_NER
    RULES_PATH = PASTA_RESUMO_CONVERSAS_NER / 'rules' / 'hardware_patterns.json'
except ImportError:
    DIRETORIO_DADOS_PRE_PROCESSAMENTO = caminho_script.parent / 'data'
    DIRETORIO_DADOS_RESUMO_CONVERSAS = caminho_script.parent / 'data'
    # CORREÇÃO: Subir um nível para achar a pasta rules que é irmã de script
    RULES_PATH = caminho_script.parent / 'rules' / 'hardware_patterns.json'

CAMINHO_ENTRADA_JSON = DIRETORIO_DADOS_PRE_PROCESSAMENTO / 'reddit_notebook_dados_limpos.json'
CAMINHO_SAIDA_JSON = DIRETORIO_DADOS_RESUMO_CONVERSAS / 'reddit_dados_com_resumo_llama_aprimorado_ingles.json'
DIR_CHECKPOINTS = DIRETORIO_DADOS_RESUMO_CONVERSAS / 'checkpoints_ia'

# --- 2. SERVIÇO DE EXTRAÇÃO (REGEX) ---
class HardwareExtractor:
    """Encapsula a lógica de NER baseada em regras fixas do JSON."""
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
            matches = set(m.group(0).strip() for m in re.finditer(pattern, text_lower))
            if matches:
                found.append(f"{category.upper()}: {', '.join(matches)}")
        return " | ".join(found)

# --- 3. AGENTE DE IA ---
class AIAgent:
    """Gerencia a comunicação com o Ollama e controle de concorrência."""
    def __init__(self, model: str = "llama3.2:latest", limit: int = 2):
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
                    temperature=0.0
                )
                return json.loads(response.choices[0].message.content)
            except Exception as e:
                return {"error": f"IA_FAIL: {str(e)}"}

# --- 4. ORQUESTRADOR DE PROCESSAMENTO ---
class RedditProcessor:
    def __init__(self):
        self.extractor = HardwareExtractor(RULES_PATH)
        self.ai = AIAgent()
        DIR_CHECKPOINTS.mkdir(parents=True, exist_ok=True)

    async def process_post(self, post, pbar):
        post_id = post.get('id', 'unknown')
        checkpoint_path = DIR_CHECKPOINTS / f"{post_id}.json"

        # Checkpoint: evita reprocessar o que já foi feito
        if checkpoint_path.exists():
            try:
                with open(checkpoint_path, 'r', encoding='utf-8') as f:
                    post['analise_ia'] = json.load(f)
                pbar.update(1)
                return
            except: pass

        # Extração Híbrida (Regex + IA)
        # Busca prioritariamente os campos limpos, mas aceita os originais se não houver
        titulo = post.get('titulo_limpo', post.get('titulo', ''))
        corpo = post.get('conteudo_texto_limpo', post.get('conteudo_texto', ''))[:1000]
        hw_hints = self.extractor.get_hints(f"{titulo} {corpo}")
        
        prompt_sys = """
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
        Tem componente need to be like this dictionary "components" 
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
        
        # Salva checkpoint individual
        with open(checkpoint_path, 'w', encoding='utf-8') as f:
            json.dump(analysis, f, ensure_ascii=False)
        
        pbar.update(1)

    async def run(self):
        if not CAMINHO_ENTRADA_JSON.exists():
            print(f"❌ Erro: Entrada não encontrada em {CAMINHO_ENTRADA_JSON}")
            return

        with open(CAMINHO_ENTRADA_JSON, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Prepara a fila de posts
        queue = [post for item in data if 'posts' in item for post in item['posts']]
        
        with tqdm(total=len(queue), desc="🤖 Processing Posts") as pbar:
            tasks = [self.process_post(p, pbar) for p in queue]
            await asyncio.gather(*tasks)

        # Salva o resultado final unificado
        with open(CAMINHO_SAIDA_JSON, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

if __name__ == "__main__":
    processor = RedditProcessor()
    asyncio.run(processor.run())
    print(f"\n✨ Processo concluído com sucesso!")