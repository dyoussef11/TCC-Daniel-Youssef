import json
import re
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

def extrair_analise_v41(arquivo_json, arquivo_saida):
    try:
        if not arquivo_json.exists():
            print(f"❌ Erro: Entrada {arquivo_json} não encontrada.")
            return

        with open(arquivo_json, 'r', encoding='utf-8') as f:
            dados = json.load(f)
        
        with open(arquivo_saida, 'w', encoding='utf-8') as f_out:
            f_out.write("=== RELATÓRIO DE DIAGNÓSTICO NARRATIVO (PRODUTO FINAL RAG) ===\n")
            f_out.write(f"Ano de Validação: 2026 | Estrutura: Prompt V41 Invertido\n")
            f_out.write("-" * 80 + "\n\n")

            for item in dados:
                resposta = item.get('resposta_rag', '')
                
                # REGEX V41: Captura o conteúdo técnico após o prefixo indutivo do JSON
                # Ele busca o que vem após "shows that", "indicates that", "Fact check:" ou "situation is that"
                match = re.search(r'(?i)(?:shows that|indicates that|Fact check:|situation is that)\s*(.*)', resposta, re.DOTALL)
                
                if match:
                    corpo_analise = match.group(1).strip()
                else:
                    # Fallback robusto: se não achar o prefixo, pega após a tag principal
                    parts = re.split(r'(?i)TECHNICAL DETAILS:', resposta)
                    corpo_analise = parts[-1].strip() if len(parts) > 1 else "Formato de resposta inconsistente."

                # Limpeza final: remove possíveis repetições do STATUS ou do prompt no final
                corpo_analise = re.split(r'(?i)STATUS:', corpo_analise)[0].strip()

                f_out.write(f"ID: {item.get('id'):02} | DATA REF: {item.get('data_simulada')} | QUERY: {item.get('pergunta')}\n")
                f_out.write(f"RESULTADO TÉCNICO:\n{corpo_analise}\n")
                f_out.write("-" * 80 + "\n\n")

        print(f"✅ Extração Qualitativa concluída: {arquivo_saida.name}")
    
    except Exception as e:
        print(f"❌ Falha crítica na extração: {e}")

if __name__ == "__main__":
    input_j = DIRETORIO_DADOS_VALID_SIST_TIMERAG / 'resultados_validacao.json'
    output_t = DIRETORIO_DADOS_VALID_SIST_TIMERAG / "relatorio_final_narrativo.txt"
    extrair_analise_v41(input_j, output_t)