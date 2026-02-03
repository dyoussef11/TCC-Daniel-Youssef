import sys
import json
import re
import asyncio
from pathlib import Path
from openai import AsyncOpenAI  # Importante: Cliente Assíncrono

# --- 1. CONFIGURAÇÕES E CAMINHOS ---
caminho_script = Path(__file__).resolve().parent
caminho_raiz_projeto = caminho_script.parent.parent 
sys.path.append(str(caminho_raiz_projeto))

try:
    from config import DIRETORIO_DADOS_RESUMO_CONVERSAS, DIRETORIO_DADOS_PRE_PROCESSAMENTO
except ImportError:
    DIRETORIO_DADOS_PRE_PROCESSAMENTO = caminho_script / 'dados_saida'
    DIRETORIO_DADOS_RESUMO_CONVERSAS = caminho_script / 'dados_saida'

CAMINHO_ENTRADA_JSON = DIRETORIO_DADOS_PRE_PROCESSAMENTO / 'reddit_dados_limpos_enriquecidos.json'
# Nome do arquivo de saída em inglês conforme discutido
CAMINHO_SAIDA_JSON = DIRETORIO_DADOS_RESUMO_CONVERSAS / 'reddit_dados_com_resumo_llama_aprimorado_ingles.json'

# --- 2. CONFIGURAÇÃO IA E CONCORRÊNCIA ---
client = AsyncOpenAI(base_url='http://localhost:11434/v1', api_key='ollama')
MODELO_OLLAMA = "llama3.2:latest"

# Semaphore em 2 para proteger a VRAM da placa de vídeo
sem = asyncio.Semaphore(2)

# --- 3. FILTROS (BLACKLIST & WHITELIST) ---

PALAVRAS_IGNORADAS = {
    "crypto", "cripto", "bitcoin", "btc", "eth", "ethereum", "wallet", "blockchain",
    "stock", "market", "invest", "investing", "investimento", "dividend", "yield",
    "share", "ação", "ações", "b3", "ibovespa", "nasdaq", "dow jones", "bull", "bear",
    "trading", "trader", "short", "long", "coin", "token", "nft", "lucro", "prejuízo",
    "wallstreet", "bets", "finance", "finança", "bank", "banco", "tax", "imposto",
    "selling", "vendo", "sale", "venda", "shipping", "frete",
    "invoice", "nota fiscal", "coupon", "cupom", "discount", "desconto",
    "politics", "política", "religion", "religião", "dating", "namoro", "relationship",
    "aita", "desabafo", "off-topic", "futebol", "soccer"
}

PALAVRAS_CHAVE_TECH = {
    "cpu", "processor", "processador", "gpu", "graphics", "vram", "video card",
    "motherboard", "ram", "memory", "ssd", "hdd", "storage", "nvme", "m.2",
    "screen", "tela", "display", "resolution", "battery", "bateria", "charge",
    "fan", "cooler", "heat", "overheat", "temp", "thermal", "throttle",
    "keyboard", "touchpad", "bios", "update", "bsod", "crash", "lag", "fix"
}

PADROES_HARDWARE = {
    "gpu": r"\b((geforce\s*)?(rtx|gtx|gt|mx|quadro|titan)\s*\d{3,4}[a-z0-9]*([\s-]*(ti|super|max-q|maxq|max q|mobile|oc|ada|lhr|ultra))?|(amd\s*)?(radeon\s*(tm|™)?\s*)?(rx|r9|r7|r5|hd|vega)\s*(\d{3,4}|[a-z0-9]+)([\s-]*(xt|xtx|gre|m|xt-m|pro|xtr))?|(intel\s*)?(arc)\s*[ab]\d{3,4}[a-z]*|iris\s*xe|uhd\s*graphics|radeon\s*graphics)\b",
    "cpu": r"(?i)\b((?:intel\s*)?core(?:\s*ultra)?\s*(?:i[3579]|[3579])[\s-]*\d{3,5}(?:hx|hk|hl|he|ue|ul|kf|ks|g[1-7]|[kfsthpuye])?|(?:intel\s*)?(?:pentium|celeron|atom|xeon)[\s-]*[a-z0-9]+|(?:amd\s*)?(?:ryzen(?:\s*(?:threadripper|ai))?\s*[3579]|athlon|fx|a[468]|a1[02])[\s-]*\d{3,4}[a-z]*)\b",
    "storage": r"\b((\d{1,4}\s*(gb|tb)\s*)?((samsung|wd|western\s*digital|crucial|kingston|sandisk|seagate|toshiba|sk\s*hynix|hynix|corsair|sabrent|adata|xpg|pny|lexar|hp|intel|teamgroup|patriot|gigabyte|hgst|hitachi)|(firecuda|barracuda|ironwolf|skyhawk|exos|blue|black|green|red|purple|gold|ultrastar|p300|x300|n300|l200|evo|qvo|pro|plus|mx500|bx500|p3|p5|nv2|kc3000|fury|legend|gammix|sn\d{3,4}))?\s*([a-z0-9-]+\s*)?(ssd|nvme|m\.2|sata|hdd|hard\s*drive|disco\s*r[ií]gido|hd|sshd|sdd|7200\s*rpm|5400\s*rpm)(\s*\d{1,4}\s*(gb|tb))?)\b",
    "ram": r"\b(((128|64|32|16|8|4|2)\s*gb\s*(x\d|2x|1x)?\s*)?((corsair|kingston|crucial|g\.?skill|samsung|sk\s*hynix|hynix|adata|teamgroup|patriot|hyperx|micron|pny|transcend|geil|mushkin|t-force|klevv)|(vengeance|fury|beast|impact|ballistix|trident|ripjaws|viper|dominator|elite|value\s*ram|aorus|predator|vulcan))?\s*([a-z0-9-]+\s*)?(ddr[2-5]|lpddr[3-5]x?|sodimm|so-dimm|dimm|udimm|ram|mem[oó]ria)(\s*\d{3,5}\s*(mhz|mt/s)?)?(\s*cl\d{1,2})?(\s*(128|64|32|16|8|4|2)\s*gb)?)\b",
    "screen": r"\b(\d{2,3}(\.\d)?[\"”]\s*|120hz|144hz|165hz|240hz|300hz|360hz|480hz|60hz|ips|tn|va|wva|pls|oled|amoled|miniled|mini-led|retina|4k|uhd|qhd|wqhd|fhd|hd\+|full\s*hd|1080p|1440p|2160p|768p|1366x768|1920x1080)\b",
    "model": r"\b(dell\s*g[357]|legion|alienware|nitro\s*5|tuf|rog|pavilion|7588)\b"
}

def extrair_hardware_regex(texto_completo):
    if not texto_completo: return None
    texto_lower = texto_completo.lower()
    encontrados = []
    for tipo, pattern in PADROES_HARDWARE.items():
        matches = re.finditer(pattern, texto_lower)
        uniques = set(m.group(0).strip() for m in matches)
        if uniques: encontrados.append(f"{tipo.upper()}: {', '.join(uniques)}")
    return " | ".join(encontrados) if encontrados else None

def eh_relevante_para_analise(titulo, corpo, subreddit, hardware_detectado):
    texto_completo = (str(titulo) + " " + str(corpo) + " " + str(subreddit)).lower()
    for t in PALAVRAS_IGNORADAS:
        if t in texto_completo: return False
    if hardware_detectado: return True
    return any(p in texto_completo for p in PALAVRAS_CHAVE_TECH)

# --- 4. FUNÇÃO ASSÍNCRONA DE IA ---

async def analisar_com_ollama_async(post, hardware_detectado):
    """
    Versão assíncrona da extração técnica via Ollama.
    """
    titulo = post.get('titulo_limpo', post.get('titulo', ''))
    corpo = post.get('conteudo_texto_limpo', post.get('conteudo_texto', ''))[:1200]
    
    comentarios = post.get('comentarios', [])
    texto_comentarios = ""
    if comentarios:
        texto_comentarios = "RELEVANT COMMUNITY COMMENTS:\n"
        for c in comentarios[:3]:
            conteudo = c.get('conteudo_limpo', c.get('conteudo', ''))
            texto_comentarios += f"- {conteudo[:300]}\n"

    hardware_str = hardware_detectado if hardware_detectado else "None detected via Regex."

    prompt_sistema = """
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
        "components": {
            "CPU": "Model or null", "GPU": "Model or null", "RAM": "Capacity/Type or null",
            "MOBO": "Model or null", "POWER": "Model or null", "DISK": "Capacity/Type or null",
            "MODEL": "Laptop model or null"
        },
        "suggested_solution": "Brief suggested solution in English or null."
    }
    """

    async with sem:
        try:
            response = await client.chat.completions.create(
                model=MODELO_OLLAMA,
                messages=[
                    {"role": "system", "content": prompt_sistema},
                    {"role": "user", "content": f"HINTS: {hardware_str}\nTITLE: {titulo}\nCONTENT: {corpo}\n{texto_comentarios}"}
                ],
                response_format={"type": "json_object"},
                temperature=0.0
            )
            post['analise_ia'] = json.loads(response.choices[0].message.content)
            print(f"✓ Processed: {titulo[:40]}...")
        except Exception as e:
            print(f"X Error: {e}")
            post['analise_ia'] = {"error": "IA Processing Failed"}

async def processar_fila_ia(fila):
    print(f"\n>>> FASE 2: Iniciando IA para {len(fila)} posts...")
    tarefas = [analisar_com_ollama_async(post, post.pop('_meta_temp_hw', None)) for post in fila]
    await asyncio.gather(*tarefas)

# --- 5. EXECUÇÃO PRINCIPAL ---

def main():
    print(f"Lendo: {CAMINHO_ENTRADA_JSON}")
    with open(CAMINHO_ENTRADA_JSON, 'r', encoding='utf-8') as f:
        dados = json.load(f)

    # FASE 1: FILTRAGEM
    fila_processamento = []
    print("\n>>> FASE 1: Aplicando filtros e Regex...")
    
    for item in dados:
        if 'posts' in item:
            posts_validos = []
            for post in item['posts']:
                t = post.get('titulo_limpo', post.get('titulo', ''))
                c = post.get('conteudo_texto_limpo', post.get('conteudo_texto', ''))
                hw = extrair_hardware_regex(f"{t} {c}")
                
                if eh_relevante_para_analise(t, c, post.get('subreddit',''), hw):
                    post['_meta_temp_hw'] = hw
                    posts_validos.append(post)
                    fila_processamento.append(post)
            item['posts'] = posts_validos

    print(f"Fase 1 completa. Selecionados: {len(fila_processamento)}")

    if not fila_processamento:
        print("Nenhum post relevante encontrado.")
        return

    # FASE 2: IA ASSÍNCRONA
    asyncio.run(processar_fila_ia(fila_processamento))

    # SALVAMENTO
    print(f"\nSalvando em: {CAMINHO_SAIDA_JSON}")
    CAMINHO_SAIDA_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(CAMINHO_SAIDA_JSON, 'w', encoding='utf-8') as f:
        json.dump(dados, f, ensure_ascii=False, indent=4)
    print("Processo concluído.")

if __name__ == "__main__":
    main()