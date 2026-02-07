import json
import re
from pathlib import Path
import sys

# --- CONFIGURAÇÃO ---
caminho_script = Path(__file__).resolve().parent
caminho_raiz_projeto = caminho_script.parent.parent 
sys.path.append(str(caminho_raiz_projeto))

try:
    from config import DIRETORIO_DADOS_SIST_TIMERAG, DIRETORIO_DADOS_VALID_SIST_TIMERAG
except ImportError:
    # Fallback caso o config.py não seja encontrado
    DIRETORIO_DADOS_SIST_TIMERAG = caminho_script / 'dados_saida'
    DIRETORIO_DADOS_VALID_SIST_TIMERAG = caminho_script / 'dados_saida'

def extrair_details_narrativo(arquivo_json, arquivo_saida):
    try:
        if not Path(arquivo_json).exists():
            print(f"Erro: O arquivo {arquivo_json} não existe.")
            return

        with open(arquivo_json, 'r', encoding='utf-8') as f:
            dados = json.load(f)
        
        with open(arquivo_saida, 'w', encoding='utf-8') as f_out:
            f_out.write("=== RELATÓRIO DE EXTRAÇÃO TÉCNICA (DETALHES DO DIAGNÓSTICO) ===\n")
            f_out.write(f"Fonte: {Path(arquivo_json).name}\n")
            f_out.write(f"Data da Extração: {Path(arquivo_json).stat().st_mtime}\n")
            f_out.write("-" * 60 + "\n\n")

            for item in dados:
                pergunta = item.get('pergunta', 'N/A')
                data_sim = item.get('data_simulada', 'N/A')
                resposta = item.get('resposta_rag', '')

                # 1. TENTA CAPTURAR ENTRE 'TECHNICAL DETAILS:' E 'EXPERT VERDICT:' (Padrão V32-V36)
                match = re.search(r'(?i)TECHNICAL DETAILS:\s*(.*?)\s*EXPERT VERDICT:', resposta, re.DOTALL)
                
                # 2. FALLBACK: Tenta o padrão antigo 'DETAILS:' e 'VERDICT:'
                if not match:
                    match = re.search(r'(?i)DETAILS:\s*(.*?)\s*VERDICT:', resposta, re.DOTALL)
                
                if match:
                    details_text = match.group(1).strip()
                else:
                    # 3. SEGUNDO FALLBACK: Se não houver tags, pega o que restou após o Status
                    # Isso evita que análises longas que o modelo "fundiu" sejam perdidas
                    parts = re.split(r'(?i)STATUS:', resposta)
                    details_text = parts[-1].strip() if len(parts) > 1 else "Conteúdo não formatado corretamente."

                # Limpeza de ruído visual (ex: múltiplos traços ou quebras de linha excessivas)
                details_text = re.sub(r'={10,}', '', details_text) 
                
                f_out.write(f"ID: {item.get('id', '??')} | DATA SIMULADA: {data_sim}\n")
                f_out.write(f"PERGUNTA: {pergunta}\n")
                f_out.write(f"ANALYSIS:\n{details_text}\n")
                f_out.write("-" * 60 + "\n\n")

        print(f"✅ Sucesso! As análises técnicas foram extraídas para: {arquivo_saida}")
    
    except Exception as e:
        print(f"❌ Erro ao processar o arquivo: {e}")

if __name__ == "__main__":
    # Ajuste os caminhos conforme sua estrutura de pastas
    arquivo_input = DIRETORIO_DADOS_VALID_SIST_TIMERAG / 'resultados_validacao.json'
    arquivo_output = DIRETORIO_DADOS_VALID_SIST_TIMERAG / "analise_detalhada_details.txt"
    
    extrair_details_narrativo(arquivo_input, arquivo_output)