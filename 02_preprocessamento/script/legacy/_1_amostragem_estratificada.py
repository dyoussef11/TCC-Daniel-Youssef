import os
import json
import pandas as pd
from collections import Counter, defaultdict
import random
from pathlib import Path

from core.paths import PREPROCESSAMENTO_DATA

# ============================================
# CONFIGURAÇÕES - AJUSTE ESTES CAMINHOS
# ============================================
PASTA_LIMPOS = PREPROCESSAMENTO_DATA / "Dados_Limpos_IniciaisV7"
PASTA_SAIDA = PREPROCESSAMENTO_DATA / "analise_estatistica"

def abrir_json_seguro(caminho):
    """Abre arquivo JSON com tratamento de encoding"""
    try:
        with open(caminho, 'r', encoding='utf-8') as f:
            return json.load(f)
    except UnicodeDecodeError:
        # Se UTF-8 falhar, tenta outros encodings
        for enc in ['latin-1', 'cp1252', 'iso-8859-1']:
            try:
                with open(caminho, 'r', encoding=enc) as f:
                    return json.load(f)
            except:
                continue
        # Último recurso: ignora erros
        with open(caminho, 'r', encoding='utf-8', errors='ignore') as f:
            return json.load(f)

def extrair_marca(nome_arquivo):
    """Extrai a marca do nome do arquivo, ignorando prefixo gen_"""
    nome_lower = nome_arquivo.lower()
    
    # Remove o prefixo 'gen_' se existir
    if nome_lower.startswith('gen_'):
        nome_lower = nome_lower[4:]  # Remove os primeiros 4 caracteres ('gen_')
    
    marcas_conhecidas = [
        'msi', 'asus', 'dell', 'lenovo', 'acer', 'hp', 'razer',
        'gigabyte', 'samsung', 'alienware', 'legion', 'predator',
        'omen', 'rog', 'tuf', 'nitro', 'pavilion', 'ideapad',
        'thinkpad', 'xps', 'inspiron', 'latitude', 'surface',
        'colorful', 'ninkear', 'nan', 'lg'
        # Removi 'gen' da lista de marcas conhecidas
    ]
    
    for marca in marcas_conhecidas:
        if marca in nome_lower:
            return marca
    
    partes = nome_arquivo.split('_')[0]
    # Se o arquivo original tinha 'gen_', pega a segunda parte
    if nome_arquivo.lower().startswith('gen_'):
        partes_originais = nome_arquivo.split('_')
        if len(partes_originais) > 1:
            partes = partes_originais[1]  # Pega o segundo elemento
    
    return partes if len(partes) < 15 else 'desconhecida'

def extrair_marca_principal(marca_detectada):
    """Agrupa variantes de marcas sob um nome principal"""
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
    """Analisa as categorias presentes em um arquivo"""
    dados = abrir_json_seguro(caminho_completo)
    
    if dados is None:
        return None
    
    categorias = []
    problemas_detectados = set()
    
    for post in dados.get('posts', []):
        categoria = post.get('categoria', 'nao_categorizado')
        categorias.append(categoria)
        
        termos = post.get('termos_especificos', [])
        problemas_detectados.update(termos)
    
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
    """
    Valida se a categoria atribuída faz sentido com o conteúdo
    """
    titulo = (post.get('titulo', '') + ' ' + post.get('conteudo_post', '')).lower()
    categoria = post.get('categoria', 'nao_categorizado')
    
    indicadores = {
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
    
    if categoria == 'nao_categorizado':
        return categoria, False, "Sem categoria definida"
    
    if categoria in indicadores:
        termos_relevantes = indicadores[categoria]
        if any(termo in titulo for termo in termos_relevantes):
            return categoria, True, "OK"
        else:
            for cat, termos in indicadores.items():
                if cat != categoria and any(termo in titulo for termo in termos):
                    return categoria, False, f"Possível categoria correta: {cat}"
            return categoria, False, "Nenhum termo indicador encontrado no título"
    
    return categoria, True, "OK"

def gerar_relatorio_diversidade(lista_arquivos_nomes):
    """Gera relatório completo de diversidade"""
    
    dados_arquivos = []
    categorias_geral = Counter()
    marcas_detectadas = Counter()
    marcas_principais = Counter()
    problemas_geral = Counter()
    inconsistencias = []
    arquivos_com_erro = []  # Lista detalhada de erros
    
    for nome_arquivo in lista_arquivos_nomes:
        caminho_completo = PASTA_LIMPOS / nome_arquivo
        
        try:
            info = analisar_categorias_arquivo(caminho_completo)
            
            if info is None:
                arquivos_com_erro.append({
                    'arquivo': nome_arquivo,
                    'erro': 'Não foi possível carregar o JSON'
                })
                continue
            
            dados_arquivos.append(info)
            
            # Contagem de categorias
            categorias_geral.update(info['categorias'])
            
            # Contagem de marcas
            marca_detectada = extrair_marca(info['arquivo'])
            marca_principal = extrair_marca_principal(marca_detectada)
            marcas_detectadas[marca_detectada] += 1
            marcas_principais[marca_principal] += 1
            
            # Contagem de problemas
            problemas_geral.update(info['problemas_detectados'])
            
            # Valida categorias dos posts
            dados = abrir_json_seguro(caminho_completo)
            if dados:
                for post in dados.get('posts', []):
                    cat, valido, motivo = validar_categoria_post(post)
                    if not valido:
                        inconsistencias.append({
                            'arquivo': nome_arquivo,
                            'post_id': post.get('id'),
                            'categoria_atual': cat,
                            'motivo': motivo,
                            'titulo': post.get('titulo', '')[:150]
                        })
        except Exception as e:
            arquivos_com_erro.append({
                'arquivo': nome_arquivo,
                'erro': str(e)
            })
    
    return {
        'total_arquivos': len(lista_arquivos_nomes),
        'arquivos_processados': len(dados_arquivos),
        'arquivos_com_erro': len(arquivos_com_erro),        # Contagem (int)
        'lista_erros_detalhada': arquivos_com_erro,          # Lista completa
        'total_posts': sum(d['total_posts'] for d in dados_arquivos),
        'distribuicao_categorias': dict(categorias_geral.most_common()),
        'distribuicao_marcas_detectadas': dict(marcas_detectadas.most_common()),
        'distribuicao_marcas_principais': dict(marcas_principais.most_common()),
        'problemas_mais_comuns': dict(problemas_geral.most_common(30)),
        'inconsistencias': inconsistencias,
        'dados_por_arquivo': dados_arquivos
    }

def selecionar_amostra_diversificada(lista_arquivos_nomes, n_selecionados, semente=42):
    """
    Seleciona amostra garantindo diversidade de marcas e categorias
    """
    random.seed(semente)
    
    # Filtra apenas arquivos que conseguimos processar
    arquivos_validos = []
    for arquivo in lista_arquivos_nomes:
        caminho_completo = PASTA_LIMPOS / arquivo
        info = analisar_categorias_arquivo(caminho_completo)
        if info is not None:
            arquivos_validos.append((arquivo, info))
    
    print(f"  Arquivos processáveis: {len(arquivos_validos)} de {len(lista_arquivos_nomes)}")
    
    # Agrupa por marca principal
    por_marca = defaultdict(list)
    for arquivo, info in arquivos_validos:
        marca = extrair_marca(arquivo)
        marca_principal = extrair_marca_principal(marca)
        por_marca[marca_principal].append(arquivo)
    
    # Agrupa por categoria principal
    por_categoria = defaultdict(list)
    for arquivo, info in arquivos_validos:
        cat_principal = info['categoria_principal']
        por_categoria[cat_principal].append(arquivo)
    
    print(f"  Marcas únicas: {len(por_marca)}")
    for m, arqs in sorted(por_marca.items()):
        print(f"    {m:<15}: {len(arqs):>3} arquivos")
    
    print(f"  Categorias únicas: {len(por_categoria)}")
    for c, arqs in sorted(por_categoria.items()):
        print(f"    {c:<25}: {len(arqs):>3} arquivos")
    
    # Estratégia de seleção
    selecionados = set()
    
    # 1. Garante pelo menos 1 de cada marca principal
    print(f"\n  Garantindo representação de marcas...")
    for marca, arquivos_marca in por_marca.items():
        if arquivos_marca:
            escolhido = random.choice(arquivos_marca)
            selecionados.add(escolhido)
    
    # 2. Garante pelo menos 1 de cada categoria
    print(f"  Garantindo representação de categorias...")
    for cat, arquivos_cat in por_categoria.items():
        if arquivos_cat:
            disponiveis = [a for a in arquivos_cat if a not in selecionados]
            if disponiveis:
                escolhido = random.choice(disponiveis)
                selecionados.add(escolhido)
    
    # 3. Preenche o restante balanceando marcas
    restantes = [a for a, _ in arquivos_validos if a not in selecionados]
    
    while len(selecionados) < n_selecionados and restantes:
        marcas_atuais = Counter(
            extrair_marca_principal(extrair_marca(a)) for a in selecionados
        )
        
        # Prioriza arquivos de marcas sub-representadas
        restantes_ordenados = sorted(
            restantes,
            key=lambda x: marcas_atuais.get(
                extrair_marca_principal(extrair_marca(x)), 0
            )
        )
        
        escolhido = restantes_ordenados[0]
        selecionados.add(escolhido)
        restantes.remove(escolhido)
    
    return list(selecionados)

# ============================================
# EXECUÇÃO PRINCIPAL
# ============================================

if __name__ == "__main__":
    # Criar pasta de saída
    os.makedirs(PASTA_SAIDA, exist_ok=True)
    
    # Lista todos os arquivos JSON na pasta
    arquivos_disponiveis = sorted([
        f for f in os.listdir(PASTA_LIMPOS) 
        if f.endswith('.json')
    ])
    
    print(f"📊 Total de arquivos disponíveis: {len(arquivos_disponiveis)}")
    
    # 1. Gera relatório de diversidade
    print("\n🔍 Gerando relatório de diversidade...")
    relatorio = gerar_relatorio_diversidade(arquivos_disponiveis)
    
    print(f"\n{'='*60}")
    print(f"📊 RESUMO DO PROCESSAMENTO:")
    print(f"  Total arquivos: {relatorio['total_arquivos']}")
    print(f"  Processados com sucesso: {relatorio['arquivos_processados']}")
    print(f"  Com erro: {relatorio['arquivos_com_erro']}")
    print(f"  Total posts: {relatorio['total_posts']}")
    
    # CORREÇÃO: Verifica se há erros e usa a lista detalhada
    if relatorio['arquivos_com_erro'] > 0:
        print(f"\n⚠️ Primeiros 10 arquivos com erro:")
        for err in relatorio['lista_erros_detalhada'][:10]:
            print(f"  - {err['arquivo'][:80]}")
            print(f"    Erro: {err['erro'][:100]}")
    
    print(f"\n📈 DISTRIBUIÇÃO DE MARCAS PRINCIPAIS:")
    for marca, count in sorted(relatorio['distribuicao_marcas_principais'].items(), key=lambda x: x[1], reverse=True):
        pct = (count / relatorio['arquivos_processados']) * 100 if relatorio['arquivos_processados'] > 0 else 0
        print(f"  {marca:<15}: {count:>3} arquivos ({pct:.1f}%)")
    
    print(f"\n📈 DISTRIBUIÇÃO DE CATEGORIAS:")
    for cat, count in relatorio['distribuicao_categorias'].items():
        print(f"  {cat:<25}: {count:>4} posts")
    
    print(f"\n⚠️ INCONSISTÊNCIAS DE CATEGORIZAÇÃO: {len(relatorio['inconsistencias'])}")
    if relatorio['inconsistencias']:
        print("  Exemplos:")
        for inc in relatorio['inconsistencias'][:5]:
            print(f"  [{inc['categoria_atual']}] -> {inc['motivo']}")
            print(f"    Arquivo: {inc['arquivo'][:60]}")
    
    # 2. Seleciona amostra diversificada
    n_amostra = min(150, relatorio['arquivos_processados'])
    
    print(f"\n{'='*60}")
    print(f"🎯 Selecionando amostra diversificada de {n_amostra} arquivos...")
    amostra = selecionar_amostra_diversificada(
        arquivos_disponiveis,
        n_selecionados=n_amostra
    )
    
    # Mostra distribuição da amostra
    print(f"\n📊 Distribuição da amostra selecionada:")
    marcas_amostra = Counter(
        extrair_marca_principal(extrair_marca(a)) for a in amostra
    )
    for marca, count in marcas_amostra.most_common():
        print(f"  {marca:<15}: {count} arquivos")
    
    # 3. Salva resultados
    resultado = {
        'metadata': {
            'total_arquivos_originais': relatorio['total_arquivos'],
            'arquivos_processados': relatorio['arquivos_processados'],
            'arquivos_com_erro': relatorio['arquivos_com_erro'],
            'total_posts': relatorio['total_posts'],
            'tamanho_amostra': len(amostra)
        },
        'distribuicao_marcas': dict(relatorio['distribuicao_marcas_principais']),
        'distribuicao_categorias': relatorio['distribuicao_categorias'],
        'problemas_mais_comuns': relatorio['problemas_mais_comuns'],
        'total_inconsistencias': len(relatorio['inconsistencias']),
        'exemplos_inconsistencias': relatorio['inconsistencias'][:20],
        'arquivos_com_erro_detalhes': relatorio['lista_erros_detalhada'],  # CORREÇÃO: usa a lista
        'amostra_selecionada': amostra
    }
    
    caminho_saida = PASTA_SAIDA / "analise_diversidade_resultado.json"
    with open(caminho_saida, 'w', encoding='utf-8') as f:
        json.dump(resultado, f, indent=2, ensure_ascii=False)
    
    # Lista de selecionados em TXT
    caminho_lista = PASTA_SAIDA / "lista_amostra_selecionada.txt"
    with open(caminho_lista, 'w', encoding='utf-8') as f:
        for arq in sorted(amostra):
            f.write(f"{arq}\n")
    
    # Relatório de inconsistências
    caminho_incons = PASTA_SAIDA / "inconsistencias_categorias.json"
    with open(caminho_incons, 'w', encoding='utf-8') as f:
        json.dump(relatorio['inconsistencias'], f, indent=2, ensure_ascii=False)
    
    # Arquivos com erro
    caminho_erros = PASTA_SAIDA / "arquivos_com_erro.json"
    with open(caminho_erros, 'w', encoding='utf-8') as f:
        json.dump(relatorio['lista_erros_detalhada'], f, indent=2, ensure_ascii=False)  # CORREÇÃO: usa a lista
    
    print(f"\n{'='*60}")
    print(f"✅ Análise concluída!")
    print(f"📁 Resultados salvos em: {PASTA_SAIDA}")
    print(f"   - analise_diversidade_resultado.json (resumo completo)")
    print(f"   - lista_amostra_selecionada.txt")
    print(f"   - inconsistencias_categorias.json")
    print(f"   - arquivos_com_erro.json")