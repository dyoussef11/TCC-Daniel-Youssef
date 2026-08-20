import asyncio
import json
import os
from pathlib import Path
from tqdm.asyncio import tqdm as async_tqdm
from openai import AsyncOpenAI
from datetime import datetime
import re

# --- CONFIGURAÇÕES ---
try:
    from core.paths import PREPROCESSAMENTO_DATA, NER_DATA
    DIR_ENTRADA = PREPROCESSAMENTO_DATA / 'dados_limpos' / 'dados_limpos_iniciaisV10'
    DIR_SAIDA_FINAL = NER_DATA / 'Base_Conhecimento_ResumidaV10_VERIFICADA'
    DIR_CHECKPOINTS = NER_DATA / "checkpoints_ia_v18_verificado"
except ImportError:
    DIR_ENTRADA = Path("./data/Dados_Limpos_IniciaisV10")
    DIR_SAIDA_FINAL = Path("./data/Base_Conhecimento_ResumidaV9_VERIFICADA")
    DIR_CHECKPOINTS = Path("./checkpoints_ia_v17_verificado")

DIR_SAIDA_FINAL.mkdir(parents=True, exist_ok=True)
DIR_CHECKPOINTS.mkdir(parents=True, exist_ok=True)

# --- PARÂMETROS ---
MAX_CONCURRENT = 1
MAX_TEMP = 82
COOLDOWN_TEMP = 72
DEBUG = True
MAX_TOKENS = 1024  # <-- AUMENTADO de 512 para 1024
NUM_CTX = 8192     # <-- AUMENTADO de 4096 para 8192

# --- CLIENTE OLLAMA ---
client = AsyncOpenAI(base_url="http://localhost:11434/v1", api_key="ollama")

# =========================================================
# PROMPT MAIS CURTO E DIRETO (evita corte)
# =========================================================
PROMPT_LLAMA_EXTRACTION = """<|begin_of_text|><|start_header_id|>system<|end_header_id|>

You are a diagnostic extraction system. You ONLY respond with valid JSON in the exact format specified. Do not output any other text or explanation.<|eot_id|><|start_header_id|>user<|end_header_id|>

Extract technical analysis from the forum post below and return ONLY a JSON object with these exact fields.

**CANONICAL MODEL**: {modelo_nome}
**POST DATE**: {post_date}

**TITLE**: {titulo}
**CONTENT**: {corpo}
**COMMENTS**: {comentarios}

**REQUIRED JSON STRUCTURE** (return ONLY this, no other text):
{{
    "summary": "{modelo_nome}, [problem description] - [key symptoms] - [affected components]",
    "intent": "Troubleshooting",
    "detected_fault": "Specific technical fault or 'None'",
    "suggested_solution": ["Step 1", "Step 2", "Step 3"],
    "technical_severity": "Medium",
    "discussion_timeline": "{post_date} to {post_date}"
}}

**VALID VALUES**:
- intent: "Technical Specifications", "Troubleshooting", "Upgrade Advice", "Compatibility", "Warranty", "Performance"
- technical_severity: "Low", "Medium", "High", "Critical"
- suggested_solution: Array of strings, max 4 items

**CRITICAL RULES**:
1. Return ONLY valid JSON - no explanations, no markdown, no extra text
2. Start summary EXACTLY with "{modelo_nome},"
3. Extract real solutions from the conversation, not placeholders
4. If no solution found, suggested_solution can be empty array []

Now output ONLY the JSON object:<|eot_id|><|start_header_id|>assistant<|end_header_id|>
"""

# =========================================================
# PARSER DE JSON ROBUSTO
# =========================================================
def parse_llama_json(raw_response: str) -> dict:
    """Tenta corrigir JSON malformado do Llama"""
    
    # Remove markdown
    raw_response = re.sub(r'```json\s*', '', raw_response)
    raw_response = re.sub(r'```\s*', '', raw_response)
    
    # Tenta encontrar JSON
    start = raw_response.find('{')
    end = raw_response.rfind('}')
    
    if start == -1 or end == -1:
        raise ValueError("No JSON object found in response")
    
    json_str = raw_response[start:end+1]
    
    # Corrige vírgulas faltantes
    json_str = re.sub(r'"\s+"', '", "', json_str)
    json_str = re.sub(r'}\s+"', '}, "', json_str)
    json_str = re.sub(r',\s*}', '}', json_str)
    json_str = re.sub(r',\s*\]', ']', json_str)
    
    # Corrige strings sem aspas em valores
    json_str = re.sub(r':\s*([a-zA-Z][a-zA-Z0-9]*)\s*[,}]', r': "\1"\2', json_str)
    
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        # Fallback: extração por regex
        result = {}
        
        summary_match = re.search(r'"summary"\s*:\s*"([^"]*(?:\\"[^"]*)*)"', json_str)
        if summary_match:
            result['summary'] = summary_match.group(1)
        
        intent_match = re.search(r'"intent"\s*:\s*"([^"]*)"', json_str)
        if intent_match:
            result['intent'] = intent_match.group(1)
        
        fault_match = re.search(r'"detected_fault"\s*:\s*"([^"]*)"', json_str)
        if fault_match:
            result['detected_fault'] = fault_match.group(1)
        
        solutions_match = re.search(r'"suggested_solution"\s*:\s*\[(.*?)\]', json_str, re.DOTALL)
        if solutions_match:
            sol_content = solutions_match.group(1)
            solucoes = re.findall(r'"([^"]*)"', sol_content)
            result['suggested_solution'] = solucoes
        
        severity_match = re.search(r'"technical_severity"\s*:\s*"([^"]*)"', json_str)
        if severity_match:
            result['technical_severity'] = severity_match.group(1)
        
        timeline_match = re.search(r'"discussion_timeline"\s*:\s*"([^"]*)"', json_str)
        if timeline_match:
            result['discussion_timeline'] = timeline_match.group(1)
        
        if result:
            return result
        raise e

# --- FUNÇÃO DE MONITORAMENTO DE GPU ---
def get_gpu_temperature():
    try:
        import subprocess
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=temperature.gpu', '--format=csv,noheader,nounits'],
            capture_output=True, text=True, timeout=5
        )
        return int(result.stdout.strip()) if result.returncode == 0 else None
    except:
        return None

async def monitorar_temperatura(stats, max_temp, cooldown_temp):
    while True:
        temp = get_gpu_temperature()
        if temp and temp > max_temp:
            stats["pausas_temperatura"] += 1
            print(f"\n🌡️ GPU a {temp}°C! Pausando até {cooldown_temp}°C...")
            while temp > cooldown_temp:
                await asyncio.sleep(10)
                temp = get_gpu_temperature() or temp
            print(f"❄️ Retomando...")
        await asyncio.sleep(5)

# --- DEBUG HELPER ---
DEBUG_DIR = Path("./debug_messages")
DEBUG_DIR.mkdir(exist_ok=True)

async def salvar_debug(post_id, etapa, conteudo):
    if not DEBUG:
        return
    
    timestamp = datetime.now().strftime('%H%M%S_%f')[:-3]
    filename = DEBUG_DIR / f"{post_id}_{etapa}_{timestamp}.txt"
    
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(f"=== {etapa} ===\n")
        f.write(f"Post: {post_id}\n")
        f.write(f"Time: {datetime.now().isoformat()}\n")
        f.write(f"{'='*60}\n\n")
        f.write(conteudo)
    
    print(f"  📝 {filename.name}")

# --- FUNÇÃO PRINCIPAL DE EXTRAÇÃO ---
async def extrair_analise(post, modelo_nome, post_id, stats, semaphore):
    checkpoint_path = DIR_CHECKPOINTS / f"{post_id}.json"
    
    # Verifica checkpoint
    if checkpoint_path.exists():
        try:
            with open(checkpoint_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            stats["checkpoints_validos"] += 1
            if DEBUG:
                print(f"  ✅ Cache: {post_id}")
            return data
        except:
            print(f"  ⚠️ Cache corrompido: {post_id}")
    
    # Prepara conteúdo (limitado mas não muito)
    titulo = post.get('titulo', '')[:500]
    corpo = post.get('conteudo_post', post.get('selftext', ''))[:4000]
    comentarios = " ".join([c.get('conteudo', '') for c in post.get('comentarios', [])])[:2000]
    
    post_date = post.get('data_post', datetime.now().strftime('%Y-%m-%d'))
    if isinstance(post_date, (int, float)):
        post_date = datetime.fromtimestamp(float(post_date)).strftime('%Y-%m-%d')
    elif not post_date:
        post_date = '2024-01-01'
    
    if DEBUG:
        print(f"\n{'='*60}")
        print(f"🔄 {post_id} | {modelo_nome[:30]}")
        print(f"📝 Título: {titulo[:60]}...")
        print(f"📊 Tamanho: corpo={len(corpo)} | comentários={len(comentarios)}")
        print(f"{'='*60}")
    
    # Prompt mais curto para evitar corte
    prompt = PROMPT_LLAMA_EXTRACTION.format(
        modelo_nome=modelo_nome[:80],
        post_date=post_date,
        titulo=titulo,
        corpo=corpo,
        comentarios=comentarios
    )
    
    if DEBUG:
        await salvar_debug(post_id, "01_prompt", prompt[:2000])  # Salva só parte
    
    try:
        async with semaphore:
            response = await client.chat.completions.create(
                model="llama3.2:3b",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=MAX_TOKENS,  # 1024 tokens
                extra_query={"num_ctx": NUM_CTX}  # 8192 contexto
            )
        
        raw_content = response.choices[0].message.content
        
        if DEBUG:
            print(f"📥 Resposta: {len(raw_content)} chars")
            print(f"  Preview: {raw_content[:150]}...")
            await salvar_debug(post_id, "02_raw", raw_content)
        
        # Parse JSON
        analise = parse_llama_json(raw_content)
        
        if DEBUG:
            print(f"✅ JSON OK")
        
        # Valida campos
        analise.setdefault('detected_fault', 'None')
        analise.setdefault('technical_severity', 'Low')
        analise.setdefault('discussion_timeline', f"{post_date} to {post_date}")
        analise.setdefault('suggested_solution', [])
        
        # Corrige summary
        summary = analise.get('summary', '')
        if not summary.startswith(modelo_nome):
            analise['summary'] = f"{modelo_nome}, {summary}"
        
        # Valida intent
        intents_validos = ['Technical Specifications', 'Troubleshooting', 'Upgrade Advice', 
                          'Compatibility', 'Warranty', 'Performance']
        if analise.get('intent') not in intents_validos:
            analise['intent'] = 'Troubleshooting'
        
        # Valida severity
        if analise.get('technical_severity') not in ['Low', 'Medium', 'High', 'Critical']:
            analise['technical_severity'] = 'Low'
        
        # Garante lista
        if not isinstance(analise.get('suggested_solution'), list):
            analise['suggested_solution'] = []
        
        # Remove placeholders
        placeholders = ['step 1', 'step 2', 'step 3', 'step1', 'step2', 
                       'action 1', 'action 2', 'specific fix 1']
        analise['suggested_solution'] = [s for s in analise['suggested_solution'] 
                                         if s and s.strip() and s.lower() not in placeholders]
        
        # Metadados
        analise['ancoragem_temporal'] = {
            "data_processamento": datetime.now().strftime('%Y-%m-%d'),
            "data_post_original": post_date
        }
        
        if DEBUG:
            await salvar_debug(post_id, "03_final", json.dumps(analise, indent=2, ensure_ascii=False))
        
        # Salva checkpoint
        async with aiofiles.open(checkpoint_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(analise, ensure_ascii=False, indent=2))
        
        stats["processados_agora"] += 1
        return analise
        
    except Exception as e:
        print(f"  ❌ Erro: {str(e)[:100]}")
        if 'raw_content' in locals():
            await salvar_debug(post_id, "99_error", f"Error: {e}\n\nRaw:\n{raw_content}")
        stats["falhas"] += 1
        return None

# --- WORKFLOW PRINCIPAL ---
async def workflow_principal():
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    stats = {"checkpoints_validos": 0, "processados_agora": 0, "falhas": 0, "pausas_temperatura": 0}
    
    arquivos = list(DIR_ENTRADA.glob("*.json"))
    
    # Filtra pendentes
    arquivos_pendentes = []
    for arq in arquivos:
        output_path = DIR_SAIDA_FINAL / f"NER_{arq.name}"
        if not output_path.exists():
            arquivos_pendentes.append(arq)
    
    arquivos_pendentes.sort(key=lambda x: os.path.getsize(x))
    
    if DEBUG:
        print("\n" + "="*80)
        print("📊 ARQUIVOS ORDENADOS (menor → maior)")
        print("="*80)
        for i, arq in enumerate(arquivos_pendentes[:15], 1):
            tamanho_kb = os.path.getsize(arq) / 1024
            print(f"  {i:2}. {arq.name[:50]:<50} {tamanho_kb:8.1f} KB")
        if len(arquivos_pendentes) > 15:
            print(f"  ... e mais {len(arquivos_pendentes)-15} arquivos")
        print("="*80 + "\n")
    
    print(f"🚀 NER V13 - Tokens: {MAX_TOKENS} | Contexto: {NUM_CTX}")
    print(f"📂 Total: {len(arquivos)} | Pendentes: {len(arquivos_pendentes)}")
    print(f"💾 Checkpoints: {len(list(DIR_CHECKPOINTS.glob('*.json')))}")
    print(f"🌡️ GPU: {MAX_TEMP}°C | Concorrência: {MAX_CONCURRENT}")
    
    if len(arquivos_pendentes) == 0:
        print("✨ Todos processados!")
        return
    
    monitor_task = asyncio.create_task(monitorar_temperatura(stats, MAX_TEMP, COOLDOWN_TEMP))
    
    for arq_path in async_tqdm(arquivos_pendentes, desc="Modelos"):
        try:
            with open(arq_path, 'r', encoding='utf-8') as f:
                dados_modelo = json.load(f)
        except Exception as e:
            print(f"❌ Erro: {arq_path.name} - {e}")
            continue
        
        modelo_nome = dados_modelo.get('modelo_original', 
                                      dados_modelo.get('modelo_busca_utilizado', 'Unknown'))
        posts = dados_modelo.get('posts', [])
        
        if DEBUG:
            print(f"\n📁 {arq_path.name} | {modelo_nome[:40]} | {len(posts)} posts")
        
        posts_processados = []
        for post in posts:
            post_id = str(post.get('id'))
            analise = await extrair_analise(post, modelo_nome, post_id, stats, semaphore)
            if analise:
                post['analise_ia'] = analise
                posts_processados.append(post)
        
        if posts_processados:
            dados_modelo['posts'] = posts_processados
            output_path = DIR_SAIDA_FINAL / f"NER_{arq_path.name}"
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(dados_modelo, f, indent=2, ensure_ascii=False)
        
        await asyncio.sleep(1)
    
    monitor_task.cancel()
    
    print(f"\n✅ Concluído!")
    print(f"📊 Processados: {stats['processados_agora']} | Cache: {stats['checkpoints_validos']} | Falhas: {stats['falhas']}")

if __name__ == "__main__":
    try:
        import aiofiles
        asyncio.run(workflow_principal())
    except KeyboardInterrupt:
        print("\n⚠️ Interrompido. Progresso salvo nos checkpoints.")
    except ImportError:
        print("Instale: pip install aiofiles")