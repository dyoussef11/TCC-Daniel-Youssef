import json
import re
from pathlib import Path

class LimpadorModelos:
    """Carrega as regras do JSON e limpa o nome do modelo preservando SKUs."""
    def __init__(self, caminho_json: Path):
        with open(caminho_json, 'r', encoding='utf-8') as f:
            config = json.load(f)
            self.termos_genericos = config['termos_genericos']
            self.padroes_corte = config['padroes_corte']
            self.regex_corte = re.compile('|'.join(self.padroes_corte), re.IGNORECASE)

    def _normalizar_texto(self, texto: str) -> str:
        if not texto:
            return ""
        termo = re.sub(r'[^\w\s\.-]', '', texto.lower())
        termo = re.sub(r'[\s\-,/]+', '_', termo)
        termo = re.sub(r'_{2,}', '_', termo)
        return termo.strip('_')

    def extrair_modelo(self, texto: str) -> str:
        """Extrai modelo limpo preservando marca + modelo + SKU"""
        if not isinstance(texto, str) or texto.lower() == 'nan':
            return "modelo_nao_identificado"
        
        nome = texto.strip().lower()

        # ========== ABORDAGEM 1 ==========
        # Converte underscore em espaço para as regex funcionarem
        nome = nome.replace('_', ' ')
        # =================================
        
        # Aplica regex_corte (remove partes indesejadas)
        if hasattr(self, 'regex_corte') and self.regex_corte:
            nome = self.regex_corte.sub('', nome)
        
        # Identifica e remove a marca (será recolocada no final)
        marcas_conhecidas = ['acer', 'apple', 'asus', 'dell', 'hp', 'lenovo', 'msi', 
                            'samsung', 'infinix', 'avita', 'ultimus', 'walker', 'wings', 'tecno']
        marca_encontrada = None
        for marca in marcas_conhecidas:
            if nome.startswith(marca):
                marca_encontrada = marca
                nome = nome[len(marca):].lstrip(' ')
                break
        
        # Remove termos genéricos do JSON
        if hasattr(self, 'termos_genericos') and self.termos_genericos:
            for termo in self.termos_genericos:
                if isinstance(termo, str):
                    nome = re.sub(termo, '', nome, flags=re.IGNORECASE)
        
        # Remove palavras lixo específicas (com espaços)
        palavras_lixo = r'\b(laptop|notebook|computer|windows|win|home|touch|convertible|dos|graph|graphics|edition|series|gen|th|nd|rd|st)\b'
        nome = re.sub(palavras_lixo, '', nome, flags=re.IGNORECASE)
        
        # Remove especificações de hardware (agora com espaços)
        nome = re.sub(r'\b\d{1,4}\s*(gb|tb)\b', '', nome, flags=re.IGNORECASE)
        nome = re.sub(r'\b(core\s*i[3579]|amd|ryzen\s*[3579]|celeron|pentium|athlon)\s*[\d-]*[a-z]*\b', '', nome, flags=re.IGNORECASE)
        nome = re.sub(r'\b\d{1,2}th_gen\b', '', nome, flags=re.IGNORECASE)
        nome = re.sub(r'\bwin\d{1,2}[_\s]?(home|pro)?\b', '', nome, flags=re.IGNORECASE)
        nome = re.sub(r'\b(ssd|hdd|nvme|pcie)\b', '', nome, flags=re.IGNORECASE)
        
        # Limpeza de caracteres especiais e normalização
        nome = re.sub(r'[^\w\s\-]', '', nome)
        # ========== ABORDAGEM 1 (continuação) ==========
        # Converte espaços de volta para underscore
        nome = re.sub(r'\s+', '_', nome.strip())
        # ===============================================
        nome = re.sub(r'_{2,}', '_', nome)
        nome = nome.strip('_')
        
        # Recoloca a marca no início
        if marca_encontrada and nome:
            nome = f"{marca_encontrada}_{nome}"
        elif marca_encontrada:
            nome = marca_encontrada
        
        # Fallback caso ainda esteja vazio
        if not nome or len(nome) < 3:
            partes = texto.strip().lower().split('_')
            if len(partes) >= 2 and partes[0] in marcas_conhecidas:
                nome = f"{partes[0]}_{partes[1]}"
            else:
                return "modelo_nao_identificado"
        
        return nome
    
    def extrair_nome_generico(self, modelo_limpo: str, marca: str) -> str:
        """Extrai nome genérico (marca + modelo base) - SEM repetir a marca"""
        if not modelo_limpo or not isinstance(modelo_limpo, str) or modelo_limpo == "modelo_nao_identificado":
            return "modelo_nao_identificado"
        
        partes = modelo_limpo.lower().split('_')
        
        # Famílias de produtos
        familias = {
            'victus', 'pavilion', 'omen', 'envy', 'spectre', 'dragonfly', 'probook', 'elitebook', 'zbook',
            'rog', 'tuf', 'zenbook', 'vivobook', 'proart', 'expertbook', 'chromebook',
            'nitro', 'predator', 'aspire', 'swift', 'extensa', 'travelmate',
            'legion', 'ideapad', 'thinkpad', 'yoga', 'thinkbook', 'loq',
            'alienware', 'xps', 'inspiron', 'latitude', 'precision', 'vostro',
            'stealth', 'katana', 'modern', 'thin', 'creator', 'summit', 'cyborg', 'sword', 'pulse',
            'galaxy_book', 'macbook', 'inbook', 'zerobook', 'nuvobook', 'megabook'
        }
        
        resultado = []
        
        # Encontra a marca (pode ser o primeiro elemento ou vir do parâmetro)
        marca_limpa = marca.lower() if marca else (partes[0] if partes else "")
        if marca_limpa and marca_limpa not in resultado:
            resultado.append(marca_limpa)
        
        # Encontra a família principal (pula a marca)
        familia_encontrada = None
        for i, p in enumerate(partes):
            if p in familias:
                familia_encontrada = p
                resultado.append(p)
                # Verifica se há um número de série/size após a família
                if i + 1 < len(partes):
                    prox = partes[i + 1]
                    # Números como 15, 16, 14 (tamanho de tela)
                    if prox.isdigit() and len(prox) <= 2:
                        resultado.append(prox)
                break
        
        # Se não encontrou família, usa o segundo elemento (se existir e não for marca)
        if not familia_encontrada and len(partes) >= 2:
            if partes[1] not in ['laptop', 'notebook'] and len(partes[1]) >= 2:
                resultado.append(partes[1])
        
        # Remove duplicatas (ex: hp_hp, acer_acer)
        resultado_limpo = []
        for item in resultado:
            if item not in resultado_limpo:
                resultado_limpo.append(item)
        
        # Garante que temos pelo menos a marca
        if len(resultado_limpo) < 2:
            if len(partes) > 1 and partes[1] not in resultado_limpo:
                resultado_limpo.append(partes[1])
            else:
                resultado_limpo.append("modelo")
        
        return "_".join(resultado_limpo).lower()
    
    def extrair_modelo_pesquisa(self, modelo_limpo: str) -> str:
        if not modelo_limpo or not isinstance(modelo_limpo, str) or modelo_limpo == "modelo_nao_identificado":
            return "modelo não identificado"
        
        partes = modelo_limpo.split('_')
        if len(partes) <= 1:
            return modelo_limpo.replace('_', ' ')

        resultado = [partes[0]]
        for p in partes[1:]:
            is_serie = any(char.isdigit() for char in p) and len(p) <= 6
            is_familia = p in ['omen', 'legion', 'victus', 'thin', 'pavilion', 'probook', 'nitro', 'tuf']
            
            if is_serie or is_familia:
                resultado.append(p)
                if len(resultado) >= 3: 
                    break
            elif len(resultado) < 2: 
                resultado.append(p)
            else:
                break
                
        return " ".join(resultado).strip()
    
    def extrair_sku(self, modelo_limpo: str) -> str:
        """Extrai apenas o código SKU/número de série do modelo"""
        if not modelo_limpo or modelo_limpo == "modelo_nao_identificado":
            return ""
        
        # Remove a marca do início
        marcas = ['acer_', 'apple_', 'asus_', 'dell_', 'hp_', 'lenovo_', 'msi_', 
                'samsung_', 'infinix_', 'avita_', 'ultimus_', 'walker_', 'wings_', 'tecno_']
        
        nome = modelo_limpo.lower()
        for marca in marcas:
            if nome.startswith(marca):
                nome = nome[len(marca):]
                break
        
        # Padrões comuns de SKU:
        # - números com letras: fx506hf, anv15_51, 82k101gsin
        # - números com hífen: 15-fb0157ax
        # - letras + números: g15_5530, 82kda01bih
        
        # Tenta encontrar um padrão de SKU (sequência alfanumérica com 4+ caracteres)
        padrao_sku = r'([a-z]?\d+[a-z-]+\d+|[a-z]+\d{2,}[a-z]*|\d+[a-z]+\d+|[a-z]{2,}\d{2,})'
        
        match = re.search(padrao_sku, nome)
        if match:
            return match.group(1)
        
        # Fallback: retorna tudo após a família
        familias = ['victus', 'pavilion', 'omen', 'envy', 'rog', 'tuf', 'zenbook', 'vivobook',
                    'nitro', 'predator', 'aspire', 'legion', 'ideapad', 'thinkpad', 'yoga',
                    'alienware', 'xps', 'inspiron', 'inspiron', 'stealth', 'katana', 'modern']
        
        for familia in familias:
            if familia in nome:
                partes = nome.split(familia)
                if len(partes) > 1:
                    return f"{familia}{partes[1]}".strip('_')
        
        return nome