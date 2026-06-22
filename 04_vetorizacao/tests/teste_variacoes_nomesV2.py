#!/usr/bin/env python3
"""
teste_variacoes_nomes.py
Mostra como a função construir_texto_embedding gera variações curtas
para diferentes nomes de modelos, sem executar embedding.
"""

import re

# ============================================================================
# FUNÇÃO SIMPLIFICADA (apenas a lógica de variações)
# ============================================================================

def gerar_texto_embedding_exemplo(nome_modelo: str) -> str:
    """
    Gera o texto do embedding com variações curtas, simulando o que será usado.
    Agora com análise dinâmica do tamanho do nome.
    """
    # ===== ANÁLISE DO NOME =====
    partes = nome_modelo.split()
    total_palavras = len(partes)
    
    # ===== VARIAÇÃO CURTA =====
    # Define quantas palavras manter para a variação curta
    if total_palavras <= 3:
        # Nome curto: mantém todas
        nome_curto = nome_modelo
        palavras_curto = total_palavras
    elif total_palavras <= 5:
        # Nome médio: mantém as primeiras 3
        nome_curto = ' '.join(partes[:3])
        palavras_curto = 3
    else:
        # Nome longo: mantém as primeiras 3
        nome_curto = ' '.join(partes[:3])
        palavras_curto = 3
    
    # ===== VARIAÇÃO MÉDIA (opcional) =====
    # Para nomes longos (>5), geramos uma variação com 4 ou 5 palavras
    if total_palavras > 5:
        # Tenta com 4 palavras, se existir
        if total_palavras >= 4:
            nome_medio = ' '.join(partes[:4])
        else:
            nome_medio = nome_curto
        # Se ainda tiver mais palavras, podemos tentar 5
        if total_palavras >= 5:
            nome_medio_5 = ' '.join(partes[:5])
        else:
            nome_medio_5 = None
    else:
        nome_medio = None
        nome_medio_5 = None
    
    # ===== NOME SEM SUFIXO =====
    # Remove a última parte se for um código
    if total_palavras > 1:
        ultima = partes[-1]
        if re.search(r'[A-Za-z]+\d+[A-Za-z]*', ultima):
            nome_sem_sufixo = ' '.join(partes[:-1])
        else:
            nome_sem_sufixo = nome_modelo
    else:
        nome_sem_sufixo = nome_modelo
    
    # ===== MONTAGEM DO TEXTO COM VARIÇÕES =====
    # Constrói a lista de variações
    variacoes = [nome_curto]
    if nome_medio and nome_medio != nome_curto:
        variacoes.append(nome_medio)
    if nome_medio_5 and nome_medio_5 not in variacoes:
        variacoes.append(nome_medio_5)
    if nome_sem_sufixo and nome_sem_sufixo not in variacoes:
        variacoes.append(nome_sem_sufixo)
    
    # Remove duplicatas mantendo a ordem
    variacoes_unicas = []
    for v in variacoes:
        if v not in variacoes_unicas:
            variacoes_unicas.append(v)
    
    # Se o nome completo não estiver na lista, adiciona no início
    if nome_modelo not in variacoes_unicas:
        variacoes_unicas.insert(0, nome_modelo)
    
    # Monta a string com as variações
    variacoes_str = ", ".join(variacoes_unicas)
    
    texto = (
        f"MODEL: {nome_modelo} (also known as: {variacoes_str}). "
        f"PROBLEM: [sumário do post] ... "
        f"FAULT: [fault] ... "
        f"SOLUTIONS: [soluções] ..."
    )
    
    # Retorna também informações sobre as variações para exibição
    return texto, {
        "total_palavras": total_palavras,
        "variacoes": variacoes_unicas,
        "nome_curto": nome_curto,
        "nome_medio": nome_medio,
        "nome_medio_5": nome_medio_5,
        "nome_sem_sufixo": nome_sem_sufixo
    }

# ============================================================================
# LISTA DE EXEMPLOS DE NOMES DE MODELOS
# ============================================================================

exemplos = [
    "Asus Vivobook 16X 2023 K3605Zf Mb541Ws",  # longo
    "Dell G15 5530 15 2023",                    # médio (5)
    "Acer Nitro 5 AN515 58",                   # médio (5)
    "HP Victus 15 FB0157AX",                   # médio (5)
    "Lenovo Legion Pro 7 16IRX9",              # médio (5)
    "Samsung Galaxy Book 3 NP750XFG",          # médio (5)
    "MSI Katana 15 B13UDXK",                   # médio (5)
    "Apple MacBook Air 2020 M1",               # médio (5)
    "Asus Zenbook S14 OLED UX5406SA",          # médio (6)
    "Dell XPS 13 9305",                        # curto (4)
    "Asus Vivobook",                           # curto (2)
    "Dell",                                    # muito curto (1)
]

print("=" * 80)
print("🧪 TESTE DE VARIAÇÕES DE NOMES DE MODELOS (com análise dinâmica)")
print("=" * 80)

for nome in exemplos:
    resultado, info = gerar_texto_embedding_exemplo(nome)
    print(f"\n📌 Nome original: {nome}")
    print(f"   Total de palavras: {info['total_palavras']}")
    print(f"   Variações geradas: {info['variacoes']}")
    print(f"   Nome curto: {info['nome_curto']}")
    if info['nome_medio']:
        print(f"   Nome médio (4 palavras): {info['nome_medio']}")
    if info['nome_medio_5']:
        print(f"   Nome médio (5 palavras): {info['nome_medio_5']}")
    if info['nome_sem_sufixo'] and info['nome_sem_sufixo'] != nome:
        print(f"   Nome sem sufixo: {info['nome_sem_sufixo']}")
    print(f"📝 Texto gerado:")
    print(f"   {resultado}...")
    print("-" * 60)