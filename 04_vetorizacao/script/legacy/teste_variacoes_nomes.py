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
    """
    # ===== GERAR VARIAÇÕES DO NOME =====
    # 1. Nome completo (já temos)
    # 2. Nome curto: primeiras 3 palavras (ex: "Asus Vivobook 16X")
    partes = nome_modelo.split()
    nome_curto = ' '.join(partes[:3]) if len(partes) >= 3 else nome_modelo
    
    # 3. Nome sem sufixo: remove a última parte se for um código
    if len(partes) > 1:
        ultima = partes[-1]
        # Verifica se a última parte parece um código (ex: "K3605Zf")
        if re.search(r'[A-Za-z]+\d+[A-Za-z]*', ultima):
            nome_sem_sufixo = ' '.join(partes[:-1])
        else:
            nome_sem_sufixo = nome_modelo
    else:
        nome_sem_sufixo = nome_modelo
    
    # Monta o texto simulado (sem o conteúdo do problema, só o cabeçalho)
    texto = (
        f"MODEL: {nome_modelo} (also known as: {nome_curto}, {nome_sem_sufixo}). "
        f"PROBLEM: [sumário do post] ... "
        f"FAULT: [fault] ... "
        f"SOLUTIONS: [soluções] ..."
    )
    return texto

# ============================================================================
# LISTA DE EXEMPLOS DE NOMES DE MODELOS
# ============================================================================

exemplos = [
    "Asus Vivobook 16X 2023 K3605Zf Mb541Ws",
    "Dell G15 5530 15 2023",
    "Acer Nitro 5 AN515 58",
    "HP Victus 15 FB0157AX",
    "Lenovo Legion Pro 7 16IRX9",
    "Samsung Galaxy Book 3 NP750XFG",
    "MSI Katana 15 B13UDXK",
    "Apple MacBook Air 2020 M1",
    "Asus Zenbook S14 OLED UX5406SA",
    "Dell XPS 13 9305",  # sem código no final
]

print("=" * 80)
print("🧪 TESTE DE VARIAÇÕES DE NOMES DE MODELOS")
print("=" * 80)

for nome in exemplos:
    resultado = gerar_texto_embedding_exemplo(nome)
    print(f"\n📌 Nome original: {nome}")
    print(f"📝 Texto gerado:")
    print(f"   {resultado[:150]}...")
    print("-" * 60)