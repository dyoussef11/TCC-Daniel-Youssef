"""config/test_suite_loader.py - Carregamento e filtragem do dataset de testes"""

from typing import Dict, List, Optional
from dataset_avaliacaoV4 import TEST_SUITE, get_traditional_tests, get_behavioral_tests


class TestSuiteLoader:
    """
    Gerencia o carregamento e filtragem do dataset de testes.
    Permite filtrar por tipo, ID, ou comportamento esperado.
    """
    
    def __init__(self):
        self._full_suite = TEST_SUITE
        self._traditional_cache = None
        self._behavioral_cache = None
    
    @property
    def all_tests(self) -> List[Dict]:
        """Retorna todos os testes"""
        return self._full_suite
    
    @property
    def traditional_tests(self) -> List[Dict]:
        """Retorna apenas testes tradicionais (DeepEval metrics)"""
        if self._traditional_cache is None:
            self._traditional_cache = get_traditional_tests()
        return self._traditional_cache
    
    @property
    def behavioral_tests(self) -> List[Dict]:
        """Retorna apenas testes comportamentais"""
        if self._behavioral_cache is None:
            self._behavioral_cache = get_behavioral_tests()
        return self._behavioral_cache
    
    def get_by_id(self, test_id: str) -> Optional[Dict]:
        """Busca um teste específico por ID"""
        for test in self._full_suite:
            if test.get('id') == test_id:
                return test
        return None
    
    def get_by_expected_behavior(self, expected: str) -> List[Dict]:
        """Filtra testes pelo comportamento esperado"""
        return [t for t in self.behavioral_tests if t.get('expected_behavior') == expected]
    
    def get_stats(self) -> Dict:
        """Retorna estatísticas do dataset"""
        traditional_count = len(self.traditional_tests)
        behavioral_count = len(self.behavioral_tests)
        
        # Conta por tipo de comportamento
        behavioral_types = {}
        for test in self.behavioral_tests:
            behavior = test.get('expected_behavior', 'unknown')
            behavioral_types[behavior] = behavioral_types.get(behavior, 0) + 1
        
        return {
            "total": len(self._full_suite),
            "traditional": traditional_count,
            "behavioral": behavioral_count,
            "behavioral_types": behavioral_types,
            "traditional_ids": [t.get('id') for t in self.traditional_tests],
            "behavioral_ids": [t.get('id') for t in self.behavioral_tests]
        }
    
    def filter_by_sku_pattern(self, sku_pattern: str) -> List[Dict]:
        """Filtra testes que contêm um padrão de SKU específico"""
        pattern_lower = sku_pattern.lower()
        return [
            t for t in self._full_suite
            if pattern_lower in t.get('input', '').lower()
        ]
    
    def print_summary(self) -> None:
        """Imprime resumo do dataset no console"""
        stats = self.get_stats()
        print("\n📊 DATASET DE TESTES")
        print("=" * 40)
        print(f"Total de casos: {stats['total']}")
        print(f"├── Tradicionais: {stats['traditional']}")
        print(f"└── Comportamentais: {stats['behavioral']}")
        
        if stats['behavioral_types']:
            print("\n📋 Tipos de comportamento:")
            for behavior, count in stats['behavioral_types'].items():
                print(f"   ├── {behavior}: {count}")
        
        print("\n🏷️ IDs dos testes:")
        print(f"   Tradicionais: {', '.join(stats['traditional_ids'])}")
        print(f"   Comportamentais: {', '.join(stats['behavioral_ids'])}")