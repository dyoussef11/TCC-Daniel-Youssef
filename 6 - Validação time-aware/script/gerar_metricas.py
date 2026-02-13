import json
import pandas as pd
from pathlib import Path
import sys

# --- BOOTSTRAP DE CAMINHO DO PROJETO ---
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.paths import (

VALIDACAO_DATA

)


DIRETORIO_DADOS_VALID_SIST_TIMERAG = VALIDACAO_DATA

def analisar_resultados(arquivo_json):
    if not arquivo_json.exists():
        print(f"❌ Erro: Arquivo {arquivo_json} não encontrado. Execute o validador primeiro.")
        return

    with open(arquivo_json, "r", encoding="utf-8") as f:
        dados = json.load(f)
    
    if not dados:
        print("⚠️ O arquivo de resultados está vazio.")
        return

    df = pd.DataFrame(dados)
    
    # Métrica de Qualidade TCC:
    # 1. Deve conter as tags técnicas.
    # 2. Deve ter corpo de texto (evita respostas curtas de erro/repetição).
    df['sucesso'] = df['resposta_rag'].apply(
    lambda x: 1 if "TECHNICAL DETAILS" in str(x) and len(str(x)) > 150 else 0
    )

    print("\n" + "="*50)
    print("📈 RELATÓRIO DE DESEMPENHO ACADÊMICO - RAG V41")
    print("="*50)
    print(f"Total de Casos Analisados: {len(df)}")
    print(f"Taxa de Conformidade (Prompt V41): {df['sucesso'].mean()*100:.1f}%")
    print(f"Latência Média: {df['tempo_segundos'].mean():.2f}s")
    print(f"Desvio Padrão Tempo: {df['tempo_segundos'].std():.2f}s")
    
    # Exportação formatada para o TCC
    caminho_csv = DIRETORIO_DADOS_VALID_SIST_TIMERAG / "metricas_finais_tcc.csv"
    df.to_csv(caminho_csv, index=False, sep=';', encoding='utf-8-sig')
    print(f"\n✅ Planilha para Tabelas (CSV) gerada: {caminho_csv.name}")

if __name__ == "__main__":
    caminho_input = DIRETORIO_DADOS_VALID_SIST_TIMERAG / "resultados_validacao.json"
    analisar_resultados(caminho_input)