import sys
from pathlib import Path
import re
import pandas as pd
from langdetect import detect_langs, DetectorFactory
from tqdm import tqdm 
import warnings

# Suprime warnings do langdetect
warnings.filterwarnings("ignore")

# --- Configuração de Caminhos ---
caminho_script = Path(__file__).resolve().parent
caminho_raiz_projeto = caminho_script.parent.parent
sys.path.append(str(caminho_raiz_projeto))

try:
    from config import DIRETORIO_DADOS_LIMPEZA_DATASETS
except ImportError as e:
    print(f"Erro ao importar módulos. Verifique 'config.py'. Erro: {e}")
    sys.exit(1)

# Garante detecção consistente
DetectorFactory.seed = 42

# --- Configurações Globais ---
TAMANHO_MINIMO_CARACTERES = 6
TAMANHO_LIMITE_FRASE_CURTA = 30

# Caminhos de entrada/saída
caminho_entrada_other = DIRETORIO_DADOS_LIMPEZA_DATASETS / 'dataset_respostas_other.csv'
caminho_entrada_ptbr = DIRETORIO_DADOS_LIMPEZA_DATASETS / 'dataset_respostas_pt.csv'
caminho_entrada_en = DIRETORIO_DADOS_LIMPEZA_DATASETS / 'dataset_respostas_en.csv'

# ========================================
# FUNÇÕES DE LIMPEZA E PRÉ-PROCESSAMENTO
# ========================================

def limpar_texto_tecnico(texto):
    """
    Remove termos técnicos que confundem o detector de idioma.
    Mantém texto suficiente para detecção confiável.
    """
    if not texto or len(texto) < TAMANHO_MINIMO_CARACTERES:
        return ""
    
    texto_original = texto
    
    # Remove marcadores genéricos
    texto = re.sub(r'\[USUARIO\]|\[URL\]|\[EMAIL\]|\[CODIGO\]|\[BLOCO_CODIGO\]|\[IMAGEM\]|\[LINK\]', ' ', texto)
    
    # Remove menções de usuário
    texto = re.sub(r'@\w+|u/\w+|USUARIO\s+\w+', ' ', texto)
    
    # Remove códigos de erro do Windows (UPPERCASE_UNDERSCORE)
    texto = re.sub(r'\b[A-Z_]{15,}\b', ' ', texto)
    
    # Remove especificações técnicas comuns
    padroes_tecnicos = [
        r'\b(?:i[3579]|GTX|RTX|AMD|Intel|NVIDIA|Ryzen)\s*[-\s]?\d+[A-Z]*\b',  # CPUs/GPUs
        r'\b\d+(?:GB|TB|MHz|GHz|fps|rpm|W|Hz)\b',  # Especificações
        r'\b(?:DDR[34]|PCIe|SATA|NVMe|SSD|HDD|M\.2|USB|HDMI)\b',  # Hardware
        r'\b(?:Win(?:dows)?|Linux|BIOS|UEFI|Driver)\s*\d*\b',  # SO/Firmware
        r'\b[A-Z]\d{1,2}\b',  # Modelos curtos (G3, G5, G7)
        r'\b\d{3,4}x\d{3,4}\b',  # Resoluções
        r'\b[A-Z]{2,}\d{3,}[A-Z]*\b',  # Códigos de modelo
    ]
    
    for padrao in padroes_tecnicos:
        texto = re.sub(padrao, ' ', texto, flags=re.IGNORECASE)
    
    # Remove números isolados
    texto = re.sub(r'\b\d+\b', ' ', texto)
    
    # Normaliza espaços
    texto = re.sub(r'\s+', ' ', texto).strip()
    
    # Se sobrou muito pouco, retorna o original
    if len(texto) < 20:
        return texto_original
    
    return texto


def calcular_heuristicas(texto):
    """
    Calcula indicadores linguísticos para PT-BR e EN.
    Retorna (pt_score, en_score, lang_sugerido)
    """
    texto_lower = texto.lower()
    
    # Padrões fortes de português brasileiro
    pt_patterns = [
        r'\b(?:que|para|com|uma?|esse?a?|dessa?|estava|foram|mais|muito|bem|já)\b',
        r'\b(?:não|então|também|até|depois|mesmo|problema|aqui|agora|quando)\b',
        r'\b(?:tenho|tinha|tive|fiz|faço|faz|está|estou|estão|vou|vai|preciso)\b',
        r'\b(?:fazer|feito|disse|disse|pode|podem|quer|quero)\b',
        r'\bç[aãeioáéíóú]s?\b',  # Cedilha é exclusiva do português
        r'\b\w+[ãõ]es?\b',  # Terminações com til
        r'\b(?:meu|minha|seu|sua|nosso|dela|dele)\b',
    ]
    
    # Padrões fortes de inglês
    en_patterns = [
        r'\b(?:the|that|this|these|those|with|from|have|been|were|was)\b',
        r'\b(?:would|should|could|will|can|may|must|need|want|get)\b',
        r'\b(?:after|before|between|without|about|which|there|where|when)\b',
        r'\b(?:your|my|his|her|our|their)\b',
        r'\b\w+ing\b',  # Gerúndio
        r'\b\w+ed\b',   # Particípio passado
    ]
    
    # Conta matches
    pt_count = sum(len(re.findall(pattern, texto_lower)) for pattern in pt_patterns)
    en_count = sum(len(re.findall(pattern, texto_lower)) for pattern in en_patterns)
    
    # Pontuação adicional para características únicas
    if 'ç' in texto_lower or 'ã' in texto_lower or 'õ' in texto_lower:
        pt_count += 2
    
    # Determina sugestão
    if pt_count > en_count * 1.5 and pt_count >= 2:
        sugestao = 'pt'
    elif en_count > pt_count * 1.5 and en_count >= 2:
        sugestao = 'en'
    else:
        sugestao = None
    
    return pt_count, en_count, sugestao


# ========================================
# FUNÇÕES DE DETECÇÃO DE IDIOMA
# ========================================

def re_detect_language_robust(text):
    """
    Detecção robusta combinando múltiplas estratégias:
    1. Heurísticas linguísticas
    2. Detecção no texto original
    3. Detecção no texto limpo (sem termos técnicos)
    4. Thresholds adaptativos
    """
    text = str(text).strip()
    
    if not text or len(text) < TAMANHO_MINIMO_CARACTERES:
        return 'other_short'
    
    try:
        # ESTRATÉGIA 1: Heurísticas (mais rápido e eficaz para textos técnicos)
        pt_score, en_score, sugestao_heuristica = calcular_heuristicas(text)
        
        # Se heurística é conclusiva, usa ela
        if sugestao_heuristica:
            return sugestao_heuristica
        
        # ESTRATÉGIA 2: Detecção com langdetect
        detections_original = detect_langs(text)
        
        # ESTRATÉGIA 3: Detecção no texto limpo
        texto_limpo = limpar_texto_tecnico(text)
        detections_limpo = []
        if len(texto_limpo) >= 20:
            try:
                detections_limpo = detect_langs(texto_limpo)
            except:
                pass
        
        # Combina todas as detecções em um dicionário
        todas_deteccoes = {}
        
        # Processa texto original
        for detection in detections_original:
            lang = str(detection).split(':')[0]
            prob = detection.prob
            if lang not in todas_deteccoes or prob > todas_deteccoes[lang]:
                todas_deteccoes[lang] = prob
        
        # Processa texto limpo (com peso maior 20%)
        for detection in detections_limpo:
            lang = str(detection).split(':')[0]
            prob = detection.prob * 1.2
            if lang not in todas_deteccoes or prob > todas_deteccoes[lang]:
                todas_deteccoes[lang] = min(prob, 1.0)  # Limita a 1.0
        
        # Ordena por probabilidade
        deteccoes_ordenadas = sorted(todas_deteccoes.items(), key=lambda x: x[1], reverse=True)
        
        # Define thresholds adaptativos baseados no tamanho
        text_length = len(text)
        if text_length <= 15:
            threshold = 0.55  # Muito flexível para textos muito curtos
        elif text_length <= TAMANHO_LIMITE_FRASE_CURTA:
            threshold = 0.65  # Flexível para textos curtos
        elif text_length > 100:
            threshold = 0.75  # Mais rigoroso para textos longos
        else:
            threshold = 0.70  # Padrão
        
        # Busca pt ou en nas detecções
        for lang, prob in deteccoes_ordenadas:
            if lang not in ['pt', 'en']:
                continue
            
            # Aplica boost baseado nas heurísticas
            if lang == 'pt' and pt_score > 0:
                prob = min(prob + (pt_score * 0.05), 1.0)
            elif lang == 'en' and en_score > 0:
                prob = min(prob + (en_score * 0.05), 1.0)
            
            if prob >= threshold:
                return lang
        
        # Verifica se tinha pt/en mas com baixa confiança
        pt_en_detected = any(lang in ['pt', 'en'] for lang, _ in deteccoes_ordenadas)
        
        if pt_en_detected:
            return 'other_low_confidence'
        else:
            return 'other_not_pt_en'
        
    except Exception as e:
        return 'other_detection_failed'


def extract_first_sentence_improved(text):
    """
    Extrai a primeira frase do texto de forma mais robusta.
    """
    if not text or pd.isna(text):
        return ""
    
    text = str(text).strip()
    if not text:
        return ""
    
    # Remove marcadores de usuário no início
    text = re.sub(r'^\[USUARIO\]\s*', '', text)
    text = re.sub(r'^USUARIO\s+\w+[\s,:;-]+', '', text, flags=re.IGNORECASE)
    text = re.sub(r'^(?:@\w+|u/\w+)[\s,:;-]+', '', text)
    
    text = text.strip()
    if not text:
        return ""
    
    # Padrões de extração (do mais específico ao mais genérico)
    patterns = [
        r'^([^.!?\n]{20,150}[.!?])',     # 20-150 chars com pontuação
        r'^([^.!?\n]{30,200})',          # 30-200 chars sem pontuação
        r'^([^.!?\n]{15,100}[.!?])',     # Fallback: 15-100 chars com pontuação
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            sentence = match.group(1).strip()
            # Validações de qualidade
            if (len(sentence) >= 15 and 
                not sentence.isdigit() and
                not re.match(r'^\[.+\]$', sentence)):  # Não é só marcador
                return sentence
    
    # Fallback: pega primeiras 10 palavras válidas
    words = text.split()
    valid_words = []
    for word in words:
        # Pula marcadores e palavras muito curtas
        if len(word) >= 2 and not re.match(r'^\[.+\]$', word):
            valid_words.append(word)
        if len(valid_words) >= 10:
            break
    
    result = ' '.join(valid_words)
    return result if len(result) >= 15 else ""


# ========================================
# FUNÇÕES DE ANÁLISE E ESTATÍSTICAS
# ========================================

def analisar_distribuicao(df, coluna='lang_reclassificado', titulo="DISTRIBUIÇÃO"):
    """
    Exibe estatísticas de distribuição de categorias.
    """
    print("\n" + "="*70)
    print(f"📊 {titulo}")
    print("="*70)
    
    dist = df[coluna].value_counts()
    total = len(df)
    
    for categoria, count in dist.items():
        percentual = (count / total) * 100
        barra = "█" * int(percentual / 2)
        print(f"{categoria:25s}: {count:6d} ({percentual:5.2f}%) {barra}")
    
    print("="*70)


def validar_resultados(df_pt, df_en, df_other, n_amostras=3):
    """
    Mostra amostras dos resultados para validação manual.
    """
    print("\n" + "="*80)
    print("🔍 VALIDAÇÃO MANUAL - Amostras Aleatórias")
    print("="*80)
    
    if len(df_pt) > 0:
        print("\n--- Reclassificados como PT-BR ---")
        amostras = df_pt.sample(n=min(n_amostras, len(df_pt)))
        for idx, row in amostras.iterrows():
            print(f"\n• {row['primeira_frase_otimizada'][:120]}...")
    
    if len(df_en) > 0:
        print("\n--- Reclassificados como EN ---")
        amostras = df_en.sample(n=min(n_amostras, len(df_en)))
        for idx, row in amostras.iterrows():
            print(f"\n• {row['primeira_frase_otimizada'][:120]}...")
    
    if len(df_other) > 0:
        print("\n--- Permaneceram como OTHER ---")
        amostras = df_other.sample(n=min(n_amostras, len(df_other)))
        for idx, row in amostras.iterrows():
            motivo = row.get('lang_reclassificado', 'unknown')
            print(f"\n• [{motivo}] {row['primeira_frase_otimizada'][:100]}...")
    
    print("\n" + "="*80)


# ========================================
# EXECUÇÃO PRINCIPAL
# ========================================

if __name__ == "__main__":
    print("\n" + "="*80)
    print("🔄 PIPELINE DE RECLASSIFICAÇÃO DE IDIOMAS - VERSÃO MELHORADA")
    print("="*80)
    
    # 1. Carregar o DataFrame "other"
    try:
        df_other = pd.read_csv(caminho_entrada_other)
        print(f"\n✅ Dataset 'other' carregado: {len(df_other)} registros")
        print(f"📋 Colunas: {list(df_other.columns)}")
    except FileNotFoundError:
        print(f"\n❌ Arquivo não encontrado: {caminho_entrada_other}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Erro ao carregar arquivo: {e}")
        sys.exit(1)
    
    # 2. Extração de sentenças
    print("\n" + "="*80)
    print("📝 ETAPA 1: Extração de Sentenças")
    print("="*80)
    
    tqdm.pandas(desc="Extraindo sentenças")
    df_other['primeira_frase_otimizada'] = df_other['Conteudo_Comentario_Limpo'].progress_apply(
        extract_first_sentence_improved
    )
    
    # Filtra registros com extração bem-sucedida
    df_other_extraido = df_other[df_other['primeira_frase_otimizada'] != ""].copy()
    
    extraidos = len(df_other_extraido)
    nao_extraidos = len(df_other) - extraidos
    
    print(f"\n✅ Sentenças extraídas: {extraidos} ({extraidos/len(df_other)*100:.1f}%)")
    print(f"❌ Não extraídas: {nao_extraidos} ({nao_extraidos/len(df_other)*100:.1f}%)")
    
    if extraidos == 0:
        print("\n⚠️  Nenhuma sentença foi extraída. Verifique a coluna 'Conteudo_Comentario_Limpo'.")
        sys.exit(1)
    
    # 3. Detecção de idioma
    print("\n" + "="*80)
    print("🔍 ETAPA 2: Detecção de Idioma")
    print("="*80)
    
    tqdm.pandas(desc="Detectando idiomas")
    df_other_extraido['lang_reclassificado'] = df_other_extraido['primeira_frase_otimizada'].progress_apply(
        re_detect_language_robust
    )
    
    # Análise da distribuição
    analisar_distribuicao(df_other_extraido, 'lang_reclassificado', "RESULTADO DA DETECÇÃO")
    
    # 4. Separação dos datasets
    df_pt_reclassificado = df_other_extraido[df_other_extraido['lang_reclassificado'] == 'pt'].copy()
    df_en_reclassificado = df_other_extraido[df_other_extraido['lang_reclassificado'] == 'en'].copy()
    df_other_final = df_other_extraido[~df_other_extraido['lang_reclassificado'].isin(['pt', 'en'])].copy()
    
    print(f"\n📊 Resumo:")
    print(f"   🇧🇷 PT-BR: {len(df_pt_reclassificado)} registros")
    print(f"   🇺🇸 EN: {len(df_en_reclassificado)} registros")
    print(f"   ❓ OTHER: {len(df_other_final)} registros")
    
    # 5. Validação manual
    validar_resultados(df_pt_reclassificado, df_en_reclassificado, df_other_final, n_amostras=3)
    
    # 6. Preparar colunas para anexar
    colunas_originais = df_other.columns.tolist()
    colunas_para_anexar = [col for col in colunas_originais if col != 'primeira_frase']
    colunas_para_anexar.append('primeira_frase_otimizada')
    
    # 7. Anexar aos datasets existentes
    print("\n" + "="*80)
    print("💾 ETAPA 3: Salvando Resultados")
    print("="*80)
    
    # Anexar PT
    if not df_pt_reclassificado.empty:
        try:
            df_pt_append = df_pt_reclassificado[colunas_para_anexar].copy()
            df_pt_append = df_pt_append.rename(columns={'primeira_frase_otimizada': 'primeira_frase'})
            df_pt_append.to_csv(caminho_entrada_ptbr, mode='a', header=False, index=False)
            print(f"✅ {len(df_pt_reclassificado)} registros PT-BR anexados a '{caminho_entrada_ptbr.name}'")
        except Exception as e:
            print(f"❌ Erro ao anexar PT: {e}")
    
    # Anexar EN
    if not df_en_reclassificado.empty:
        try:
            df_en_append = df_en_reclassificado[colunas_para_anexar].copy()
            df_en_append = df_en_append.rename(columns={'primeira_frase_otimizada': 'primeira_frase'})
            df_en_append.to_csv(caminho_entrada_en, mode='a', header=False, index=False)
            print(f"✅ {len(df_en_reclassificado)} registros EN anexados a '{caminho_entrada_en.name}'")
        except Exception as e:
            print(f"❌ Erro ao anexar EN: {e}")
    
    # Salvar OTHER final
    if not df_other_final.empty:
        df_other_final_clean = df_other_final.drop(columns=['lang_reclassificado'], errors='ignore').copy()
        df_other_final_clean = df_other_final_clean.rename(
            columns={'primeira_frase_otimizada': 'primeira_frase'}
        )
        
        caminho_saida_repescagem = DIRETORIO_DADOS_LIMPEZA_DATASETS / 'dataset_repescagem_other_final.csv'
        df_other_final_clean.to_csv(caminho_saida_repescagem, index=False)
        print(f"✅ {len(df_other_final)} registros OTHER salvos em '{caminho_saida_repescagem.name}'")
    
    # 8. Resumo final
    print("\n" + "="*80)
    print("🎉 PIPELINE CONCLUÍDO COM SUCESSO!")
    print("="*80)
    print(f"📥 Total processado: {len(df_other)} registros")
    print(f"📝 Sentenças extraídas: {extraidos} registros")
    print(f"🇧🇷 Reclassificados PT-BR: {len(df_pt_reclassificado)} registros")
    print(f"🇺🇸 Reclassificados EN: {len(df_en_reclassificado)} registros")
    print(f"❓ Permaneceram OTHER: {len(df_other_final)} registros")
    print(f"💾 Arquivos atualizados:")
    print(f"   • {caminho_entrada_ptbr.name}")
    print(f"   • {caminho_entrada_en.name}")
    print(f"   • dataset_repescagem_other_final.csv")
    print("="*80 + "\n")