import re



def extrair_modelo_curto(texto):
    if not isinstance(texto, str):
        return ""
    
    nome = texto.strip()

    # 1. Remover termos genéricos, mas PRESERVAR "Gaming"
    termos_genericos = [
        r'\blaptop\b', r'\bnotebook\b', 
        r'\bultrabook\b', r'\bbrand new\b'
    ]
    for termo in termos_genericos:
        nome = re.sub(termo, '', nome, flags=re.IGNORECASE).strip()

    # 2. Padrões de CORTE (Onde o nome termina e a spec técnica começa)
    padroes_corte = [
        r'\s*\(',                          # Parênteses
        r'\s*\[',                          # Colchetes
        r'\b\d{1,2}th\s+gen\b',            # Ex: 12th Gen
        r'\bintel\b', r'\bamd\b',          # Marcas de chips
        r'\bnvidia\b', r'\bradeon\b',      
        r'\bgeforce\b', r'\brtx\b', r'\bgtx\b',
        r'core\s+i\d', r'ryzen\s+\d',                     
        r'\b\d+\s?gb\b',                   # RAM
        r'\b\d+\s?tb\b',                   # Armazenamento
        r'win(?:dows)?\s?\d+',             # OS
        r'\bwith\b',                       # Marketing
        r'\bbattery\b',
        r'\b\d+\.?\d*["\s-]*inch\b',       # Tela
        r'\bai\s+powered\b', r'\bai\s+pc\b',
        r'\bdual\b', r'\bhexa\b', r'\bocta\b', r'\bquad\b', r'\bcore\b',
        r'\s+-\s+'                         # Separador
    ]
    
    regex_corte = re.compile('|'.join(padroes_corte), re.IGNORECASE)
    match = regex_corte.search(nome)
    
    if match:
        nome = nome[:match.start()].strip()
    
    # 3. Limpeza final
    nome = re.sub(r'[\s\-,/]+$', '', nome) 
    nome = re.sub(r'\s+', ' ', nome)      
    
    return nome.strip()

# Amostra de modelos extraídos dos seus CSVs (Lista completa no arquivo gerado)
laptops_para_teste = [
    "HP Victus 15-fb0157AX Gaming Laptop (AMD Ryzen 5 5600H/ 8GB/ 512GB SSD)",
    "Asus Vivobook 16 2023 M1605YA-MB541WS Laptop (Ryzen 5 7530U)",
    "Acer Nitro 5 AN515-47 NH.QL3SI.003 Gaming Laptop",
    "Dell G7 15 7588",
    "MSI Stealth GS77 12UHS-226IN",
    "Apple MacBook Air 2020 MGND3HN Laptop",
    "Infinix Zero Book Ultra Laptop (Intel Core i9)",
    "ASUS ROG Strix G15 Advantage Edition with 90Whr Battery",
    "Lenovo V15 ITL G2 82KBA033IH Laptop",
    "AGB Octev GA-9009 Gaming Laptop",
    "ALIENWARE Intel Core i9 10th Gen 10980HK - (32 GB/1 TB ...",
    "ASUS ROG Strix G16 Intel Core i9 14th Gen 14900HX - (16...",
    "ASUS TUF Gaming A15 AMD Ryzen 7 Octa Core 7435HS",
    "Acer Aspire 7 Intel Core i5 13th Gen 13420H",
    "Acer Predator Helios 500 Ph517-52",
    "Dell Inspiron 3520 Laptop",
    "HP Pavilion Gaming 15",
    "Lenovo LOQ Intel Core i5 12th Gen 12450HX",
    "MSI Titan GT77 HX 13VI-092IN",
    "Samsung Odyssey Z"
    # ... (Acesse o arquivo lista_completa_laptops.py para os outros 2.395 nomes)
]

print(f"{'ORIGINAL':<65} | {'RESULTADO'}")
print("-" * 100)
for original in laptops_para_teste:
    print(f"{original[:63]:<65} | {extrair_modelo_curto(original)}")
    print(f"{original[:63]:<65} | {extrair_modelo_curto(original)}")