# Garante que as bibliotecas necessárias para o pipeline estejam importadas
import pandas as pd
from transformers import pipeline, AutoTokenizer, AutoModelForSeq2SeqLM
from pathlib import Path
import sys
import re 
from langdetect import detect, DetectorFactory
from tqdm import tqdm 
import torch
import warnings
import time

# from utilis_preprocessamento_texto import preparar_texto_para_sumarizacao
# from utilis_preprocessamento_texto import validar_resumo

# Suprime avisos
warnings.filterwarnings("ignore", "Your max_length is set to")
warnings.filterwarnings("ignore", category=FutureWarning)

# --- CONFIGURAÇÕES GLOBAIS ---
NUM_AMOSTRAS = 10
# NUM_AMOSTRAS = 1500
COLUNA_TEXTO = 'Conteudo_Comentario_Limpo'
DetectorFactory.seed = 42

# --- Configuração de Caminhos ---
caminho_script = Path(__file__).resolve().parent
caminho_raiz_projeto = caminho_script.parent.parent
sys.path.append(str(caminho_raiz_projeto))

try:
    from config import DIRETORIO_DADOS_LIMPEZA_DATASETS,DIRETORIO_DADOS_SUMARIZACAO_DE_TEXTOS, utils_dirs
except ImportError:
    print("Erro: Não foi possível importar diretórios de config.py.")
    sys.exit(1)

from preprocessamento_texto_sumarizar import preparar_texto_para_sumarizacao, validar_resumo

# --- Diagnóstico e Configuração de Hardware ---
DEVICE = 0 if torch.cuda.is_available() else -1
if DEVICE == 0:
    print(f"✅ CUDA disponível")
    print(f"📊 GPU: {torch.cuda.get_device_name(0)}")
    print(f"💾 Memória GPU disponível: {torch.cuda.get_device_properties(0).total_memory / 1e9:.2f} GB")
else:
    print("⚠️  Usando CPU. O processamento será lento.")

# --- CONFIGURAÇÕES DE SUMARIZAÇÃO ---
BATCH_SIZE = 8  # Reduzido para evitar OOM

# PT-BR: Configurações otimizadas (Ajustado para ~20 palavras)
MODELO_PTBR = "facebook/mbart-large-50-many-to-many-mmt"
MIN_LENGTH_PTBR = 25  # NOVO: Mínimo reduzido para permitir resumos curtos e coerentes
MAX_LENGTH_PTBR = 200  # NOVO: Máximo ajustado para cerca de 20-25 palavras (tokens)
NUM_BEAMS_PTBR = 4    # Beam search para melhor qualidade
IDIOMA_PTBR = "pt_XX" # NOVO: Código de idioma para o mBART

# EN: Configurações otimizadas (Ajustado para ~20 palavras)
MODELO_EN = "facebook/bart-large-cnn"  # Melhor que LED para textos curtos
MIN_LENGTH_EN = 25    # NOVO: Mínimo reduzido para permitir resumos curtos e coerentes
MAX_LENGTH_EN = 200    # NOVO: Máximo ajustado para cerca de 20-25 palavras (tokens)
NUM_BEAMS_EN = 4


# ========================================
# CARREGAMENTO DE MODELOS
# ========================================

print("\n" + "="*80)
print("🤖 CARREGANDO MODELOS DE SUMARIZAÇÃO")
print("="*80)

# --- Modelo PT-BR (PTT5) ---
print(f"\n[LOG] ⏳ Carregando modelo PT-BR: {MODELO_PTBR}")
start_time = time.time()

try:
    # Tokenizer: Define o idioma de origem para tokenização
    tokenizer_ptbr = AutoTokenizer.from_pretrained(MODELO_PTBR, src_lang=IDIOMA_PTBR)
    model_ptbr = AutoModelForSeq2SeqLM.from_pretrained(MODELO_PTBR)
    
    # NOVO: Obtém o ID do token de início de sentença (BOS) para forçar o PT-BR na saída
    global PORTUGUESE_BOS_TOKEN_ID
    PORTUGUESE_BOS_TOKEN_ID = tokenizer_ptbr.lang_code_to_id[IDIOMA_PTBR]
    
    if DEVICE >= 0:
        model_ptbr = model_ptbr.to('cuda')
    
    print(f"[LOG] ✅ mBART-50 carregado em {time.time() - start_time:.2f}s")
except Exception as e:
    print(f"[ERRO] ❌ Falha ao carregar mBART-50: {e}")
    sys.exit(1)

# --- Modelo EN (BART) ---
print(f"\n[LOG] ⏳ Carregando modelo EN: {MODELO_EN}")
start_time = time.time()

try:
    tokenizer_en = AutoTokenizer.from_pretrained(MODELO_EN)
    model_en = AutoModelForSeq2SeqLM.from_pretrained(MODELO_EN)
    
    if DEVICE >= 0:
        model_en = model_en.to('cuda')
    
    print(f"[LOG] ✅ BART carregado em {time.time() - start_time:.2f}s")
except Exception as e:
    print(f"[ERRO] ❌ Falha ao carregar BART: {e}")
    sys.exit(1)


# ========================================
# FUNÇÕES DE SUMARIZAÇÃO
# ========================================

def sumarizar_texto_ptbr(texto):
    """
    Sumariza texto em português usando mBART-50 (sem prefixo T5, com forçamento de idioma).
    """
    texto_preparado = preparar_texto_para_sumarizacao(texto)
    
    if not texto_preparado:
        return ""
    
    try:
        # Não adiciona prefixo T5!
        
        # Tokeniza (o tokenizer já sabe que o idioma de origem é pt_BR)
        inputs = tokenizer_ptbr(
            texto_preparado, # Sem prefixo!
            max_length=512,
            truncation=True,
            return_tensors="pt"
        )
        
        # Move para GPU se disponível
        if DEVICE >= 0:
            inputs = {k: v.to('cuda') for k, v in inputs.items()}
        
        # Gera resumo
        with torch.no_grad():
            outputs = model_ptbr.generate(
                **inputs,
                max_length=MAX_LENGTH_PTBR,
                min_length=MIN_LENGTH_PTBR,
                num_beams=NUM_BEAMS_PTBR,
                length_penalty=2.0,
                early_stopping=True,
                no_repeat_ngram_size=3,
                # NOVO: FORÇA O IDIOMA DE SAÍDA PARA PORTUGUÊS
                forced_bos_token_id=PORTUGUESE_BOS_TOKEN_ID 
            )
        
        # ... (Resto da função de decodificação e validação é mantido)
        resumo = tokenizer_ptbr.decode(outputs[0], skip_special_tokens=True)
        
        # Valida
        if not validar_resumo(resumo, texto_preparado):
            return "[RESUMO_INVALIDO]"
        
        return resumo
        
    except Exception as e:
        print(f"[ERRO] PT-BR: {str(e)[:80]}")
        return "[ERRO_SUMARIZACAO]"


def sumarizar_texto_en(texto):
    """
    Sumariza texto em inglês usando o modelo diretamente (sem pipeline).
    """
    texto_preparado = preparar_texto_para_sumarizacao(texto)
    
    if not texto_preparado:
        return ""
    
    try:
        # Tokeniza (BART não precisa de prefixo)
        inputs = tokenizer_en(
            texto_preparado,
            max_length=1024,
            truncation=True,
            return_tensors="pt"
        )
        
        # Move para GPU se disponível
        if DEVICE >= 0:
            inputs = {k: v.to('cuda') for k, v in inputs.items()}
        
        # Gera resumo
        with torch.no_grad():
            outputs = model_en.generate(
                **inputs,
                max_length=MAX_LENGTH_EN,
                min_length=MIN_LENGTH_EN,
                num_beams=NUM_BEAMS_EN,
                length_penalty=2.0,
                early_stopping=True,
                no_repeat_ngram_size=3
            )
        
        # Decodifica
        resumo = tokenizer_en.decode(outputs[0], skip_special_tokens=True)
        
        # Valida
        if not validar_resumo(resumo, texto_preparado):
            return "[RESUMO_INVALIDO]"
        
        return resumo
        
    except Exception as e:
        print(f"[ERRO] EN: {str(e)[:80]}")
        return "[ERRO_SUMARIZACAO]"


def sumarizar_batch_ptbr(textos):
    """
    Sumariza lote de textos PT-BR usando o modelo diretamente.
    """
    textos_preparados = [preparar_texto_para_sumarizacao(t) for t in textos]
    textos_validos = [f"resuma: {t}" for t in textos_preparados if t]
    
    if not textos_validos:
        return [""] * len(textos)
    
    try:
        # Tokeniza batch
        inputs = tokenizer_ptbr(
            textos_validos,
            max_length=512,
            truncation=True,
            padding=True,
            return_tensors="pt"
        )
        
        if DEVICE >= 0:
            inputs = {k: v.to('cuda') for k, v in inputs.items()}
        
        # Gera resumos
        with torch.no_grad():
            outputs = model_ptbr.generate(
                **inputs,
                max_length=MAX_LENGTH_PTBR,
                min_length=MIN_LENGTH_PTBR,
                num_beams=NUM_BEAMS_PTBR,
                length_penalty=2.0,
                early_stopping=True,
                no_repeat_ngram_size=3
            )
        
        # Decodifica todos
        resumos = [tokenizer_ptbr.decode(output, skip_special_tokens=True) for output in outputs]
        return resumos
        
    except Exception as e:
        print(f"[ERRO] Batch PT-BR: {str(e)[:80]}")
        return ["[ERRO]"] * len(textos_validos)


def sumarizar_batch_en(textos):
    """
    Sumariza lote de textos EN usando o modelo diretamente.
    """
    textos_preparados = [preparar_texto_para_sumarizacao(t) for t in textos]
    textos_validos = [t for t in textos_preparados if t]
    
    if not textos_validos:
        return [""] * len(textos)
    
    try:
        # Tokeniza batch
        inputs = tokenizer_en(
            textos_validos,
            max_length=1024,
            truncation=True,
            padding=True,
            return_tensors="pt"
        )
        
        if DEVICE >= 0:
            inputs = {k: v.to('cuda') for k, v in inputs.items()}
        
        # Gera resumos
        with torch.no_grad():
            outputs = model_en.generate(
                **inputs,
                max_length=MAX_LENGTH_EN,
                min_length=MIN_LENGTH_EN,
                num_beams=NUM_BEAMS_EN,
                length_penalty=2.0,
                early_stopping=True,
                no_repeat_ngram_size=3
            )
        
        # Decodifica todos
        resumos = [tokenizer_en.decode(output, skip_special_tokens=True) for output in outputs]
        return resumos
        
    except Exception as e:
        print(f"[ERRO] Batch EN: {str(e)[:80]}")
        return ["[ERRO]"] * len(textos_validos)


# ========================================
# PROCESSAMENTO PRINCIPAL
# ========================================

def processar_datasets():
    print("\n" + "="*80)
    print("📥 CARREGANDO DATASETS")
    print("="*80)
    
    try:
        # Carrega com configurações robustas para lidar com vírgulas nos textos
        df_pt_br_full = pd.read_csv(
            DIRETORIO_DADOS_LIMPEZA_DATASETS / 'dataset_respostas_pt.csv',
            on_bad_lines='skip',  # Pula linhas problemáticas
            engine='python',       # Engine mais flexível
            quoting=1,            # QUOTE_ALL
            encoding='utf-8'
        )
        
        df_en_full = pd.read_csv(
            DIRETORIO_DADOS_LIMPEZA_DATASETS / 'dataset_respostas_en.csv',
            on_bad_lines='skip',
            engine='python',
            quoting=1,
            encoding='utf-8'
        )
        
        print(f"✅ PT-BR carregado: {len(df_pt_br_full)} registros (total)")
        print(f"✅ EN carregado: {len(df_en_full)} registros (total)")
        
        # Verifica se a coluna existe
        if COLUNA_TEXTO not in df_pt_br_full.columns:
            print(f"[ERRO] ❌ Coluna '{COLUNA_TEXTO}' não encontrada em PT-BR")
            print(f"Colunas disponíveis: {list(df_pt_br_full.columns)}")
            sys.exit(1)
        
        if COLUNA_TEXTO not in df_en_full.columns:
            print(f"[ERRO] ❌ Coluna '{COLUNA_TEXTO}' não encontrada em EN")
            print(f"Colunas disponíveis: {list(df_en_full.columns)}")
            sys.exit(1)
        
        # Amostragem
        df_pt_br = df_pt_br_full.head(NUM_AMOSTRAS).copy()
        df_en = df_en_full.head(NUM_AMOSTRAS).copy()
        
        print(f"📊 Amostra PT-BR: {len(df_pt_br)} registros")
        print(f"📊 Amostra EN: {len(df_en)} registros")
        
        # Garante tipo string e remove valores nulos
        df_pt_br[COLUNA_TEXTO] = df_pt_br[COLUNA_TEXTO].fillna('').astype(str)
        df_en[COLUNA_TEXTO] = df_en[COLUNA_TEXTO].fillna('').astype(str)
        
        # Remove linhas vazias
        df_pt_br = df_pt_br[df_pt_br[COLUNA_TEXTO] != ''].reset_index(drop=True)
        df_en = df_en[df_en[COLUNA_TEXTO] != ''].reset_index(drop=True)
        
        print(f"✅ PT-BR válido: {len(df_pt_br)} registros")
        print(f"✅ EN válido: {len(df_en)} registros")
        
    except FileNotFoundError as e:
        print(f"[ERRO] ❌ Arquivo não encontrado: {e}")
        print(f"Verifique se os arquivos existem em: {DIRETORIO_DADOS_LIMPEZA_DATASETS}")
        sys.exit(1)
    except Exception as e:
        print(f"[ERRO] ❌ Falha ao carregar datasets: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # --- PROCESSAMENTO PT-BR ---
    print("\n" + "="*80)
    print("🇧🇷 SUMARIZANDO TEXTOS PT-BR")
    print("="*80)
    
    start_time = time.time()
    
    tqdm.pandas(desc="Sumarizando PT-BR")
    df_pt_br['Resumo_Abstrativo'] = df_pt_br[COLUNA_TEXTO].progress_apply(sumarizar_texto_ptbr)
    
    tempo_ptbr = time.time() - start_time
    
    # Estatísticas
    resumos_validos = df_pt_br[df_pt_br['Resumo_Abstrativo'] != ""].shape[0]
    resumos_invalidos = df_pt_br[df_pt_br['Resumo_Abstrativo'] == "[RESUMO_INVALIDO]"].shape[0]
    
    print(f"\n✅ Sumarização PT-BR concluída em {tempo_ptbr:.2f}s")
    print(f"📊 Resumos válidos: {resumos_validos}/{len(df_pt_br)} ({resumos_validos/len(df_pt_br)*100:.1f}%)")
    print(f"⚠️  Resumos inválidos: {resumos_invalidos}")
    
    # Mostra exemplos
    print("\n--- Exemplos PT-BR ---")
    for idx in range(min(3, len(df_pt_br))):
        original = df_pt_br.iloc[idx][COLUNA_TEXTO]
        resumo = df_pt_br.iloc[idx]['Resumo_Abstrativo']
        print(f"\n[{idx+1}] Original ({len(original.split())} palavras):")
        print(f"    {original[:150]}...")
        print(f"    Resumo ({len(resumo.split())} palavras):")
        print(f"    {resumo}")
    
    # Salva PT-BR
    caminho_pt = DIRETORIO_DADOS_SUMARIZACAO_DE_TEXTOS / 'sumarizacao_pt_br_amostra.csv'
    df_pt_br.to_csv(caminho_pt, index=False)
    print(f"\n💾 Salvo em: {caminho_pt}")
    
    # --- PROCESSAMENTO EN ---
    print("\n" + "="*80)
    print("🇺🇸 SUMARIZANDO TEXTOS EN")
    print("="*80)
    
    start_time = time.time()
    
    tqdm.pandas(desc="Sumarizando EN")
    df_en['Resumo_Abstrativo'] = df_en[COLUNA_TEXTO].progress_apply(sumarizar_texto_en)
    
    tempo_en = time.time() - start_time
    
    # Estatísticas
    resumos_validos_en = df_en[df_en['Resumo_Abstrativo'] != ""].shape[0]
    resumos_invalidos_en = df_en[df_en['Resumo_Abstrativo'] == "[RESUMO_INVALIDO]"].shape[0]
    
    print(f"\n✅ Sumarização EN concluída em {tempo_en:.2f}s")
    print(f"📊 Resumos válidos: {resumos_validos_en}/{len(df_en)} ({resumos_validos_en/len(df_en)*100:.1f}%)")
    print(f"⚠️  Resumos inválidos: {resumos_invalidos_en}")
    
    # Mostra exemplos
    print("\n--- Exemplos EN ---")
    for idx in range(min(3, len(df_en))):
        original = df_en.iloc[idx][COLUNA_TEXTO]
        resumo = df_en.iloc[idx]['Resumo_Abstrativo']
        print(f"\n[{idx+1}] Original ({len(original.split())} palavras):")
        print(f"    {original[:150]}...")
        print(f"    Resumo ({len(resumo.split())} palavras):")
        print(f"    {resumo}")
    
    # Salva EN
    caminho_en = DIRETORIO_DADOS_SUMARIZACAO_DE_TEXTOS / 'sumarizacao_en_amostra.csv'
    df_en.to_csv(caminho_en, index=False)
    print(f"\n💾 Salvo em: {caminho_en}")
    
    # --- RESUMO FINAL ---
    print("\n" + "="*80)
    print("🎉 PROCESSAMENTO CONCLUÍDO")
    print("="*80)
    print(f"⏱️  Tempo total PT-BR: {tempo_ptbr:.2f}s")
    print(f"⏱️  Tempo total EN: {tempo_en:.2f}s")
    print(f"📊 Taxa de sucesso PT-BR: {resumos_validos/len(df_pt_br)*100:.1f}%")
    print(f"📊 Taxa de sucesso EN: {resumos_validos_en/len(df_en)*100:.1f}%")
    print("="*80 + "\n")


if __name__ == "__main__":
    tqdm.pandas()
    processar_datasets()