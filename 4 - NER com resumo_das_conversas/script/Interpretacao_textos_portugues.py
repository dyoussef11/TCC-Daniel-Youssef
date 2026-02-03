import sys
import json
import re
from pathlib import Path
from openai import OpenAI

# --- 1. CONFIGURAÇÕES E CAMINHOS ---
caminho_script = Path(__file__).resolve().parent
caminho_raiz_projeto = caminho_script.parent.parent 
sys.path.append(str(caminho_raiz_projeto))

try:
    from config import DIRETORIO_DADOS_RESUMO_CONVERSAS, DIRETORIO_DADOS_PRE_PROCESSAMENTO
except ImportError:
    print("Aviso: Módulos de configuração não encontrados. Usando caminhos locais.")
    DIRETORIO_DADOS_PRE_PROCESSAMENTO = caminho_script / 'dados_saida'
    DIRETORIO_DADOS_RESUMO_CONVERSAS = caminho_script / 'dados_saida'

CAMINHO_ENTRADA_JSON = DIRETORIO_DADOS_PRE_PROCESSAMENTO / 'reddit_dados_limpos_enriquecidos.json'
CAMINHO_SAIDA_JSON = DIRETORIO_DADOS_RESUMO_CONVERSAS / 'reddit_dados_com_resumo_llama_aprimorado_portugues.json'

# --- 2. FILTROS (BLACKLIST & WHITELIST) ---

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
    "cpu", "processor", "processador", "silicon", "core", "clock", "overclock", "undervolt",
    "gpu", "graphics", "grafica", "vram", "video card", "placa de video", "placa gráfica",
    "motherboard", "mobo", "mainboard", "placa mae", "placa mãe", "logic board", "pcb",
    "ram", "memory", "memoria", "dimm", "sodimm", "stick", "pente", "xmp", "docp", "dual channel",
    "psu", "power supply", "fonte", "voltage", "voltagem", "wattage", "watts",
    "ssd", "hdd", "hard drive", "disco rigido", "disco rígido", "storage", "armazenamento",
    "nvme", "m.2", "sata", "pcie", "boot drive", "partition", "partição", "format", "formatar",
    "smart status", "corrupt", "corrompido", "read/write", "leitura/escrita",
    "screen", "tela", "display", "monitor", "panel", "painel", "lcd", "led", "oled", "ips", "tn", "va",
    "resolution", "resolução", "pixels", "dead pixel", "stuck pixel", "pixel morto",
    "backlight", "backlight bleed", "vazamento de luz", "brightness", "brilho", "dim", "escurecendo",
    "flicker", "flickering", "piscando", "artifact", "artifacting", "artefatos", "ghosting",
    "hz", "refresh rate", "taxa de atualização", "fps", "frame rate", "bezel", "borda",
    "battery", "bateria", "charge", "charging", "charger", "carregador", "carregando",
    "ac adapter", "power brick", "fonte de alimentação", "plugged in", "conectado",
    "drain", "draining", "descarregando", "viciada", "health", "wear level", "ciclos", "cycles",
    "not turning on", "ligar", "boot", "post", "power on",
    "fan", "cooler", "ventoinha", "ventilador", "spin", "girando", "noise", "barulho", "loud", "alto",
    "whine", "coil whine", "grinding", "zunido", "click", "clicking", "estalo",
    "heat", "overheat", "overheating", "aquecendo", "superaquecimento", "quente", "hot",
    "temp", "temperature", "temperatura", "thermal", "thermal paste", "pasta termica", "pasta térmica",
    "throttle", "throttling", "thermal throttling", "engasgando", "airflow", "fluxo de ar",
    "heatsink", "dissipador", "liquid metal", "metal liquido",
    "keyboard", "teclado", "key", "tecla", "switch", "numpad", "backlit", "retroiluminado",
    "touchpad", "trackpad", "mouse", "clickpad", "cursor", "seta",
    "usb", "usb-c", "type-c", "thunderbolt", "hdmi", "displayport", "jack", "port", "porta", "slot",
    "hinge", "hinges", "dobradiça", "chassis", "carcaça", "case", "gabinete", "screw", "parafuso",
    "webcam", "camera", "microphone", "microfone", "audio", "sound", "som", "speaker", "alto falante",
    "bios", "uefi", "firmware", "driver", "update", "atualização", "manager", "gerenciador",
    "windows", "linux", "ubuntu", "install", "instalar", "clean install", "instalação limpa",
    "bsod", "blue screen", "tela azul", "black screen", "tela preta", "crash", "crashing", "crahsou",
    "freeze", "freezing", "congelando", "travando", "stutter", "lag", "lento", "slow",
    "error", "erro", "code", "codigo", "bug", "glitch", "failure", "falha", "broken", "quebrado",
    "fix", "repair", "conserto", "upgrade", "melhoria", "replace", "trocar", "substituir"
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
    componentes_encontrados = []
    for tipo, pattern in PADROES_HARDWARE.items():
        matches = re.finditer(pattern, texto_lower)
        uniques = set(m.group(0).strip() for m in matches)
        if uniques:
            componentes_encontrados.append(f"{tipo.upper()}: {', '.join(uniques)}")
    
    if componentes_encontrados:
        return " | ".join(componentes_encontrados)
    return None

def eh_relevante_para_analise(titulo, corpo, subreddit, hardware_detectado):
    texto_completo = (str(titulo) + " " + str(corpo) + " " + str(subreddit)).lower()
    
    # 1. Blacklist (Eliminação)
    for termo_ignorado in PALAVRAS_IGNORADAS:
        if termo_ignorado in texto_completo:
            return False

    # 2. Regex (Confirmação Forte)
    if hardware_detectado:
        return True

    # 3. Whitelist (Confirmação Padrão)
    for palavra in PALAVRAS_CHAVE_TECH:
        if palavra in texto_completo:
            return True
            
    return False

# --- 3. CONFIGURAÇÃO IA ---
client = OpenAI(base_url='http://localhost:11434/v1', api_key='ollama')
MODELO_OLLAMA = "llama3.2:latest"

def analisar_com_ollama(titulo, corpo, comentarios, hardware_detectado):
    texto_titulo = titulo if titulo else ""
    texto_corpo = corpo[:1200] if corpo else "" # Aumentei levemente o contexto
    
    texto_comentarios = ""
    if comentarios:
        texto_comentarios = "COMENTARIOS RELEVANTES DA COMUNIDADE (podem conter specs):\n"
        for c in comentarios[:3]:
            conteudo = c.get('conteudo_limpo', c.get('conteudo', ''))
            texto_comentarios += f"- {conteudo[:300]}\n"

    # Passamos o que o seu Regex já achou para ajudar a IA a não alucinar
    hardware_str = hardware_detectado if hardware_detectado else "Nenhum detectado via Regex."

    texto_entrada_final = f"""
    [REGEX HINTS - USE COM CAUTELA]: {hardware_str}
    
    TITULO: {texto_titulo}
    TEXTO DO POST: {texto_corpo}
    {texto_comentarios}
    """

    # --- PROMPT REFORÇADO E ESTRITO ---
    prompt_sistema = """
    Você é um extrator de dados técnicos JSON estrito.
    Sua missão é identificar componentes de hardware e categorizar o post.

    ### REGRAS DE OURO PARA COMPONENTES (SIGA RIGOROSAMENTE):
    1. VALOR ÚNICO: Nunca retorne listas, alternativas ("ou") ou incertezas. Se houver "GTX 1060 ou 1050", escolha a primeira citada ou a mais provável.
    2. SEJA ESPECÍFICO: "Nvidia GPU" -> null. "Intel Core" -> null. Precisa ter o modelo (ex: "RTX 3060", "i5-12400").
    3. RAM LIMPA: Apenas Capacidade + Tipo. Ex: "16GB DDR4". Nunca escreva "memória ram", "2x8gb sticks". Apenas "16GB".
    4. STORAGE LIMPO: Apenas Capacidade + Tipo. Ex: "1TB NVMe", "500GB SSD". Se houver vários, pegue apenas o principal (onde está o OS).
    5. NULL SE GENÉRICO: Se o texto diz apenas "meu processador", retorne null. Não invente.

    Retorne APENAS um JSON válido com este schema:
    {
        "resumo": "Resumo de 1 frase (pt-BR).",
        "intencao": "Uma destas: 'Problema Técnico', 'Compra', 'Upgrade', 'Discussão', 'Outro'.",
        "componentes": {
            "CPU": "Modelo exato (Ex: 'Ryzen 5 5600', 'i7-13700K') ou null",
            "GPU": "Modelo exato (Ex: 'RTX 4060', 'RX 6600') ou null",
            "RAM": "Apenas capacidade/tipo (Ex: '16GB DDR4', '8GB') ou null",
            "MOBO": "Modelo curto (Ex: 'B550M Aorus', 'Z790') ou null",
            "FONTE": "Modelo ou potência (Ex: '650W Corsair', '750W') ou null",
            "DISK": "Apenas capacidade/tipo (Ex: '1TB SSD', '2TB HDD') ou null",
            "MODELO": "Modelo do notebook se aplicável (Ex: 'Dell G15', 'Lenovo Legion') ou null"
        },
        "solucao_sugerida": "Breve solução sugerida ou null se não houver problema."
    }
    """

    try:
        response = client.chat.completions.create(
            model=MODELO_OLLAMA,
            messages=[
                {"role": "system", "content": prompt_sistema},
                {"role": "user", "content": texto_entrada_final}
            ],
            response_format={"type": "json_object"}, 
            temperature=0.0 # ZERO para máxima determinística e menos criatividade
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"X - Erro IA: {e}")
        return None


# --- 4. EXECUÇÃO PRINCIPAL (DUAS FASES) ---

print(f"Carregando: {CAMINHO_ENTRADA_JSON}")
with open(CAMINHO_ENTRADA_JSON, 'r', encoding='utf-8') as f:
    dados = json.load(f)

# === FASE 1: FILTRAGEM E SELEÇÃO ===
print("\n>>> FASE 1: Varrendo base de dados e aplicando filtros...")

fila_processamento = [] # Lista temporária para guardar o que deve ir pra IA
total_posts_originais = 0
posts_ignorados = 0

for item in dados:
    if 'posts' in item:
        total_posts_originais += len(item['posts'])
        posts_validos_deste_item = []
        
        for post in item['posts']:
            titulo = post.get('titulo_limpo', post.get('titulo', ''))
            corpo = post.get('conteudo_texto_limpo', post.get('conteudo_texto', ''))
            subreddit = post.get('subreddit', '')
            
            # Pré-computa o regex
            hw_info = extrair_hardware_regex(f"{titulo} {corpo}")
            
            # Aplica a lógica de decisão
            if eh_relevante_para_analise(titulo, corpo, subreddit, hw_info):
                # Guarda metadados úteis para não recalcular depois
                post['_meta_temp_hw'] = hw_info 
                
                # Adiciona na lista do item (para salvar no JSON final)
                posts_validos_deste_item.append(post)
                
                # Adiciona na fila global de processamento (para a Fase 2)
                fila_processamento.append(post)
            else:
                posts_ignorados += 1
        
        # Atualiza o item original, removendo os ignorados
        item['posts'] = posts_validos_deste_item

print(f"--- Resumo Fase 1 ---")
print(f"Total Original: {total_posts_originais}")
print(f"Ignorados (Lixo/Blacklist): {posts_ignorados}")
print(f"Selecionados para IA: {len(fila_processamento)}")
print("---------------------")

if len(fila_processamento) == 0:
    print("Nenhum post relevante encontrado. Encerrando.")
    sys.exit()

# === FASE 2: PROCESSAMENTO COM IA ===
print(f"\n>>> FASE 2: Iniciando IA ({MODELO_OLLAMA}) para {len(fila_processamento)} posts...")

try:
    for i, post in enumerate(fila_processamento):
        titulo = post.get('titulo_limpo', post.get('titulo', ''))
        corpo = post.get('conteudo_texto_limpo', '')
        comentarios = post.get('comentarios', [])
        hw_info = post.pop('_meta_temp_hw', None) # Recupera e limpa o dado temporário
        
        print(f"[{i+1}/{len(fila_processamento)}] Analisando: {titulo[:50]}...")
        
        resultado = analisar_com_ollama(titulo, corpo, comentarios, hw_info)
        
        if resultado:
            post['analise_ia'] = resultado
            # print(f"   -> Resumo: {resultado.get('resumo')}") # Descomente para ver detalhes
        else:
            post['analise_ia'] = {"erro": "Falha na resposta da IA"}

except KeyboardInterrupt:
    print("\n! Interrompido pelo usuário. Salvando progresso parcial...")

# === SALVAMENTO ===
print(f"\nSalvando arquivo final em: {CAMINHO_SAIDA_JSON}")
CAMINHO_SAIDA_JSON.parent.mkdir(parents=True, exist_ok=True)
with open(CAMINHO_SAIDA_JSON, 'w', encoding='utf-8') as f:
    # A variável 'dados' já foi atualizada pois os dicionários em 'fila_processamento'
    # eram referências aos objetos dentro de 'dados'.
    json.dump(dados, f, ensure_ascii=False, indent=4)

print("Concluído.")