import os
import json
import re
import pandas as pd
from collections import Counter, defaultdict
import random
from pathlib import Path

from core.paths import PREPROCESSAMENTO_DATA

# ============================================
# CONFIGURAÇÕES - AJUSTE ESTES CAMINHOS
# ============================================

PASTA_LIMPOS = PREPROCESSAMENTO_DATA / "Dados_Limpos_IniciaisV10"
PASTA_SAIDA = PREPROCESSAMENTO_DATA / "analise_estatisticaV4"

# NOVO: Indicadores movidos para o escopo global para contagem por grupo
INDICADORES_CATEGORIAS = {
    "performance_issues": [
        "fps drop", "stuttering", "bottleneck", "low performance",
        "lag", "frame drop", "slow", "sluggish", "choppy", "stutter", 
        "underperform", "gpu usage", "cpu usage", "cpu bottleneck"
    ],
    "thermal_failure": [
        "overheating", "thermal throttling", "repaste", "fan noise",
        "hot", "temperature", "throttle", "thermal", "heat", "cooling",
        "fan", "loud", "high temp", "thermal paste", "cpu temp", "gpu temp",
        "hotspot", "prochot", "fan curve", "fan speed", "rpm", "vrm temp",
        "clean fan", "dusty", "airflow"
    ],
    "power_and_battery": [
        "battery drain", "battery health", "not charging", "cycle count",
        "battery life", "poor battery", "battery issue", "power adapter",
        "charger", "power brick", "battery problem", "battery wear",
        "discharge", "power draw", "usb-c charging", "pd charging", 
        "dc jack", "charging port", "loose charger", "drain while gaming", 
        "plugged in", "on battery", "battery bypass"
    ],
    "display_defects": [
        "backlight bleed", "flickering", "ips glow", "dead pixels",
        "screen issue", "display problem", "pixel", "bleed", "backlight",
        "screen flicker", "monitor issue", "panel", "screen tear",
        "ghosting", "oled burn", "image retention", "dead pixel", 
        "stuck pixel", "bright pixel", "dark spot", "mura", "clouding",
        "hinge issue", "screen wobble", "flex"
    ],
    "system_stability": [
        "bsod", "system freeze", "driver crash", "blue screen", "bootloop",
        "crash", "freeze", "freezing", "hang", "unstable", "lock up",
        "reboot", "restart", "shutdown", "black screen", "no post",
        "bios", "boot", "startup", "whea error", "kernel power", 
        "event id 41", "bugcheck", "memory dump", "artifacting", 
        "graphical glitch", "visual bug", "memory error", "memtest"
    ],
    "hardware_faults": [
        "coil whine", "buzzing", "electrical noise", "keyboard issue", 
        "key stuck", "trackpad", "touchpad", "click issue",
        "wifi issue", "wifi card", "connection drop", "network drop",
        "speaker", "audio issue", "sound crackling", "audio driver",
        "headphone jack", "3.5mm", "mic issue", "usb port", "hdmi", 
        "motherboard", "mobo", "vrm", "power delivery issue",
        "build quality", "creaking", "warranty", "rma", "customer service"
    ],
    "critical_software": [
        "driver update", "nvidia driver", "amd driver", "ddu",
        "clean install", "fresh install", "armoury crate", 
        "omen gaming hub", "msi center", "lenovo vantage",
        "alienware command", "bios update", "vbios", "firmware"
    ]
}

def abrir_json_seguro(caminho):
    try:
        with open(caminho, 'r', encoding='utf-8') as f:
            return json.load(f)
    except UnicodeDecodeError:
        for enc in ['latin-1', 'cp1252', 'iso-8859-1']:
            try:
                with open(caminho, 'r', encoding=enc) as f:
                    return json.load(f)
            except:
                continue
        with open(caminho, 'r', encoding='utf-8', errors='ignore') as f:
            return json.load(f)

def extrair_marca(nome_arquivo):
    nome_lower = nome_arquivo.lower()
    if nome_lower.startswith('gen_'):
        nome_lower = nome_lower[4:]
    
    marcas_conhecidas = [
        'msi', 'asus', 'dell', 'lenovo', 'acer', 'hp', 'razer',
        'gigabyte', 'samsung', 'alienware', 'legion', 'predator',
        'omen', 'rog', 'tuf', 'nitro', 'pavilion', 'ideapad',
        'thinkpad', 'xps', 'inspiron', 'latitude', 'surface',
        'colorful', 'ninkear', 'nan', 'lg'
    ]
    
    for marca in marcas_conhecidas:
        if marca in nome_lower:
            return marca
    
    partes = nome_arquivo.split('_')[0]
    if nome_arquivo.lower().startswith('gen_'):
        partes_originais = nome_arquivo.split('_')
        if len(partes_originais) > 1:
            partes = partes_originais[1]
    
    return partes if len(partes) < 15 else 'desconhecida'

def extrair_marca_principal(marca_detectada):
    agrupamento = {
        'msi': ['msi'],
        'asus': ['asus', 'rog', 'tuf', 'zenbook', 'vivobook', 'proart'],
        'dell': ['dell', 'alienware', 'inspiron', 'xps', 'latitude'],
        'lenovo': ['lenovo', 'legion', 'ideapad', 'thinkpad', 'loq', 'yoga'],
        'acer': ['acer', 'predator', 'nitro'],
        'hp': ['hp', 'omen', 'pavilion', 'victus', 'probook', 'zbook', 'envy'],
        'gigabyte': ['gigabyte', 'aorus', 'aero'],
        'razer': ['razer', 'blade'],
        'samsung': ['samsung', 'galaxy'],
        'lg': ['lg', 'gram'],
        'colorful': ['colorful'],
        'ninkear': ['ninkear'],
        'nan': ['nan'],
        'gen': ['gen']
    }
    for marca_principal, variantes in agrupamento.items():
        if marca_detectada in variantes:
            return marca_principal
    return marca_detectada

def analisar_categorias_arquivo(caminho_completo):
    dados = abrir_json_seguro(caminho_completo)
    if dados is None: return None
    
    categorias = []
    problemas_detectados = set()
    for post in dados.get('posts', []):
        categoria = post.get('categoria', 'nao_categorizado')
        categorias.append(categoria)
        problemas_detectados.update(post.get('termos_especificos', []))
    
    cat_counter = Counter(categorias)
    return {
        'arquivo': os.path.basename(caminho_completo),
        'total_posts': len(dados.get('posts', [])),
        'categorias': cat_counter,
        'categoria_principal': cat_counter.most_common(1)[0][0] if cat_counter else 'sem_categoria',
        'problemas_detectados': problemas_detectados,
        'modelo': dados.get('modelo_original', 'desconhecido')
    }

def validar_categoria_post(post):
    titulo = (post.get('titulo', '') + ' ' + post.get('conteudo_post', '')).lower()
    categoria = post.get('categoria', 'nao_categorizado')
    
    if categoria == 'nao_categorizado':
        return categoria, False, "Sem categoria definida"
    
    if categoria in INDICADORES_CATEGORIAS:
        termos_relevantes = INDICADORES_CATEGORIAS[categoria]
        if any(termo in titulo for termo in termos_relevantes):
            return categoria, True, "OK"
        else:
            for cat, termos in INDICADORES_CATEGORIAS.items():
                if cat != categoria and any(termo in titulo for termo in termos):
                    return categoria, False, f"Possível categoria correta: {cat}"
            return categoria, False, "Nenhum termo indicador encontrado no título"
    return categoria, True, "OK"

def gerar_relatorio_diversidade(lista_arquivos_nomes):
    dados_arquivos = []
    categorias_geral = Counter()
    marcas_principais = Counter()
    problemas_geral = Counter()
    
    # NOVO: Rastreamento de termos por grupo
    termos_por_grupo = defaultdict(Counter)
    
    inconsistencias = []
    arquivos_com_erro = []
    
    for nome_arquivo in lista_arquivos_nomes:
        caminho_completo = PASTA_LIMPOS / nome_arquivo
        try:
            info = analisar_categorias_arquivo(caminho_completo)
            if info is None:
                arquivos_com_erro.append({'arquivo': nome_arquivo, 'erro': 'Erro ao carregar JSON'})
                continue
            
            dados_arquivos.append(info)
            categorias_geral.update(info['categorias'])
            marca_principal = extrair_marca_principal(extrair_marca(info['arquivo']))
            marcas_principais[marca_principal] += 1
            
            # Análise detalhada de posts para termos por grupo
            dados = abrir_json_seguro(caminho_completo)
            if dados:
                for post in dados.get('posts', []):
                    cat, valido, motivo = validar_categoria_post(post)
                    
                    # NOVO: Lógica de contagem por categoria
                    texto_completo = (post.get('titulo', '') + ' ' + post.get('conteudo_post', '')).lower()
                    if cat in INDICADORES_CATEGORIAS:
                        for termo in INDICADORES_CATEGORIAS[cat]:
                            padrao = re.compile(rf'\b{re.escape(termo)}\b')
                            ocorrencias = len(padrao.findall(texto_completo))
                            if ocorrencias >= 2 or padrao.search(post.get('titulo', '').lower()):
                                termos_por_grupo[cat][termo] += 1
                                problemas_geral[termo] += 1
                    
                    if not valido:
                        inconsistencias.append({
                            'arquivo': nome_arquivo,
                            'post_id': post.get('id'),
                            'categoria_atual': cat,
                            'motivo': motivo,
                            'titulo': post.get('titulo', ''),
                            'conteudo_post': post.get('conteudo_post', '')
                        })
        except Exception as e:
            arquivos_com_erro.append({'arquivo': nome_arquivo, 'erro': str(e)})
    
    # Formatação final para o JSON
    termos_por_grupo_dict = {cat: dict(counts.most_common()) for cat, counts in termos_por_grupo.items()}

    return {
        'total_arquivos': len(lista_arquivos_nomes),
        'arquivos_processados': len(dados_arquivos),
        'arquivos_com_erro': len(arquivos_com_erro),
        'lista_erros_detalhada': arquivos_com_erro,
        'total_posts': sum(d['total_posts'] for d in dados_arquivos),
        'distribuicao_categorias': dict(categorias_geral.most_common()),
        'distribuicao_marcas_principais': dict(marcas_principais.most_common()),
        'termos_por_grupo': termos_por_grupo_dict, # <-- NOVO
        'problemas_mais_comuns': dict(problemas_geral.most_common(30)),
        'inconsistencias': inconsistencias,
        'dados_por_arquivo': dados_arquivos
    }

def selecionar_amostra_diversificada(lista_arquivos_nomes, n_selecionados, semente=42):
    random.seed(semente)
    arquivos_validos = []
    for arquivo in lista_arquivos_nomes:
        info = analisar_categorias_arquivo(PASTA_LIMPOS / arquivo)
        if info: arquivos_validos.append((arquivo, info))
    
    por_marca = defaultdict(list)
    por_categoria = defaultdict(list)
    for arquivo, info in arquivos_validos:
        marca = extrair_marca_principal(extrair_marca(arquivo))
        por_marca[marca].append(arquivo)
        por_categoria[info['categoria_principal']].append(arquivo)
    
    selecionados = set()
    for marca, arqs in por_marca.items(): selecionados.add(random.choice(arqs))
    for cat, arqs in por_categoria.items():
        disponiveis = [a for a in arqs if a not in selecionados]
        if disponiveis: selecionados.add(random.choice(disponiveis))
    
    restantes = [a for a, _ in arquivos_validos if a not in selecionados]
    while len(selecionados) < n_selecionados and restantes:
        marcas_atuais = Counter(extrair_marca_principal(extrair_marca(a)) for a in selecionados)
        restantes.sort(key=lambda x: marcas_atuais.get(extrair_marca_principal(extrair_marca(x)), 0))
        escolhido = restantes.pop(0)
        selecionados.add(escolhido)
    
    return list(selecionados)

if __name__ == "__main__":
    os.makedirs(PASTA_SAIDA, exist_ok=True)
    arquivos_disponiveis = sorted([f for f in os.listdir(PASTA_LIMPOS) if f.endswith('.json')])
    
    print("🔍 Iniciando processamento e análise de termos por grupo...")
    relatorio = gerar_relatorio_diversidade(arquivos_disponiveis)
    
    # Amostragem
    n_amostra = min(len(arquivos_disponiveis), relatorio['arquivos_processados'])
    amostra = selecionar_amostra_diversificada(arquivos_disponiveis, n_selecionados=n_amostra)
    
    # Salvar resultados
    resultado = {
        'metadata': {
            'total_arquivos_originais': relatorio['total_arquivos'],
            'arquivos_processados': relatorio['arquivos_processados'],
            'total_posts': relatorio['total_posts'],
            'tamanho_amostra': len(amostra)
        },
        'distribuicao_marcas': relatorio['distribuicao_marcas_principais'],
        'distribuicao_categorias': relatorio['distribuicao_categorias'],
        'termos_por_grupo': relatorio['termos_por_grupo'], # <-- Incluído no JSON final
        'problemas_mais_comuns': relatorio['problemas_mais_comuns'],
        'total_inconsistencias': len(relatorio['inconsistencias']),
        'arquivos_com_erro_detalhes': relatorio['lista_erros_detalhada'],
        'amostra_selecionada': amostra
    }
    
    with open(PASTA_SAIDA / "analise_diversidade_resultado.json", 'w', encoding='utf-8') as f:
        json.dump(resultado, f, indent=2, ensure_ascii=False)
    
    # Manter demais arquivos de saída
    with open(PASTA_SAIDA / "lista_amostra_selecionada.txt", 'w', encoding='utf-8') as f:
        for arq in sorted(amostra): f.write(f"{arq}\n")
    
    with open(PASTA_SAIDA / "inconsistencias_categorias.json", 'w', encoding='utf-8') as f:
        json.dump(relatorio['inconsistencias'], f, indent=2, ensure_ascii=False)

    print(f"✅ Concluído! Relatórios disponíveis em: {PASTA_SAIDA}")