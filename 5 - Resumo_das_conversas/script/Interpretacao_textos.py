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
CAMINHO_SAIDA_JSON = DIRETORIO_DADOS_RESUMO_CONVERSAS / 'reddit_dados_com_resumo_llama.json'

# --- 2. CONFIGURAÇÃO DO REGEX DE HARDWARE (ATUALIZADO) ---
# Padrões definidos para rodar em texto .lower() (minúsculo)
# --- 2. CONFIGURAÇÃO DO REGEX DE HARDWARE (VERSÃO FINAL 2010-2026 + HDD REFORÇADO) ---
PADROES_HARDWARE = {
    # GPU: NVIDIA (GT/GTX/RTX/Quadro/Titan/MX), AMD (HD/R-Series/RX/Vega), INTEL (Arc/Iris/UHD)
    "gpu": r"\b("
           r"(geforce\s*)?(rtx|gtx|gt|mx|quadro|titan)\s*\d{3,4}[a-z0-9]*([\s-]*(ti|super|max-q|mobile|oc|ada|lhr))?|"  # NVIDIA
           r"(amd\s*)?(radeon\s*(tm|™)?\s*)?(rx|r9|r7|r5|hd|vega)\s*(\d{3,4}|[a-z0-9]+)([\s-]*(xt|xtx|gre|m|xt-m|pro))?|"  # AMD Radeon
           r"(intel\s*)?(arc)\s*[ab]\d{3,4}[a-z]*|" # Intel ARC
           r"iris\s*xe|uhd\s*graphics|radeon\s*graphics" # Integradas
           r")\b",
    
    # CPU: INTEL (Core i/Ultra/Pentium/Celeron/Xeon), AMD (Ryzen/Threadripper/Athlon/FX/A-Series)
    "cpu": r"\b("
           r"(intel\s*)?(core\s*(ultra)?\s*)?(i[3579]|[3579])[\s-]*\d{3,5}[a-z0-9]*|" # Core i3, Core Ultra 7
           r"(intel\s*)?(pentium|celeron|atom|xeon)[\s-]*[a-z0-9]+|" # Low-end/Server
           r"(amd\s*)?(ryzen\s*(threadripper)?\s*[3579]|athlon|fx|a[468]|a1[02])[\s-]*(\d{3,4}[a-z]*)?" # Ryzen, FX, A-Series
           r")\b",
    
    # STORAGE: SSDs (NVMe/SATA) e HDDs (Mecânicos/RPM/Enterprise)
    "storage": r"\b("
               r"(\d{1,4}\s*(gb|tb)\s*)?" # Capacidade (ex: 1TB) no início
               r"(" # GRUPO DE IDENTIFICAÇÃO (Marca ou Linha)
                   r"(samsung|wd|western\s*digital|crucial|kingston|sandisk|seagate|toshiba|sk\s*hynix|hynix|corsair|sabrent|adata|xpg|pny|lexar|hp|intel|teamgroup|patriot|gigabyte|hgst|hitachi)|" # Marcas
                   r"(firecuda|barracuda|ironwolf|skyhawk|exos|blue|black|green|red|purple|gold|ultrastar|p300|x300|n300|l200|evo|qvo|pro|plus|mx500|bx500|p3|p5|nv2|kc3000|fury|legend|gammix|sn\d{3,4})" # Linhas SSD e HDD
               r")?\s*"
               r"([a-z0-9-]+\s*)?" # Modelo alfanumérico solto
               r"(ssd|nvme|m\.2|sata|hdd|hard\s*drive|disco\s*r[ií]gido|hd|sshd|sdd|7200\s*rpm|5400\s*rpm)" # OBRIGATÓRIO: Tipo ou Rotação
               r"(\s*\d{1,4}\s*(gb|tb))?" # Capacidade (ex: 500GB) no fim
               r")\b",
    
    # RAM:
    "ram": r"\b("
           r"(\d{1,3}\s*gb\s*)?" 
           r"(ddr[345]|lpddr[345]x?|sodimm|dimm|ram|mem[oó]ria)"
           r"(\s*\d{3,5}\s*(mhz|mt/s)?)?"
           r"(\s*ram)?"
           r")\b",
    
    # TELA:
    "screen": r"\b("
              r"\d{2,3}(\.\d)?[\"”]\s*|" # Tamanho
              r"120hz|144hz|165hz|240hz|300hz|360hz|60hz|" # Frequência
              r"ips|tn|va|wva|pls|oled|amoled|miniled|mini-led|retina|" # Painel
              r"4k|uhd|qhd|wqhd|fhd|hd\+|full\s*hd|1080p|1440p|2160p|768p|1366x768|1920x1080" # Resolução
              r")\b"
}
def extrair_hardware_regex(texto_completo):
    """
    Varre o texto em busca de hardware e retorna uma string formatada.
    Ex: 'GPU: rtx 3060 max-q, STORAGE: ssd nvme'
    """
    if not texto_completo: return None
    
    texto_lower = texto_completo.lower()
    componentes_encontrados = []

    for tipo, pattern in PADROES_HARDWARE.items():
        matches = re.finditer(pattern, texto_lower)
        # strip() remove espaços extras capturados nas bordas
        uniques = set(m.group(0).strip() for m in matches)
        if uniques:
            # Formata como "TIPO: componente"
            componentes_encontrados.append(f"{tipo.upper()}: {', '.join(uniques)}")
    
    if componentes_encontrados:
        return " | ".join(componentes_encontrados)
    return "Nenhum componente específico detectado automaticamente."

# --- 3. CONFIGURAÇÃO DO CLIENTE OLLAMA ---
client = OpenAI(
    base_url='http://localhost:11434/v1',
    api_key='ollama'
)

MODELO_OLLAMA = "llama3.2:latest"

def analisar_com_ollama(titulo, corpo, comentarios):
    """
    Envia o texto para o Llama local e retorna um resumo estruturado.
    """
    
    # 1. Preparação dos Textos
    texto_titulo = titulo if titulo else ""
    texto_corpo = corpo[:1000] if corpo else ""
    
    texto_comentarios = ""
    if comentarios:
        texto_comentarios = "COMENTARIOS RELEVANTES:\n"
        for c in comentarios[:3]:
            conteudo = c.get('conteudo_limpo', c.get('conteudo', ''))
            texto_comentarios += f"- {conteudo[:300]}\n"

    # 2. Executa o REGEX (Enriquecimento)
    texto_para_regex = f"{texto_titulo} {texto_corpo} {texto_comentarios}"
    hardware_detectado = extrair_hardware_regex(texto_para_regex)

    # 3. Montagem do Prompt com DADOS TÉCNICOS
    texto_entrada_final = f"""
[DADOS TÉCNICOS EXTRAÍDOS VIA SISTEMA]
Componentes identificados no texto: {hardware_detectado}
---------------------------------------------------
TITULO: {texto_titulo}
TEXTO: {texto_corpo}
{texto_comentarios}
"""

    # 4. Prompt do Sistema
    prompt_sistema = """
    Você é um especialista em suporte técnico de notebooks.
    
    Sua tarefa é analisar o texto do usuário e os [DADOS TÉCNICOS EXTRAÍDOS] se houver.
    Use os dados extraídos para preencher o campo 'componente' com precisão.
    
    Retorne APENAS um objeto JSON (sem markdown, sem explicações).
    
    O JSON deve ter exatamente estas chaves:
    {
        "resumo": "Resumo de 1 frase em português sobre o problema discutido, evite erros de português e afins.",
        "intencao": "Escolha entre: Problema Técnico, Compra, Upgrade, ou Outro",
        "componente": "Nome do componente principal citado (ex: RTX 3060, Tela, SSD) ou null",
        "solucao": "Solução sugerida nos comentários ou null, evite erros de português e afins."
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
            temperature=0.1 
        )
        
        conteudo_resposta = response.choices[0].message.content
        return json.loads(conteudo_resposta)

    except json.JSONDecodeError:
        print("X - Erro: O modelo não retornou um JSON válido.")
        return None
    except Exception as e:
        print(f"X - Erro de conexão ou execução: {e}")
        return None

# --- 4. EXECUÇÃO PRINCIPAL ---

print(f"Carregando dados de: {CAMINHO_ENTRADA_JSON}")
with open(CAMINHO_ENTRADA_JSON, 'r', encoding='utf-8') as f:
    dados = json.load(f)

print(f"Iniciando análise com OLLAMA (Modelo: {MODELO_OLLAMA})...")
print("Pressione Ctrl+C para parar a qualquer momento.")

posts_analisados = 0

try:
    for item in dados:
        if 'posts' in item:
            for post in item['posts']:
                titulo = post.get('titulo', 'Sem título')
                print(f"\n[{posts_analisados+1}] Analisando: {titulo[:50]}...")
                
                resultado = analisar_com_ollama(
                    titulo,
                    post.get('conteudo_texto', ''),
                    post.get('comentarios', [])
                )
                
                if resultado:
                    post['analise_ia'] = resultado
                    print(f"   -> Componente (IA): {resultado.get('componente')}")
                    print(f"   -> Resumo: {resultado.get('resumo')}")
                    print(f"   -> Solução: {resultado.get('solucao')}")

                else:
                    post['analise_ia'] = {"erro": "Falha na análise do Ollama"}
                
                posts_analisados += 1

except KeyboardInterrupt:
    print("\n\nOperação interrompida pelo usuário. Salvando o que já foi feito...")

# --- 5. SALVAMENTO ---
CAMINHO_SAIDA_JSON.parent.mkdir(parents=True, exist_ok=True)
with open(CAMINHO_SAIDA_JSON, 'w', encoding='utf-8') as f:
    json.dump(dados, f, ensure_ascii=False, indent=4)

print(f"\nProcessamento finalizado.")
print(f"Total de posts analisados: {posts_analisados}")
print(f"Arquivo salvo em: {CAMINHO_SAIDA_JSON}")