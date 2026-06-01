"""
Análise de Prevalência com VADER Calibrado - ALINHADO COM BUSCA REDDIT
Inclui métricas de diversidade temática (quantos temas diferentes por post/modelo)
"""
import os
import json
import pandas as pd
import numpy as np
import re
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm

from core.paths import PREPROCESSAMENTO_DATA

# ============ CONFIGURAÇÕES ============
CAMINHO_JSON = PREPROCESSAMENTO_DATA / "Dados_Limpos_IniciaisV3"
CAMINHO_SAIDA = PREPROCESSAMENTO_DATA / "Contagem_Analise_VaderV6_CALIBRADO"
CAMINHO_SAIDA.mkdir(parents=True, exist_ok=True)

# ============================================================
# TEMAS E PALAVRAS-CHAVE - EXATAMENTE OS MESMOS DA BUSCA REDDIT
# ============================================================
SEARCH_GROUPS = {
    "performance": [
                "fps drop", "stuttering", "bottleneck", "benchmarks", "low performance",
                "lag", "frame drop", "frame rate", "low fps", "poor performance",
                "slow", "sluggish", "choppy", "stutter", "underperform",
                "power limit", "tdp", "wattage", "clock speed", "utilization",
                "micro stutter", "frametime", "frame pacing", "1% lows",
                "gpu usage", "cpu usage", "cpu bottleneck", "gpu bottleneck",
                "underclock", "overclock fail", "boost clock", "base clock",
                "performance mode", "turbo mode", "silent mode", "balanced mode",
                "rtx", "dlss", "fsr", "ray tracing", "dx12", "vulkan",
                "unigine", "3dmark", "timespy", "firestrike", "cinebench",
                "geekbench", "passmark", "userbenchmark", "pcmark"
            ],

            "thermal": [
                "overheating", "thermal throttling", "undervolt", "repaste", "fan noise",
                "hot", "temperature", "throttle", "thermal", "heat", "cooling",
                "fan", "loud", "high temp", "thermal paste", "cpu temp", "gpu temp",
                "degrees", "celsius", "fahrenheit", "hotspot", "prochot",
                "liquid metal", "ptm7950", "honeywell", "thermal pad", "thermal putty",
                "vapor chamber", "heatpipe", "heatsink", "cooling pad", "laptop stand",
                "intake", "exhaust", "airflow", "dust", "dusty", "clean fan",
                "fan curve", "fan speed", "rpm", "noctua", "arctic mx",
                "thermal grizzly", "kryonaut", "conductonaut", "tg-7",
                "idle temp", "load temp", "ambient temp", "room temperature",
                "vrms", "vrm temp", "ssd temp", "nvme temp", "chipset temp"
            ],

            "energy": [
                "battery drain", "battery health", "not charging", "cycle count",
                "battery life", "poor battery", "battery issue", "power adapter",
                "charger", "power brick", "battery problem", "battery wear",
                "battery", "charge", "discharge", "power draw", "watt",
                "battery report", "battery capacity", "design capacity", "full charge",
                "battery calibration", "battery saver", "power plan", "power profile",
                "usb-c charging", "pd charging", "power delivery", "type c charge",
                "barrel charger", "dc jack", "charging port", "loose charger",
                "power limit throttling", "pl1", "pl2", "pl4", "cross loading",
                "drain while gaming", "plugged in", "on battery", "battery boost",
                "nvidia whisper mode", "battery bypass", "direct power"
            ],

            "display": [
                "backlight bleed", "flickering", "ips glow", "dead pixels",
                "screen issue", "display problem", "pixel", "bleed", "backlight",
                "screen flicker", "monitor issue", "panel", "screen tear",
                "screen", "display", "monitor", "color accuracy", "brightness",
                "ghosting", "response time", "motion blur", "overdrive",
                "gsync", "freesync", "vrr", "adaptive sync", "screen tearing",
                "color banding", "gradient", "color accuracy", "delta e",
                "srgb", "dci-p3", "adobe rgb", "ntsc", "color gamut",
                "hdr", "dolby vision", "brightness nits", "contrast ratio",
                "oled burn", "oled burn in", "image retention", "pwm flicker",
                "mini led", "blooming", "local dimming", "backlight zones",
                "dead pixel", "stuck pixel", "bright pixel", "dark spot",
                "mura", "clouding", "dse", "dirty screen effect",
                "screen bezel", "hinge issue", "screen wobble", "flex"
            ],

            "stability": [
                "bsod", "system freeze", "driver crash", "blue screen", "bootloop",
                "crash", "freeze", "freezing", "hang", "unstable", "lock up",
                "reboot", "restart", "shutdown", "black screen", "no post",
                "bios", "boot", "startup", "wake", "sleep", "hibernate",
                "whea error", "kernel power", "event id 41", "bugcheck",
                "memory dump", "minidump", "crash dump", "bsod viewer",
                "irql", "dpc watchdog", "page fault", "driver irql",
                "dxgmms2", "nvlddmkm", "amdkmdag", "atikmpag",
                "ctd", "crash to desktop", "hard lock", "soft lock",
                "artifact", "artifacting", "graphical glitch", "visual bug",
                "memory error", "memtest", "ram test", "xmp", "expo",
                "secure boot", "tpm", "bitlocker", "windows update issue"
            ],

            "hardware_specific": [
                "coil whine", "buzzing", "electrical noise", "humming",
                "keyboard issue", "key stuck", "keyboard ghosting", "keyboard backlight",
                "trackpad", "touchpad", "mouse pad", "click issue",
                "wifi issue", "wifi card", "mediatek", "intel ax", "realtek",
                "bluetooth", "bt issue", "connection drop", "network drop",
                "speaker", "audio issue", "sound crackling", "audio driver",
                "headphone jack", "3.5mm", "mic issue", "microphone",
                "usb port", "usb c", "thunderbolt", "hdmi", "displayport",
                "ram upgrade", "ssd upgrade", "nvme slot", "sodimm",
                "motherboard", "mobo", "vrm", "power delivery issue",
                "bent", "warped", "build quality", "creaking", "flex",
                "screw stripped", "warranty", "rma", "customer service"
            ],

            "software_issues": [
                "driver update", "nvidia driver", "amd driver", "intel driver",
                "geforce experience", "adrenalin", "command center", "ddu",
                "clean install", "fresh install", "windows 11", "windows 10",
                "optimize", "debloat", "bloatware", "preinstalled",
                "armoury crate", "omen gaming hub", "msi center", "lenovo vantage",
                "alienware command", "predator sense", "nitro sense",
                "throttlestop", "msi afterburner", "rtss", "hwinfo",
                "gpu-z", "cpu-z", "ryzen master", "xtu", "intel xtu",
                "bios update", "vbios", "firmware", "chipset driver"
            ]
}

# Pré-compilação Regex
PATTERNS = {
    tema: re.compile(r'\b(' + '|'.join(map(re.escape, cfg["keywords"])) + r')\b', re.IGNORECASE)
    for tema, cfg in SEARCH_GROUPS.items()
}

analyzer = SentimentIntensityAnalyzer()

def analisar_mencao_calibrada(texto, match, threshold_vader=-0.15):
    """Análise calibrada de sentimento com threshold -0.15"""
    start = max(0, match.start() - 100)
    end = min(len(texto), match.end() + 100)
    contexto = texto[start:end]
    compound = analyzer.polarity_scores(contexto)['compound']
    return compound < threshold_vader, compound

def contar_palavras(texto):
    return len(re.findall(r'\w+', texto))

def processar_arquivo(arquivo):
    try:
        with open(CAMINHO_JSON / arquivo, 'r', encoding='utf-8') as f:
            dados = json.load(f)
        
        modelo = dados.get('modelo_busca_utilizado')
        posts = dados.get('posts', [])
        
        res = {
            "modelo": modelo,
            "posts_unicos": len(posts),
            "palavras": 0,
            "comentarios_total": 0,
            # Métricas de diversidade
            "diversidade_temas_modelo": 0,
            "media_temas_por_post": 0.0,
            "max_temas_em_um_post": 0,
            "posts_com_multiplos_temas": 0,
            "cobertura_tematica_percentual": 0.0
        }
        
        # Inicializa contadores para cada tema
        for tema in SEARCH_GROUPS:
            res[tema] = 0
            res[f"{tema}_compound_mean"] = []
        
        # Armazena temas únicos do modelo (de todos os posts)
        temas_unicos_modelo = set()
        
        # Para cada post, armazena quantos temas diferentes foram encontrados
        temas_por_post = []
        
        for post in posts:
            # SET para armazenar temas únicos deste post
            temas_encontrados_no_post = set()
            
            txt_post = f"{post.get('titulo', '')} {post.get('conteudo_post', '')}".lower()
            res["palavras"] += contar_palavras(txt_post)
            
            for tema, pattern in PATTERNS.items():
                compounds = []
                for match in pattern.finditer(txt_post):
                    is_neg, compound = analisar_mencao_calibrada(txt_post, match)
                    if is_neg:
                        res[tema] += 1
                        temas_encontrados_no_post.add(tema)
                    compounds.append(compound)
                if compounds:
                    res[f"{tema}_compound_mean"].extend(compounds)
            
            # Processa comentários
            for coment in post.get('comentarios', []):
                txt_c = str(coment.get('conteudo', '')).lower()
                if not txt_c:
                    continue
                
                res["palavras"] += contar_palavras(txt_c)
                res["comentarios_total"] += 1
                
                for tema, pattern in PATTERNS.items():
                    for match in pattern.finditer(txt_c):
                        is_neg, compound = analisar_mencao_calibrada(txt_c, match)
                        if is_neg:
                            res[tema] += 1
                            temas_encontrados_no_post.add(tema)
            
            # Atualiza temas únicos do modelo
            temas_unicos_modelo.update(temas_encontrados_no_post)
            
            # Armazena quantos temas este post teve (diversidade do post)
            qtd_temas_post = len(temas_encontrados_no_post)
            temas_por_post.append(qtd_temas_post)
        
        # Calcula métricas de diversidade
        res["diversidade_temas_modelo"] = len(temas_unicos_modelo)
        res["cobertura_tematica_percentual"] = (len(temas_unicos_modelo) / len(SEARCH_GROUPS)) * 100
        res["media_temas_por_post"] = np.mean(temas_por_post) if temas_por_post else 0.0
        res["max_temas_em_um_post"] = max(temas_por_post) if temas_por_post else 0
        res["posts_com_multiplos_temas"] = sum(1 for x in temas_por_post if x >= 2)
        
        # Converte listas de compound para média
        for tema in SEARCH_GROUPS:
            compounds = res[f"{tema}_compound_mean"]
            res[f"{tema}_compound_mean"] = np.mean(compounds) if compounds else 0.0
        
        return res
    except Exception as e:
        return f"Erro em {arquivo}: {e}"

def analisar_prevalencia_reddit_aligned():
    arquivos = [f for f in os.listdir(CAMINHO_JSON) if f.endswith('.json')]
    resultados = []
    
    print("="*70)
    print("📊 ANÁLISE VADER CALIBRADA - ALINHADA COM BUSCA REDDIT")
    print("🧩 INCLUINDO MÉTRICAS DE DIVERSIDADE TEMÁTICA")
    print("="*70)
    print(f"📁 Total de arquivos: {len(arquivos)}")
    print(f"🔍 Termos por tema:")
    for tema, cfg in SEARCH_GROUPS.items():
        print(f"   - {tema}: {len(cfg['keywords'])} termos")
    print(f"⚙️ Threshold VADER: -0.15 (calibrado para domínio técnico)")
    
    with ProcessPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(processar_arquivo, arq): arq for arq in arquivos}
        for future in tqdm(as_completed(futures), total=len(arquivos), desc="Processando"):
            resultado = future.result()
            if isinstance(resultado, dict):
                resultados.append(resultado)
    
    df = pd.DataFrame(resultados)
    temas = list(SEARCH_GROUPS.keys())
    
    # Métricas básicas
    df['total_mencoes'] = df[temas].sum(axis=1)
    df['densidade_tecnica'] = (df['total_mencoes'] / df['palavras'] * 1000).fillna(0).round(2)
    df['engajamento'] = (df['comentarios_total'] / df['posts_unicos']).fillna(0).round(2)
    
    # Percentuais por tema
    for tema in temas:
        df[f"{tema}_percentual"] = (df[tema] / df['total_mencoes'] * 100).fillna(0).round(1)
    
    # Classificação por diversidade temática
    def classificar_diversidade(valor):
        if valor >= 5:
            return "Muito Alta (5/5 temas)"
        elif valor == 4:
            return "Alta (4 temas)"
        elif valor == 3:
            return "Média (3 temas)"
        elif valor == 2:
            return "Baixa (2 temas)"
        else:
            return "Muito Baixa (0-1 tema)"
    
    df['classificacao_diversidade'] = df['diversidade_temas_modelo'].apply(classificar_diversidade)
    
    # Ordena e salva
    df_sorted = df.sort_values('densidade_tecnica', ascending=False)
    
    df_sorted.to_csv(
        CAMINHO_SAIDA / "prevalencia_com_diversidade.csv", 
        index=False, sep=';', encoding='utf-8-sig'
    )
    
    # Colunas para resumo expandido
    colunas_resumo = [
        'modelo', 'posts_unicos', 'palavras', 'total_mencoes', 
        'densidade_tecnica', 'engajamento',
        'diversidade_temas_modelo', 'cobertura_tematica_percentual',
        'media_temas_por_post', 'max_temas_em_um_post', 'posts_com_multiplos_temas',
        'classificacao_diversidade'
    ] + temas
    
    df_resumo = df_sorted[colunas_resumo].copy()
    df_resumo.to_csv(
        CAMINHO_SAIDA / "prevalencia_com_diversidade_resumo.csv", 
        index=False, sep=';', encoding='utf-8-sig'
    )
    
    # ============ RELATÓRIO ============
    print("\n" + "="*70)
    print("📊 RELATÓRIO DE PREVALÊNCIA COM DIVERSIDADE TEMÁTICA")
    print("="*70)
    
    print(f"\n📈 TOP 10 MODELOS COM MAIOR DENSIDADE DE PROBLEMAS:")
    print("-"*60)
    top10 = df_sorted.head(10)
    for i, row in top10.iterrows():
        print(f"{row['modelo']:<35} | {row['densidade_tecnica']:.2f} menções/1k palavras | {row['total_mencoes']} total")
    
    print(f"\n📊 DISTRIBUIÇÃO TEMÁTICA (média por modelo):")
    print("-"*60)
    for tema in temas:
        media = df[tema].mean()
        std = df[tema].std()
        total = df[tema].sum()
        pct_total = total / df['total_mencoes'].sum() * 100
        print(f"{tema:<15} | média: {media:.1f} | desvio: {std:.1f} | total: {total} ({pct_total:.1f}%)")
    
    print(f"\n🧩 MÉTRICAS DE DIVERSIDADE TEMÁTICA (média entre modelos):")
    print("-"*60)
    print(f"   Diversidade média por modelo:    {df['diversidade_temas_modelo'].mean():.1f} / {len(temas)} temas")
    print(f"   Modelos com alta diversidade (≥4 temas): {df[df['diversidade_temas_modelo'] >= 4].shape[0]} ({df[df['diversidade_temas_modelo'] >= 4].shape[0]/len(df)*100:.1f}%)")
    print(f"   Modelos com baixa diversidade (≤2 temas): {df[df['diversidade_temas_modelo'] <= 2].shape[0]} ({df[df['diversidade_temas_modelo'] <= 2].shape[0]/len(df)*100:.1f}%)")
    print(f"   Média de temas por post:         {df['media_temas_por_post'].mean():.2f}")
    print(f"   Posts com múltiplos temas:       {df['posts_com_multiplos_temas'].sum():,} no total")
    print(f"   Cobertura temática média:        {df['cobertura_tematica_percentual'].mean():.1f}%")
    
    print(f"\n🏆 TOP 5 MODELOS COM MAIOR DIVERSIDADE TEMÁTICA:")
    print("-"*60)
    top_diversidade = df_sorted.nlargest(5, 'diversidade_temas_modelo')[['modelo', 'diversidade_temas_modelo', 'cobertura_tematica_percentual', 'media_temas_por_post']]
    for i, row in top_diversidade.iterrows():
        print(f"{row['modelo']:<35} | {row['diversidade_temas_modelo']:.0f}/5 temas | {row['cobertura_tematica_percentual']:.0f}% cobertura | {row['media_temas_por_post']:.2f} temas/post")
    
    print(f"\n📊 CORRELAÇÃO ENTRE TEMAS (matriz de Pearson):")
    print("-"*60)
    corr_matrix = df[temas].corr()
    for tema in temas:
        correlations = corr_matrix[tema].sort_values(ascending=False)
        print(f"\n{tema}:")
        for other, corr in correlations.items():
            if other != tema:
                print(f"   ↔ {other}: {corr:.2f}")
    
    print(f"\n📈 CORRELAÇÃO: DIVERSIDADE vs DENSIDADE DE PROBLEMAS:")
    print("-"*60)
    corr_diversidade_densidade = df['diversidade_temas_modelo'].corr(df['densidade_tecnica'])
    print(f"   Correlação de Pearson: {corr_diversidade_densidade:.3f}")
    if corr_diversidade_densidade > 0.5:
        print(f"   ⚠️ Modelos com mais temas tendem a ter MAIOR densidade de menções")
    elif corr_diversidade_densidade < -0.3:
        print(f"   ℹ️ Modelos com mais temas tendem a ter MENOR densidade (problemas especializados)")
    else:
        print(f"   ℹ️ Não há correlação forte entre diversidade e densidade")
    
    # Estatísticas de cobertura
    print(f"\n📊 ESTATÍSTICAS DE COBERTURA:")
    print("-"*60)
    print(f"   Total de menções: {df['total_mencoes'].sum():,}")
    print(f"   Média de menções/modelo:  {df['total_mencoes'].mean():.1f}")
    print(f"   Modelos com pelo menos 1 menção: {(df['total_mencoes'] > 0).sum()} ({((df['total_mencoes'] > 0).sum()/len(df))*100:.1f}%)")
    
    print(f"\n✅ Arquivos salvos em: {CAMINHO_SAIDA}")
    print(f"   - prevalencia_com_diversidade.csv (completo)")
    print(f"   - prevalencia_com_diversidade_resumo.csv (resumido)")

if __name__ == "__main__":
    analisar_prevalencia_reddit_aligned()