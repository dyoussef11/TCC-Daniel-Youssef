"""
Contador de Caracteres para Posts e Comentários
Conta caracteres em títulos, conteúdo principal e comentários
"""

import os
import json
import pandas as pd
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm

from core.paths import PREPROCESSAMENTO_DATA

# ============ CONFIGURAÇÕES ============
CAMINHO_JSON = PREPROCESSAMENTO_DATA / "Dados_Limpos_IniciaisV12"
CAMINHO_SAIDA = PREPROCESSAMENTO_DATA / "Analise_Caracteres"
CAMINHO_SAIDA.mkdir(parents=True, exist_ok=True)


def contar_caracteres(texto):
    """Conta caracteres de um texto (inclui espaços)"""
    if not texto or not isinstance(texto, str):
        return 0
    return len(texto)


def contar_caracteres_sem_espacos(texto):
    """Conta caracteres ignorando espaços"""
    if not texto or not isinstance(texto, str):
        return 0
    return len(texto.replace(' ', '').replace('\n', '').replace('\t', ''))


def processar_arquivo(arquivo):
    """Processa um arquivo JSON e conta caracteres dos posts e comentários"""
    try:
        with open(CAMINHO_JSON / arquivo, 'r', encoding='utf-8') as f:
            dados = json.load(f)
        
        modelo = dados.get('modelo_original', 'desconhecido')
        posts = dados.get('posts', [])
        
        # Inicializa estrutura de resultados
        resultado = {
            "modelo": modelo,
            "arquivo": arquivo,
            "total_posts": len(posts),
            "total_comentarios": 0,
            "caracteres_titulos": 0,
            "caracteres_conteudos": 0,
            "caracteres_comentarios": 0,
            "caracteres_totais": 0,
            "caracteres_sem_espacos_titulos": 0,
            "caracteres_sem_espacos_conteudos": 0,
            "caracteres_sem_espacos_comentarios": 0,
            "caracteres_sem_espacos_totais": 0,
            "detalhes_posts": []
        }
        
        for idx, post in enumerate(posts):
            titulo = post.get('titulo', '')
            conteudo = post.get('conteudo_post', '')
            
            # Conta caracteres do título
            len_titulo = contar_caracteres(titulo)
            len_titulo_sem_espacos = contar_caracteres_sem_espacos(titulo)
            
            # Conta caracteres do conteúdo
            len_conteudo = contar_caracteres(conteudo)
            len_conteudo_sem_espacos = contar_caracteres_sem_espacos(conteudo)
            
            # Acumula totais
            resultado["caracteres_titulos"] += len_titulo
            resultado["caracteres_conteudos"] += len_conteudo
            resultado["caracteres_sem_espacos_titulos"] += len_titulo_sem_espacos
            resultado["caracteres_sem_espacos_conteudos"] += len_conteudo_sem_espacos
            
            # Processa comentários do post atual
            comentarios_post = []
            total_caracteres_comentarios_post = 0
            total_caracteres_sem_espacos_comentarios_post = 0
            
            for coment in post.get('comentarios', []):
                conteudo_coment = coment.get('conteudo', '')
                len_coment = contar_caracteres(conteudo_coment)
                len_coment_sem_espacos = contar_caracteres_sem_espacos(conteudo_coment)
                
                total_caracteres_comentarios_post += len_coment
                total_caracteres_sem_espacos_comentarios_post += len_coment_sem_espacos
                
                comentarios_post.append({
                    "len_caracteres": len_coment,
                    "len_sem_espacos": len_coment_sem_espacos,
                    "conteudo_preview": conteudo_coment[:50] + "..." if len(conteudo_coment) > 50 else conteudo_coment
                })
            
            resultado["caracteres_comentarios"] += total_caracteres_comentarios_post
            resultado["caracteres_sem_espacos_comentarios"] += total_caracteres_sem_espacos_comentarios_post
            resultado["total_comentarios"] += len(post.get('comentarios', []))
            
            # Armazena detalhes do post
            resultado["detalhes_posts"].append({
                "post_id": idx,
                "titulo": titulo[:100] + "..." if len(titulo) > 100 else titulo,
                "len_titulo": len_titulo,
                "len_conteudo": len_conteudo,
                "len_comentarios": total_caracteres_comentarios_post,
                "num_comentarios": len(post.get('comentarios', [])),
                "len_total_post": len_titulo + len_conteudo + total_caracteres_comentarios_post
            })
        
        # Calcula totais finais
        resultado["caracteres_totais"] = (
            resultado["caracteres_titulos"] + 
            resultado["caracteres_conteudos"] + 
            resultado["caracteres_comentarios"]
        )
        
        resultado["caracteres_sem_espacos_totais"] = (
            resultado["caracteres_sem_espacos_titulos"] + 
            resultado["caracteres_sem_espacos_conteudos"] + 
            resultado["caracteres_sem_espacos_comentarios"]
        )
        
        # Métricas derivadas
        if resultado["total_posts"] > 0:
            resultado["media_caracteres_por_post"] = resultado["caracteres_totais"] / resultado["total_posts"]
            resultado["media_titulo"] = resultado["caracteres_titulos"] / resultado["total_posts"]
            resultado["media_conteudo"] = resultado["caracteres_conteudos"] / resultado["total_posts"]
            
            if resultado["total_comentarios"] > 0:
                resultado["media_comentario"] = resultado["caracteres_comentarios"] / resultado["total_comentarios"]
            else:
                resultado["media_comentario"] = 0
        
        return resultado
        
    except Exception as e:
        return {"erro": True, "arquivo": arquivo, "mensagem": str(e)}


def analisar_caracteres():
    """Função principal para análise de caracteres"""
    
    arquivos = [f for f in os.listdir(CAMINHO_JSON) if f.endswith('.json')]
    resultados = []
    
    print("="*70)
    print("📊 CONTADOR DE CARACTERES - POSTS E COMENTÁRIOS")
    print("="*70)
    print(f"📁 Total de arquivos: {len(arquivos)}")
    print(f"📂 Diretório: {CAMINHO_JSON}")
    print("\n🔍 Campos analisados:")
    print("   - post.titulo")
    print("   - post.conteudo_post")
    print("   - post.comentarios.conteudo")
    print("="*70)
    
    # Processa arquivos em paralelo
    with ProcessPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(processar_arquivo, arq): arq for arq in arquivos}
        for future in tqdm(as_completed(futures), total=len(arquivos), desc="Processando arquivos"):
            resultado = future.result()
            if isinstance(resultado, dict) and not resultado.get("erro", False):
                resultados.append(resultado)
            elif isinstance(resultado, dict) and resultado.get("erro", False):
                print(f"⚠️ Erro no arquivo {resultado['arquivo']}: {resultado['mensagem']}")
    
    if not resultados:
        print("❌ Nenhum resultado válido foi processado!")
        return
    
    # Cria DataFrame principal
    df = pd.DataFrame(resultados)
    
    # Seleciona colunas para o resumo principal
    colunas_resumo = [
        'modelo', 'arquivo', 'total_posts', 'total_comentarios',
        'caracteres_titulos', 'caracteres_conteudos', 'caracteres_comentarios',
        'caracteres_totais', 'caracteres_sem_espacos_totais',
        'media_caracteres_por_post', 'media_titulo', 'media_conteudo', 'media_comentario'
    ]
    
    df_resumo = df[colunas_resumo].copy()
    
    # Ordena por total de caracteres
    df_resumo = df_resumo.sort_values('caracteres_totais', ascending=False)
    
    # Salva resultados principais
    df_resumo.to_csv(
        CAMINHO_SAIDA / "contagem_caracteres_por_modelo.csv",
        index=False, sep=';', encoding='utf-8-sig'
    )
    
    # Cria e salva estatísticas agregadas
    estatisticas = {
        "Metrica": [
            "Total de caracteres (todos os campos)",
            "Total de caracteres (sem espaços)",
            "Total de caracteres em títulos",
            "Total de caracteres em conteúdos",
            "Total de caracteres em comentários",
            "Média de caracteres por post",
            "Média de caracteres por título",
            "Média de caracteres por conteúdo",
            "Média de caracteres por comentário",
            "Total de posts analisados",
            "Total de comentários analisados",
            "Total de modelos analisados"
        ],
        "Valor": [
            f"{df['caracteres_totais'].sum():,}",
            f"{df['caracteres_sem_espacos_totais'].sum():,}",
            f"{df['caracteres_titulos'].sum():,}",
            f"{df['caracteres_conteudos'].sum():,}",
            f"{df['caracteres_comentarios'].sum():,}",
            f"{df['media_caracteres_por_post'].mean():.2f}",
            f"{df['media_titulo'].mean():.2f}",
            f"{df['media_conteudo'].mean():.2f}",
            f"{df[df['media_comentario'] > 0]['media_comentario'].mean():.2f}",
            f"{df['total_posts'].sum():,}",
            f"{df['total_comentarios'].sum():,}",
            f"{len(df):,}"
        ]
    }
    
    df_estatisticas = pd.DataFrame(estatisticas)
    df_estatisticas.to_csv(
        CAMINHO_SAIDA / "estatisticas_gerais_caracteres.csv",
        index=False, sep=';', encoding='utf-8-sig'
    )
    
    # Cria relatório de top modelos
    top_modelos = df_resumo[['modelo', 'caracteres_totais', 'total_posts', 'total_comentarios']].head(20)
    top_modelos.to_csv(
        CAMINHO_SAIDA / "top20_modelos_mais_caracteres.csv",
        index=False, sep=';', encoding='utf-8-sig'
    )
    
    # ============ RELATÓRIO ============
    print("\n" + "="*70)
    print("📊 RELATÓRIO DE CONTAGEM DE CARACTERES")
    print("="*70)
    
    print(f"\n📈 ESTATÍSTICAS GERAIS:")
    print("-"*60)
    print(f"   Total de caracteres (com espaços):   {df['caracteres_totais'].sum():,}")
    print(f"   Total de caracteres (sem espaços):   {df['caracteres_sem_espacos_totais'].sum():,}")
    print(f"   Total de caracteres em títulos:      {df['caracteres_titulos'].sum():,}")
    print(f"   Total de caracteres em conteúdos:    {df['caracteres_conteudos'].sum():,}")
    print(f"   Total de caracteres em comentários:  {df['caracteres_comentarios'].sum():,}")
    print(f"   Total de posts analisados:           {df['total_posts'].sum():,}")
    print(f"   Total de comentários analisados:     {df['total_comentarios'].sum():,}")
    print(f"   Total de modelos analisados:         {len(df)}")
    
    print(f"\n📊 MÉDIAS GERAIS:")
    print("-"*60)
    print(f"   Média de caracteres por post:        {df['media_caracteres_por_post'].mean():.2f}")
    print(f"   Média de caracteres por título:      {df['media_titulo'].mean():.2f}")
    print(f"   Média de caracteres por conteúdo:    {df['media_conteudo'].mean():.2f}")
    
    media_comentarios = df[df['media_comentario'] > 0]['media_comentario'].mean()
    print(f"   Média de caracteres por comentário:  {media_comentarios:.2f}")
    
    print(f"\n🏆 TOP 10 MODELOS COM MAIS CARACTERES (total):")
    print("-"*60)
    for i, row in top_modelos.head(10).iterrows():
        print(f"{row['modelo']:<40} | {row['caracteres_totais']:>10,} caracteres | {row['total_posts']:>3} posts | {row['total_comentarios']:>4} comentários")
    
    print(f"\n📊 DISTRIBUIÇÃO POR TIPO DE CONTEÚDO (% do total):")
    print("-"*60)
    total_caracteres = df['caracteres_totais'].sum()
    pct_titulos = (df['caracteres_titulos'].sum() / total_caracteres) * 100
    pct_conteudos = (df['caracteres_conteudos'].sum() / total_caracteres) * 100
    pct_comentarios = (df['caracteres_comentarios'].sum() / total_caracteres) * 100
    
    print(f"   Títulos:     {pct_titulos:.1f}% ({df['caracteres_titulos'].sum():,} caracteres)")
    print(f"   Conteúdos:   {pct_conteudos:.1f}% ({df['caracteres_conteudos'].sum():,} caracteres)")
    print(f"   Comentários: {pct_comentarios:.1f}% ({df['caracteres_comentarios'].sum():,} caracteres)")
    
    print(f"\n✅ Arquivos salvos em: {CAMINHO_SAIDA}")
    print(f"   - contagem_caracteres_por_modelo.csv (detalhado por modelo)")
    print(f"   - estatisticas_gerais_caracteres.csv (métricas agregadas)")
    print(f"   - top20_modelos_mais_caracteres.csv (top 20 modelos)")
    
    return df, df_estatisticas


def exportar_detalhes_completos():
    """Exporta detalhes completos de cada post (opcional - pode ser pesado)"""
    
    print("\n" + "="*70)
    print("📝 Exportando detalhes completos dos posts...")
    print("="*70)
    
    arquivos = [f for f in os.listdir(CAMINHO_JSON) if f.endswith('.json')]
    todos_detalhes = []
    
    for arquivo in tqdm(arquivos, desc="Processando detalhes"):
        try:
            with open(CAMINHO_JSON / arquivo, 'r', encoding='utf-8') as f:
                dados = json.load(f)
            
            modelo = dados.get('modelo_busca_utilizado', 'desconhecido')
            
            for idx, post in enumerate(dados.get('posts', [])):
                titulo = post.get('titulo', '')
                conteudo = post.get('conteudo_post', '')
                
                detalhe = {
                    "modelo": modelo,
                    "arquivo": arquivo,
                    "post_id": idx,
                    "titulo": titulo,
                    "len_titulo": contar_caracteres(titulo),
                    "len_conteudo": contar_caracteres(conteudo),
                    "num_comentarios": len(post.get('comentarios', [])),
                    "len_comentarios": sum(contar_caracteres(c.get('conteudo', '')) for c in post.get('comentarios', [])),
                    "len_total": (
                        contar_caracteres(titulo) + 
                        contar_caracteres(conteudo) + 
                        sum(contar_caracteres(c.get('conteudo', '')) for c in post.get('comentarios', []))
                    )
                }
                todos_detalhes.append(detalhe)
                
        except Exception as e:
            print(f"Erro ao processar detalhes de {arquivo}: {e}")
    
    if todos_detalhes:
        df_detalhes = pd.DataFrame(todos_detalhes)
        df_detalhes.to_csv(
            CAMINHO_SAIDA / "detalhes_completos_posts.csv",
            index=False, sep=';', encoding='utf-8-sig'
        )
        print(f"✅ Detalhes completos salvos: {len(todos_detalhes):,} posts")
        print(f"   Arquivo: {CAMINHO_SAIDA / 'detalhes_completos_posts.csv'}")
    else:
        print("⚠️ Nenhum detalhe de post foi processado!")


if __name__ == "__main__":
    # Executa análise principal
    df_resultados, df_stats = analisar_caracteres()
    
    # Pergunta se quer exportar detalhes completos (pode ser demorado para muitos arquivos)
    resposta = input("\n📝 Deseja exportar detalhes completos de cada post? (s/N): ").lower()
    if resposta in ['s', 'sim', 'y', 'yes']:
        exportar_detalhes_completos()
    
    print("\n🎉 Análise concluída com sucesso!")