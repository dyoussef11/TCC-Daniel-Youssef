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
    DIR_ENTRADA = PREPROCESSAMENTO_DATA / 'Dados_Limpos_IniciaisV10'
    DIR_SAIDA_FINAL = NER_DATA / 'Base_Conhecimento_ResumidaV11_VERIFICADA'
    DIR_CHECKPOINTS = NER_DATA / "checkpoints_ia_v19_verificado"
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
MAX_TOKENS = 1024
NUM_CTX = 8192

# --- CLIENTE OLLAMA ---
client = AsyncOpenAI(base_url="http://localhost:11434/v1", api_key="ollama")

# =========================================================
# PROMPT EQUILIBRADO (instruções claras mas concisas)
# =========================================================
PROMPT_LLAMA_EXTRACTION = """<|begin_of_text|><|start_header_id|>system<|end_header_id|>

Extract technical information from laptop forum posts. Return ONLY valid JSON. Extract REAL information from the text, NOT placeholders.<|eot_id|><|start_header_id|>user<|end_header_id|>

Device: {modelo_nome}
Date: {post_date}
Title: {titulo}
Content: {corpo}
Comments: {comentarios}

Analyze the conversation and extract:
1. summary: Start with device name, then describe the actual problem, symptoms, and affected components
2. intent: Choose from "Technical Specifications", "Troubleshooting", "Upgrade Advice", "Compatibility", "Warranty", "Performance"
3. detected_fault: Describe the specific technical fault found, or "None" if no fault
4. suggested_solution: Array of actionable steps (max 4). Extract from comments if present.
5. technical_severity: "Low", "Medium", "High", or "Critical"
6. discussion_timeline: Format as "{post_date} to {post_date}"

CRITICAL: Extract REAL information from the conversation above. Do NOT use placeholders like "PROBLEM - SYMPTOMS" or "fault or None". Use the actual text.

Return ONLY valid JSON. Example format:
{{"summary":"DeviceName, actual problem described from text","intent":"Troubleshooting","detected_fault":"specific issue or None","suggested_solution":["step1","step2"],"technical_severity":"Medium","discussion_timeline":"2024-01-01 to 2024-01-01"}}
<|eot_id|><|start_header_id|>assistant<|end_header_id|>
"""

# =========================================================
# PARSER QUE CORRIGE JSON CORTADO
# =========================================================
def parse_llama_json(raw_response: str) -> dict:
    """Corrige JSON incompleto/cortado do Llama"""
    
    # Remove markdown
    raw_response = re.sub(r'```json\s*', '', raw_response)
    raw_response = re.sub(r'```\s*', '', raw_response)
    
    # Tenta encontrar JSON
    start = raw_response.find('{')
    if start == -1:
        raise ValueError("No JSON object found")
    
    json_str = raw_response[start:]
    
    # Conta chaves e adiciona } faltantes
    open_braces = json_str.count('{')
    close_braces = json_str.count('}')
    
    if open_braces > close_braces:
        missing = open_braces - close_braces
        json_str += '}' * missing
        if DEBUG:
            print(f"  🔧 Adicionado {missing} '}}' faltante(s)")
    
    # Corrige vírgulas no final
    json_str = re.sub(r',\s*}', '}', json_str)
    json_str = re.sub(r',\s*\]', ']', json_str)
    
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        # Fallback: extração por regex
        if DEBUG:
            print(f"  🔧 Fallback regex...")
        
        result = {}
        
        summary_match = re.search(r'"summary"\s*:\s*"([^"]*?)(?:"\s*[,}]|$)', json_str, re.DOTALL)
        if summary_match:
            result['summary'] = summary_match.group(1).rstrip('",')
        
        intent_match = re.search(r'"intent"\s*:\s*"([^"]*)"', json_str)
        if intent_match:
            result['intent'] = intent_match.group(1)
        
        fault_match = re.search(r'"detected_fault"\s*:\s*"([^"]*?)(?:"\s*[,}]|$)', json_str, re.DOTALL)
        if fault_match:
            result['detected_fault'] = fault_match.group(1).rstrip('",')
        
        solutions_match = re.search(r'"suggested_solution"\s*:\s*\[(.*?)(?:\]|$)', json_str, re.DOTALL)
        if solutions_match:
            sol_content = solutions_match.group(1)
            solucoes = re.findall(r'"([^"]*)"', sol_content)
            result['suggested_solution'] = solucoes
        
        severity_match = re.search(r'"technical_severity"\s*:\s*"([^"]*)"', json_str)
        if severity_match:
            result['technical_severity'] = severity_match.group(1)
        
        timeline_match = re.search(r'"discussion_timeline"\s*:\s*"([^"]*?)(?:"\s*[,}]|$)', json_str, re.DOTALL)
        if timeline_match:
            result['discussion_timeline'] = timeline_match.group(1).rstrip('",')
        
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
    
    # Prepara conteúdo
    titulo = post.get('titulo', '')[:300]
    corpo = post.get('conteudo_post', post.get('selftext', ''))[:2500]
    comentarios = " ".join([c.get('conteudo', '') for c in post.get('comentarios', [])])[:1500]
    
    post_date = post.get('data_post', datetime.now().strftime('%Y-%m-%d'))
    if isinstance(post_date, (int, float)):
        post_date = datetime.fromtimestamp(float(post_date)).strftime('%Y-%m-%d')
    elif not post_date:
        post_date = '2024-01-01'
    
    if DEBUG:
        print(f"\n{'='*60}")
        print(f"🔄 {post_id} | {modelo_nome[:30]}")
        print(f"📝 Título: {titulo[:80]}...")
        print(f"📊 Tamanhos: corpo={len(corpo)} | comentários={len(comentarios)}")
        print(f"{'='*60}")
    
    prompt = PROMPT_LLAMA_EXTRACTION.format(
        modelo_nome=modelo_nome[:80],
        post_date=post_date,
        titulo=titulo,
        corpo=corpo if corpo else "(no content)",
        comentarios=comentarios if comentarios else "(no comments)"
    )
    
    if DEBUG:
        await salvar_debug(post_id, "01_prompt", prompt[:2000])
        print(f"📏 Tamanho do prompt: {len(prompt)} chars")
    
    try:
        async with semaphore:
            response = await client.chat.completions.create(
                model="llama3.2:3b",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=MAX_TOKENS,
                extra_query={"num_ctx": NUM_CTX}
            )
        
        raw_content = response.choices[0].message.content
        
        if hasattr(response, 'usage'):
            print(f"📥 Resposta: {len(raw_content)} chars | tokens: prompt={response.usage.prompt_tokens}, completion={response.usage.completion_tokens}")
        else:
            print(f"📥 Resposta: {len(raw_content)} chars")
        
        if DEBUG:
            print(f"  Preview: {raw_content[:200]}...")
            await salvar_debug(post_id, "02_raw", raw_content)
        
        # Parse JSON
        analise = parse_llama_json(raw_content)
        
        if DEBUG:
            print(f"✅ JSON OK")
        
        # Verifica se o modelo usou placeholders
        summary = analise.get('summary', '')
        if 'PROBLEM - SYMPTOMS' in summary or '[problem description]' in summary:
            # Fallback: construir summary manualmente
            if DEBUG:
                print(f"  🔧 Placeholder detectado, construindo summary manual...")
            
            # Tenta extrair informação real do título/comentários
            clean_summary = f"{modelo_nome}, "
            if titulo and len(titulo) > 5:
                clean_summary += titulo[:100]
            elif comentarios and len(comentarios) > 10:
                clean_summary += comentarios[:100]
            else:
                clean_summary += "Technical discussion"
            analise['summary'] = clean_summary
        
        # Valida campos
        analise.setdefault('detected_fault', 'None')
        analise.setdefault('technical_severity', 'Low')
        analise.setdefault('discussion_timeline', f"{post_date} to {post_date}")
        analise.setdefault('suggested_solution', [])
        
        # Se detected_fault for placeholder, usa None
        if analise.get('detected_fault') in ['fault or None', 'specific fault or None']:
            analise['detected_fault'] = 'None'
        
        # Corrige summary se necessário
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
        
        # Remove placeholders comuns
        placeholders = ['step 1', 'step 2', 'step 3', 'step1', 'step2', 
                       'action 1', 'action 2', 'specific fix 1', 'solution step 1',
                       'describe the problem', 'problem description']
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
        print(f"  ❌ Erro: {str(e)[:150]}")
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
    
    print(f"🚀 NER V17 - Prompt equilibrado com fallback manual")
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
    print(f"📊 Processados: {stats['processados_agora']} | Cache: {stats['checkpoints_validos']} | Falhas: {stats['falhas']} | Pausas: {stats['pausas_temperatura']}")

if __name__ == "__main__":
    try:
        import aiofiles
        asyncio.run(workflow_principal())
    except KeyboardInterrupt:
        print("\n⚠️ Interrompido. Progresso salvo nos checkpoints.")
    except ImportError:
        print("Instale: pip install aiofiles")