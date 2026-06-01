import pandas as pd
import re
import json
from pathlib import Path
from collections import defaultdict
from difflib import SequenceMatcher
import unicodedata

from core.paths import DATASET_FINAL_CSV, VALIDACAO_CONFIG

CSV_PATH = DATASET_FINAL_CSV / 'dataset_laptops_GAMER_ONLY_V2.csv'
OUTPUT_PATH = VALIDACAO_CONFIG / 'dictionary_synonyms_refinedV3.json'

def normalize_text(text):
    """Normaliza texto: remove acentos, converte para lowercase e remove caracteres especiais"""
    text = str(text).lower()
    text = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('ASCII')
    text = re.sub(r'[^\w\s-]', '', text)
    return text.strip()

def extract_model_family(model_name):
    """Extrai a família principal do modelo com base em padrões conhecidos"""
    model_lower = model_name.lower()
    
    # Mapeamento de padrões para famílias (prioridade: específico > genérico)
    family_patterns = [
        # Acer
        (r'predator\s+helios\s+neo\s+16', 'predator helios neo 16'),
        (r'predator\s+helios\s+neo', 'predator helios neo'),
        (r'predator\s+helios\s+300', 'predator helios 300'),
        (r'predator\s+helios\s+16', 'predator helios 16'),
        (r'predator\s+helios\s+500', 'predator helios 500'),
        (r'predator\s+triton', 'predator triton'),
        (r'predator', 'predator'),
        (r'nitro\s+v', 'nitro v'),
        (r'nitro\s+5', 'nitro 5'),
        (r'nitro\s+16', 'nitro 16'),
        (r'nitro', 'nitro'),
        (r'aspire\s+7', 'aspire 7'),
        (r'aspire\s+5', 'aspire 5'),
        (r'aspire', 'aspire'),
        (r'swift\s+x', 'swift x'),
        
        # ASUS
        (r'rog\s+strix\s+scar', 'rog strix scar'),
        (r'rog\s+strix\s+g', 'rog strix'),
        (r'rog\s+zephyrus', 'rog zephyrus'),
        (r'rog\s+flow', 'rog flow'),
        (r'rog', 'rog'),
        (r'tuf\s+gaming', 'tuf gaming'),
        (r'tuf\s+dash', 'tuf dash'),
        (r'tuf\s+f', 'tuf f'),
        (r'tuf\s+a', 'tuf a'),
        (r'tuf', 'tuf'),
        (r'vivobook\s+pro', 'vivobook pro'),
        (r'vivobook', 'vivobook'),
        (r'zenbook\s+pro', 'zenbook pro'),
        
        # Dell
        (r'xps\s+15', 'xps 15'),
        (r'xps\s+17', 'xps 17'),
        (r'g\d+', 'g series'),
        (r'alienware\s+m', 'alienware m'),
        (r'alienware\s+x', 'alienware x'),
        (r'alienware', 'alienware'),
        
        # HP
        (r'omen\s+max', 'omen max'),
        (r'omen\s+transcend', 'omen transcend'),
        (r'omen\s+16', 'omen 16'),
        (r'omen\s+17', 'omen 17'),
        (r'omen', 'omen'),
        (r'victus\s+16', 'victus 16'),
        (r'victus\s+15', 'victus 15'),
        (r'victus', 'victus'),
        (r'pavilion\s+gaming', 'pavilion gaming'),
        (r'pavilion', 'pavilion'),
        
        # Lenovo
        (r'legion\s+pro', 'legion pro'),
        (r'legion\s+slim', 'legion slim'),
        (r'legion\s+5', 'legion 5'),
        (r'legion\s+7', 'legion 7'),
        (r'legion\s+9', 'legion 9'),
        (r'legion', 'legion'),
        (r'loq\s+15', 'loq 15'),
        (r'loq', 'loq'),
        (r'ideapad\s+gaming', 'ideapad gaming'),
        (r'ideapad', 'ideapad'),
        (r'thinkpad', 'thinkpad'),
        (r'yoga', 'yoga'),
        
        # MSI
        (r'katana', 'katana'),
        (r'sword', 'sword'),
        (r'vector', 'vector'),
        (r'raider', 'raider'),
        (r'stealth', 'stealth'),
        (r'pulse', 'pulse'),
        (r'crosshair', 'crosshair'),
        (r'titan', 'titan'),
        (r'cyborg', 'cyborg'),
        (r'bravo', 'bravo'),
        (r'creator', 'creator'),
        (r'thin', 'thin'),
        (r'gf\d+', 'gf series'),
        (r'gs\d+', 'gs series'),
        (r'ge\d+', 'ge series'),
        (r'gp\d+', 'gp series'),
        
        # Outros
        (r'gigabyte\s+g\d+', 'gigabyte g series'),
        (r'aero', 'aero'),
        (r'aorus', 'aorus'),
        (r'blade', 'blade'),
    ]
    
    for pattern, family in family_patterns:
        if re.search(pattern, model_lower):
            return family
    
    # Fallback: primeiras 2-3 palavras do modelo
    words = model_lower.split()
    return ' '.join(words[:2]) if len(words) >= 2 else model_lower

def extract_skus_from_text(text):
    """Extrai SKUs/códigos de produto com melhor precisão"""
    text_lower = text.lower()
    skus = set()
    
    # Padrões mais específicos para SKUs - CORRIGIDOS com grupos de captura
    patterns = [
        # Padrão Acer: letras + números (an515, ph315, phn16)
        r'\b([a-z]{2,4}[0-9]{2,4}(?:-[a-z0-9]{2,6})?)\b',
        # Padrão ASUS: 90nr0gw1, fx506, g513
        r'\b(90nr[a-z0-9]+|fx[0-9]{3}|g[0-9]{3}|ga[0-9]{3}|gu[0-9]{3}|fa[0-9]{3})\b',
        # Padrão Lenovo: 82k1, 83dv, etc
        r'\b(82[a-z0-9]{4}|83[a-z0-9]{4}|20[a-z0-9]{6})\b',
        # Padrão Dell: números com hífen
        r'\b(g15-[0-9]{4}|xps[0-9]{4})\b',
        # SKUs numéricos maiores (model numbers)
        r'\b([0-9]{5,}[a-z]{0,3})\b',
        # Códigos de 6-8 caracteres alfanuméricos
        r'\b([a-z0-9]{6,8})\b',
    ]
    
    # Palavras a ignorar (falsos positivos)
    ignore_words = {'acer', 'asus', 'dell', 'hp', 'lenovo', 'msi', 'gigabyte', 
                    'intel', 'amd', 'core', 'ryzen', 'ddr', 'nvme', 'ssd', 'hdd',
                    'windows', 'linux', 'gaming', 'laptop', 'notebook', 'graphics',
                    'graph', 'display', 'modelo', 'edition', 'plus', 'studio', 'pro'}
    
    for pattern in patterns:
        matches = re.finditer(pattern, text_lower)
        for match in matches:
            # Pega o primeiro grupo de captura (o que tem parênteses)
            sku = match.group(1) if match.groups() else match.group(0)
            # Validação: tamanho mínimo, não está na lista de ignorados
            if len(sku) >= 4 and sku not in ignore_words:
                # Remove sufixos comuns de especificações
                sku = re.sub(r'-(?:gaming|edition|pro|max)$', '', sku)
                # Verifica se não é uma data ou ano
                if not re.match(r'^20[0-9]{2}$', sku):
                    skus.add(sku)
    
    return skus

def extract_key_specs(filename):
    """Extrai especificações chave do nome do arquivo NER"""
    specs = {}
    
    # Extrai processador
    cpu_match = re.search(r'(?:corei[3579]|ryzen[3579]|intel|amd)[a-z0-9]+', filename.lower())
    if cpu_match:
        specs['cpu'] = cpu_match.group()
    
    # Extrai RAM
    ram_match = re.search(r'_(\d{1,2})[gb_]', filename.lower())
    if ram_match:
        specs['ram'] = f"{ram_match.group(1)}gb"
    
    return specs

def similarity_score(a, b):
    """Calcula similaridade entre strings para deduplicação"""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

def gerar_dicionario_notebooks(csv_path):
    print(f"🔍 Lendo base de dados: {csv_path}")
    df = pd.read_csv(csv_path)
    
    # Limpeza inicial
    df = df[df['modelo_limpo'].notna()]
    df = df[df['modelo_limpo'] != 'não identificado']
    
    # Dicionário principal: família -> conjunto de sinônimos
    dicionario = defaultdict(set)
    
    # Rastrear modelos já processados para evitar duplicatas
    processed_models = set()
    
    # Estrutura para armazenar relações entre SKUs e famílias
    sku_to_family = {}
    
    print(f"📊 Processando {len(df)} modelos...")
    
    for idx, row in df.iterrows():
        modelo_raw = str(row['modelo_limpo'])
        modelo_norm = normalize_text(modelo_raw)
        marca = normalize_text(str(row.get('marca', '')))
        
        # Pula duplicatas muito similares
        if modelo_norm in processed_models:
            continue
        processed_models.add(modelo_norm)
        
        # 1. Identifica a família do modelo
        family = extract_model_family(modelo_norm)
        
        # 2. Extrai SKUs
        skus = extract_skus_from_text(modelo_raw)
        skus.update(extract_skus_from_text(modelo_norm))
        
        # 3. Adiciona variações do nome
        variations = set()
        
        # Nome canônico da família
        variations.add(family)
        
        # Nome com marca
        if marca and marca != 'nan' and marca not in family:
            variations.add(f"{marca} {family}")
        
        # Nome original limpo
        variations.add(modelo_norm)
        
        # Nome original sem palavras comuns
        clean_name = re.sub(r'\b(?:gaming|laptop|notebook|edition)\b', '', modelo_norm).strip()
        if clean_name and clean_name != modelo_norm:
            variations.add(clean_name)
        
        # Versões abreviadas
        if ' ' in family:
            short_version = family.split()[0]  # Pega só a primeira palavra
            if len(short_version) >= 3:
                variations.add(short_version)
        
        # Adiciona todas as variações ao dicionário
        for var in variations:
            if len(var) >= 3:  # Ignora variações muito curtas
                dicionario[family].add(var)
        
        # Adiciona SKUs
        for sku in skus:
            dicionario[family].add(sku)
            sku_to_family[sku] = family
        
        # Se houver dados de arquivo NER, extrai specs adicionais
        if 'arquivo' in row and pd.notna(row['arquivo']):
            specs = extract_key_specs(str(row['arquivo']))
            if specs.get('cpu'):
                dicionario[family].add(specs['cpu'])
    
    # Pós-processamento: deduplicação e merge de famílias similares
    print("🔧 Pós-processando dicionário...")
    
    # Converte para lista e ordena
    result = {}
    for family, synonyms in dicionario.items():
        # Remove duplicatas internas
        synonyms_list = sorted(list(synonyms))
        
        # Limpa sinônimos muito curtos ou genéricos
        synonyms_list = [s for s in synonyms_list if len(s) >= 3 and s not in ['gaming', 'laptop', 'notebook']]
        
        # Adiciona família como primeiro elemento se não estiver presente
        if family not in synonyms_list:
            synonyms_list.insert(0, family)
        
        # Ordena por tamanho (menor primeiro) para melhor legibilidade
        synonyms_list.sort(key=len)
        
        if len(synonyms_list) > 1:  # Só mantém se tiver mais de um sinônimo
            result[family] = synonyms_list
    
    # Merge de famílias muito similares (ex: "legion 5" e "legion")
    families = list(result.keys())
    merged = {}
    used = set()
    
    for i, fam1 in enumerate(families):
        if fam1 in used:
            continue
        
        current_set = set(result[fam1])
        
        for fam2 in families[i+1:]:
            if fam2 in used:
                continue
            
            # Verifica se são similares
            if similarity_score(fam1, fam2) > 0.7 or fam2 in current_set or fam1 in result.get(fam2, []):
                current_set.update(result[fam2])
                used.add(fam2)
                print(f"  → Mesclando '{fam2}' em '{fam1}'")
        
        merged[fam1] = sorted(list(current_set))
        used.add(fam1)
    
    print(f"\n✅ Dicionário gerado com {len(merged)} famílias")
    
    # Estatísticas
    total_synonyms = sum(len(v) for v in merged.values())
    print(f"📊 Total de sinônimos: {total_synonyms}")
    print(f"📊 Média por família: {total_synonyms/len(merged):.1f}")
    
    return merged

def validate_dictionary(dictionary):
    """Valida o dicionário gerado e reporta problemas"""
    print("\n🔍 Validando dicionário...")
    
    issues = []
    
    for family, synonyms in dictionary.items():
        # Verifica duplicatas
        if len(synonyms) != len(set(synonyms)):
            issues.append(f"⚠️ Duplicatas em '{family}'")
        
        # Verifica se família está na lista de sinônimos
        if family not in synonyms:
            issues.append(f"⚠️ Família '{family}' não está na lista de sinônimos")
        
        # Verifica sinônimos muito curtos
        short_syns = [s for s in synonyms if len(s) < 3]
        if short_syns:
            issues.append(f"⚠️ Sinônimos muito curtos em '{family}': {short_syns}")
    
    if issues:
        print("\nProblemas encontrados:")
        for issue in issues[:10]:  # Mostra apenas os 10 primeiros
            print(f"  {issue}")
    else:
        print("✅ Validação passou sem problemas!")
    
    return len(issues) == 0

if __name__ == "__main__":
    resultado = gerar_dicionario_notebooks(CSV_PATH)
    
    # Validação
    validate_dictionary(resultado)
    
    # Salva o dicionário
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(resultado, f, indent=4, ensure_ascii=False)
    
    print(f"\n💾 Dicionário salvo em: {OUTPUT_PATH}")
    
    # Exibe alguns exemplos
    print("\n📋 Exemplos de sinônimos gerados:")
    for i, (family, synonyms) in enumerate(list(resultado.items())[:5]):
        print(f"\n{family}:")
        print(f"  → {', '.join(synonyms[:8])}{'...' if len(synonyms) > 8 else ''}")