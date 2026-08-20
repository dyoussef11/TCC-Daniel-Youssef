# generate_sku_dictionary_v4.py
"""
Dicionário de sinônimos hierárquico V4 - OTIMIZADO PARA V9 (Temporal)
- Usa id_unico como SKU principal
- Separa termos genéricos de SKUs específicos
- Gera dois dicionários: 
  1. hierarchical_v4.json (estrutura completa)
  2. flat_v9.json (apenas termos genéricos para expansão)
"""

import pandas as pd
import re
import json
from pathlib import Path
from collections import defaultdict
import unicodedata

from core.paths import DATASET_FINAL_CSV, VALIDACAO_CONFIG


CSV_PATH = DATASET_FINAL_CSV / 'dataset_laptops_UNICOS_V10.csv'
OUTPUT_HIERARCHICAL = VALIDACAO_CONFIG / 'dictionary_synonyms_hierarchical_v4.json'
OUTPUT_FLAT_V9 = VALIDACAO_CONFIG / 'dictionary_synonyms_flat_v9.json'  # Para V9 (genérico)
OUTPUT_FLAT_V1 = VALIDACAO_CONFIG / 'dictionary_synonyms_flat_v3.json'   # Para V1 (completo)


def normalize(text: str) -> str:
    """Normaliza texto."""
    text = str(text).lower()
    text = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('ASCII')
    return text.strip()


def is_specific_sku(term: str) -> bool:
    """
    Verifica se um termo é um SKU específico (não deve ser usado para expansão).
    
    Exemplos de SKUs específicos:
    - an515-57-7447 (completo)
    - an515-58-526e (completo)
    - 15ach6 (código)
    - fa5075 (código)
    - 82k2022xin (código Lenovo)
    """
    term_lower = term.lower()
    
    # Padrões de SKU específico
    sku_patterns = [
        r'[a-z]{2,3}[-]?\d{3}[-]?\d{2,4}',      # an515-57-7447
        r'[a-z]{2,3}[-]?\d{3}',                 # an515-57
        r'\d{2,4}[a-z]{2,4}',                   # 15ach6, 16irx9
        r'[a-z]{3,4}\d{4}',                     # fa5075, gv301
        r'[a-z]{3}[-]?\d{3}$',                  # g15, g16
        r'82[a-z0-9]{4}',                       # 82k2022xin (Lenovo)
        r'83[a-z0-9]{4}',                       # 83jj000din (Lenovo)
        r'20[a-z0-9]{6}',                       # 20yss01j00 (ThinkPad)
        r'phn16',                               # Predator Helios Neo
        r'ph16',                                # Predator Helios
    ]
    
    for pattern in sku_patterns:
        if re.search(pattern, term_lower):
            return True
    
    # Termos muito curtos ou genéricos NÃO são SKUs específicos
    generic_terms = ['nitro 5', 'legion 5', 'tuf a15', 'rog strix', 'victus 15', 'omen 16', 'g15', 'xps 15']
    if term_lower in generic_terms:
        return False
    
    # Se tem números mas é muito curto (ex: "15", "16") - é tamanho, não SKU
    if term.isdigit() and len(term) <= 2:
        return False
    
    return False


def detect_brand(modelo_limpo: str, id_unico: str) -> str:
    """Detecta a marca do modelo usando id_unico como prioridade."""
    texto = f"{normalize(modelo_limpo)} {normalize(id_unico)}"
    
    brands = {
        'hp': ['hp', 'hewlett packard', 'hp_'],
        'asus': ['asus', 'asustek', 'rog', 'tuf', 'zenbook', 'vivobook', 'proart', 'asus_'],
        'lenovo': ['lenovo', 'legion', 'ideapad', 'loq', 'thinkpad', 'yoga', 'lenovo_'],
        'dell': ['dell', 'alienware', 'xps', 'inspiron', 'precision', 'dell_'],
        'msi': ['msi', 'microstar', 'ge', 'gs', 'gp', 'gf', 'msi_'],
        'acer': ['acer', 'predator', 'nitro', 'aspire', 'swift', 'acer_'],
        'gigabyte': ['gigabyte', 'aorus', 'aero', 'gigabyte_'],
        'razer': ['razer', 'blade', 'razer_'],
        'samsung': ['samsung', 'galaxy', 'samsung_'],
    }
    
    for brand, keywords in brands.items():
        for kw in keywords:
            if kw in texto:
                return brand
    return 'outros'


def detect_family(modelo_limpo: str, id_unico: str) -> str:
    """Detecta a família principal do modelo."""
    texto = normalize(f"{modelo_limpo} {id_unico}")
    
    families = [
        ('victus', 'victus'),
        ('omen', 'omen'),
        ('pavilion', 'pavilion'),
        ('envy', 'envy'),
        ('zbook', 'zbook'),
        
        # ASUS
        ('tuf', 'tuf'),
        ('rogstrix', 'rog_strix'),
        ('rogzephyrus', 'rog_zephyrus'),
        ('rogflow', 'rog_flow'),
        ('vivobook', 'vivobook'),
        ('zenbook', 'zenbook'),
        ('proart', 'proart'),
        
        # Lenovo
        ('legion', 'legion'),
        ('legionslim', 'legion_slim'),
        ('legionpro', 'legion_pro'),
        ('ideapadgaming', 'ideapad_gaming'),
        ('loq', 'loq'),
        ('thinkpad', 'thinkpad'),
        ('yoga', 'yoga'),
        
        # Acer
        ('nitro', 'nitro'),
        ('predatorheliosneo', 'predator_helios_neo'),
        ('predatorhelios', 'predator_helios'),
        ('predator', 'predator'),
        ('aspire', 'aspire'),
        ('swift', 'swift'),
        
        # MSI
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
        
        # Dell
        ('alienware', 'alienware'),
        ('xps', 'xps'),
        ('gseries', 'g_series'),
        ('inspiron', 'inspiron'),
    ]
    
    for keyword, family in families:
        if keyword in texto:
            return family
    return 'outros'


def extract_sku_from_id_unico(id_unico: str) -> str:
    """Extrai o SKU principal do id_unico."""
    if not id_unico or id_unico == 'nan':
        return ""
    
    # O id_unico tem formato: marca_modelo_cpu_ram
    # Ex: hp_hpvictus15-fb0157axgaming_ryzen5_8
    parts = id_unico.split('_')
    if len(parts) >= 2:
        # A segunda parte geralmente contém o modelo
        model_part = parts[1]
        # Tenta extrair padrões de SKU
        patterns = [
            r'[a-z]{2,3}[-]?\d{3}[-]?\d{2,4}',  # an515-57-7447
            r'[a-z]{2,3}[-]?\d{3}',             # an515-57
            r'\d{2,4}[a-z]{2,4}',               # 15ach6
            r'[a-z]{3,4}\d{4}',                 # fa5075
            r'82[a-z0-9]{4}',                   # 82k2022xin
        ]
        for pattern in patterns:
            match = re.search(pattern, model_part)
            if match:
                return match.group(0)
    
    return ""


def generate_optimized_dictionaries(csv_path: Path) -> tuple:
    """
    Gera dicionários otimizados para V1 e V9.
    
    Returns:
        tuple: (hierarchical_dict, flat_v9_dict, flat_v1_dict)
    """
    print("=" * 60)
    print("📖 GERANDO DICIONÁRIO HIERÁRQUICO V4 (OTIMIZADO)")
    print("=" * 60)
    
    df = pd.read_csv(csv_path)
    df = df[df['id_unico'].notna()]
    df = df[df['id_unico'] != 'não identificado']
    
    print(f"📊 Processando {len(df)} modelos...")
    
    hierarchical = defaultdict(lambda: defaultdict(lambda: defaultdict(set)))
    flat_v9 = defaultdict(set)      # Apenas termos genéricos (para V9)
    flat_v1 = defaultdict(set)      # Todos os termos (para V1)
    
    # Termos genéricos que queremos incluir (não são SKUs específicos)
    generic_terms_to_add = {
        'asus tuf a15': ['tuf a15', 'asus tuf a15', 'tuf a 15', 'a15 tuf'],
        'asus tuf f15': ['tuf f15', 'asus tuf f15', 'tuf gaming f15'],
        'asus rog strix': ['rog strix', 'asus rog strix', 'strix gaming'],
        'asus rog zephyrus': ['rog zephyrus', 'asus rog zephyrus', 'zephyrus gaming'],
        'lenovo legion 5': ['legion 5', 'lenovo legion 5', 'legion 5 gaming'],
        'lenovo legion slim 5': ['legion slim 5', 'slim 5 legion'],
        'acer nitro 5': ['nitro 5', 'acer nitro 5', 'nitro 5 gaming'],
        'acer predator helios 16': ['predator helios 16', 'helios 16'],
        'hp victus 15': ['victus 15', 'hp victus 15', 'victus 15 gaming'],
        'hp omen 16': ['omen 16', 'hp omen 16', 'omen 16 gaming'],
        'dell g15': ['g15', 'dell g15', 'g15 gaming'],
        'msi katana 15': ['katana 15', 'msi katana 15', 'katana gaming'],
    }
    
    # Adiciona termos genéricos manuais
    for key, variants in generic_terms_to_add.items():
        for var in variants:
            flat_v9[key].add(var)
        flat_v9[key].add(key)
    
    for _, row in df.iterrows():
        modelo_limpo = str(row.get('modelo_limpo', ''))
        modelo_completo = str(row.get('modelo_completo', ''))
        id_unico = str(row.get('id_unico', ''))
        
        if not modelo_limpo or modelo_limpo == 'nan':
            continue
        
        brand = detect_brand(modelo_limpo, id_unico)
        family = detect_family(modelo_limpo, id_unico)
        sku = extract_sku_from_id_unico(id_unico)
        
        # Detecta subfamília (tamanho)
        subfamily = 'base'
        if '15' in modelo_limpo or '15' in sku:
            subfamily = '15'
        elif '16' in modelo_limpo or '16' in sku:
            subfamily = '16'
        elif '17' in modelo_limpo or '17' in sku:
            subfamily = '17'
        elif 'a15' in modelo_limpo.lower():
            subfamily = 'a15'
        elif 'f15' in modelo_limpo.lower():
            subfamily = 'f15'
        
        # Adiciona SKU ao dicionário hierárquico
        if sku:
            hierarchical[brand][family][subfamily].add(sku)
        
        modelo_clean = normalize(modelo_limpo)
        if modelo_clean and len(modelo_clean) > 5:
            hierarchical[brand][family][subfamily].add(modelo_clean)
        
        # ⭐ DICIONÁRIO V9 (apenas termos genéricos)
        flat_key = f"{brand} {family}"
        if subfamily != 'base':
            flat_key = f"{brand} {family} {subfamily}"
        
        # Só adiciona ao V9 se NÃO for SKU específico
        if not is_specific_sku(modelo_clean):
            flat_v9[flat_key].add(modelo_clean)
        
        # ⭐ DICIONÁRIO V1 (todos os termos, inclusive SKUs)
        if sku:
            flat_v1[flat_key].add(sku)
        flat_v1[flat_key].add(modelo_clean)
    
    # Converte sets para listas ordenadas
    result_hierarchical = {}
    for brand, families in hierarchical.items():
        result_hierarchical[brand] = {}
        for family, subfamilies in families.items():
            if not subfamilies:
                continue
            result_hierarchical[brand][family] = {}
            for subfamily, items in subfamilies.items():
                if items:
                    item_list = sorted(list(items), key=len)
                    # Move o termo base para o início
                    base_term = f"{brand} {family}"
                    if subfamily != 'base':
                        base_term = f"{brand} {family} {subfamily}"
                    if base_term in item_list:
                        item_list.remove(base_term)
                        item_list.insert(0, base_term)
                    result_hierarchical[brand][family][subfamily] = item_list
    
    # Converte flat para listas ordenadas
    result_flat_v9 = {}
    for key, items in flat_v9.items():
        if items:
            item_list = sorted(list(items), key=len)
            # Garante que a chave está no início
            if key not in item_list:
                item_list.insert(0, key)
            result_flat_v9[key] = item_list[:10]  # Limita a 10 termos
    
    result_flat_v1 = {}
    for key, items in flat_v1.items():
        if items:
            item_list = sorted(list(items), key=len)
            if key not in item_list:
                item_list.insert(0, key)
            result_flat_v1[key] = item_list[:15]  # Limita a 15 termos
    
    # Estatísticas
    print(f"\n✅ Dicionário hierárquico gerado:")
    print(f"   - Marcas: {len(result_hierarchical)}")
    
    print(f"\n✅ Dicionário V9 (genérico): {len(result_flat_v9)} chaves")
    print(f"   - Apenas termos genéricos (sem SKUs específicos)")
    
    print(f"\n✅ Dicionário V1 (completo): {len(result_flat_v1)} chaves")
    print(f"   - Inclui SKUs específicos")
    
    return result_hierarchical, result_flat_v9, result_flat_v1


def print_samples(hierarchical: dict, flat_v9: dict, flat_v1: dict):
    """Exibe amostras dos dicionários gerados."""
    
    print("\n" + "=" * 60)
    print("📋 EXEMPLOS - DICIONÁRIO HIERÁRQUICO")
    print("=" * 60)
    
    # Mostra estrutura
    for brand in list(hierarchical.keys())[:3]:
        print(f"\n🔹 {brand}:")
        for family in list(hierarchical[brand].keys())[:2]:
            print(f"   ├── {family}:")
            for subfamily, items in list(hierarchical[brand][family].items())[:2]:
                print(f"   │   └── {subfamily}: {items[:3]}")
    
    print("\n" + "=" * 60)
    print("📋 EXEMPLOS - DICIONÁRIO V9 (GENÉRICO - PARA EXPANSÃO)")
    print("=" * 60)
    
    for key in list(flat_v9.keys())[:5]:
        print(f"\n🔹 {key}:")
        print(f"   → {', '.join(flat_v9[key][:5])}")
    
    print("\n" + "=" * 60)
    print("📋 EXEMPLOS - DICIONÁRIO V1 (COMPLETO)")
    print("=" * 60)
    
    for key in list(flat_v1.keys())[:5]:
        print(f"\n🔹 {key}:")
        print(f"   → {', '.join(flat_v1[key][:5])}")


if __name__ == "__main__":
    hierarchical, flat_v9, flat_v1 = generate_optimized_dictionaries(CSV_PATH)
    
    # Salva os dicionários
    with open(OUTPUT_HIERARCHICAL, 'w', encoding='utf-8') as f:
        json.dump(hierarchical, f, indent=2, ensure_ascii=False)
    
    with open(OUTPUT_FLAT_V9, 'w', encoding='utf-8') as f:
        json.dump(flat_v9, f, indent=2, ensure_ascii=False)
    
    with open(OUTPUT_FLAT_V1, 'w', encoding='utf-8') as f:
        json.dump(flat_v1, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 Hierárquico salvo em: {OUTPUT_HIERARCHICAL}")
    print(f"💾 Flat V9 (genérico) salvo em: {OUTPUT_FLAT_V9}")
    print(f"💾 Flat V1 (completo) salvo em: {OUTPUT_FLAT_V1}")
    
    print_samples(hierarchical, flat_v9, flat_v1)