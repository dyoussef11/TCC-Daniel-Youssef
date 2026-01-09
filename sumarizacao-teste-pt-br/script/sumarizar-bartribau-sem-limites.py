
import pandas as pd
from transformers import pipeline, AutoTokenizer
from pathlib import Path
import sys
import re 
from langdetect import detect, DetectorFactory
from tqdm import tqdm 
import torch
import warnings

# Suprime o aviso de "max_length set" que é inofensivo
warnings.filterwarnings("ignore", "Your max_length is set to")

# Configurações globais
COLUNA_TEXTO = 'Conteudo_Comentario_Limpo'
DetectorFactory.seed = 42 

# --- Configuração de Caminhos ---
caminho_script = Path(__file__).resolve().parent
caminho_raiz_projeto = caminho_script.parent.parent
sys.path.append(str(caminho_raiz_projeto))

# Tenta importar as variáveis de configuração
try:
 from config import DIRETORIO_DADOS_LIMPEZA_DATASETS 
except ImportError:
 print("Erro: Não foi possível importar diretórios de config.py.")
 sys.exit(1)


# --- Diagnóstico e Configuração de Hardware ---
# Garante que o PyTorch e a GPU estão prontos
DEVICE = 0 if torch.cuda.is_available() else -1
if DEVICE == 0:
 print(f"CUDA disponível: {torch.cuda.is_available()}")
 print(f"Nome da GPU: {torch.cuda.get_device_name(0)}")
else:
 print("Usando CPU. O processamento será lento.")


# --- 1. Configuração do Pipeline PT-BR (PTT5) ---
MODELO_SUMARIZACAO_PTBR = "unicamp-dl/ptt5-base-portuguese-vocab"
MAX_TOKENS_SAIDA_PTBR = 50
BATCH_SIZE = 16

tokenizer_ptbr = AutoTokenizer.from_pretrained(MODELO_SUMARIZACAO_PTBR)
summarizer_ptbr = pipeline(
 "summarization", 
 model=MODELO_SUMARIZACAO_PTBR,
 tokenizer=tokenizer_ptbr,
 device=DEVICE 
)

# --- 2. Configuração do Pipeline EN (LED) ---
MODELO_SUMARIZACAO_EN = "allenai/led-base-16384"
MAX_TOKENS_SAIDA_EN = 100 
LED_MAX_INPUT_TOKENS = 16384
LED_CHUNK_SIZE = 4096 

tokenizer_en = AutoTokenizer.from_pretrained(MODELO_SUMARIZACAO_EN)

# Correção: Forçar max_length/min_length na instanciação para evitar conflitos
summarizer_en = pipeline(
 "summarization",
 model=MODELO_SUMARIZACAO_EN,
 tokenizer=tokenizer_en,
 device=DEVICE, 
 max_length=128, 
 min_length=10 
)

# ----------------------------------------------------------------------
## 🧠 Funções Map-Reduce para Textos Longos em EN
# ----------------------------------------------------------------------

def chunk_text_by_tokens(text: str, tokenizer, max_chunk_size: int, overlap: int = 50) -> list[str]:
 """Divide um texto em chunks de tamanho máximo de tokens com alguma sobreposição."""
 tokens = tokenizer.encode(text)
 chunks = []
 start_index = 0
 while start_index < len(tokens):
  end_index = min(start_index + max_chunk_size, len(tokens))
  chunk_tokens = tokens[start_index:end_index]
  chunks.append(tokenizer.decode(chunk_tokens, skip_special_tokens=True))
  if end_index == len(tokens):
   break
  start_index += max_chunk_size - overlap
 return chunks


def map_reduce_summarize(text: str, summarizer, tokenizer, max_model_tokens: int) -> str:
 """Aplica a sumarização Map-Reduce se o texto exceder o limite do modelo, caso contrário, direta."""
 
 # Sumarização Direta (para textos que cabem)
 if len(tokenizer.encode(text)) <= max_model_tokens:
  try:
   resumo = summarizer(
    text,
    max_new_tokens=MAX_TOKENS_SAIDA_EN,
    min_length=int(MAX_TOKENS_SAIDA_EN * 0.5),
    do_sample=False
   )[0]['summary_text']
   return resumo
  except Exception:
   # Fallback para Map-Reduce em caso de erro inesperado (ex: truncamento)
   pass 

 # Map-Reduce (para textos muito longos ou fallback)
 
 # 1. MAP: Divide o texto e gera resumos parciais
 chunks = chunk_text_by_tokens(text, tokenizer, LED_CHUNK_SIZE)
 
 resumos_parciais = summarizer(
  chunks,
  max_new_tokens=int(MAX_TOKENS_SAIDA_EN / 2),
  min_length=10,
  do_sample=False,
  batch_size=BATCH_SIZE,
#   tqdm=False # Desativa a barra interna aqui para não atrapalhar o progress_apply
 )
 
 # 2. REDUCE: Concatena os resumos e gera um resumo final
 textos_resumidos = " ".join([r['summary_text'] for r in resumos_parciais])
 
 resumo_final = summarizer(
  f"Gere um resumo final e coeso baseado nos seguintes resumos parciais: {textos_resumidos}",
  max_new_tokens=MAX_TOKENS_SAIDA_EN,
  min_length=int(MAX_TOKENS_SAIDA_EN * 0.75),
  do_sample=False
 )[0]['summary_text']
 
 return resumo_final

# ----------------------------------------------------------------------
## 🚀 Processamento Principal
# ----------------------------------------------------------------------

def processar_datasets():
 # Carregar Dados
 try:
  df_pt_br = pd.read_csv(DIRETORIO_DADOS_LIMPEZA_DATASETS / 'dataset_respostas_pt.csv')
  df_en = pd.read_csv(DIRETORIO_DADOS_LIMPEZA_DATASETS / 'dataset_respostas_en.csv')
  
  # Garante que não haja valores nulos causando problemas de tipo
  df_pt_br[COLUNA_TEXTO] = df_pt_br[COLUNA_TEXTO].fillna('').astype(str)
  df_en[COLUNA_TEXTO] = df_en[COLUNA_TEXTO].fillna('').astype(str)
  
 except Exception as e:
  print(f"Erro ao carregar os datasets: {e}")
  sys.exit(1)

 # --- Processamento PT-BR (Sumarização Direta em Lote) ---
 print("\n" + "="*50)
 print(f"### 🇧🇷 Aplicando Sumarização PT-BR (Lote Otimizado: {MODELO_SUMARIZACAO_PTBR}) ###")
 print("="*50)

 textos_pt = df_pt_br[COLUNA_TEXTO].tolist()
 
 # Chamada otimizada em lote com TQDM
 resultados_pt = summarizer_ptbr(
  textos_pt,
  max_new_tokens=MAX_TOKENS_SAIDA_PTBR,
  min_length=10,
  do_sample=False,
  batch_size=BATCH_SIZE,
#   tqdm=True 
 )

 df_pt_br['Resumo_Abstrativo'] = [r['summary_text'] for r in resultados_pt]
 
 print("\nSumarização PT-BR concluída.")
 print("--- Amostra de PT-BR ---")
 print(df_pt_br[[COLUNA_TEXTO, 'Resumo_Abstrativo']].head())
 print("-" * 50)
    
    # --- SALVAMENTO IMEDIATO PT-BR ---
 caminho_pt = DIRETORIO_DADOS_LIMPEZA_DATASETS / 'sumarizacao_pt_br_final.csv'
 df_pt_br.to_csv(caminho_pt, index=False)
 print(f"\n✅ Sumarização PT-BR salva com sucesso em: {caminho_pt}")
 print("--------------------------------------------------")
 
 # --- Processamento EN (Map-Reduce Híbrido com TQDM) ---
 print("\n" + "="*50)
 print(f"### 🇬🇧 Aplicando Sumarização EN (Map-Reduce Híbrido: {MODELO_SUMARIZACAO_EN}) ###")
 print("="*50)

 # O Map-Reduce é aplicado linha a linha, usando progress_apply para a barra
 df_en['Resumo_Abstrativo'] = df_en[COLUNA_TEXTO].progress_apply(
  lambda x: map_reduce_summarize(x, summarizer_en, tokenizer_en, LED_MAX_INPUT_TOKENS)
 )

 print("\nSumarização EN concluída.")
 print("--- Amostra de EN ---")
 print(df_en[[COLUNA_TEXTO, 'Resumo_Abstrativo']].head())
 print("-" * 50)

 # --- SALVAMENTO EN ---
 caminho_en = DIRETORIO_DADOS_LIMPEZA_DATASETS / 'sumarizacao_en_final.csv'
 df_en.to_csv(caminho_en, index=False)
 print(f"\n✅ Sumarização EN salva com sucesso em: {caminho_en}")
 print("--------------------------------------------------")

 print("\n✨ Processamento e salvamento de AMBOS datasets concluído!")


if __name__ == "__main__":
 tqdm.pandas() # Registra o progress_apply para o pandas
 processar_datasets()
