# NerResumLLAMA3.2-3.8bV6_SEGURO.py
import asyncio
import json
from pathlib import Path
from tqdm.asyncio import tqdm as async_tqdm
from openai import AsyncOpenAI
from datetime import datetime
import aiofiles
import subprocess
import time

# --- CONFIGURAÇÕES CONSERVADORAS ---
try:
    from core.paths import PREPROCESSAMENTO_DATA, NER_DATA
    DIR_ENTRADA = PREPROCESSAMENTO_DATA / 'Dados_Final_Threshold_V12'
    DIR_SAIDA_FINAL = NER_DATA / 'Base_Conhecimento_ResumidaV7_VERIFICADA'
    DIR_CHECKPOINTS = NER_DATA / "checkpoints_ia_v15_verificado"
except ImportError:
    DIR_ENTRADA = Path("./data/Dados_Final_ThresholdV6")
    DIR_SAIDA_FINAL = Path("./data/Base_Conhecimento_ResumidaV5_VERIFICADA")
    DIR_CHECKPOINTS = Path("./checkpoints_ia_v13_verificado")

DIR_SAIDA_FINAL.mkdir(parents=True, exist_ok=True)
DIR_CHECKPOINTS.mkdir(parents=True, exist_ok=True)

# 🎯 CONCORRÊNCIA MÍNIMA para GTX 1050 Ti 4GB
MAX_CONCURRENT = 12  # MUITO reduzido para segurança
semaphore = asyncio.Semaphore(MAX_CONCURRENT)

# 🌡️ LIMITES DE TEMPERATURA
MAX_TEMP = 78  # Desliga se passar de 75°C
COOLDOWN_TEMP = 70  # Retoma quando esfriar para 65°C
CHECK_INTERVAL = 5  # Verifica temperatura a cada 5 segundos

client = AsyncOpenAI(
    base_url="http://localhost:11434/v1", 
    api_key="ollama",
    timeout=300.0,  # 5 minutos
    max_retries=2
)

stats = {
    "checkpoints_validos": 0,
    "checkpoints_corrompidos": 0,
    "processados_agora": 0,
    "falhas": 0,
    "pausas_temperatura": 0
}

def get_gpu_temperature():
    """Obtém temperatura da GPU via nvidia-smi."""
    try:
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=temperature.gpu', '--format=csv,noheader,nounits'],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return int(result.stdout.strip())
    except:
        pass
    return None

async def monitorar_temperatura():
    """Monitora temperatura e pausa se necessário."""
    while True:
        temp = get_gpu_temperature()
        if temp and temp > MAX_TEMP:
            stats["pausas_temperatura"] += 1
            print(f"\n🌡️ GPU a {temp}°C! Pausando até {COOLDOWN_TEMP}°C...")
            while temp > COOLDOWN_TEMP:
                await asyncio.sleep(10)
                temp = get_gpu_temperature() or temp
            print(f"❄️ GPU resfriada para {temp}°C. Retomando...")
        await asyncio.sleep(CHECK_INTERVAL)

def verificar_checkpoint_valido(checkpoint_path):
    try:
        with open(checkpoint_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        campos = ["summary", "intent", "detected_fault", "suggested_solution"]
        for campo in campos:
            if campo not in data:
                return False, f"Campo ausente: {campo}"
        return True, data
    except:
        return False, "Erro ao ler checkpoint"

async def extrair_seguro(post, modelo_nome, post_id):
    """Extração com pausas para respiro da GPU."""
    
    checkpoint_path = DIR_CHECKPOINTS / f"{post_id}.json"
    
    if checkpoint_path.exists():
        valido, data_ou_erro = verificar_checkpoint_valido(checkpoint_path)
        if valido:
            stats["checkpoints_validos"] += 1
            return data_ou_erro
        else:
            stats["checkpoints_corrompidos"] += 1
            checkpoint_path.unlink()
    
    titulo = post.get('titulo', 'N/A')[:80]
    corpo = post.get('conteudo_post', 'N/A')[:500]  # Mais curto
    comentarios = " ".join([
        c.get('conteudo', '')[:80] 
        for c in post.get('comentarios', [])[:1]  # Apenas 1 comentário
    ])
    
    ts = post.get('data_post')
    post_date = datetime.fromtimestamp(float(ts)).strftime('%Y-%m-%d') if ts else "2024-01-01"
    
    prompt = PROMPT_LLAMA_EXTRACTION.format(
        modelo_nome=modelo_nome,
        post_date=post_date,
        titulo=titulo,
        corpo=corpo,
        comentarios=comentarios
    )
    
    for tentativa in range(2):
        try:
            async with semaphore:
                response = await client.chat.completions.create(
                    model="llama3.2:3b",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    extra_query={
                        "num_ctx": 512,  # MUITO reduzido
                        "num_predict": 100,  # Mais curto
                        "top_p": 0.9,
                    },
                    response_format={"type": "json_object"}
                )
            
            content = response.choices[0].message.content
            
            try:
                analise = json.loads(content)
            except:
                analise = reparar_json_malformado(content)
            
            analise['ancoragem_temporal'] = {
                "data_post": post_date,
                "periodo_referencia": post_date[:7]
            }
            
            if isinstance(analise.get('suggested_solution'), str):
                analise['suggested_solution'] = [analise['suggested_solution']]
            
            async with aiofiles.open(checkpoint_path, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(analise, ensure_ascii=False))
            
            stats["processados_agora"] += 1
            
            # PAUSA ENTRE POSTS para GPU respirar
            await asyncio.sleep(1.0)
            
            return analise
            
        except Exception as e:
            if tentativa == 1:
                stats["falhas"] += 1
                print(f"  ❌ Falha no post {post_id}: {str(e)[:40]}")
                return {
                    "summary": f"{modelo_nome}, extraction failed - N/A",
                    "intent": "Technical Specifications",
                    "detected_fault": "None",
                    "suggested_solution": ["Unable to extract"],
                    "technical_severity": "Low",
                    "discussion_timeline": f"{post_date} to {post_date}",
                    "ancoragem_temporal": {"data_post": post_date, "periodo_referencia": post_date[:7]}
                }
            await asyncio.sleep(3.0 * (tentativa + 1))
    
    return None

async def processar_modelo_seguro(arq_path):
    try:
        with open(arq_path, 'r', encoding='utf-8') as f:
            dados_modelo = json.load(f)
    except:
        return None
    
    modelo_nome = dados_modelo.get('modelo_busca_utilizado', 'Unknown')
    posts = dados_modelo.get('posts', [])
    
    posts_para_processar = []
    posts_processados = []
    
    for p in posts:
        p_id = str(p.get('id'))
        checkpoint_path = DIR_CHECKPOINTS / f"{p_id}.json"
        
        if checkpoint_path.exists():
            valido, data_ou_erro = verificar_checkpoint_valido(checkpoint_path)
            if valido:
                p['analise_ia'] = data_ou_erro
                posts_processados.append(p)
                stats["checkpoints_validos"] += 1
            else:
                checkpoint_path.unlink()
                posts_para_processar.append(p)
        else:
            if len(str(p)) < 4000:  # Mais restritivo
                posts_para_processar.append(p)
    
    temp = get_gpu_temperature()
    print(f"\n  📊 {modelo_nome}: {len(posts_processados)} cache, {len(posts_para_processar)} novo(s) | GPU: {temp}°C")
    
    if posts_para_processar:
        # Processa UM POR VEZ para segurança máxima
        for post in posts_para_processar:
            analise = await extrair_seguro(post, modelo_nome, str(post.get('id')))
            if analise:
                post['analise_ia'] = analise
                posts_processados.append(post)
            # Pausa entre posts
            await asyncio.sleep(2.0)
    
    if posts_processados:
        dados_modelo['posts'] = posts_processados
        return dados_modelo, arq_path.name
    
    return None, None

async def workflow_seguro():
    # Inicia monitor de temperatura em background
    monitor_task = asyncio.create_task(monitorar_temperatura())
    
    arquivos = list(DIR_ENTRADA.glob("*.json"))
    print(f"🛡️ LLAMA 3.2 - MODO SEGURO COM MONITORAMENTO TÉRMICO")
    print(f"📁 {len(arquivos)} arquivos")
    print(f"⚡ Concorrência: {MAX_CONCURRENT} (ultra-conservadora)")
    print(f"🌡️ Limite: {MAX_TEMP}°C | Cooldown: {COOLDOWN_TEMP}°C")
    
    temp = get_gpu_temperature()
    print(f"🌡️ Temperatura inicial da GPU: {temp}°C")
    
    checkpoints = list(DIR_CHECKPOINTS.glob("*.json"))
    print(f"💾 Checkpoints: {len(checkpoints)}")
    
    # Remove corrompidos
    corrompidos = 0
    for cp in checkpoints:
        valido, _ = verificar_checkpoint_valido(cp)
        if not valido:
            corrompidos += 1
            cp.unlink()
    if corrompidos:
        print(f"🗑️ {corrompidos} corrompidos removidos")
    
    for arq_path in async_tqdm(arquivos, desc="Modelos"):
        dados, nome = await processar_modelo_seguro(arq_path)
        if dados:
            output_path = DIR_SAIDA_FINAL / f"NER_{nome}"
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(dados, f, indent=2, ensure_ascii=False)
    
    monitor_task.cancel()
    
    print(f"\n📊 RELATÓRIO FINAL:")
    print(f"   ✅ Cache: {stats['checkpoints_validos']}")
    print(f"   🆕 Processados: {stats['processados_agora']}")
    print(f"   🌡️ Pausas por temperatura: {stats['pausas_temperatura']}")
    print(f"   ❌ Falhas: {stats['falhas']}")
    print(f"\n✅ COMPLETO! Dados em: {DIR_SAIDA_FINAL}")

PROMPT_LLAMA_EXTRACTION = """[INST] You are a hardware diagnostic extraction system. Extract technical problem and solutions from this forum post.

CANONICAL MODEL: {modelo_nome}
POST DATE: {post_date}

TITLE: {titulo}
CONTENT: {corpo}
COMMENTS: {comentarios}

Return ONLY valid JSON with these exact fields:
{{
  "summary": "{modelo_nome}, [problem description] - [key symptoms] - [affected components]",
  "intent": "Technical Specifications|Troubleshooting|Upgrade Advice|Compatibility|Warranty|Performance",
  "detected_fault": "specific technical fault or 'None'",
  "suggested_solution": ["solution step 1", "solution step 2", "solution step 3"],
  "technical_severity": "Low|Medium|High|Critical",
  "discussion_timeline": "{post_date} to {post_date}"
}}

CRITICAL FORMAT FOR "suggested_solution":
- MUST be an ARRAY of strings, NOT a single string
- Each solution step should be a concise, actionable instruction
- Order by: software fixes first, then hardware fixes, then replacement
- Maximum 4 solution steps

EXAMPLES OF CORRECT "suggested_solution":
✓ ["Update NVIDIA drivers to latest version", "Clean install drivers using DDU", "If issue persists, RMA the GPU"]
✓ ["Clean fans and heatsink with compressed air", "Repaste CPU with PTM7950", "Undervolt CPU by -50mV", "Limit turbo boost to 3.5GHz"]
✓ ["Replace display cable (inexpensive fix)", "If flickering continues, replace LCD panel"]

EXAMPLES OF INCORRECT "suggested_solution" (DO NOT DO THIS):
✗ "Clean fans and repaste CPU"  <- NOT AN ARRAY!
✗ ["Check and clean fans, apply new thermal paste"]  <- TOO MANY ACTIONS IN ONE STRING!

CRITICAL FORMAT FOR "summary":
You MUST follow this exact structure:
"{modelo_nome}, [problem description] - [key symptoms] - [affected components]"

EXAMPLE COMPLETE OUTPUT:
{{
  "summary": "Acer Predator Helios Neo 16 RTX 4050, CPU reaches 100°C during Cinebench R23 - thermal throttling despite 40W undervolt - cooling system, CPU",
  "intent": "Troubleshooting",
  "detected_fault": "Thermal throttling due to inadequate cooling",
  "suggested_solution": ["Clean cooling fans and heatsink", "Repaste CPU and GPU with PTM7950", "Undervolt CPU by -50mV using ThrottleStop", "Use cooling pad during intensive tasks"],
  "technical_severity": "Medium",
  "discussion_timeline": "2025-08-18 to 2025-08-18"
}}

Be concise. Extract only solutions mentioned in the post or comments. [/INST]"""

def reparar_json_malformado(content: str) -> dict:
    import re
    match = re.search(r'\{.*\}', content, re.DOTALL)
    if not match:
        raise ValueError("JSON not found")
    json_str = match.group(0)
    if not json_str.endswith('}'):
        json_str += '}' * (json_str.count('{') - json_str.count('}'))
    return json.loads(json_str)

if __name__ == "__main__":
    try:
        asyncio.run(workflow_seguro())
    except KeyboardInterrupt:
        print(f"\n⚠️ Interrompido. Progresso salvo em checkpoints.")
        print(f"   Processados: {stats['processados_agora']}")