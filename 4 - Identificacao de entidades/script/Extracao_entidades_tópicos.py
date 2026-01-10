import sys
import json
import spacy
import re
from pathlib import Path

# --- 1. CONFIGURAÇÕES E CAMINHOS ---
caminho_script = Path(__file__).resolve().parent
caminho_raiz_projeto = caminho_script.parent.parent 
sys.path.append(str(caminho_raiz_projeto))

try:
    from config import DIRETORIO_DADOS_PRE_PROCESSAMENTO, DIRETORIO_DADOS_IDENTIFICACAO_ENTIDADES
except ImportError:
    print("Aviso: Módulos de configuração não encontrados. Usando caminhos locais.")
    DIRETORIO_DADOS_PRE_PROCESSAMENTO = caminho_script / 'dados_saida'
    DIRETORIO_DADOS_IDENTIFICACAO_ENTIDADES = caminho_script / 'dados_saida'

CAMINHO_ENTRADA_JSON = DIRETORIO_DADOS_PRE_PROCESSAMENTO / 'reddit_dados_limpos_enriquecidos.json'
CAMINHO_SAIDA_JSON = DIRETORIO_DADOS_IDENTIFICACAO_ENTIDADES / 'reddit_dados_enriquecidos_com_entidades.json'

# --- 2. CARREGAR MODELO SPACY ---
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    print("ERRO: Modelo Spacy não encontrado. Execute: python -m spacy download en_core_web_sm")
    sys.exit()

# --- 3. DEFINIR DICIONÁRIOS E PADRÕES ---

TERMOS_TECNICOS = {
    'hardware': [
        'cpu', 'gpu', 'ram', 'memory', 'ssd', 'hdd', 'hard drive', 'fan', 'heatsink', 
        'motherboard', 'mobo', 'battery', 'charger', 'adapter', 'power supply', 'psu',
        'thermal paste', 'connector', 'cable', 'ribbon cable', 'port', 'jack',
        'screen', 'display', 'monitor', 'panel', 'ips', 'keyboard', 'key', 'trackpad', 
        'touchpad', 'mouse', 'webcam', 'camera', 'speaker', 'mic', 'microphone', 
        'chassis', 'hinge', 'bezel', 'case', 'vent',
        'bios', 'uefi', 'driver', 'firmware', 'windows', 'linux', 'ubuntu'
    ],
    'marcas': [
        'dell', 'lenovo', 'hp', 'asus', 'acer', 'apple', 'samsung', 'msi', 'toshiba', 
        'microsoft', 'alienware', 'razer', 'lg', 'gigabyte', 'sony',
        'intel', 'nvidia', 'amd', 'radeon', 'geforce', 'logitech', 'corsair'
    ],
    'problemas': [
        'overheat', 'overheating', 'hot', 'warm', 'temperature', 'thermal', 
        'throttle', 'throttling', 'lag', 'lagging', 'freeze', 'freezing', 'stutter', 
        'slow', 'fps drop', 'performance', 'bottleneck',
        'crash', 'crashing', 'bsod', 'blue screen', 'boot loop', 'shutdown', 'restart', 
        'dead', 'brick', 'bricked', 'fail', 'failure', 'error',
        'noise', 'noisy', 'loud', 'whine', 'coil whine', 'grinding', 'click',
        'broken', 'damage', 'damaged', 'crack', 'cracked', 'loose', 'stuck',
        'flicker', 'flickering', 'bleed', 'backlight bleed', 'dead pixel', 'artifact', 'glitch'
    ],
    # --- NOVA CATEGORIA: SOLUÇÕES ---
    'solucoes': [
        # Ações Físicas
        'replace', 'replacement', 'swap', 'change', 'install', 'installation',
        'clean', 'cleaning', 'dust', 'dusting', 'compressed air',
        'repaste', 'repasting', 'thermal pad', 'cooling pad', 'cooler',
        'open', 'screw', 'tighten', 'solder', 'fix', 'repair',
        
        # Ações de Software / Configuração
        'update', 'updating', 'upgrade', 'downgrade', 'flash', 'reinstall',
        'format', 'reset', 'restore', 'factory reset',
        'undervolt', 'undervolting', 'underclock', 'overclock', 'throttle stop',
        'disable', 'enable', 'turn off', 'turn on', 'tweak', 'optimize',
        
        # Administrativo
        'warranty', 'rma', 'service', 'support', 'technician', 'tech',
        'return', 'refund', 'send back', 'contact', 'call'
    ]
}

REGEX_MODELOS = [
    r'\b(g[357])\b', r'\b(\d{4})\b', r'\b(xps\s?\d{2})\b', r'\b(inspiron)\b', 
    r'\b(latitude)\b', r'\b(precision)\b', r'\b(vostro)\b', r'\b(alienware)\b', 
    r'\b(nitro\s?5)\b', r'\b(predator)\b', r'\b(legion)\b'
]

def extrair_entidades(texto):
    if not isinstance(texto, str) or not texto.strip():
        return None
    
    texto_lower = texto.lower()
    doc = nlp(texto_lower) 
    
    entidades_encontradas = {
        'hardware': set(),
        'marcas': set(),
        'problemas': set(),
        'modelos': set(),
        'solucoes': set(), # --- NOVA CHAVE ---
        'organizacoes_spacy': set()
    }
    
    # 1. Busca por Palavras-Chave (Lematização)
    for token in doc:
        lemma = token.lemma_ 
        
        if lemma in TERMOS_TECNICOS['hardware']:
            entidades_encontradas['hardware'].add(lemma)
        elif lemma in TERMOS_TECNICOS['marcas']:
            entidades_encontradas['marcas'].add(lemma)
        elif lemma in TERMOS_TECNICOS['problemas']:
            entidades_encontradas['problemas'].add(lemma)
        elif lemma in TERMOS_TECNICOS['solucoes']: # --- NOVA VERIFICAÇÃO ---
            entidades_encontradas['solucoes'].add(lemma)

    # 2. Busca por Modelos via Regex
    for padrao in REGEX_MODELOS:
        matches = re.findall(padrao, texto_lower)
        for match in matches:
            modelo = match if isinstance(match, str) else match[0]
            entidades_encontradas['modelos'].add(modelo)

    # 3. Busca por Entidades Nomeadas do Spacy
    doc_original = nlp(texto)
    for ent in doc_original.ents:
        if ent.label_ == "ORG": 
            if ent.text.lower() not in TERMOS_TECNICOS['marcas']:
                entidades_encontradas['organizacoes_spacy'].add(ent.text)
        elif ent.label_ == "PRODUCT":
            if ent.text.lower() not in entidades_encontradas['modelos']:
                 entidades_encontradas['hardware'].add(ent.text.lower())

    resultado = {k: list(v) for k, v in entidades_encontradas.items() if v}
    return resultado if resultado else None

# --- 4. PROCESSAMENTO DO JSON ---
print(f"Carregando dados de: {CAMINHO_ENTRADA_JSON}")
with open(CAMINHO_ENTRADA_JSON, 'r', encoding='utf-8') as f:
    dados = json.load(f)

print("Iniciando extração de entidades (Hardware, Marcas, Problemas, Soluções)...")
stats = {'posts': 0, 'comentarios': 0}

for item in dados:
    if 'posts' in item:
        for post in item['posts']:
            
            # Post
            texto_post = f"{post.get('titulo', '')} {post.get('conteudo_texto', '')}".strip()
            entidades_post = extrair_entidades(texto_post)
            if entidades_post:
                post['entidades_detectadas'] = entidades_post
            stats['posts'] += 1

            # Comentários
            if 'comentarios' in post:
                for comentario in post['comentarios']:
                    texto_comentario = comentario.get('conteudo_limpo', '')
                    if not texto_comentario:
                        texto_comentario = comentario.get('conteudo', '') # Fallback

                    entidades_comentario = extrair_entidades(texto_comentario)
                    if entidades_comentario:
                        comentario['entidades_detectadas'] = entidades_comentario
                    stats['comentarios'] += 1

# --- 5. SALVAMENTO ---
print(f"Processamento concluído.")
print(f"Posts analisados: {stats['posts']}")
print(f"Comentários analisados: {stats['comentarios']}")

CAMINHO_SAIDA_JSON.parent.mkdir(parents=True, exist_ok=True)
with open(CAMINHO_SAIDA_JSON, 'w', encoding='utf-8') as f:
    json.dump(dados, f, ensure_ascii=False, indent=4)

print(f"Arquivo salvo com sucesso em: {CAMINHO_SAIDA_JSON}")