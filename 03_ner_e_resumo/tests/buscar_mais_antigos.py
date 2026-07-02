#!/usr/bin/env python3
"""
buscar_mais_antigos.py
Lista os posts mais antigos da base vetorizada a partir do arquivo .meta.json.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

# === CONFIGURAÇÃO ===
META_PATH = Path("./04_vetorizacao/data/base_conhecimento_multilingueV9.meta.json")
TOP_N = 580                   # quantos registros exibir
ORDENAR_POR = "data_post_original"   # ou "data_processamento" ou "date_iso"
SAIR_CSV = Path("03_ner_e_resumo/tests/resultados_busca_antigos/mais_antigos.csv")  # opcional: salvar em CSV

def carregar_metadados(caminho: Path) -> List[Dict]:
    """Carrega o arquivo .meta.json."""
    with open(caminho, 'r', encoding='utf-8') as f:
        return json.load(f)

def extrair_data(registro: Dict, chave: str) -> Optional[datetime]:
    """
    Extrai a data do registro, tratando formatos ISO ou strings vazias.
    Retorna None se a data for inválida ou ausente.
    """
    # Primeiro, tenta obter do campo metadata[chave]
    data_str = registro.get('metadata', {}).get(chave)
    if not data_str:
        # Fallback para 'date_iso' do nível superior
        if chave == 'date_iso':
            data_str = registro.get('date_iso')
        else:
            return None

    if not data_str or data_str.lower() in ('none', 'null', ''):
        return None

    # Tenta parsear formatos comuns
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d"):
        try:
            return datetime.strptime(data_str, fmt)
        except ValueError:
            continue
    # Se não conseguir, retorna None
    return None

def formatar_solucoes(solucoes) -> str:
    """Converte lista de soluções em string legível."""
    if not solucoes:
        return "N/A"
    if isinstance(solucoes, list):
        return "; ".join(solucoes[:3])
    return str(solucoes)

def main():
    if not META_PATH.exists():
        print(f"❌ Arquivo não encontrado: {META_PATH}")
        return

    print(f"📂 Carregando metadados de {META_PATH}...")
    dados = carregar_metadados(META_PATH)
    print(f"✅ Total de registros: {len(dados)}")

    # Filtrar registros que possuem a data desejada
    registros_com_data = []
    for reg in dados:
        dt = extrair_data(reg, ORDENAR_POR)
        if dt is not None:
            registros_com_data.append((dt, reg))

    if not registros_com_data:
        print(f"⚠️ Nenhum registro com data válida no campo '{ORDENAR_POR}'.")
        return

    # Ordenar do mais antigo para o mais recente
    registros_com_data.sort(key=lambda x: x[0])
    # mais_antigos = registros_com_data[:TOP_N]
    mais_antigos = registros_com_data

    print(f"\n📅 Os {TOP_N} posts mais antigos (ordenados por '{ORDENAR_POR}'):")
    print("=" * 80)

    resultados = []
    for i, (data, reg) in enumerate(mais_antigos, start=1):
        meta = reg.get('metadata', {})
        # Campos de interesse
        model = meta.get('model', 'Desconhecido')
        summary = meta.get('summary', 'Sem resumo')
        fault = meta.get('fault', 'Sem falha')
        solutions = formatar_solucoes(meta.get('solutions', []))
        data_post = meta.get('data_post_original', 'N/A')
        data_proc = meta.get('data_processamento', 'N/A')

        print(f"\n🔹 #{i} – {data.strftime('%Y-%m-%d')}")
        print(f"   Modelo : {model}")
        print(f"   Post ID: {reg.get('id', 'N/A')}")
        print(f"   Data original: {data_post}")
        print(f"   Data processamento: {data_proc}")
        print(f"   Resumo (summary): {summary[:200]}{'...' if len(summary)>200 else ''}")
        print(f"   Falha (fault): {fault}")
        print(f"   Soluções: {solutions}")
        print(f"   Texto completo (original_text): {reg.get('original_text', '')[:300]}...")

        resultados.append({
            'posicao': i,
            'data_ordenacao': data.isoformat(),
            'id': reg.get('id'),
            'modelo': model,
            'data_post_original': data_post,
            'data_processamento': data_proc,
            'summary': summary,
            'fault': fault,
            'solutions': solutions,
            'original_text_preview': reg.get('original_text', '')[:500]
        })

    # Opcional: salvar em CSV para catalogação
    if SAIR_CSV:
        import pandas as pd
        df = pd.DataFrame(resultados)
        df.to_csv(SAIR_CSV, index=False, encoding='utf-8-sig')
        print(f"\n💾 Resultados salvos em {SAIR_CSV}")

if __name__ == "__main__":
    main()