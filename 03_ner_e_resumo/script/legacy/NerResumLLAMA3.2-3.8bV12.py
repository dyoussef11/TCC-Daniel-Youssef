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
DEBUG = True  # Liga/desliga debug

# --- CLIENTE OLLAMA ---
client = AsyncOpenAI(base_url="http://localhost:11434/v1", api_key="ollama")

# =========================================================
# PROMPT OTIMIZADO COM TAGS LLAMA (baseado no seu V11)
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
        f.write(f"=== ETAPA: {etapa} ===\n")
        f.write(f"Post ID: {post_id}\n")
        f.write(f"Timestamp: {datetime.now().isoformat()}\n")
        f.write(f"{'='*60}\n\n")
        f.write(conteudo)
    
    print(f"  📝 Debug: {filename.name}")

def limpar_resposta_json(raw_response: str) -> str:
    """Limpa a resposta do modelo para extrair JSON puro"""
    # Remove tags de markdown se existirem
    raw_response = re.sub(r'```json\s*', '', raw_response)
    raw_response = re.sub(r'```\s*', '', raw_response)
    
    # Se tiver text explicativo antes/depois, tenta extrair só o JSON
    json_match = re.search(r'\{.*\}', raw_response, re.DOTALL)
    if json_match:
        return json_match.group(0)
    
    return raw_response.strip()

# --- FUNÇÃO PRINCIPAL DE EXTRAÇÃO (COM PROMPT OTIMIZADO) ---
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
        print(f"🔄 Processando: {post_id}")
        print(f"📌 Modelo: {modelo_nome}")
        print(f"📌 Título: {titulo[:80]}...")
        print(f"📌 Tamanho: {len(corpo)} chars")
        print(f"{'='*60}")
    
    # Monta prompt com tags Llama
    prompt = PROMPT_LLAMA_EXTRACTION.format(
        modelo_nome=modelo_nome,
        post_date=post_date,
        titulo=titulo[:300],
        corpo=corpo[:4000],
        comentarios=comentarios[:2000]
    )
    
    if DEBUG:
        await salvar_debug(post_id, "01_prompt", prompt)
    
    try:
        async with semaphore:
            response = await client.chat.completions.create(
                model="llama3.2:3b",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=512,
                extra_query={"num_ctx": 4096}
            )
        
        raw_content = response.choices[0].message.content
        
        if DEBUG:
            print(f"📥 Resposta recebida ({len(raw_content)} chars)")
            print(f"  Preview: {raw_content[:200]}...")
            await salvar_debug(post_id, "02_raw_response", raw_content)
        
        # Limpa e parseia JSON
        json_content = limpar_resposta_json(raw_content)
        analise = json.loads(json_content)
        
        if DEBUG:
            print(f"✅ JSON parseado com sucesso")
        
        # Validação e correção dos campos
        analise.setdefault('detected_fault', 'None')
        analise.setdefault('technical_severity', 'Low')
        analise.setdefault('discussion_timeline', f"{post_date} to {post_date}")
        analise.setdefault('suggested_solution', [])
        
        # Corrige summary
        summary = analise.get('summary', '')
        if not summary.startswith(modelo_nome):
            analise['summary'] = f"{modelo_nome}, {summary}"
            if DEBUG:
                print(f"  🔧 Summary prefixado")
        
        # Valida intent
        intents_validos = ['Technical Specifications', 'Troubleshooting', 'Upgrade Advice', 
                          'Compatibility', 'Warranty', 'Performance']
        if analise.get('intent') not in intents_validos:
            analise['intent'] = 'Troubleshooting'
        
        # Valida severity
        if analise.get('technical_severity') not in ['Low', 'Medium', 'High', 'Critical']:
            analise['technical_severity'] = 'Low'
        
        # Garante que suggested_solution é lista
        if not isinstance(analise.get('suggested_solution'), list):
            analise['suggested_solution'] = []
        
        # Remove placeholders comuns
        placeholders = ['step 1', 'step 2', 'step 3', 'step 4', 
                       'action 1', 'action 2', 'specific fix 1']
        analise['suggested_solution'] = [s for s in analise['suggested_solution'] 
                                         if s and s.lower() not in placeholders]
        
        # Adiciona metadados
        analise['ancoragem_temporal'] = {
            "data_processamento": datetime.now().strftime('%Y-%m-%d'),
            "data_post_original": post_date
        }
        
        if DEBUG:
            await salvar_debug(post_id, "03_final_json", json.dumps(analise, indent=2, ensure_ascii=False))
        
        # Salva checkpoint
        async with aiofiles.open(checkpoint_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(analise, ensure_ascii=False, indent=2))
        
        stats["processados_agora"] += 1
        return analise
        
    except json.JSONDecodeError as e:
        print(f"  ❌ Erro JSON: {e}")
        await salvar_debug(post_id, "99_error", f"JSONError: {e}\n\nRaw: {raw_content[:500]}")
        stats["falhas"] += 1
        return None
    except Exception as e:
        print(f"  ❌ Erro: {str(e)[:100]}")
        stats["falhas"] += 1
        return None

# --- WORKFLOW PRINCIPAL ---
async def workflow_principal():
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    stats = {"checkpoints_validos": 0, "processados_agora": 0, "falhas": 0, "pausas_temperatura": 0}
    
    arquivos = list(DIR_ENTRADA.glob("*.json"))
    
    # Filtra pendentes e ordena por tamanho
    arquivos_pendentes = []
    for arq in arquivos:
        output_path = DIR_SAIDA_FINAL / f"NER_{arq.name}"
        if not output_path.exists():
            arquivos_pendentes.append(arq)
    
    arquivos_pendentes.sort(key=lambda x: os.path.getsize(x))
    
    # Debug: mostra ordenação
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
    
    print(f"🚀 NER com prompt otimizado Llama")
    print(f"📂 Total: {len(arquivos)} | Pendentes: {len(arquivos_pendentes)}")
    print(f"💾 Checkpoints: {len(list(DIR_CHECKPOINTS.glob('*.json')))}")
    print(f"🌡️ GPU: {MAX_TEMP}°C | Concorrência: {MAX_CONCURRENT}")
    print(f"🐛 Debug: {'ON' if DEBUG else 'OFF'}\n")
    
    if len(arquivos_pendentes) == 0:
        print("✨ Todos processados!")
        return
    
    monitor_task = asyncio.create_task(monitorar_temperatura(stats, MAX_TEMP, COOLDOWN_TEMP))
    
    for arq_path in async_tqdm(arquivos_pendentes, desc="Modelos"):
        try:
            with open(arq_path, 'r', encoding='utf-8') as f:
                dados_modelo = json.load(f)
        except Exception as e:
            print(f"❌ Erro ao ler {arq_path.name}: {e}")
            continue
        
        modelo_nome = dados_modelo.get('modelo_original', 
                                      dados_modelo.get('modelo_busca_utilizado', 'Unknown'))
        posts = dados_modelo.get('posts', [])
        
        if DEBUG:
            print(f"\n📁 {arq_path.name} | Modelo: {modelo_nome} | Posts: {len(posts)}")
        
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
            if DEBUG:
                print(f"  💾 Salvo: {output_path.name}")
        
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