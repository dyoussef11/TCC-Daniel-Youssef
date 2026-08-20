# NerResumLLAMA3.1-8bV2_FALLBACK.py
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
    # DIR_ENTRADA = PREPROCESSAMENTO_DATA / 'dados_limpos' / 'dados_limpos_iniciaisV10'
    DIR_ENTRADA = PREPROCESSAMENTO_DATA /  'dados_limpos'/ 'dados_limpos_iniciaisV12'

    DIR_SAIDA_FINAL = NER_DATA / 'base_conhecimento_resumidaV12'
    DIR_CHECKPOINTS = NER_DATA / "checkpoints_resumos_ia" /"checkpoints_ia_v21_verificado"
except ImportError:
    DIR_ENTRADA = Path("./data/Dados_Limpos_IniciaisV10")
    DIR_SAIDA_FINAL = Path("./data/Base_Conhecimento_ResumidaV9_VERIFICADA")
    DIR_CHECKPOINTS = Path("./checkpoints_ia_v17_verificado")

DIR_SAIDA_FINAL.mkdir(parents=True, exist_ok=True)
DIR_CHECKPOINTS.mkdir(parents=True, exist_ok=True)

# --- PARÂMETROS OTIMIZADOS RTX 3090 ---
MAX_CONCURRENT = 6
MAX_TEMP = 85
COOLDOWN_TEMP = 75
DEBUG = False
MAX_TOKENS = 3072
NUM_CTX = 32768
BATCH_SIZE = 4
MAX_RECENT_COMMENTS = 30

# --- DETECÇÃO GPU ---
def get_gpu_info():
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

# --- CLIENTE OLLAMA ---
client = AsyncOpenAI(
    base_url="http://localhost:11434/v1", 
    api_key="ollama",
    timeout=180.0,
    max_retries=3
)

# =========================================================
# PROMPT (INALTERADO - MANTIDO EXATAMENTE COMO VOCÊ QUER)
# =========================================================
PROMPT_LLAMA_EXTRACTION = """<|begin_of_text|><|start_header_id|>system<|end_header_id|>

You are a technical laptop support expert. Extract REAL technical information from forum conversations. Return ONLY valid JSON. Never use placeholders. Use actual information from the text.<|eot_id|><|start_header_id|>user<|end_header_id|>

Device: {modelo_nome}
Date: {post_date}
Title: {titulo}
Content: {corpo}
Comments: {comentarios}

Extract:
1. summary: Start with device name, concise technical summary (2-3 sentences) of problem, symptoms, affected components
2. intent: "Technical Specifications", "Troubleshooting", "Upgrade Advice", "Compatibility", "Warranty", or "Performance"
3. detected_fault: Specific technical fault found, or "None"
4. suggested_solution: Array of actionable steps (max 4). Extract REAL solutions
5. technical_severity: "Low", "Medium", "High", or "Critical"
6. discussion_timeline: Format as "{post_date} to {post_date}"

CRITICAL: Extract REAL information. NO placeholders like "PROBLEM - SYMPTOMS" or "describe the problem". Be specific.

Example:
{{"summary":"Dell XPS 15 9570 randomly shuts down under load. CPU reaches 95°C before shutdown. Cooling system issue.","intent":"Troubleshooting","detected_fault":"Overheating due to dried thermal paste","suggested_solution":["Clean fans","Apply new thermal paste","Update BIOS"],"technical_severity":"High","discussion_timeline":"2024-01-15 to 2024-01-20"}}
<|eot_id|><|start_header_id|>assistant<|end_header_id|>
"""

# =========================================================
# PARSER COM FALLBACK SUPER ROBUSTO
# =========================================================

def extract_json_super_robust(raw_response, post_id, titulo, modelo_nome, corpo, post_date):
    """Extrai JSON com múltiplos níveis de fallback - NUNCA retorna None"""
    
    result = {}
    
    # ========== TENTATIVA 1: Parse normal ==========
    try:
        # Remove markdown
        cleaned = re.sub(r'```json\s*', '', raw_response)
        cleaned = re.sub(r'```\s*', '', cleaned)
        
        start = cleaned.find('{')
        if start != -1:
            json_str = cleaned[start:]
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
                json_str = re.sub(r',\s*}', '}', json_str)
                json_str = re.sub(r',\s*\]', ']', json_str)
                result = json.loads(json_str)
                print(f"  ✅ JSON válido obtido")
                return result
    except Exception as e:
        print(f"  ⚠️ Parse normal falhou: {str(e)[:50]}")
    
    # ========== TENTATIVA 2: Extração por regex campo a campo ==========
    print(f"  🔧 Tentando extração por regex...")
    
    # Summary
    summary_patterns = [
        r'"summary"\s*:\s*"((?:[^"\\]|\\.)*?)(?:"\s*[,}])',
        r'summary["\s:]+([^"\n]+)',
        r'Summary:\s*(.+?)(?:\n|$)',
    ]
    for pattern in summary_patterns:
        match = re.search(pattern, raw_response, re.DOTALL | re.IGNORECASE)
        if match:
            result['summary'] = match.group(1).replace('\\"', '"').strip()[:300]
            break
    
    # Intent
    intent_match = re.search(r'"intent"\s*:\s*"([^"]*)"', raw_response, re.IGNORECASE)
    if intent_match:
        result['intent'] = intent_match.group(1)
    
    # Detected fault
    fault_patterns = [
        r'"detected_fault"\s*:\s*"((?:[^"\\]|\\.)*?)(?:"\s*[,}])',
        r'detected_fault["\s:]+([^"\n]+)',
    ]
    for pattern in fault_patterns:
        match = re.search(pattern, raw_response, re.DOTALL | re.IGNORECASE)
        if match:
            result['detected_fault'] = match.group(1).replace('\\"', '"').strip()
            break
    
    # Suggested solutions
    solutions_match = re.search(r'"suggested_solution"\s*:\s*\[(.*?)(?:\]|$)', raw_response, re.DOTALL)
    if solutions_match:
        sol_content = solutions_match.group(1)
        solucoes = re.findall(r'"((?:[^"\\]|\\.)*?)"', sol_content)
        result['suggested_solution'] = [s.replace('\\"', '"').strip() for s in solucoes if len(s) > 5]
    
    # Severity
    severity_match = re.search(r'"technical_severity"\s*:\s*"([^"]*)"', raw_response, re.IGNORECASE)
    if severity_match:
        result['technical_severity'] = severity_match.group(1)
    
    # Timeline
    timeline_match = re.search(r'"discussion_timeline"\s*:\s*"((?:[^"\\]|\\.)*?)(?:"\s*[,}])', raw_response, re.DOTALL)
    if timeline_match:
        result['discussion_timeline'] = timeline_match.group(1).strip()
    
    # Se conseguiu pelo menos o summary, considera sucesso parcial
    if result.get('summary'):
        print(f"  ✅ Extração por regex bem-sucedida")
        # Preenche campos faltantes
        result.setdefault('intent', 'Troubleshooting')
        result.setdefault('detected_fault', 'None')
        result.setdefault('suggested_solution', [])
        result.setdefault('technical_severity', 'Medium')
        result.setdefault('discussion_timeline', f"{post_date} to {post_date}")
        return result
    
    # ========== TENTATIVA 3: Fallback inteligente baseado no título ==========
    print(f"  🔧 Criando fallback inteligente...")
    
    # Tenta extrair informação relevante do título
    titulo_limpo = titulo[:200] if titulo else ""
    corpo_limpo = corpo[:200] if corpo else ""
    
    # Verifica se há palavras-chave de problema
    problema_keywords = ['problem', 'issue', 'error', 'fault', 'fail', 'crash', 'freeze', 'slow', 'lag']
    problema_detectado = "None"
    for kw in problema_keywords:
        if kw.lower() in titulo_limpo.lower() or kw.lower() in corpo_limpo.lower():
            problema_detectado = titulo_limpo[:100]
            break
    
    # Cria summary base
    if titulo_limpo:
        summary_base = f"{modelo_nome}, {titulo_limpo}"
    elif corpo_limpo:
        primeira_frase = corpo_limpo.split('.')[0]
        summary_base = f"{modelo_nome}, {primeira_frase}"
    else:
        summary_base = f"{modelo_nome}, technical discussion about laptop issue"
    
    result = {
        "summary": summary_base[:300],
        "intent": "Troubleshooting",
        "detected_fault": problema_detectado if problema_detectado != "None" else "Information could not be extracted automatically",
        "suggested_solution": ["Check forum thread for solutions", "Review community comments for fixes"],
        "technical_severity": "Medium",
        "discussion_timeline": f"{post_date} to {post_date}",
        "fallback_used": True
    }
    
    print(f"  ⚠️ Fallback usado para {post_id}")
    return result

# =========================================================
# PARSER ORIGINAL (MANTIDO PARA COMPATIBILIDADE)
# =========================================================
def parse_llama_json(raw_response: str) -> dict:
    """Corrige JSON incompleto/cortado do Llama com fallback robusto"""
    
    raw_response = re.sub(r'```json\s*', '', raw_response)
    raw_response = re.sub(r'```\s*', '', raw_response)
    
    start = raw_response.find('{')
    if start == -1:
        raise ValueError("No JSON object found")
    
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
        open_braces = json_str.count('{')
        close_braces = json_str.count('}')
        if open_braces > close_braces:
            json_str += '}' * (open_braces - close_braces)
    
    json_str = re.sub(r',\s*}', '}', json_str)
    json_str = re.sub(r',\s*\]', ']', json_str)
    json_str = re.sub(r'\n\s*', ' ', json_str)
    
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
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

# --- MONITORAMENTO GPU ---
async def monitorar_gpu_otimizado(stats, max_temp, cooldown_temp):
    global MAX_CONCURRENT
    
    while True:
        gpu_info = get_gpu_info()
        if gpu_info:
            temp = gpu_info['temperature']
            vram_free = gpu_info['memory_free']
            gpu_util = gpu_info['gpu_util']
            
            if vram_free > 18000:
                new_concurrency = 8
            elif vram_free > 14000:
                new_concurrency = 6
            elif vram_free > 10000:
                new_concurrency = 5
            elif vram_free > 6000:
                new_concurrency = 3
            else:
                new_concurrency = 2
            
            if new_concurrency != MAX_CONCURRENT and stats.get("processados_agora", 0) > 5:
                print(f"\n⚙️ Ajustando concorrência: {MAX_CONCURRENT} → {new_concurrency} (VRAM livre: {vram_free}MB)")
                MAX_CONCURRENT = new_concurrency
            
            if temp > max_temp:
                stats["pausas_temperatura"] += 1
                print(f"\n🌡️ GPU a {temp}°C (utilização: {gpu_util}%)! Pausando até {cooldown_temp}°C...")
                old_concurrency = MAX_CONCURRENT
                MAX_CONCURRENT = max(1, MAX_CONCURRENT // 2)
                while temp > cooldown_temp:
                    await asyncio.sleep(10)
                    gpu_info = get_gpu_info()
                    temp = gpu_info['temperature'] if gpu_info else temp
                MAX_CONCURRENT = old_concurrency
                print(f"❄️ Retomando com concorrência {MAX_CONCURRENT}...")
            
            if stats.get("processados_agora", 0) % 25 == 0 and stats["processados_agora"] > 0:
                print(f"\n📊 GPU: {temp}°C | VRAM: {gpu_info['memory_used']}/{gpu_info['memory_total']}MB | Util: {gpu_util}% | Conc: {MAX_CONCURRENT}")
        
        await asyncio.sleep(3)

# --- FUNÇÃO PRINCIPAL DE EXTRAÇÃO COM FALLBACK ---
async def extrair_analise(post, modelo_nome, post_id, stats, semaphore):
    checkpoint_path = DIR_CHECKPOINTS / f"{post_id}.json"
    
    if checkpoint_path.exists():
        try:
            with open(checkpoint_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            stats["checkpoints_validos"] += 1
            return data
        except:
            print(f"  ⚠️ Cache corrompido: {post_id}")
    
    # Prepara conteúdo
    titulo = post.get('titulo', '')
    corpo = post.get('conteudo_post', post.get('selftext', ''))
    
    comentarios_lista = post.get('comentarios', [])
    
    def get_comment_date(comment):
        data = comment.get('data', comment.get('data_post', comment.get('timestamp', '')))
        if isinstance(data, (int, float)):
            return data
        if isinstance(data, str) and data:
            try:
                return datetime.strptime(data, '%Y-%m-%d').timestamp()
            except:
                pass
        return 0
    
    comentarios_ordenados = sorted(comentarios_lista, key=get_comment_date, reverse=True)
    comentarios_recentes = comentarios_ordenados[:MAX_RECENT_COMMENTS]
    comentarios = " ".join([c.get('conteudo', '') for c in comentarios_recentes])
    
    post_date = post.get('data_post', datetime.now().strftime('%Y-%m-%d'))
    if isinstance(post_date, (int, float)):
        post_date = datetime.fromtimestamp(float(post_date)).strftime('%Y-%m-%d')
    elif not post_date:
        post_date = '2024-01-01'
    
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
                model="llama3.1:8b",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=MAX_TOKENS,
                extra_query={
                    "num_ctx": NUM_CTX,
                    "num_predict": MAX_TOKENS,
                    "mirostat": 2,
                    "mirostat_tau": 5.0,
                    "mirostat_eta": 0.1,
                    "repeat_penalty": 1.15,
                    "temperature": 0.1,
                    "top_k": 40,
                    "top_p": 0.9,
                    "stop": ["<|eot_id|>", "<|end_of_text|>"]
                }
            )
        
        raw_content = response.choices[0].message.content
        
        # ========== PONTO CRÍTICO: USAR O FALLBACK SUPER ROBUSTO ==========
        analise = extract_json_super_robust(
            raw_content, post_id, titulo, modelo_nome, corpo, post_date
        )
        
        # Validação dos campos obrigatórios
        analise.setdefault('detected_fault', 'None')
        analise.setdefault('technical_severity', 'Low')
        analise.setdefault('discussion_timeline', f"{post_date} to {post_date}")
        analise.setdefault('suggested_solution', [])
        
        # Valida intent
        valid_intents = ['Technical Specifications', 'Troubleshooting', 'Upgrade Advice', 
                        'Compatibility', 'Warranty', 'Performance']
        if analise.get('intent') not in valid_intents:
            analise['intent'] = 'Troubleshooting'
        
        # Remove placeholders das soluções
        placeholders = ['step 1', 'step 2', 'step 3', 'step1', 'step2', 'step3',
                       'action 1', 'action 2', 'specific fix', 'solution step',
                       'describe the problem', 'problem description', 'fix the issue',
                       'troubleshoot the problem', 'identify the root cause']
        if isinstance(analise.get('suggested_solution'), list):
            analise['suggested_solution'] = [s for s in analise['suggested_solution'] 
                                             if s and isinstance(s, str) and s.strip() 
                                             and s.lower() not in placeholders 
                                             and len(s) > 10]
        
        # Metadados
        analise['ancoragem_temporal'] = {
            "data_processamento": datetime.now().strftime('%Y-%m-%d'),
            "data_post_original": post_date,
            "comentarios_analisados": len(comentarios_recentes),
            "total_comentarios": len(comentarios_lista),
            "priorizacao_recentes": True
        }
        
        # Salva checkpoint
        import aiofiles
        async with aiofiles.open(checkpoint_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(analise, ensure_ascii=False, indent=2))
        
        stats["processados_agora"] += 1
        
        if analise.get('fallback_used'):
            stats["falhas"] += 1  # Conta como falha parcial
        
        return analise
        
    except Exception as e:
        print(f"  ❌ Erro crítico {post_id}: {str(e)[:100]}")
        stats["falhas"] += 1
        
        # Fallback de último recurso
        fallback_final = {
            "summary": f"{modelo_nome}, {titulo[:150] if titulo else 'Technical discussion'}",
            "intent": "Troubleshooting",
            "detected_fault": "Extraction failed due to API error",
            "suggested_solution": ["Check original forum thread for solutions"],
            "technical_severity": "Medium",
            "discussion_timeline": f"{post_date} to {post_date}",
            "error": str(e)[:100],
            "emergency_fallback": True
        }
        
        # Salva mesmo com erro
        import aiofiles
        async with aiofiles.open(checkpoint_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(fallback_final, ensure_ascii=False, indent=2))
        
        return fallback_final

# --- WORKFLOW PRINCIPAL ---
async def workflow_principal():
    global MAX_CONCURRENT
    
    stats = {"checkpoints_validos": 0, "processados_agora": 0, "falhas": 0, "pausas_temperatura": 0}
    
    arquivos = list(DIR_ENTRADA.glob("*.json"))
    
    arquivos_pendentes = []
    for arq in arquivos:
        output_path = DIR_SAIDA_FINAL / f"NER_{arq.name}"
        if not output_path.exists():
            arquivos_pendentes.append(arq)
    
    arquivos_pendentes.sort(key=lambda x: os.path.getsize(x))
    
    print(f"\n{'='*80}")
    print(f"🚀 NER COM FALLBACK ROBUSTO - Llama3.1:8B")
    print(f"📌 PRIORIZANDO OS {MAX_RECENT_COMMENTS} COMENTÁRIOS MAIS RECENTES")
    print(f"🔧 FALLBACK: Extração por regex + Inteligente")
    gpu_info = get_gpu_info()
    if gpu_info:
        print(f"📊 GPU: {gpu_info['name']} | VRAM: {gpu_info['memory_total']}MB | Temp: {gpu_info['temperature']}°C")
    print(f"📂 Total: {len(arquivos)} | Pendentes: {len(arquivos_pendentes)}")
    print(f"💾 Checkpoints: {len(list(DIR_CHECKPOINTS.glob('*.json')))}")
    print(f"⚙️ Concorrência: {MAX_CONCURRENT} | Contexto: {NUM_CTX} | Max Tokens: {MAX_TOKENS}")
    print(f"{'='*80}\n")
    
    if len(arquivos_pendentes) == 0:
        print("✨ Todos processados!")
        return
    
    monitor_task = asyncio.create_task(monitorar_gpu_otimizado(stats, MAX_TEMP, COOLDOWN_TEMP))
    
    for i in range(0, len(arquivos_pendentes), BATCH_SIZE):
        batch = arquivos_pendentes[i:i+BATCH_SIZE]
        semaphore = asyncio.Semaphore(MAX_CONCURRENT)
        
        for arq_path in async_tqdm(batch, desc=f"Lote {i//BATCH_SIZE + 1}"):
            try:
                with open(arq_path, 'r', encoding='utf-8') as f:
                    dados_modelo = json.load(f)
            except Exception as e:
                print(f"❌ Erro ao ler {arq_path.name}: {e}")
                continue
            
            modelo_nome = dados_modelo.get('modelo_original', 
                                          dados_modelo.get('modelo_busca_utilizado', 'Unknown'))
            posts = dados_modelo.get('posts', [])
            
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
            
            await asyncio.sleep(0.3)
        
        if i + BATCH_SIZE < len(arquivos_pendentes):
            print(f"\n⏸️ Pausa entre lotes por 2 segundos...")
            await asyncio.sleep(2)
    
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