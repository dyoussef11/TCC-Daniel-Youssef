# NerResumLLAMA3.2-3.8bV16_OTIMIZADO.py

import asyncio
import json
import os
from pathlib import Path
from tqdm.asyncio import tqdm as async_tqdm
from openai import AsyncOpenAI
from datetime import datetime
import re
import torch

# --- CONFIGURAÇÕES OTIMIZADAS PARA RTX 3090 (24GB VRAM) ---
try:
    from core.paths import PREPROCESSAMENTO_DATA, NER_DATA
    DIR_ENTRADA = PREPROCESSAMENTO_DATA / 'dados_limpos' / 'dados_limpos_iniciaisV10'
    DIR_SAIDA_FINAL = NER_DATA / 'bases_de_conhecimento_resumos'/ 'base_conhecimento_resumidaV11'
    DIR_CHECKPOINTS = NER_DATA / "checkpoints_resumos_ia" /"checkpoints_ia_v19_verificado"
except ImportError:
    DIR_ENTRADA = Path("./data/Dados_Limpos_IniciaisV10")
    DIR_SAIDA_FINAL = Path("./data/Base_Conhecimento_ResumidaV9_VERIFICADA")
    DIR_CHECKPOINTS = Path("./checkpoints_ia_v17_verificado")

DIR_SAIDA_FINAL.mkdir(parents=True, exist_ok=True)
DIR_CHECKPOINTS.mkdir(parents=True, exist_ok=True)

# --- PARÂMETROS OTIMIZADOS RTX 3090 ---
MAX_CONCURRENT = 4              # Aumentado de 1 para 4 (24GB VRAM aguenta)
MAX_TEMP = 82                   # Mantido
COOLDOWN_TEMP = 72              # Mantido
DEBUG = True
MAX_TOKENS = 2048               # Aumentado de 1024 para 2048
NUM_CTX = 16384                 # Aumentado de 8192 para 16384
BATCH_SIZE = 2                  # Novo: processamento em lote

# --- DETECÇÃO GPU E OTIMIZAÇÕES ---
def get_gpu_info():
    """Obtém informações detalhadas da GPU"""
    try:
        import subprocess
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=name,memory.total,memory.free,memory.used,temperature.gpu,utilization.gpu',
             '--format=csv,noheader,nounits'],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split(', ')
            return {
                'name': parts[0],
                'memory_total': int(parts[1]),
                'memory_free': int(parts[2]),
                'memory_used': int(parts[3]),
                'temperature': int(parts[4]),
                'gpu_util': int(parts[5])
            }
    except:
        pass
    return None

# --- CLIENTE OLLAMA COM CONFIGURAÇÃO OTIMIZADA ---
client = AsyncOpenAI(
    base_url="http://localhost:11434/v1", 
    api_key="ollama",
    timeout=120.0,              # Timeout maior para respostas longas
    max_retries=3               # Retry automático
)

# =========================================================
# PROMPT EM INGLÊS (otimizado para extração de resumos)
# =========================================================
PROMPT_LLAMA_EXTRACTION = """<|begin_of_text|><|start_header_id|>system<|end_header_id|>

You are a technical laptop support expert. Extract REAL technical information from forum conversations. Return ONLY valid JSON. Never use placeholders like "PROBLEM - SYMPTOMS" or "describe the problem". Use actual information from the text.<|eot_id|><|start_header_id|>user<|end_header_id|>

Device: {modelo_nome}
Date: {post_date}
Title: {titulo}
Content: {corpo}
Comments: {comentarios}

Analyze and extract:
1. summary: Start with device name, then write a CONCISE technical summary (2-3 sentences max) describing the actual problem, symptoms, and affected components
2. intent: Choose ONE from "Technical Specifications", "Troubleshooting", "Upgrade Advice", "Compatibility", "Warranty", "Performance"
3. detected_fault: Describe the specific technical fault found, or "None" if no fault was identified
4. suggested_solution: Array of actionable steps (max 4). Extract REAL solutions from comments
5. technical_severity: "Low", "Medium", "High", or "Critical"
6. discussion_timeline: Format as "{post_date} to {post_date}"

CRITICAL RULES:
- Extract REAL information from the conversation above
- NO placeholders like "PROBLEM - SYMPTOMS" or "fault or None"
- NO generic descriptions - be specific
- Summaries MUST be in English

Example output:
{{"summary":"Dell XPS 15 9570, laptop randomly shuts down under load. CPU temperature reaches 95°C before shutdown. Affected component appears to be cooling system.","intent":"Troubleshooting","detected_fault":"Overheating due to dried thermal paste and dust-clogged fans","suggested_solution":["Clean fans and heatsink","Apply new thermal paste","Update BIOS to latest version","Use ThrottleStop to undervolt"],"technical_severity":"High","discussion_timeline":"2024-01-15 to 2024-01-20"}}
<|eot_id|><|start_header_id|>assistant<|end_header_id|>
"""

# =========================================================
# PARSER MELHORADO
# =========================================================
def parse_llama_json(raw_response: str) -> dict:
    """Corrige JSON incompleto/cortado do Llama com fallback robusto"""
    
    # Remove markdown
    raw_response = re.sub(r'```json\s*', '', raw_response)
    raw_response = re.sub(r'```\s*', '', raw_response)
    
    # Tenta encontrar JSON
    start = raw_response.find('{')
    if start == -1:
        raise ValueError("No JSON object found")
    
    # Tenta encontrar o final correto (último } balanceado)
    json_str = raw_response[start:]
    brace_count = 0
    end_pos = 0
    for i, char in enumerate(json_str):
        if char == '{':
            brace_count += 1
        elif char == '}':
            brace_count -= 1
            if brace_count == 0:
                end_pos = i + 1
                break
    
    if end_pos > 0:
        json_str = json_str[:end_pos]
    else:
        # Fallback: adiciona } faltantes
        open_braces = json_str.count('{')
        close_braces = json_str.count('}')
        if open_braces > close_braces:
            json_str += '}' * (open_braces - close_braces)
    
    # Corrige vírgulas no final
    json_str = re.sub(r',\s*}', '}', json_str)
    json_str = re.sub(r',\s*\]', ']', json_str)
    json_str = re.sub(r'\n\s*', ' ', json_str)
    
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        # Fallback: extração por regex mais robusta
        result = {}
        
        summary_match = re.search(r'"summary"\s*:\s*"((?:[^"\\]|\\.)*?)(?:"\s*[,}])', json_str, re.DOTALL)
        if summary_match:
            result['summary'] = summary_match.group(1).replace('\\"', '"').strip()
        
        intent_match = re.search(r'"intent"\s*:\s*"([^"]*)"', json_str)
        if intent_match:
            result['intent'] = intent_match.group(1)
        
        fault_match = re.search(r'"detected_fault"\s*:\s*"((?:[^"\\]|\\.)*?)(?:"\s*[,}])', json_str, re.DOTALL)
        if fault_match:
            result['detected_fault'] = fault_match.group(1).replace('\\"', '"').strip()
        
        solutions_match = re.search(r'"suggested_solution"\s*:\s*\[(.*?)(?:\]|$)', json_str, re.DOTALL)
        if solutions_match:
            sol_content = solutions_match.group(1)
            solucoes = re.findall(r'"((?:[^"\\]|\\.)*?)"', sol_content)
            result['suggested_solution'] = [s.replace('\\"', '"').strip() for s in solucoes]
        
        severity_match = re.search(r'"technical_severity"\s*:\s*"([^"]*)"', json_str)
        if severity_match:
            result['technical_severity'] = severity_match.group(1)
        
        timeline_match = re.search(r'"discussion_timeline"\s*:\s*"((?:[^"\\]|\\.)*?)(?:"\s*[,}])', json_str, re.DOTALL)
        if timeline_match:
            result['discussion_timeline'] = timeline_match.group(1).strip()
        
        if result:
            return result
        raise e

# --- MONITORAMENTO GPU OTIMIZADO ---
async def monitorar_gpu_otimizado(stats, max_temp, cooldown_temp):
    """Monitora GPU e ajusta concorrência dinamicamente"""
    global MAX_CONCURRENT
    
    while True:
        gpu_info = get_gpu_info()
        if gpu_info:
            temp = gpu_info['temperature']
            vram_free = gpu_info['memory_free']
            gpu_util = gpu_info['gpu_util']
            
            # Ajuste dinâmico da concorrência baseado na VRAM livre
            if vram_free > 15000:  # >15GB livre
                new_concurrency = 5
            elif vram_free > 10000:  # >10GB livre
                new_concurrency = 4
            elif vram_free > 6000:   # >6GB livre
                new_concurrency = 3
            else:
                new_concurrency = 2
            
            # Aplica ajuste se mudou
            if new_concurrency != MAX_CONCURRENT and stats.get("processados_agora", 0) > 10:
                print(f"\n⚙️ Ajustando concorrência: {MAX_CONCURRENT} → {new_concurrency} (VRAM livre: {vram_free}MB)")
                MAX_CONCURRENT = new_concurrency
            
            # Controle de temperatura
            if temp > max_temp:
                stats["pausas_temperatura"] += 1
                print(f"\n🌡️ GPU a {temp}°C (utilização: {gpu_util}%)! Pausando até {cooldown_temp}°C...")
                while temp > cooldown_temp:
                    await asyncio.sleep(10)
                    gpu_info = get_gpu_info()
                    temp = gpu_info['temperature'] if gpu_info else temp
                print(f"❄️ Retomando...")
            
            # Debug periodico
            if DEBUG and stats.get("processados_agora", 0) % 10 == 0:
                print(f"\n📊 GPU: {temp}°C | VRAM: {gpu_info['memory_used']}/{gpu_info['memory_total']}MB | Util: {gpu_util}% | Conc: {MAX_CONCURRENT}")
        
        await asyncio.sleep(5)

# --- FUNÇÃO PRINCIPAL DE EXTRAÇÃO (OTIMIZADA) ---
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
    
    # Prepara conteúdo (aumentado para capturar mais contexto)
    titulo = post.get('titulo', '')
    corpo = post.get('conteudo_post', post.get('selftext', ''))
    comentarios = " ".join([c.get('conteudo', '') for c in post.get('comentarios', [])])
    
    post_date = post.get('data_post', datetime.now().strftime('%Y-%m-%d'))
    if isinstance(post_date, (int, float)):
        post_date = datetime.fromtimestamp(float(post_date)).strftime('%Y-%m-%d')
    elif not post_date:
        post_date = '2024-01-01'
    
    if DEBUG:
        print(f"\n{'='*60}")
        print(f"🔄 {post_id} | {modelo_nome[:40]}")
        print(f"📝 Título: {titulo[:80]}...")
        print(f"📊 Tamanhos: corpo={len(corpo)} | comentários={len(comentarios)}")
        print(f"{'='*60}")
    
    prompt = PROMPT_LLAMA_EXTRACTION.format(
        modelo_nome=modelo_nome[:100],
        post_date=post_date,
        titulo=titulo,
        corpo=corpo if corpo else "(no content)",
        comentarios=comentarios if comentarios else "(no comments)"
    )
    
    try:
        async with semaphore:
            response = await client.chat.completions.create(
                model="granite3.2:8b",  # Ou o modelo sugerido abaixo
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=MAX_TOKENS,
                extra_query={
                    "num_ctx": NUM_CTX,
                    "num_predict": MAX_TOKENS,
                    "mirostat": 1,           # Melhora coerência
                    "mirostat_tau": 5.0,
                    "mirostat_eta": 0.1,
                    "repeat_penalty": 1.1
                }
            )
        
        raw_content = response.choices[0].message.content
        
        if hasattr(response, 'usage'):
            print(f"📥 Resposta: {len(raw_content)} chars | tokens: prompt={response.usage.prompt_tokens}, completion={response.usage.completion_tokens}")
        
        # Parse JSON
        analise = parse_llama_json(raw_content)
        
        # Verifica e corrige placeholders
        summary = analise.get('summary', '')
        if 'PROBLEM' in summary.upper() or 'SYMPTOMS' in summary.upper() or '[problem' in summary.lower():
            # Fallback inteligente
            clean_summary = f"{modelo_nome}, "
            if titulo and len(titulo) > 10:
                clean_summary += titulo[:150]
            elif corpo and len(corpo) > 20:
                # Extrai primeira frase significativa
                first_sentence = corpo.split('.')[0][:150]
                clean_summary += first_sentence
            else:
                clean_summary += "Technical discussion about laptop issue"
            analise['summary'] = clean_summary
        
        # Validação dos campos
        analise.setdefault('detected_fault', 'None')
        analise.setdefault('technical_severity', 'Low')
        analise.setdefault('discussion_timeline', f"{post_date} to {post_date}")
        analise.setdefault('suggested_solution', [])
        
        # Remove placeholders das soluções
        placeholders = ['step 1', 'step 2', 'step 3', 'step1', 'step2', 'step3',
                       'action 1', 'action 2', 'specific fix', 'solution step',
                       'describe the problem', 'problem description', 'fix the issue',
                       'troubleshoot the problem', 'identify the root cause']
        analise['suggested_solution'] = [s for s in analise['suggested_solution'] 
                                         if s and s.strip() and s.lower() not in placeholders 
                                         and len(s) > 10]
        
        # Metadados
        analise['ancoragem_temporal'] = {
            "data_processamento": datetime.now().strftime('%Y-%m-%d'),
            "data_post_original": post_date
        }
        
        # Salva checkpoint
        async with aiofiles.open(checkpoint_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(analise, ensure_ascii=False, indent=2))
        
        stats["processados_agora"] += 1
        return analise
        
    except Exception as e:
        print(f"  ❌ Erro: {str(e)[:150]}")
        stats["falhas"] += 1
        return None

# --- WORKFLOW PRINCIPAL OTIMIZADO ---
async def workflow_principal():
    global MAX_CONCURRENT
    
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
    
    print(f"\n{'='*80}")
    print(f"🚀 NER OTIMIZADO PARA RTX 3090")
    print(f"📊 GPU: {get_gpu_info()}")
    print(f"📂 Total: {len(arquivos)} | Pendentes: {len(arquivos_pendentes)}")
    print(f"💾 Checkpoints: {len(list(DIR_CHECKPOINTS.glob('*.json')))}")
    print(f"⚙️ Concorrência inicial: {MAX_CONCURRENT} | Contexto: {NUM_CTX} | Max Tokens: {MAX_TOKENS}")
    print(f"{'='*80}\n")
    
    if len(arquivos_pendentes) == 0:
        print("✨ Todos processados!")
        return
    
    # Monitor GPU em background
    monitor_task = asyncio.create_task(monitorar_gpu_otimizado(stats, MAX_TEMP, COOLDOWN_TEMP))
    
    for arq_path in async_tqdm(arquivos_pendentes, desc="Processando modelos"):
        try:
            with open(arq_path, 'r', encoding='utf-8') as f:
                dados_modelo = json.load(f)
        except Exception as e:
            print(f"❌ Erro ao ler {arq_path.name}: {e}")
            continue
        
        modelo_nome = dados_modelo.get('modelo_original', 
                                      dados_modelo.get('modelo_busca_utilizado', 'Unknown'))
        posts = dados_modelo.get('posts', [])
        
        # Atualiza semaphore com nova concorrência
        semaphore = asyncio.Semaphore(MAX_CONCURRENT)
        
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
        
        await asyncio.sleep(0.5)  # Pequena pausa entre modelos
    
    monitor_task.cancel()
    
    print(f"\n{'='*80}")
    print(f"✅ PROCESSAMENTO CONCLUÍDO!")
    print(f"📊 Processados agora: {stats['processados_agora']}")
    print(f"💾 Cache utilizado: {stats['checkpoints_validos']}")
    print(f"❌ Falhas: {stats['falhas']}")
    print(f"🌡️ Pausas por temperatura: {stats['pausas_temperatura']}")
    print(f"{'='*80}")

if __name__ == "__main__":
    try:
        import aiofiles
        asyncio.run(workflow_principal())
    except KeyboardInterrupt:
        print("\n⚠️ Interrompido. Progresso salvo nos checkpoints.")
    except ImportError:
        print("Instale as dependências: pip install aiofiles torch")