"""core/behavioral_analyzer.py - Análise de testes comportamentais"""

import re
from typing import Dict, Tuple
from core.paths import VALIDACAO_SCRIPT, AVALIACAO_SCRIPT
import sys
sys.path.append(str(VALIDACAO_SCRIPT))
sys.path.append(str(AVALIACAO_SCRIPT / "eval_modules"))

from helpers import extract_sku_from_query


def check_sku_integrity(query: str, response: str) -> bool:
    target_sku = extract_sku_from_query(query)
    found_sku = extract_sku_from_query(response)
    
    # Se a query tem um SKU e a resposta cita um SKU DIFERENTE, é falha crítica (Alucinação)
    if target_sku and found_sku and target_sku.lower() != found_sku.lower():
        return False
    return True

class BehavioralTestAnalyzer:
    """Analisa testes comportamentais para ambas as versões"""
    
    def analyze(self, test_case: Dict, response_v1: str, response_v9: str) -> Tuple[bool, bool, str, str]:
        expected = test_case.get("expected_behavior", "should_admit_unavailability")
        forbidden = test_case.get("forbidden_patterns", [])
        required = test_case.get("required_patterns", [])
        
        def check(response: str) -> Tuple[bool, str]:
            resp_lower = response.casefold()
            forbidden_found = [p for p in forbidden if p.lower() in resp_lower]
            required_found = [p for p in required if p.lower() in resp_lower]
            min_required = test_case.get("min_required_matches", len(required))

            behaviors = {
            "should_admit_unavailability": lambda: (len(required_found) >= min_required) and not forbidden_found,
            "should_admit_unavailability_or_fallback": lambda: (
                (len(required_found) >= min_required) and 
                not any(sku in resp_lower for sku in ["an515-57", "an515-58", "g7 7590", "15ach6h"])
            ),
            "should_ask_for_sku": lambda: (len(required_found) >= min_required) and not forbidden_found,
            "should_explain_concept": lambda: len(required_found) >= min_required,
            "should_admit_cannot_compare": lambda: (len(required_found) >= min_required) and not forbidden_found,
            "should_acknowledge_future_or_unavailable": lambda: (len(required_found) >= min_required) and not forbidden_found,
            "should_use_internal_fallback_honestly": lambda: (len(required_found) >= min_required and not forbidden_found),
            "should_include_audit_with_tags": lambda: (re.search(r"AUDIT:", response, re.I) is not None and(re.search(r"\[RAG:", response, re.I) is not None or re.search(r"\[INTERNAL:", response, re.I) is not None)),
            "should_compare_with_fallback": lambda: len(required_found) >= min_required,
            "should_ask_for_sku_and_avoid_internal_specs": lambda: (len(required_found) >= min_required and not forbidden_found),
            "should_combine_rag_and_internal": lambda: len(required_found) >= min_required}
            
            passed = behaviors.get(expected, lambda: False)()
            reason = f"Required: {required_found[:3]}. Forbidden: {forbidden_found[:3] if forbidden_found else 'none'}"
            
            return passed, reason
        
        passed_v1, reason_v1 = check(response_v1)
        passed_v9, reason_v9 = check(response_v9)
        if not check_sku_integrity(test_case["input"], response_v9):
            passed_v9 = False
            reason_v9 += " | CRITICAL FAILURE: SKU Mismatch detected."
        
        return passed_v1, passed_v9, reason_v1, reason_v9