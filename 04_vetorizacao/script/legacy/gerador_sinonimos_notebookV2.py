# generate_sku_dictionary_v2.py
"""
Dicionário de sinônimos hierárquico: Marca -> Família -> Subfamília -> SKUs
Exemplo: hp -> victus -> 15 -> [fa1062tx, fb1017ax, ...]
                -> 16 -> [d0302tx, d0023dx, ...]
"""

import pandas as pd
import re
import json
from pathlib import Path
from collections import defaultdict
import unicodedata

from core.paths import DATASET_FINAL_CSV, VALIDACAO_CONFIG

CSV_PATH = DATASET_FINAL_CSV / 'dataset_laptops_GAMER_ONLY_V2.csv'
OUTPUT_PATH = VALIDACAO_CONFIG / 'dictionary_synonyms_hierarchical.json'
FLAT_OUTPUT_PATH = VALIDACAO_CONFIG / 'dictionary_synonyms_flat.json'


def normalize(text: str) -> str:
    """Normaliza texto."""
    text = str(text).lower()
    text = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('ASCII')
    return text.strip()


def detect_brand(modelo_limpo: str, id_unico: str) -> str:
    """Detecta a marca do modelo."""
    texto = f"{normalize(modelo_limpo)} {normalize(id_unico)}"
    
    brands = {
        'hp': ['hp', 'hewlett packard'],
        'asus': ['asus', 'asustek', 'rog', 'tuf', 'zenbook', 'vivobook', 'proart'],
        'lenovo': ['lenovo', 'legion', 'ideapad', 'loq', 'thinkpad', 'yoga'],
        'dell': ['dell', 'alienware', 'xps', 'inspiron', 'precision'],
        'msi': ['msi', 'microstar', 'ge', 'gs', 'gp', 'gf'],
        'acer': ['acer', 'predator', 'nitro', 'aspire', 'swift'],
        'gigabyte': ['gigabyte', 'aorus', 'aero'],
        'razer': ['razer', 'blade'],
        'samsung': ['samsung', 'galaxy'],
    }
    
    for brand, keywords in brands.items():
        for kw in keywords:
            if kw in texto:
                return brand
    return 'outros'


def detect_family(modelo_limpo: str) -> str:
    """Detecta a família principal do modelo."""
    texto = normalize(modelo_limpo)
    
    families = [
        ('victus', 'victus'),
        ('omen', 'omen'),
        ('pavilion', 'pavilion'),
        ('envy', 'envy'),
        ('zbook', 'zbook'),
        ('tuf', 'tuf'),
        ('rog strix', 'rog_strix'),
        ('rog zephyrus', 'rog_zephyrus'),
        ('rog flow', 'rog_flow'),
        ('vivobook', 'vivobook'),
        ('zenbook', 'zenbook'),
        ('proart', 'proart'),
        ('legion', 'legion'),
        ('ideapad gaming', 'ideapad_gaming'),
        ('loq', 'loq'),
        ('thinkpad', 'thinkpad'),
        ('yoga', 'yoga'),
        ('nitro', 'nitro'),
        ('predator', 'predator'),
        ('aspire', 'aspire'),
        ('swift', 'swift'),
        ('katana', 'katana'),
        ('sword', 'sword'),
        ('vector', 'vector'),
        ('raider', 'raider'),
        ('stealth', 'stealth'),
        ('pulse', 'pulse'),
        ('thin', 'thin'),
        ('cyborg', 'cyborg'),
        ('bravo', 'bravo'),
        ('crosshair', 'crosshair'),
        ('titan', 'titan'),
        ('alienware', 'alienware'),
        ('xps', 'xps'),
        ('g series', 'g_series'),
    ]
    
    for keyword, family in families:
        if keyword in texto:
            return family
    return 'outros'


def detect_subfamily(modelo_limpo: str, modelo_completo: str, sku: str) -> str:
    """
    Detecta a subfamília (tamanho/geração/baseada em SKU).
    Isso resolve o problema do HP Victus 15 vs 16.
    """
    texto = normalize(f"{modelo_limpo} {modelo_completo}")
    
    # Padrões baseados no modelo limpo
    size_patterns = [
        (r'victus\s*15', '15'),
        (r'victus\s*16', '16'),
        (r'omen\s*16', '16'),
        (r'omen\s*17', '17'),
        (r'legion\s*5', '5'),
        (r'legion\s*7', '7'),
        (r'legion\s*9', '9'),
        (r'nitro\s*5', '5'),
        (r'nitro\s*16', '16'),
        (r'predator\s*helios\s*16', '16'),
        (r'predator\s*helios\s*300', '300'),
        (r'tuf\s*a15', 'a15'),
        (r'tuf\s*a16', 'a16'),
        (r'tuf\s*f15', 'f15'),
        (r'tuf\s*f16', 'f16'),
        (r'tuf\s*f17', 'f17'),
        (r'rog\s*strix\s*g15', 'g15'),
        (r'rog\s*strix\s*g16', 'g16'),
        (r'rog\s*strix\s*g17', 'g17'),
        (r'rog\s*zephyrus\s*g14', 'g14'),
        (r'rog\s*zephyrus\s*g15', 'g15'),
        (r'rog\s*zephyrus\s*g16', 'g16'),
    ]
    
    for pattern, subfamily in size_patterns:
        if re.search(pattern, texto):
            return subfamily
    
    # Padrões baseados no SKU (prioridade!)
    if sku:
        # HP Victus: fa/fb = 15, d = 16
        if sku.startswith(('fa', 'fb')):
            return '15'
        if sku.startswith('d'):
            return '16'
        
        # ASUS TUF: fx = f15, fa = a15
        if sku.startswith('fx'):
            return 'f15'
        if sku.startswith('fa'):
            return 'a15'
        
        # ASUS ROG: g5xx = 15, g6xx = 16
        if sku.startswith('g5'):
            return 'g15'
        if sku.startswith('g6'):
            return 'g16'
        
        # Dell G15: 5520, 5530
        if 'g15' in sku:
            return 'g15'
    
    return 'base'


def extract_sku(modelo_completo: str) -> str:
    """Extrai o SKU do modelo completo."""
    texto = normalize(modelo_completo)
    
    patterns = [
        # HP Victus: faXXXX, fbXXXX, dXXXX
        r'\b(f[a-b][0-9]{4}[a-z]*[0-9]*)\b',
        r'\b(d[0-9]{4}[a-z]*[0-9]*)\b',
        # ASUS: fxXXXX, gXXXX, gaXXXX
        r'\b(fx[0-9]{3}[a-z]*|g[0-9]{3}[a-z]*|ga[0-9]{3})\b',
        # Acer: anXXXX, phnXX
        r'\b(an[0-9]{3,4}|phn[0-9]{2})\b',
        # Lenovo: 82XXXX, 83XXXX
        r'\b(82[a-z0-9]{4}|83[a-z0-9]{4})\b',
        # Dell: g15-XXXX
        r'\b(g15-[0-9]{4})\b',
        # MSI padrão: 3 letras + números
        r'\b([a-z]{3}[0-9]{3,4}[a-z]*)\b',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, texto)
        if match:
            sku = match.group(1)
            sku = re.sub(r'(gaming|edition)$', '', sku)
            if len(sku) >= 3 and not sku.isdigit():
                return sku
    return ""


def extract_size_from_sku(sku: str) -> str:
    """Extrai tamanho do SKU quando disponível."""
    # HP: fa/fb = 15, d = 16
    if sku.startswith(('fa', 'fb')):
        return '15'
    if sku.startswith('d'):
        return '16'
    # ASUS: g5 = 15, g6 = 16, g7 = 17
    if sku.startswith('g5'):
        return 'g15'
    if sku.startswith('g6'):
        return 'g16'
    if sku.startswith('g7'):
        return 'g17'
    return None


def generate_hierarchical_dictionary(csv_path: Path) -> tuple:
    """
    Gera dois dicionários:
    1. Hierárquico: marca -> família -> subfamília -> [SKUs]
    2. Flat: "marca família subfamília" -> [SKUs] (para expansão simples)
    """
    print("=" * 60)
    print("📖 GERANDO DICIONÁRIO HIERÁRQUICO (MARCA -> FAMÍLIA -> SUBFAMÍLIA)")
    print("=" * 60)
    
    df = pd.read_csv(csv_path)
    df = df[df['id_unico'].notna()]
    df = df[df['id_unico'] != 'não identificado']
    
    print(f"📊 Processando {len(df)} modelos...")
    
    # Estrutura hierárquica: brand -> family -> subfamily -> set(skus)
    hierarchical = defaultdict(lambda: defaultdict(lambda: defaultdict(set)))
    
    # Estrutura flat para expansão simples
    flat = defaultdict(set)
    
    for _, row in df.iterrows():
        modelo_limpo = str(row.get('modelo_limpo', ''))
        modelo_completo = str(row.get('modelo_completo', ''))
        id_unico = str(row.get('id_unico', ''))
        
        if not modelo_limpo or modelo_limpo == 'nan':
            continue
        
        # Detecção
        brand = detect_brand(modelo_limpo, id_unico)
        family = detect_family(modelo_limpo)
        sku = extract_sku(modelo_completo)
        
        # Detecção de subfamília (prioriza SKU, depois texto)
        subfamily = detect_subfamily(modelo_limpo, modelo_completo, sku)
        
        # Se tem SKU, tenta extrair tamanho dele
        size_from_sku = extract_size_from_sku(sku)
        if size_from_sku:
            subfamily = size_from_sku
        
        # Adiciona à estrutura hierárquica
        if sku:
            hierarchical[brand][family][subfamily].add(sku)
        
        # Adiciona modelo limpo como referência
        modelo_clean = normalize(modelo_limpo)
        if modelo_clean and len(modelo_clean) > 5:
            hierarchical[brand][family][subfamily].add(modelo_clean)
        
        # Adiciona à estrutura flat (chave composta)
        flat_key = f"{brand} {family}"
        if subfamily != 'base':
            flat_key = f"{brand} {family} {subfamily}"
        
        if sku:
            flat[flat_key].add(sku)
        flat[flat_key].add(modelo_clean)
    
    # Converte sets para listas ordenadas
    result_hierarchical = {}
    for brand, families in hierarchical.items():
        result_hierarchical[brand] = {}
        for family, subfamilies in families.items():
            result_hierarchical[brand][family] = {}
            for subfamily, skus in subfamilies.items():
                if skus:
                    sku_list = sorted(list(skus), key=len)
                    # Adiciona o nome da subfamília como primeiro elemento
                    if subfamily not in sku_list and subfamily != 'base':
                        sku_list.insert(0, subfamily)
                    result_hierarchical[brand][family][subfamily] = sku_list
    
    # Estrutura flat para expansão
    result_flat = {}
    for key, skus in flat.items():
        if skus:
            sku_list = sorted(list(skus), key=len)
            # Adiciona a chave como primeiro elemento
            if key not in sku_list:
                sku_list.insert(0, key)
            result_flat[key] = sku_list
    
    # Estatísticas
    total_brands = len(result_hierarchical)
    total_families = sum(len(f) for f in result_hierarchical.values())
    total_subfamilies = sum(len(sf) for f in result_hierarchical.values() for sf in f.values())
    total_skus = sum(len(s) for f in result_hierarchical.values() for sf in f.values() for s in sf.values())
    
    print(f"\n✅ Dicionário hierárquico gerado:")
    print(f"   - Marcas: {total_brands}")
    print(f"   - Famílias: {total_families}")
    print(f"   - Subfamílias: {total_subfamilies}")
    print(f"   - Total SKUs/variações: {total_skus}")
    print(f"\n✅ Dicionário flat gerado: {len(result_flat)} chaves")
    
    return result_hierarchical, result_flat


def print_samples(hierarchical: dict, flat: dict):
    """Exibe amostras dos dicionários gerados."""
    
    print("\n" + "=" * 60)
    print("📋 EXEMPLOS - DICIONÁRIO HIERÁRQUICO")
    print("=" * 60)
    
    for brand in ['hp', 'asus', 'lenovo', 'dell', 'msi', 'acer']:
        if brand not in hierarchical:
            continue
        
        print(f"\n🔹 {brand.upper()}:")
        for family, subfamilies in list(hierarchical[brand].items())[:2]:
            print(f"   ├── {family}:")
            for subfamily, skus in list(subfamilies.items())[:3]:
                preview = skus[:5]
                print(f"   │   └── {subfamily}: {', '.join(preview)}")
                if len(skus) > 5:
                    print(f"   │       ... e mais {len(skus)-5}")
    
    print("\n" + "=" * 60)
    print("📋 EXEMPLOS - DICIONÁRIO FLAT (para expansão)")
    print("=" * 60)
    
    for key, skus in list(flat.items())[:10]:
        preview = skus[:5]
        print(f"\n🔹 {key}:")
        print(f"   → {', '.join(preview)}")
        if len(skus) > 5:
            print(f"   → ... e mais {len(skus)-5}")


if __name__ == "__main__":
    hierarchical, flat = generate_hierarchical_dictionary(CSV_PATH)
    
    # Salva ambos os formatos
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(hierarchical, f, indent=2, ensure_ascii=False)
    
    with open(FLAT_OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(flat, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 Hierárquico salvo em: {OUTPUT_PATH}")
    print(f"💾 Flat salvo em: {FLAT_OUTPUT_PATH}")
    
    # Exibe amostras
    print_samples(hierarchical, flat)