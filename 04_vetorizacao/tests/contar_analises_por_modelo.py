#!/usr/bin/env python3
"""
contar_analises_por_modelo.py
Conta quantos posts (documentos) existem por modelo na base vetorizada.
Baseia-se no campo 'model' extraído dos metadados.
"""

import json
from pathlib import Path
from collections import Counter
from core.paths import VETORIZATION_DATA
# ============================================================================
# CONFIGURAÇÃO
# ============================================================================
META_PATH = VETORIZATION_DATA / "base_conhecimento_multilingueV9.meta.json"

# ============================================================================
# CARREGAMENTO
# ============================================================================

def carregar_metadados() -> list:
    if not META_PATH.exists():
        raise FileNotFoundError(f"❌ Metadados não encontrados: {META_PATH}")
    with open(META_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

# ============================================================================
# CONTAGEM
# ============================================================================

def contar_por_modelo(metadados: list) -> dict:
    """
    Retorna um dicionário com a contagem de documentos por modelo.
    """
    modelos = []
    for item in metadados:
        meta = item.get('metadata', {})
        modelo = meta.get('model', 'Desconhecido')
        modelos.append(modelo)
    return dict(Counter(modelos))

def exibir_contagem(contagem: dict, top_n: int = 20):
    print("=" * 60)
    print(f"📊 CONTAGEM DE DOCUMENTOS POR MODELO (total: {sum(contagem.values())})")
    print("=" * 60)
    # Ordena do mais frequente para o menos
    ordenados = sorted(contagem.items(), key=lambda x: x[1], reverse=True)
    for i, (modelo, qtd) in enumerate(ordenados[:top_n], start=1):
        print(f"{i:3d}. {modelo[:50]:50} {qtd:5d}")
    if len(ordenados) > top_n:
        print(f"... e mais {len(ordenados) - top_n} modelos.")

def salvar_csv(contagem: dict, output_dir: Path):
    import pandas as pd
    output_dir.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(list(contagem.items()), columns=["modelo", "quantidade"])
    df = df.sort_values("quantidade", ascending=False)
    csv_path = output_dir / "contagem_por_modelo.csv"
    df.to_csv(csv_path, index=False, encoding='utf-8-sig')
    print(f"✅ CSV salvo em: {csv_path}")

# ============================================================================
# MAIN
# ============================================================================

def main():
    try:
        print("🚀 Carregando metadados...")
        metadados = carregar_metadados()
        print(f"✅ Total de documentos: {len(metadados)}")
        
        contagem = contar_por_modelo(metadados)
        exibir_contagem(contagem)
        
        # Opcional: salvar em CSV
        output_dir = Path("04_vetorizacao/tests/resultados_sematicos")
        salvar_csv(contagem, output_dir)
        
    except Exception as e:
        print(f"❌ Erro: {e}")

if __name__ == "__main__":
    main()