import sys
import json
import re
import spacy
from collections import Counter
from pathlib import Path

# --- 1. CONFIGURAÇÕES E CAMINHOS ---
caminho_script = Path(__file__).resolve().parent
caminho_raiz_projeto = caminho_script.parent.parent 
sys.path.append(str(caminho_raiz_projeto))

try:
    from config import DIRETORIO_DADOS_RESUMO_CONVERSAS, DIRETORIO_DADOS_PRE_PROCESSAMENTO, DIRETORIO_DADOS_IDENTIFICACAO_ENTIDADES
except ImportError:
    print("Aviso: Módulos de configuração não encontrados. Usando caminhos locais.")
    DIRETORIO_DADOS_EXTRACAO_QA = caminho_script / 'dados_saida'
    DIRETORIO_DADOS_PRE_PROCESSAMENTO = caminho_script / 'dados_saida'
    DIRETORIO_DADOS_RESUMO_CONVERSAS = caminho_script / 'dados_saida' # Ajuste aqui para fallback funcionar

# Entra o arquivo limpo/enriquecido, sai o arquivo com tópicos identificados
CAMINHO_ENTRADA_JSON = DIRETORIO_DADOS_PRE_PROCESSAMENTO / 'reddit_dados_limpos_enriquecidos.json'
CAMINHO_SAIDA_JSON = DIRETORIO_DADOS_RESUMO_CONVERSAS / 'reddit_dados_com_topicos.json'

# --- 2. CARREGAR MODELO E DEFINIR TERMOS ---
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    print("Modelo Spacy 'en_core_web_sm' não encontrado. Instale-o primeiro.")
    sys.exit()

# Dicionário de Termos
TERMOS = {
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
    'solucoes': [
        'replace', 'replacement', 'swap', 'change', 'install', 'installation',
        'clean', 'cleaning', 'dust', 'dusting', 'compressed air',
        'repaste', 'repasting', 'thermal pad', 'cooling pad', 'cooler',
        'open', 'screw', 'tighten', 'solder', 'fix', 'repair',
        'update', 'updating', 'upgrade', 'downgrade', 'flash', 'reinstall',
        'format', 'reset', 'restore', 'factory reset',
        'undervolt', 'undervolting', 'underclock', 'overclock', 'throttle stop',
        'disable', 'enable', 'turn off', 'turn on', 'tweak', 'optimize',
        'warranty', 'rma', 'service', 'support', 'technician', 'tech',
        'return', 'refund', 'send back', 'contact', 'call'
    ]
}

REGEX_MODELOS = [
    r'\b(g[357])\b', r'\b(\d{4})\b', r'\b(xps\s?\d{2})\b', r'\b(inspiron)\b', 
    r'\b(latitude)\b', r'\b(precision)\b', r'\b(vostro)\b', r'\b(alienware)\b', 
    r'\b(nitro\s?5)\b', r'\b(predator)\b', r'\b(legion)\b'
]

# --- 3. FUNÇÕES DE ANÁLISE ---

def extrair_termos_simples(texto):
    """Extrai termos baseados apenas na lista (mais rápido para contagem)"""
    if not isinstance(texto, str): return []
    
    doc = nlp(texto.lower())
    encontrados = []
    
    # 1. Busca por termos do dicionário (via Spacy Lemmas)
    for token in doc:
        lemma = token.lemma_
        if lemma in TERMOS['hardware']: encontrados.append(('hardware', lemma))
        elif lemma in TERMOS['problemas']: encontrados.append(('problema', lemma))
        elif lemma in TERMOS['solucoes']: encontrados.append(('solucao', lemma))
    
    # 2. Busca modelos via Regex (CORREÇÃO DO ERRO)
    # Precisamos iterar sobre a lista de regex, um por um
    for padrao in REGEX_MODELOS:
        matches = re.findall(padrao, texto.lower())
        for match in matches:
            # Se o regex tiver grupos e retornar tupla, pega o primeiro item
            modelo = match if isinstance(match, str) else match[0]
            encontrados.append(('modelo', modelo))
        
    return encontrados

def gerar_resumo_topico(post):
    """
    Analisa o post e comentários para determinar o tema central.
    Usa sistema de pesos: Título (3x), Corpo (2x), Comentários (1x).
    """
    contador_geral = Counter()
    
    # 1. Analisa Título (Peso 3)
    termos_titulo = extrair_termos_simples(post.get('titulo', ''))
    for categoria, termo in termos_titulo:
        contador_geral[(categoria, termo)] += 3
        
    # 2. Analisa Corpo (Peso 2)
    termos_corpo = extrair_termos_simples(post.get('conteudo_texto', ''))
    for categoria, termo in termos_corpo:
        contador_geral[(categoria, termo)] += 2
        
    # 3. Analisa Comentários (Peso 1 - Contexto coletivo)
    if 'comentarios' in post:
        for comentario in post['comentarios']:
            # Usa conteudo_limpo se existir, senão conteudo normal
            texto = comentario.get('conteudo_limpo', comentario.get('conteudo', ''))
            termos_coments = extrair_termos_simples(texto)
            for categoria, termo in termos_coments:
                contador_geral[(categoria, termo)] += 1

    # --- SÍNTESE DO TÓPICO ---
    top_problema = "General Discussion"
    top_hardware = "Laptop"
    top_solucao = None
    
    # Filtra contadores por categoria
    probs = [k[1] for k in contador_geral if k[0] == 'problema']
    hards = [k[1] for k in contador_geral if k[0] == 'hardware']
    sols = [k[1] for k in contador_geral if k[0] == 'solucao']
    
    if probs:
        top_problema = Counter({k[1]: v for k, v in contador_geral.items() if k[0] == 'problema'}).most_common(1)[0][0]
    
    if hards:
        top_hardware = Counter({k[1]: v for k, v in contador_geral.items() if k[0] == 'hardware'}).most_common(1)[0][0]
        
    if sols:
        top_solucao = Counter({k[1]: v for k, v in contador_geral.items() if k[0] == 'solucao'}).most_common(1)[0][0]

    # Cria a string legível
    resumo = f"Issue with {top_hardware.upper()} ({top_problema})"
    
    tags = {
        "componente_foco": top_hardware,
        "problema_principal": top_problema,
        "solucao_sugerida": top_solucao
    }
    
    return resumo, tags

# --- 4. EXECUÇÃO PRINCIPAL ---

print(f"Lendo arquivo: {CAMINHO_ENTRADA_JSON}")
with open(CAMINHO_ENTRADA_JSON, 'r', encoding='utf-8') as f:
    dados = json.load(f)

print("Gerando resumos dos tópicos...")
contagem = 0

for item in dados:
    if 'posts' in item:
        for post in item['posts']:
            resumo_texto, tags_dict = gerar_resumo_topico(post)
            
            post['resumo_conversa'] = resumo_texto
            post['tags_topico'] = tags_dict
            
            contagem += 1

# --- 5. SALVAMENTO ---
CAMINHO_SAIDA_JSON.parent.mkdir(parents=True, exist_ok=True)
with open(CAMINHO_SAIDA_JSON, 'w', encoding='utf-8') as f:
    json.dump(dados, f, ensure_ascii=False, indent=4)

print(f"Processamento concluído. {contagem} conversas analisadas.")
print(f"Arquivo salvo em: {CAMINHO_SAIDA_JSON}")

# --- EXEMPLO VISUAL ---
if dados and 'posts' in dados[0] and len(dados[0]['posts']) > 0:
    print("\n--- Exemplo de Resultado ---")
    p = dados[0]['posts'][0]
    print(f"Título: {p.get('titulo')}")
    print(f"Resumo Gerado: {p.get('resumo_conversa')}")
    print(f"Tags: {p.get('tags_topico')}")