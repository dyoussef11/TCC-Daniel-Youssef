
import asyncio
import json
import re
import gc
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from openai import AsyncOpenAI
from tqdm import tqdm
from pynvml import *

# --- CONFIGURAÇÕES DE AMBIENTE E PATHS ---
try:
    from utils.utils_ner import (
        CAMINHO_ENTRADA_JSON, CAMINHO_SAIDA_JSONLLAMA, 
        DIR_CHECKPOINTSLLAMA, CustomEncoder
    )
except ImportError:
    CAMINHO_ENTRADA_JSON = Path("data/reddit_50_notebooks_w_componentsV2.json")
    CAMINHO_SAIDA_JSONLLAMA = Path("data/reddit_dados_com_resumo_Llama.json")
    DIR_CHECKPOINTSLLAMA = Path("checkpoints_ia_Llama")
    CustomEncoder = None
    logging.warning("⚠️ Utils não encontrado. Usando caminhos padrão.")

DIR_CHECKPOINTSLLAMA.mkdir(parents=True, exist_ok=True)

TAMANHO_CHUNK = 15

# Segurança Térmica para o Dell G7
TARGET_TEMP = 80
COOLDOWN_TEMP = 65

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logging.getLogger("httpx").setLevel(logging.WARNING)

PROMPT_SYS = """
You are a Technical Data Structurer. Your objective is to extract technical facts from a laptop repair discussion chunk.

STRICT RULES:
1. SUMMARY FORMAT: You MUST start the summary string EXACTLY with the laptop model name, it MUST BE followed by a comma (,). Immediately after the comma, write the technical facts. 
2. NO CHATBOT TEXT: NEVER use conversational filler phrases like "The user reported", "The author says", or "This chunk discusses". Write objectively like a technical log.
3. PRIORITY: Identify if a cause or fix is mentioned in this specific chunk.
4. LANGUAGE: English.
5. FORMAT: You must return ONLY a valid JSON object. Do not add markdown blocks, explanations, or conversational text.

EXPECTED JSON SCHEMA:
{
    "summary": "[Laptop Model], Chronological narrative of the problem, context, and actions.",
    "intent": "Technical Problem | Purchase Advice | Upgrade | Benchmarking | Discussion | N/A",
    "detected_fault": "Fault identified in this chunk (or null if none)",
    "suggested_solution": "Solution mentioned in this chunk (or null if none)",
    "technical_severity": "Low | Medium | High | Critical | N/A"
}

EXAMPLE OF DESIRED OUTPUT:
{
    "summary": "Acer Aspire 5 15.6, Targeted for college use with emphasis on battery life and low fan noise. AMD chips may throttle under sustained workloads due to thermal inefficiency.",
    "intent": "Purchase Advice",
    "detected_fault": "None",
    "suggested_solution": "Choose the HP 15.6 (AMD Ryzen 57520U) at $380.",
    "technical_severity": "Low"
}
"""

PROMPT_CONSOLIDATION = """
You are a Technical Data Merger. You will receive multiple JSON analyses of the same laptop case.
Combine them into one final, high-density technical JSON.

RULES:
1. SUMMARY: Merge all summaries into a chronological narrative.
2. RESOLUTION: Prioritize the solution that actually worked.
3. SEVERITY: Use the highest severity found.
4. CLEANUP: Ignore redundant or empty data points.
5. FORMAT: You MUST return ONLY a valid JSON object using the exact schema below.

EXPECTED JSON SCHEMA:
{
    "summary": "Merged chronological narrative...",
    "intent": "Technical Problem | Purchase Advice | Upgrade | Benchmarking | Discussion | N/A",
    "detected_fault": "Combined fault identified",
    "suggested_solution": "Final working solution",
    "technical_severity": "Low | Medium | High | Critical | N/A"
}
"""

# --- CLASSES DE SUPORTE ---

class HardwareManager:
    def __init__(self):
        try:
            nvmlInit()
            self.handle = nvmlDeviceGetHandleByIndex(0)
            self.enabled = True
        except:
            self.enabled = False

    def get_stats(self):
        if not self.enabled: return 0, 0
        temp = nvmlDeviceGetTemperature(self.handle, NVML_TEMPERATURE_GPU)
        mem = nvmlDeviceGetMemoryInfo(self.handle)
        return temp, (mem.used / mem.total) * 100

    async def throttle(self, pbar=None):
        if not self.enabled: return
        temp, _ = self.get_stats()
        if temp >= TARGET_TEMP:
            while temp > COOLDOWN_TEMP:
                if pbar: pbar.set_description(f"❄️ Resfriando GPU... {temp}°C")
                await asyncio.sleep(10)
                temp, _ = self.get_stats()

class AIAgent:
    def __init__(self, model: str = "qwen3:4b-instruct"):
        self.client = AsyncOpenAI(
            base_url='http://localhost:11434/v1', 
            api_key='ollama',
            timeout=120.0
        )
        self.model = model

    async def analyze(self, system_prompt: str, user_content: str) -> Dict:
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                response_format={"type": "json_object"},
                extra_body={
                    "options": {
                        "num_ctx": 4096,
                        "temperature": 0.0,
                        "num_thread": 8
                    }
                }
            )
            raw = response.choices[0].message.content
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            return json.loads(match.group() if match else raw)
        except Exception as e:
            return {"summary": "Error", "error": str(e), "intent": "N/A"}

# --- LÓGICA DE PROCESSAMENTO ---

class RAGProcessor:
    def __init__(self, agent: AIAgent, hardware: HardwareManager):
        self.agent = agent
        self.hardware = hardware
        self.checkpoints = {f.stem for f in DIR_CHECKPOINTSLLAMA.glob("*.json")}

    def _extrair_timeline(self, post: Dict) -> str:
        """Recupera o selo temporal da discussão."""
        datas = []
        if post.get('data_post'): datas.append(post.get('data_post'))
        for c in post.get('comentarios', []):
            if c.get('data_comentario'): datas.append(c.get('data_comentario'))
        
        if not datas: return "Timeline: Unknown"
        dt_min = datetime.fromtimestamp(min(datas))
        dt_max = datetime.fromtimestamp(max(datas))
        return f"{dt_min.strftime('%Y-%m-%d')} to {dt_max.strftime('%Y-%m-%d')}"

    async def process_post(self, post: Dict, group: str, pbar_ref=None) -> Dict:
        post_id = str(post.get('id'))
        timeline = self._extrair_timeline(post)

        if post_id in self.checkpoints:
            try:
                with open(DIR_CHECKPOINTSLLAMA / f"{post_id}.json", 'r', encoding='utf-8') as f:
                    dados = json.load(f)
                    dados['discussion_timeline'] = timeline
                    return dados
            except: pass

        comentarios = [c for c in post.get('comentarios', []) if len(c.get('conteudo_limpo','')) > 5]
        analises_parciais = []
        
        # Chunks de 15 comentários para acelerar a inferência
        for i in range(0, len(comentarios), TAMANHO_CHUNK):
            await self.hardware.throttle(pbar_ref)
            chunk = comentarios[i : i + TAMANHO_CHUNK]
            txt_chunk = "".join([f"COMMENT: {c.get('conteudo_limpo','')}\n" for c in chunk])
            
            content = (f"TIMELINE: {timeline}\nGROUP: {group}\n"
                       f"TITLE: {post.get('titulo_limpo','')}\n"
                       f"OP: {post.get('conteudo_post_limpo','')}\nCHUNK:\n{txt_chunk}")
            
            res = await self.agent.analyze(PROMPT_SYS, content)
            if "error" not in res:
                analises_parciais.append(res)

        # Consolidação Final
        if len(analises_parciais) > 1:
            analise_final = await self.agent.analyze(PROMPT_CONSOLIDATION, json.dumps(analises_parciais))
        elif analises_parciais:
            analise_final = analises_parciais[0]
        else:
            analise_final = {"summary": "No technical discussion found", "intent": "N/A"}

        analise_final['discussion_timeline'] = timeline

        with open(DIR_CHECKPOINTSLLAMA / f"{post_id}.json", 'w', encoding='utf-8') as f:
            json.dump(analise_final, f, ensure_ascii=False)
        return analise_final

async def workflow():
    agent = AIAgent()
    hardware = HardwareManager()
    processor = RAGProcessor(agent, hardware)

    print(f"🚀 Iniciando RAG (V3 Final) em: {CAMINHO_ENTRADA_JSON}")

    with open(CAMINHO_ENTRADA_JSON, 'r', encoding='utf-8') as f:
        objetos = json.load(f)

    for item in tqdm(objetos, desc="Modelos"):
        group = item.get('modelo_busca_utilizado', 'general')
        posts_list = item.get('posts', [])
        pbar_posts = tqdm(posts_list, desc=" -> Analisando", leave=False)
        for post in tqdm(item.get('posts', []), desc=" -> Analisando", leave=False):

            t, v = hardware.get_stats()

            pbar_posts.set_description(f"🌡️ {t}°C | 🧠 {v:.1f}% | Post {post.get('id')}")
            
            post['analise_ia'] = await processor.process_post(post, group, pbar_posts)
            gc.collect()

    with open(CAMINHO_SAIDA_JSONLLAMA, 'w', encoding='utf-8') as f:
        json.dump(objetos, f, ensure_ascii=False, indent=4, cls=CustomEncoder)
    
    print(f"✨ Concluído! Resultado com Timeline salvo em {CAMINHO_SAIDA_JSONLLAMA}")

if __name__ == "__main__":
    asyncio.run(workflow())