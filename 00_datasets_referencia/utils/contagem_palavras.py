import pandas as pd
import re
from pathlib import Path
from collections import Counter
import logging

# Configura logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Importa os caminhos do seu projeto
from core.paths import DATASET_GAMER

# Define os caminhos
PASTA_ENTRADA = DATASET_GAMER / "em_tratamento" / "unificados"
PASTA_SAIDA = DATASET_GAMER / "em_tratamento" / "analise_palavras"
ARQUIVO_FINAL = PASTA_ENTRADA / "laptops_centralizado_modelos.csv"

def classificar_palavra(palavra: str) -> str:
    """
    Classifica uma palavra em categorias:
    - 'apenas_letras': palavras como "asus", "vivobook"
    - 'apenas_numeros': palavras como "14", "16", "2023"
    - 'misto_letras_numeros': palavras como "x1502za", "fx506hf"
    - 'com_hifen': palavras como "15-fa1062tx", "book2-pro"
    - 'ruido': caracteres especiais, pontuação, lixo
    """
    if not palavra:
        return 'vazio'
    
    # Verifica se tem hífen
    if '-' in palavra:
        return 'com_hifen'
    
    # Limpa caracteres especiais para verificar conteúdo real
    palavra_limpa = re.sub(r'[^\w]', '', palavra)
    if not palavra_limpa:
        return 'ruido'
    
    # Verifica se tem apenas letras
    if re.match(r'^[a-z]+$', palavra_limpa):
        return 'apenas_letras'
    
    # Verifica se tem apenas números
    if re.match(r'^\d+$', palavra_limpa):
        return 'apenas_numeros'
    
    # Verifica se é misto (letras + números)
    if re.match(r'^[a-z]+\d+[a-z]*$', palavra_limpa, re.IGNORECASE):
        return 'misto_letras_numeros'
    
    # Outros casos
    return 'outros'

def limpar_numero(numero: str) -> str:
    """Remove zeros à esquerda de números"""
    if numero.isdigit():
        return str(int(numero))
    return numero

def analisar_dataset_unificado():
    """
    Analisa o dataset unificado e conta estatísticas das palavras
    """
    if not ARQUIVO_FINAL.exists():
        logger.error(f"❌ Arquivo não encontrado: {ARQUIVO_FINAL}")
        return
    
    logger.info("=" * 70)
    logger.info("📊 ANÁLISE DO DATASET UNIFICADO")
    logger.info("=" * 70)
    logger.info(f"📁 Arquivo: {ARQUIVO_FINAL}")
    
    df = pd.read_csv(ARQUIVO_FINAL)
    logger.info(f"📊 Total de linhas: {len(df)}")
    logger.info(f"📋 Colunas disponíveis: {list(df.columns)}")
    
    # Colunas que contêm texto de modelo
    colunas_modelo = ['modelo_centralizado', 'modelo_generico', 'modelo_limpo', 'modelo_completo']
    colunas_disponiveis = [col for col in colunas_modelo if col in df.columns]
    
    if not colunas_disponiveis:
        logger.error("❌ Nenhuma coluna de modelo encontrada!")
        return
    
    logger.info(f"\n📋 Colunas de modelo analisadas: {colunas_disponiveis}")
    
    # Para cada coluna, faz a análise
    for coluna in colunas_disponiveis:
        logger.info(f"\n{'='*70}")
        logger.info(f"🔍 ANALISANDO COLUNA: '{coluna}'")
        logger.info(f"{'='*70}")
        
        todas_palavras = []
        palavras_unicas = set()
        
        for valor in df[coluna].dropna():
            palavras = re.split(r'[_\-]+', str(valor).lower())
            for p in palavras:
                p_limpo = re.sub(r'[^\w\-]', '', p)  # Remove caracteres especiais
                if p_limpo and len(p_limpo) > 0:
                    todas_palavras.append(p_limpo)
                    palavras_unicas.add(p_limpo)
        
        logger.info(f"📊 Total de palavras (com repetição): {len(todas_palavras):,}")
        logger.info(f"📊 Total de palavras únicas: {len(palavras_unicas):,}")
        
        # Classifica as palavras únicas
        classificacao = {
            'apenas_letras': [],
            'apenas_numeros': [],
            'misto_letras_numeros': [],
            'com_hifen': [],
            'ruido': [],
            'outros': []
        }
        
        for palavra in palavras_unicas:
            cat = classificar_palavra(palavra)
            classificacao[cat].append(palavra)
        
        # Estatísticas por categoria
        logger.info(f"\n📊 CLASSIFICAÇÃO DAS PALAVRAS ÚNICAS:")
        logger.info(f"   {'Categoria':<25} | {'Quantidade':>10} | {'Percentual':>10}")
        logger.info(f"   {'-'*25}-+-{'-'*10}-+-{'-'*10}")
        
        total_unicas = len(palavras_unicas)
        for cat, palavras in classificacao.items():
            qtd = len(palavras)
            pct = (qtd / total_unicas * 100) if total_unicas > 0 else 0
            if qtd > 0:  # Só mostra categorias com palavras
                logger.info(f"   {cat:<25} | {qtd:>10} | {pct:>9.1f}%")
        
        # Mostra exemplos
        logger.info(f"\n📝 EXEMPLOS POR CATEGORIA:")
        for cat, palavras in classificacao.items():
            if palavras:
                exemplos = sorted(palavras)[:10]
                # Limpa números com zeros à esquerda para exibição
                exemplos_limpos = [limpar_numero(p) if p.isdigit() else p for p in exemplos]
                logger.info(f"\n   🔹 {cat.upper()} ({len(palavras)} palavras):")
                for i in range(0, len(exemplos_limpos), 5):
                    grupo = exemplos_limpos[i:i+5]
                    logger.info(f"      {', '.join(grupo)}")
    
    logger.info("\n" + "=" * 70)
    logger.info("✅ ANÁLISE CONCLUÍDA!")
    logger.info("=" * 70)

def exportar_analise_para_csv():
    """
    Exporta a análise detalhada para um arquivo CSV
    """
    if not ARQUIVO_FINAL.exists():
        logger.error(f"❌ Arquivo não encontrado: {ARQUIVO_FINAL}")
        return
    
    PASTA_ANALISE = PASTA_SAIDA
    PASTA_ANALISE.mkdir(parents=True, exist_ok=True)
    
    df = pd.read_csv(ARQUIVO_FINAL)
    
    # Usa a coluna disponível (modelo_completo)
    coluna_principal = 'modelo_completo' if 'modelo_completo' in df.columns else None
    if not coluna_principal:
        logger.error("Nenhuma coluna de modelo encontrada para exportar!")
        return
    
    logger.info(f"📊 Exportando análise da coluna: '{coluna_principal}'")
    
    # Cria DataFrame com análise detalhada de cada modelo
    analise = []
    for idx, valor in enumerate(df[coluna_principal].dropna()):
        palavras = re.split(r'[_\-]+', str(valor).lower())
        
        for palavra in palavras:
            palavra_limpa = re.sub(r'[^\w\-]', '', palavra)
            if palavra_limpa:
                analise.append({
                    'id': idx,
                    'modelo_completo': valor,
                    'palavra': palavra_limpa,
                    'tamanho': len(palavra_limpa),
                    'categoria': classificar_palavra(palavra_limpa)
                })
    
    if not analise:
        logger.error("Nenhuma palavra encontrada para análise!")
        return
    
    df_analise = pd.DataFrame(analise)
    
    # Adiciona colunas booleanas para facilitar filtros
    df_analise['apenas_letras'] = (df_analise['categoria'] == 'apenas_letras').astype(int)
    df_analise['apenas_numeros'] = (df_analise['categoria'] == 'apenas_numeros').astype(int)
    df_analise['misto'] = (df_analise['categoria'] == 'misto_letras_numeros').astype(int)
    df_analise['com_hifen'] = (df_analise['categoria'] == 'com_hifen').astype(int)
    df_analise['ruido'] = (df_analise['categoria'] == 'ruido').astype(int)
    
    # Salva análise detalhada
    caminho_analise = PASTA_ANALISE / "analise_palavras_modelos.csv"
    df_analise.to_csv(caminho_analise, index=False, encoding='utf-8')
    logger.info(f"📁 Análise detalhada salva em: {caminho_analise}")
    logger.info(f"   Total de registros: {len(df_analise):,}")
    
    # Salva dicionário de palavras únicas
    palavras_unicas = df_analise.groupby('palavra').agg({
        'categoria': 'first',
        'tamanho': 'first',
        'id': 'count'
    }).rename(columns={'id': 'frequencia'}).reset_index()
    palavras_unicas = palavras_unicas.sort_values('frequencia', ascending=False)
    
    caminho_dict = PASTA_ANALISE / "dicionario_palavras_unicas.csv"
    palavras_unicas.to_csv(caminho_dict, index=False, encoding='utf-8')
    logger.info(f"📁 Dicionário de palavras únicas salvo em: {caminho_dict}")
    logger.info(f"   Total de palavras únicas: {len(palavras_unicas):,}")
    
    # Salva estatísticas por categoria
    stats = palavras_unicas['categoria'].value_counts().reset_index()
    stats.columns = ['categoria', 'quantidade']
    stats['percentual'] = (stats['quantidade'] / stats['quantidade'].sum() * 100).round(1)
    
    caminho_stats = PASTA_ANALISE / "estatisticas_categorias.csv"
    stats.to_csv(caminho_stats, index=False, encoding='utf-8')
    logger.info(f"📁 Estatísticas salvas em: {caminho_stats}")

if __name__ == "__main__":
    analisar_dataset_unificado()
    
    print("\n" + "=" * 70)
    resposta = input("Deseja exportar a análise detalhada para CSV? (s/n): ")
    if resposta.lower() == 's':
        exportar_analise_para_csv()
        print("\n✅ Exportação concluída!")
        print(f"📁 Arquivos salvos em: {PASTA_ENTRADA / 'analise'}")