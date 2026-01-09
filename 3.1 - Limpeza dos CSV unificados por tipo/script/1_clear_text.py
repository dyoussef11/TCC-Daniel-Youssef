# Garante que as bibliotecas necessárias para o pipeline estejam importadas
import pandas as pd
from transformers import pipeline, AutoTokenizer
from pathlib import Path
import sys
import re 
from langdetect import detect, DetectorFactory
from tqdm import tqdm 
import torch
import warnings
import time
from html import unescape

# Suprime o aviso de "max_length set" que é inofensivo
warnings.filterwarnings("ignore", "Your max_length is set to")

# --- CONFIGURAÇÕES GLOBAIS ---
NUM_AMOSTRAS = None
COLUNA_TEXTO = 'Conteudo_Comentario_Limpo'
DetectorFactory.seed = 42 

# --- Configuração de Caminhos ---
caminho_script = Path(__file__).resolve().parent
caminho_raiz_projeto = caminho_script.parent.parent
sys.path.append(str(caminho_raiz_projeto))

# Tenta importar as variáveis de configuração
try:
    from config import DIRETORIO_DADOS_LIMPEZA_DATASETS, DIRETORIO_DADOS_UNIFICACAO
except ImportError:
    print("Erro: Não foi possível importar diretórios de config.py.")
    sys.exit(1)

# ========================================
# FUNÇÕES DE LIMPEZA DE TEXTO
# ========================================

def limpeza_basica(texto):
    """
    Etapa 1: Normalização básica - decodifica HTML e normaliza espaços
    """
    if pd.isna(texto) or texto == "":
        return ""
    
    # Converte para string se não for
    texto = str(texto)
    
    # Decodificar entidades HTML (&nbsp;, &quot;, etc)
    texto = unescape(texto)
    
    # Normalizar múltiplos espaços em branco, tabs, newlines
    texto = re.sub(r'\s+', ' ', texto)
    
    # Remover espaços no início e fim
    texto = texto.strip()
    
    return texto


def remover_elementos_tecnicos(texto, preservar_urls=False):
    """
    Etapa 2: Remove elementos técnicos mas preserva marcadores
    
    Args:
        texto: string a ser limpa
        preservar_urls: se True, mantém marcador [URL], se False remove completamente
    """
    if pd.isna(texto) or texto == "":
        return ""
    
    # URLs - substituir por marcador ou remover
    if preservar_urls:
        texto = re.sub(r'http\S+|www\.\S+', '[URL]', texto)
    else:
        texto = re.sub(r'http\S+|www\.\S+', '', texto)
    
    # E-mails
    texto = re.sub(r'\S+@\S+', '[EMAIL]', texto)
    
    # Menções de usuários (padrão comum: @usuario ou u/usuario)
    texto = re.sub(r'@\w+', '[USUARIO]', texto)
    texto = re.sub(r'u/\w+', '[USUARIO]', texto)
    
    # Código entre backticks
    texto = re.sub(r'`[^`]+`', '[CODIGO]', texto)
    texto = re.sub(r'```[\s\S]*?```', '[BLOCO_CODIGO]', texto)
    
    return texto


def limpar_formatacao(texto, remover_markdown=True):
    """
    Etapa 3: Remove formatação Markdown/BBCode/HTML
    
    Args:
        texto: string a ser limpa
        remover_markdown: se True, remove formatação markdown
    """
    if pd.isna(texto) or texto == "":
        return ""
    
    if remover_markdown:
        # Markdown - preserva o texto mas remove formatação
        texto = re.sub(r'\*\*([^*]+)\*\*', r'\1', texto)  # **negrito**
        texto = re.sub(r'__([^_]+)__', r'\1', texto)      # __italico__
        texto = re.sub(r'\*([^*]+)\*', r'\1', texto)      # *italico*
        texto = re.sub(r'_([^_]+)_', r'\1', texto)        # _italico_
        texto = re.sub(r'~~([^~]+)~~', r'\1', texto)      # ~~tachado~~
    
    # BBCode comum em fóruns
    texto = re.sub(r'\[quote\].*?\[/quote\]', '', texto, flags=re.DOTALL | re.IGNORECASE)
    texto = re.sub(r'\[img\].*?\[/img\]', '[IMAGEM]', texto, flags=re.IGNORECASE)
    texto = re.sub(r'\[url=.*?\].*?\[/url\]', '[LINK]', texto, flags=re.IGNORECASE)
    texto = re.sub(r'\[b\](.*?)\[/b\]', r'\1', texto, flags=re.IGNORECASE)
    texto = re.sub(r'\[i\](.*?)\[/i\]', r'\1', texto, flags=re.IGNORECASE)
    
    # Tags HTML residuais
    texto = re.sub(r'<[^>]+>', '', texto)
    
    return texto


def remover_caracteres_especiais(texto, manter_pontuacao=True):
    """
    Etapa 4: Remove caracteres especiais mas mantém pontuação importante
    
    Args:
        texto: string a ser limpa
        manter_pontuacao: se True, mantém pontuação básica (.,!?;:)
    """
    if pd.isna(texto) or texto == "":
        return ""
    
    if manter_pontuacao:
        # Remove apenas caracteres não-alfabéticos, não-numéricos e não-pontuação básica
        # Mantém: letras, números, espaços, .,!?;:()-'
        texto = re.sub(r'[^\w\s.,!?;:()\-\']', '', texto, flags=re.UNICODE)
    else:
        # Remove todos caracteres especiais exceto espaços
        texto = re.sub(r'[^\w\s]', '', texto, flags=re.UNICODE)
    
    # Normaliza espaços novamente após remoção
    texto = re.sub(r'\s+', ' ', texto).strip()
    
    return texto

def remover_placeholders(texto):
    """
    Remove todos os placeholders definidos (ex: [USUARIO], [EMAIL], etc.)
    que podem contaminar a detecção de idioma e a classificação.
    """
    if pd.isna(texto) or texto == "":
        return ""

    # Lista de placeholders que são transformados em palavras após a remoção de colchetes
    placeholders = [
        r'\[USUARIO\]', r'\[EMAIL\]', r'\[URL\]', r'\[CODIGO\]',
        r'\[BLOCO_CODIGO\]', r'\[IMAGEM\]', r'\[LINK\]'
    ]

    # Na Etapa 4 (remover_caracteres_especiais) os colchetes são removidos.
    # O que resta são as palavras em caixa alta: USUARIO, EMAIL, etc.
    # Vamos focar na remoção dessas palavras.

    palavras_placeholder = [
        'USUARIO', 'EMAIL', 'URL', 'CODIGO',
        'BLOCO CODIGO', 'IMAGEM', 'LINK'
    ]
    
    # Cria um padrão regex que casa apenas a palavra completa
    # (usamos \b para garantir que não remova 'E-MAIL' de 'OUTRO_E-MAIL')
    padrao = r'\b(' + '|'.join(map(re.escape, palavras_placeholder)) + r')\b'
    
    texto = re.sub(padrao, '', texto, flags=re.IGNORECASE)

    # Normaliza espaços novamente após a remoção
    texto = re.sub(r'\s+', ' ', texto).strip()

    return texto


def pipeline_limpeza_completo(df, coluna_original='Conteudo_Comentario', 
                               coluna_limpa='Conteudo_Comentario_Limpo',
                               preservar_urls=False,
                               remover_markdown=True,
                               manter_pontuacao=True,
                               remover_todos_placeholders = True,
                               verbose=True):
    """
    Pipeline completo de limpeza - seguro e rastreável
    
    Args:
        df: DataFrame com os dados
        coluna_original: nome da coluna com texto original
        coluna_limpa: nome da coluna para salvar texto limpo
        preservar_urls: se True, substitui URLs por [URL]
        remover_markdown: se True, remove formatação markdown
        manter_pontuacao: se True, mantém pontuação básica
        verbose: se True, mostra progresso detalhado
    
    Returns:
        DataFrame com coluna limpa e estatísticas
    """
    if verbose:
        print(f"\n[LOG] 🧹 Iniciando limpeza de {len(df)} comentários...")
        inicio = time.time()
    
    # Criar coluna de backup se não existir
    if 'Conteudo_Comentario_Original' not in df.columns:
        df['Conteudo_Comentario_Original'] = df[coluna_original].copy()
    
    # Aplicar pipeline de limpeza com barra de progresso
    if verbose:
        tqdm.pandas(desc="Etapa 1/5: Limpeza básica") # 5 etapas agora
        df[coluna_limpa] = df[coluna_original].progress_apply(limpeza_basica)
        
        tqdm.pandas(desc="Etapa 2/5: Elementos técnicos (Insere placeholders)")
        df[coluna_limpa] = df[coluna_limpa].progress_apply(
            lambda x: remover_elementos_tecnicos(x, preservar_urls=preservar_urls)
        )
        
        tqdm.pandas(desc="Etapa 3/5: Formatação")
        df[coluna_limpa] = df[coluna_limpa].progress_apply(
            lambda x: limpar_formatacao(x, remover_markdown=remover_markdown)
        )
        
        tqdm.pandas(desc="Etapa 4/5: Caracteres especiais (Remove [ ])")
        df[coluna_limpa] = df[coluna_limpa].progress_apply(
            lambda x: remover_caracteres_especiais(x, manter_pontuacao=manter_pontuacao)
        )
        
        # NOVA ETAPA
        if remover_todos_placeholders:
            tqdm.pandas(desc="Etapa 5/5: Remove placeholders restantes")
            df[coluna_limpa] = df[coluna_limpa].progress_apply(remover_placeholders)
    else:
        df[coluna_limpa] = df[coluna_original].apply(limpeza_basica)
        df[coluna_limpa] = df[coluna_limpa].apply(
            lambda x: remover_elementos_tecnicos(x, preservar_urls=preservar_urls)
        )
        df[coluna_limpa] = df[coluna_limpa].apply(
            lambda x: limpar_formatacao(x, remover_markdown=remover_markdown)
        )
        df[coluna_limpa] = df[coluna_limpa].apply(
            lambda x: remover_caracteres_especiais(x, manter_pontuacao=manter_pontuacao)
        )
    
    # Normalização final
    df[coluna_limpa] = df[coluna_limpa].str.strip()
    
    # Adicionar flags úteis para análise posterior
    df['Tamanho_Original'] = df[coluna_original].str.len()
    df['Tamanho_Limpo'] = df[coluna_limpa].str.len()
    df['Texto_Vazio'] = df[coluna_limpa].str.len() == 0
    df['Texto_Muito_Curto'] = df[coluna_limpa].str.len() < 10
    df['Reducao_Percentual'] = ((df['Tamanho_Original'] - df['Tamanho_Limpo']) / 
                                 df['Tamanho_Original'] * 100).round(2)
    
    if verbose:
        tempo_total = time.time() - inicio
        print(f"\n[LOG] ✅ Limpeza concluída em {tempo_total:.2f}s")
        print_estatisticas_limpeza(df, coluna_original, coluna_limpa)
    
    return df


def print_estatisticas_limpeza(df, coluna_original, coluna_limpa):
    """
    Imprime estatísticas sobre o processo de limpeza
    """
    print("\n" + "="*60)
    print("📊 ESTATÍSTICAS DE LIMPEZA")
    print("="*60)
    
    total = len(df)
    vazios = df['Texto_Vazio'].sum()
    muito_curtos = df['Texto_Muito_Curto'].sum()
    
    print(f"Total de comentários: {total}")
    print(f"Textos vazios após limpeza: {vazios} ({vazios/total*100:.2f}%)")
    print(f"Textos muito curtos (<10 chars): {muito_curtos} ({muito_curtos/total*100:.2f}%)")
    print(f"\nTamanho médio original: {df['Tamanho_Original'].mean():.0f} caracteres")
    print(f"Tamanho médio limpo: {df['Tamanho_Limpo'].mean():.0f} caracteres")
    print(f"Redução média: {df['Reducao_Percentual'].mean():.2f}%")
    print("="*60 + "\n")


def validar_limpeza(df, coluna_original='Conteudo_Comentario', 
                    coluna_limpa='Conteudo_Comentario_Limpo', n_exemplos=5):
    """
    Mostra exemplos antes/depois para validação manual
    """
    import random
    
    print("\n" + "="*80)
    print("🔍 VALIDAÇÃO DE LIMPEZA - Exemplos Aleatórios")
    print("="*80)
    
    # Seleciona exemplos aleatórios que não ficaram vazios
    df_validos = df[~df['Texto_Vazio']].copy()
    indices = random.sample(range(len(df_validos)), min(n_exemplos, len(df_validos)))
    
    for idx, i in enumerate(indices, 1):
        row = df_validos.iloc[i]
        print(f"\n--- Exemplo {idx} ---")
        print(f"ORIGINAL ({row['Tamanho_Original']} chars):")
        print(f"  {str(row[coluna_original])[:200]}{'...' if len(str(row[coluna_original])) > 200 else ''}")
        print(f"\nLIMPO ({row['Tamanho_Limpo']} chars, redução: {row['Reducao_Percentual']:.1f}%):")
        print(f"  {str(row[coluna_limpa])[:200]}{'...' if len(str(row[coluna_limpa])) > 200 else ''}")
        print("-" * 80)



# ========================================
# EXECUÇÃO PRINCIPAL
# ========================================

if __name__ == "__main__":
    print("\n[LOG] ⏳ Carregando dataset unificado...")
    
    try:
        # Carrega dataset unificado
        caminho_entrada = DIRETORIO_DADOS_UNIFICACAO / 'respostas_combinadas_final.csv'
        df_full = pd.read_csv(caminho_entrada)
        
        print(f"[LOG] ✅ Dataset carregado: {len(df_full)} registros")
        print(f"[LOG] 📋 Colunas disponíveis: {list(df_full.columns)}")
        
        # Identifica a coluna de conteúdo (tenta várias possibilidades)
        colunas_possiveis = ['Conteudo_Comentario', 'conteudo', 'texto', 'comment', 'content', 'body']
        coluna_conteudo = None
        
        for col in colunas_possiveis:
            if col in df_full.columns:
                coluna_conteudo = col
                break
        
        if coluna_conteudo is None:
            print(f"[ERRO] ❌ Não foi encontrada coluna de conteúdo. Colunas disponíveis: {list(df_full.columns)}")
            sys.exit(1)
        
        print(f"[LOG] 📝 Usando coluna de conteúdo: '{coluna_conteudo}'")
        
        # Aplica amostragem se necessário
        # if NUM_AMOSTRAS and NUM_AMOSTRAS < len(df_full):
        #     df = df_full.sample(n=NUM_AMOSTRAS, random_state=42).reset_index(drop=True)
        #     print(f"[LOG] 🎲 Amostragem aplicada: {NUM_AMOSTRAS} registros")
        # else:
        df = df_full.copy()
        print(f"[LOG] 📊 Processando dataset completo: {len(df)} registros")
        
        # Mostra exemplo de dados antes da limpeza
        print("\n" + "="*80)
        print("📄 EXEMPLO DE DADOS ANTES DA LIMPEZA")
        print("="*80)
        exemplo = df[coluna_conteudo].iloc[0] if len(df) > 0 else "N/A"
        print(f"{str(exemplo)[:300]}{'...' if len(str(exemplo)) > 300 else ''}")
        print("="*80)
        
        # Aplica limpeza no dataset
        print("\n" + "="*80)
        print("🧹 PROCESSANDO DATASET UNIFICADO")
        print("="*80)
        df = pipeline_limpeza_completo(
            df,
            coluna_original=coluna_conteudo,
            coluna_limpa='Conteudo_Comentario_Limpo',
            preservar_urls=False,  # Ajuste conforme necessidade
            remover_markdown=True,
            manter_pontuacao=True,
            remover_todos_placeholders=True,
            verbose=True
        )
        
        # Valida limpeza
        validar_limpeza(df, coluna_original=coluna_conteudo, n_exemplos=5)
        
        # Análise de línguas detectadas (se houver coluna language)
        if 'language' in df.columns:
            print("\n" + "="*80)
            print("🌍 DISTRIBUIÇÃO DE LÍNGUAS NO DATASET")
            print("="*80)
            dist_linguas = df['language'].value_counts()
            for lingua, count in dist_linguas.items():
                print(f"  {lingua}: {count} ({count/len(df)*100:.2f}%)")
            print("="*80)
        
        # Filtra registros válidos (não vazios)
        df_validos = df[~df['Texto_Vazio']].copy()
        textos_removidos = len(df) - len(df_validos)

        registros_originais = len(df)
        df = df.dropna(subset=[coluna_conteudo])
        registros_removidos = registros_originais - len(df)
        
        if textos_removidos > 0:
            print(f"\n[LOG] ⚠️  {textos_removidos} textos ficaram vazios após limpeza e serão removidos")
            print(f"[LOG] ✅ {len(df_validos)} textos válidos serão salvos")
        
        # Salva resultado
        print("\n[LOG] 💾 Salvando dataset limpo...")
        caminho_saida = DIRETORIO_DADOS_LIMPEZA_DATASETS / 'respostas_combinadas_limpo.csv'
        
        df_validos.to_csv(caminho_saida, index=False)
        
        print(f"[LOG] ✅ Dataset limpo salvo em: {caminho_saida}")
        print(f"[LOG] 📊 Total de registros salvos: {len(df_validos)}")
        
        # Resumo final
        print("\n" + "="*80)
        print("🎉 PIPELINE DE LIMPEZA CONCLUÍDO COM SUCESSO!")
        print("="*80)
        print(f"📥 Entrada: {len(df_full)} registros")
        print(f"🎲 Processados: {len(df)} registros")
        print(f"✅ Válidos: {len(df_validos)} registros")
        print(f"❌ Removidos (vazios): {textos_removidos} registros")
        print(f"📁 Arquivo de saída: {caminho_saida}")
        print("="*80 + "\n")
        
    except FileNotFoundError as e:
        print(f"[ERRO] ❌ Arquivo não encontrado: {e}")
        print(f"[DICA] 💡 Verifique se o arquivo existe em: {DIRETORIO_DADOS_UNIFICACAO}")
        sys.exit(1)
    except Exception as e:
        print(f"[ERRO] ❌ Erro durante processamento: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)