# query_expansion.py - VERSÃO CORRIGIDA COM SKU DETECTION

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class QueryExpander:
    """
    Expande queries usando dicionário hierárquico.
    Só expande queries SEM SKU específico.
    """
    
    def __init__(self, 
                 hierarchical_path: Optional[Path] = None,
                 flat_dict_path: Optional[Path] = None,
                 max_terms: int = 5,
                 variant: str = "vanilla"):
        
        self.max_terms = max_terms
        self.variant = variant  # 'vanilla' ou 'temporal'
        
        # Carrega dicionário hierárquico
        self.hierarchical = {}
        if hierarchical_path:
            self._load_hierarchical(hierarchical_path)
        
        # Fallback para flat (se necessário)
        self.flat_dict = {}
        if flat_dict_path:
            self._load_flat(flat_dict_path)
    
    def _load_hierarchical(self, path: Path) -> None:
        """Carrega dicionário hierárquico."""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                self.hierarchical = json.load(f)
            print(f"✅ Dicionário hierárquico carregado: {len(self.hierarchical)} marcas")
        except Exception as e:
            print(f"⚠️ Erro ao carregar dicionário hierárquico: {e}")
    
    def _load_flat(self, path: Path) -> None:
        """Carrega dicionário flat (fallback)."""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                self.flat_dict = json.load(f)
            print(f"✅ Dicionário flat carregado: {len(self.flat_dict)} entradas")
        except Exception as e:
            print(f"⚠️ Erro ao carregar dicionário flat: {e}")
    
    def has_exact_sku(self, query: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Verifica se a query já contém um SKU específico.
        Retorna (tem_sku, sku, marca)
        """
        query_lower = query.lower()
        
        # ⭐ 1. Primeiro: padrões de SKU específico (com números)
        sku_patterns = [
            r'[A-Z]{2,3}[-]?\d{3}[-]?\d{2,4}',     # AN515-56, AN515-57-7447
            r'\d{2,4}[A-Z]{2,4}',                   # 15ACH6, 15IRX9
            r'[A-Z]{2,3}\s\d{3}\s\d{4}',            # G7 7588, XPS 15 9500
            r'[a-z]+\s\d{1,2}[a-z]?\s?\d{4}[a-z]?', # Legion 5 15ACH6
            r'[a-z]{3,4}\d{4}',                     # fa5075, gv301
            r'82[a-z0-9]{4}',                       # 82k2022xin (Lenovo)
            r'83[a-z0-9]{4}',                       # 83jj000din (Lenovo)
            r'g7\s*7588',                           # G7 7588
            r'xps\s*15\s*9500',                     # XPS 15 9500
        ]
        
        for pattern in sku_patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                sku = match.group(0)
                # Verifica se parece um SKU real (tem números)
                if re.search(r'\d', sku):
                    print(f"   🔍 SKU detectado pelo padrão '{pattern}': {sku}")
                    return True, sku, None
        
        # ⭐ 2. Verifica termos que são claramente SKUs (NÃO genéricos)
        non_generic_terms = [
            '15ach6', '15ach6h', '15iah7', '15arp8', '15imh6', '15ith6',  # Lenovo
            'an515-56', 'an515-57', 'an515-58', 'an515-46', 'an515-47',    # Acer
            'g7 7588', 'g7 7590', 'g15 5510', 'g15 5520',                   # Dell
            'fa5075', 'fx507', 'gv301', 'gz301',                             # ASUS
            'victus 15-fa', 'victus 16-d',                                   # HP
        ]
        
        for term in non_generic_terms:
            if term in query_lower:
                print(f"   🔍 SKU detectado (termo específico): {term}")
                return True, term.upper(), None
        
        return False, None, None
    
    # query_expansion.py - Adicione este método

    def has_specific_sku(self, query: str) -> bool:
        """
        Verifica se a query contém um SKU específico.
        Retorna True se encontrar qualquer padrão de SKU.
        """
        query_lower = query.lower()
        
        # Lista de SKUs conhecidos (para detecção rápida)
        known_skus = [
            # Lenovo Legion
            '15ach6', '15ach6h', '15iah7', '15arp8', '15imh6', '15ith6',
            '15irx9', '15irx10', '15iax10', '16irx9', '16irx8',
            
            # Acer Nitro
            'an515-56', 'an515-57', 'an515-58', 'an515-46', 'an515-47',
            'an515-45', 'an515-51',
            
            # Dell
            'g7 7588', 'g7 7590', 'g15 5510', 'g15 5511', 'g15 5515',
            'g15 5520', 'g15 5525', 'g15 5530', 'xps 15 9500', 'xps 15 9520',
            
            # ASUS
            'fx507', 'fa507', 'gv301', 'gz301', 'ga402', 'gu603',
            
            # HP
            'victus 15-fa', 'victus 16-d', 'omen 16-wf',
        ]
        
        for sku in known_skus:
            if sku in query_lower:
                print(f"   🔒 SKU conhecido detectado: {sku}")
                return True
        
        # Padrões regex para SKU
        sku_patterns = [
            r'[A-Z]{2,3}[-]?\d{3}[-]?\d{2,4}',     # AN515-56, AN515-57-7447
            r'\d{2,4}[A-Z]{2,4}',                   # 15ACH6, 16IRX9
            r'[A-Z]{2,3}\s\d{3}\s\d{4}',            # G7 7588, XPS 15 9500
            r'[a-z]+\s\d{1,2}[a-z]?\s?\d{4}[a-z]?', # Legion 5 15ACH6
            r'[a-z]{3,4}\d{4}',                     # fa5075, gv301
            r'82[a-z0-9]{4}',                       # 82k2022xin (Lenovo)
            r'83[a-z0-9]{4}',                       # 83jj000din (Lenovo)
            r'g7\s*7588',                           # G7 7588
            r'xps\s*15\s*9500',                     # XPS 15 9500
            r'pavilion\s*15-ec\d{4}',               # Pavilion 15-ec9999
        ]
        
        for pattern in sku_patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                sku = match.group(0)
                print(f"   🔒 SKU detectado pelo padrão: {sku}")
                return True
        
        # Verifica se a query tem padrão de "modelo + número" (ex: "Nitro 5" não é SKU)
        # Mas "Nitro 5 AN515-56" tem SKU
        if re.search(r'[A-Z]{2,3}\d{3}', query, re.IGNORECASE):
            print(f"   🔒 Padrão de SKU detectado (letras+números)")
            return True
        
        return False
    
    def get_synonyms_for_expansion(self, brand: str, family: str, subfamily: str) -> List[str]:
        """
        Retorna sinônimos para expansão (APENAS termos GENÉRICOS).
        """
        synonyms = []
        
        # ⭐ Mapeamento manual para termos genéricos (recomendado)
        manual_synonyms = {
            ('acer', 'nitro', '5'): [
                'acer nitro 5',
                'nitro 5 gaming',
                'acer nitro series'
            ],
            ('acer', 'nitro', 'base'): [
                'acer nitro',
                'nitro gaming'
            ],
            ('dell', 'g_series', '15'): [
                'dell g15',
                'dell g series 15',
                'g15 gaming laptop'
            ],
            ('dell', 'g_series', 'base'): [
                'dell g series',
                'g series gaming'
            ],
            ('lenovo', 'legion', '5'): [
                'lenovo legion 5',
                'legion 5 gaming',
                'lenovo legion series'
            ],
            ('lenovo', 'legion', 'base'): [
                'lenovo legion',
                'legion gaming'
            ],
            ('hp', 'victus', '15'): [
                'hp victus 15',
                'victus 15 gaming'
            ],
            ('hp', 'victus', 'base'): [
                'hp victus',
                'victus gaming'
            ],
            ('asus', 'tuf', 'f15'): [
                'asus tuf f15',
                'tuf gaming f15'
            ],
            ('asus', 'tuf', 'a15'): [
                'asus tuf a15',
                'tuf gaming a15'
            ],
            ('asus', 'tuf', 'base'): [
                'asus tuf',
                'tuf gaming'
            ],
            ('msi', 'thin', 'base'): [
                'msi thin',
                'thin gaming'
            ],
            ('msi', 'katana', 'base'): [
                'msi katana',
                'katana gaming'
            ],
        }
        
        key = (brand, family, subfamily)
        if key in manual_synonyms:
            return manual_synonyms[key][:self.max_terms]
        
        # Busca no dicionário hierárquico (com filtro rigoroso)
        if brand in self.hierarchical:
            if family in self.hierarchical[brand]:
                if subfamily in self.hierarchical[brand][family]:
                    items = self.hierarchical[brand][family][subfamily]
                    
                    for item in items:
                        # ⭐ SÓ ADICIONA se NÃO parecer um SKU específico
                        if self._is_generic_term(item):
                            if item not in synonyms and item != subfamily:
                                synonyms.append(item)
        
        # Remove duplicatas e limita
        synonyms = list(dict.fromkeys(synonyms))[:self.max_terms]
        
        return synonyms

    def _is_generic_term(self, term: str) -> bool:
        """Verifica se um termo é genérico (não é SKU específico)."""
        term_lower = term.lower()
        
        # ⭐ Termos que são claramente SKUs específicos (com números e hífens)
        if re.search(r'[a-z]{2,3}[-]?\d{3}[-]?\d{2,4}', term_lower):
            return False
        
        if re.search(r'\d{4}[a-z]{2,4}', term_lower):  # 15ACH6
            return False
        
        if re.search(r'[a-z]{3}\d{4}', term_lower):    # fa5075
            return False
        
        if re.search(r'82[a-z0-9]{4}', term_lower):    # 82k2022xin
            return False
        
        # ⭐ Termos genéricos permitidos
        generic_terms = [
            'acer nitro 5', 'nitro 5 gaming', 'acer nitro',
            'lenovo legion 5', 'legion 5 gaming', 'lenovo legion',
            'dell g15', 'g15 gaming', 'dell g series',
            'asus tuf', 'tuf gaming', 'asus tuf f15', 'asus tuf a15',
            'hp victus', 'victus gaming', 'hp victus 15',
            'msi thin', 'thin gaming', 'msi katana', 'katana gaming',
            'nitro 5', 'legion 5', 'victus 15', 'omen 16'
        ]
        
        if term_lower in generic_terms:
            return True
        
        # Termos muito curtos ou genéricos
        if len(term.split()) <= 3 and not re.search(r'\d', term):
            return True
        
        return False

    def extract_brand_and_family(self, query: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Extrai marca, família e subfamília da query para expansão.
        """
        query_lower = query.lower()
        
        # ⭐ Verificações manuais prioritárias (resolvem conflitos)
        manual_mappings = [
            (r'acer.*nitro', 'acer', 'nitro', '5'),
            (r'nitro 5(?!.*acer)', 'acer', 'nitro', '5'),
            (r'lenovo.*legion', 'lenovo', 'legion', '5'),
            (r'legion 5(?!.*lenovo)', 'lenovo', 'legion', '5'),
            (r'hp.*victus', 'hp', 'victus', '15'),
            (r'victus(?!.*hp)', 'hp', 'victus', '15'),
            (r'dell.*g7', 'dell', 'g_series', '15'),
            (r'g7\s*7588', 'dell', 'g_series', '15'),
            (r'asus.*tuf', 'asus', 'tuf', 'base'),
            (r'tuf(?!.*asus)', 'asus', 'tuf', 'base'),
            (r'msi.*thin', 'msi', 'thin', 'base'),
            (r'msi.*katana', 'msi', 'katana', 'base'),
        ]
        
        for pattern, brand, family, subfamily in manual_mappings:
            if re.search(pattern, query_lower):
                return brand, family, subfamily
        
        # ⭐ Busca no dicionário hierárquico
        brand_priority = ['acer', 'lenovo', 'asus', 'dell', 'hp', 'msi']
        
        for brand in brand_priority:
            if brand in self.hierarchical:
                for family, subfamilies in self.hierarchical[brand].items():
                    family_readable = family.replace('_', ' ')
                    
                    if family_readable in query_lower:
                        for subfamily_name, items in subfamilies.items():
                            subfamily_readable = subfamily_name.replace('_', ' ')
                            if subfamily_readable in query_lower and subfamily_readable != 'base':
                                return brand, family, subfamily_name
        
        # ⭐ Tenta detectar apenas pela marca
        for brand in brand_priority:
            if brand in query_lower:
                # Marca detectada, mas família não - retorna genérico
                if brand == 'acer':
                    return brand, 'nitro', '5'
                elif brand == 'lenovo':
                    return brand, 'legion', '5'
                elif brand == 'dell':
                    return brand, 'g_series', '15'
                elif brand == 'hp':
                    return brand, 'victus', '15'
                elif brand == 'asus':
                    return brand, 'tuf', 'base'
        
        return None, None, None
    
    def expand_query(self, query: str) -> str:
        """
        Expande query usando dicionário hierárquico.
        ⭐ Só expande se NÃO houver SKU específico!
        """
        # ⭐ VERIFICAÇÃO FORTE: Se tem SKU, NÃO expande
        if self.has_specific_sku(query):
            print(f"   🚫 SKU detectado - expansão CANCELADA")
            return query
        
        # Para V9 (temporal), verifica também números
        if self.variant == "temporal":
            # Verifica se a query tem padrão de modelo com números
            if re.search(r'\b[A-Za-z]*\d{3,}[A-Za-z]*\b', query):
                print(f"   🚫 Padrão de modelo detectado - expansão CANCELADA")
                return query
        
        # Extrai marca e família para expansão
        brand, family, subfamily = self.extract_brand_and_family(query)
        
        if not brand or not family:
            return query
        
        # Obtém sinônimos da mesma subfamília
        synonyms = self.get_synonyms_for_expansion(brand, family, subfamily)
        
        if not synonyms:
            return query
        
        # Constrói query expandida
        new_terms = []
        query_lower = query.lower()
        
        for term in synonyms:
            term_lower = term.lower()
            if term_lower not in query_lower and len(term) >= 3:
                # ⭐ Verifica se o termo não contém SKU
                if not self.has_specific_sku(term):
                    new_terms.append(term)
        
        new_terms = new_terms[:self.max_terms]
        
        if new_terms:
            expanded = f"{query} {' '.join(new_terms)}"
            print(f"   🔧 Expansão: +{len(new_terms)} termos")
            print(f"   📝 Termos adicionados: {new_terms}")
            return expanded
        
        return query
    
    def debug_query(self, query: str) -> Dict:
        """Debug: mostra o que seria adicionado."""
        has_sku, sku, brand = self.has_exact_sku(query)
        
        if has_sku:
            return {
                "query": query,
                "has_sku": True,
                "sku": sku,
                "brand": brand,
                "will_expand": False,
                "reason": f"SKU específico detectado: {sku}"
            }
        
        # Verifica se tem números
        if self.variant == "temporal" and re.search(r'\d{3,}', query):
            return {
                "query": query,
                "has_sku": True,
                "sku": "números detectados",
                "brand": None,
                "will_expand": False,
                "reason": "Números detectados na query (possível SKU)"
            }
        
        brand, family, subfamily = self.extract_brand_and_family(query)
        
        if not brand or not family:
            return {
                "query": query,
                "has_sku": False,
                "brand": brand,
                "family": family,
                "will_expand": False,
                "reason": "Família não identificada"
            }
        
        synonyms = self.get_synonyms_for_expansion(brand, family, subfamily)
        
        return {
            "query": query,
            "has_sku": False,
            "brand": brand,
            "family": family,
            "subfamily": subfamily,
            "will_expand": len(synonyms) > 0,
            "synonyms": synonyms[:self.max_terms],
            "expanded": self.expand_query(query) if synonyms else query
        }