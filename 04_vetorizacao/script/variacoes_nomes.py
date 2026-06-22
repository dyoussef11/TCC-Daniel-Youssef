#!/usr/bin/env python3
"""
variacoes_nomes.py
Funções para gerar variações curtas de nomes de modelos, para enriquecer embeddings.
"""

import re
from typing import Dict, List, Optional

def gerar_variacoes_nome(nome_modelo: str) -> Dict[str, str]:
    """
    Gera variações do nome do modelo para melhorar a recuperação.

    Args:
        nome_modelo: Nome completo do modelo (ex: "Asus Vivobook 16X 2023 K3605Zf Mb541Ws")

    Returns:
        Dicionário com as variações:
        - 'completo': nome original
        - 'curto': primeiras 3 palavras (ex: "Asus Vivobook 16X")
        - 'sem_sufixo': remove o último código (ex: "Asus Vivobook 16X 2023 K3605Zf")
        - 'marca_linha': marca + linha (ex: "Asus Vivobook")
        - 'modelo_curto': sem ano e sem sufixo (ex: "Vivobook 16X")
    """
    if not nome_modelo:
        return {
            'completo': '',
            'curto': '',
            'sem_sufixo': '',
            'marca_linha': '',
            'modelo_curto': ''
        }

    partes = nome_modelo.split()
    num_palavras = len(partes)

    # 1. Nome curto: primeiras 3 palavras
    nome_curto = ' '.join(partes[:3]) if num_palavras >= 3 else nome_modelo

    # 2. Nome sem sufixo: remove última parte se for código
    nome_sem_sufixo = nome_modelo
    if num_palavras > 1:
        ultima = partes[-1]
        # Detecta código: letras + números + letras (ex: K3605Zf, 16IRX9)
        if re.search(r'[A-Za-z]+\d+[A-Za-z]*', ultima) or re.search(r'\d+[A-Z]+\d*', ultima):
            nome_sem_sufixo = ' '.join(partes[:-1])

    # 3. Marca + linha: primeiras 2 palavras (marca + nome da linha)
    marca_linha = ' '.join(partes[:2]) if num_palavras >= 2 else nome_modelo

    # 4. Modelo curto: sem a marca e sem sufixo (remover primeira palavra se for marca)
    modelo_curto = ''
    if num_palavras >= 2:
        # Tenta remover a marca (primeira palavra) e depois aplicar sem sufixo
        sem_marca = ' '.join(partes[1:])
        # Remove sufixo se houver
        if sem_marca:
            ultima_sem_marca = sem_marca.split()[-1]
            if re.search(r'[A-Za-z]+\d+[A-Za-z]*', ultima_sem_marca) or re.search(r'\d+[A-Z]+\d*', ultima_sem_marca):
                modelo_curto = ' '.join(sem_marca.split()[:-1])
            else:
                modelo_curto = sem_marca

    # Se modelo_curto ficou vazio, usa o nome_curto sem a marca
    if not modelo_curto and num_palavras >= 2:
        modelo_curto = ' '.join(partes[1:3])  # linha + tamanho

    return {
        'completo': nome_modelo,
        'curto': nome_curto,
        'sem_sufixo': nome_sem_sufixo,
        'marca_linha': marca_linha,
        'modelo_curto': modelo_curto
    }

def construir_texto_embedding(post: Dict, nome_modelo: str, 
                             incluir_summary: bool = True,
                             incluir_fault: bool = True,
                             incluir_solucoes: bool = True) -> str:
    """
    Constrói o texto final para embedding, incluindo variações do nome.

    Args:
        post: Dicionário do post com 'analise_ia'
        nome_modelo: Nome completo do modelo (já tratado com marca)
        incluir_summary: Incluir sumário no texto
        incluir_fault: Incluir fault no texto
        incluir_solucoes: Incluir soluções no texto

    Returns:
        Texto pronto para embedding.
    """
    analise = post.get('analise_ia', {})
    if not analise:
        return ""

    # Gera variações
    variacoes = gerar_variacoes_nome(nome_modelo)

    # Monta a parte do nome com variações
    nome_variacoes = (
        f"MODEL: {variacoes['completo']} (also known as: "
        f"{variacoes['curto']}, {variacoes['sem_sufixo']}, "
        f"{variacoes['marca_linha']}, {variacoes['modelo_curto']})."
    )

    # Partes opcionais
    partes_texto = [nome_variacoes]

    if incluir_summary:
        summary = analise.get('summary', '')
        if summary:
            partes_texto.append(f"PROBLEM: {summary}.")

    if incluir_fault:
        # Usa a função já existente (assumindo que está disponível)
        try:
            from mapeamento_modelos import extrair_fault_limpo
            fault = extrair_fault_limpo(analise.get('detected_fault', 'None'))
        except ImportError:
            # Fallback
            fault = analise.get('detected_fault', 'None')
            if fault and len(fault) > 100:
                fault = fault[:97] + "..."
        if fault:
            partes_texto.append(f"FAULT: {fault}.")

    if incluir_solucoes:
        solucoes = analise.get('suggested_solution', [])
        if solucoes:
            if isinstance(solucoes, str):
                solucoes = [solucoes]
            elif isinstance(solucoes, list):
                solucoes = [str(s) for s in solucoes[:3]]
            solucoes_str = " | ".join(solucoes[:3])
            if solucoes_str:
                partes_texto.append(f"SOLUTIONS: {solucoes_str}.")

    return ' '.join(partes_texto)

# ============================================================================
# TESTE RÁPIDO (se executar diretamente)
# ============================================================================

if __name__ == "__main__":
    # Teste com um post simulado
    post_teste = {
        'analise_ia': {
            'summary': 'User reports fan noise on Asus Vivobook 16X',
            'detected_fault': 'Fan bearing failure',
            'suggested_solution': ['Replace fan', 'Clean heatsink']
        }
    }
    nome_teste = "Asus Vivobook 16X 2023 K3605Zf Mb541Ws"
    resultado = construir_texto_embedding(post_teste, nome_teste)
    print("🧪 Teste do módulo variacoes_nomes:")
    print(resultado)