import os
import json
from pathlib import Path
from collections import defaultdict
import pandas as pd
from core.paths import EXTRACAO_DATA_BRUTO

# --- CONFIGURAÇÕES DE CAMINHO ---
CAMINHO_ENTRADA = EXTRACAO_DATA_BRUTO

def analisar_arquivos_json():
    """
    Analisa todos os arquivos JSON na pasta EXTRACAO_DATA_BRUTO
    e gera estatísticas detalhadas por notebook/arquivo.
    """
    
    if not CAMINHO_ENTRADA.exists():
        print(f"❌ Pasta não encontrada: {CAMINHO_ENTRADA}")
        return
    
    arquivos = list(CAMINHO_ENTRADA.glob("*.json"))
    
    if not arquivos:
        print(f"⚠️ Nenhum arquivo JSON encontrado em: {CAMINHO_ENTRADA}")
        return
    
    print(f"📊 ANALISANDO {len(arquivos)} ARQUIVOS\n")
    print("=" * 100)
    
    # Estatísticas gerais
    estatisticas = []
    total_posts_geral = 0
    total_comentarios_geral = 0
    arquivos_com_problemas = []
    
    for arquivo in sorted(arquivos):
        try:
            with open(arquivo, 'r', encoding='utf-8') as f:
                dados = json.load(f)
            
            # Extrair informações do notebook
            nome_notebook = arquivo.stem  # nome do arquivo sem extensão
            
            # Tentar extrair modelo original do conteúdo
            modelo_original = dados.get('modelo_original', 'N/A')
            modelo_busca = dados.get('modelo_busca_utilizado', 'N/A')
            
            # Estatísticas de posts
            posts = dados.get('posts', [])
            num_posts = len(posts)
            
            # Estatísticas de comentários
            total_comentarios = sum(len(post.get('comentarios', [])) for post in posts)
            
            # Média de comentários por post
            media_comentarios = total_comentarios / num_posts if num_posts > 0 else 0
            
            # Detalhes adicionais
            data_extracao = dados.get('data_extracao', 'N/A')
            total_posts_encontrados_api = dados.get('total_posts_encontrados', 'N/A')
            
            # Verificar se tem posts sem comentários (problema)
            posts_sem_comentarios = sum(1 for post in posts if len(post.get('comentarios', [])) == 0)
            
            # Acumular totais
            total_posts_geral += num_posts
            total_comentarios_geral += total_comentarios
            
            # Armazenar estatísticas
            estatisticas.append({
                'notebook': nome_notebook,
                'modelo_original': modelo_original[:50] + '...' if len(str(modelo_original)) > 50 else modelo_original,
                'modelo_busca': modelo_busca,
                'num_posts': num_posts,
                'total_comentarios': total_comentarios,
                'media_comentarios_post': round(media_comentarios, 2),
                'posts_sem_comentarios': posts_sem_comentarios,
                'total_posts_api': total_posts_encontrados_api,
                'arquivo': arquivo.name
            })
            
            # Debug para arquivos suspeitos
            if num_posts == 0:
                arquivos_com_problemas.append((nome_notebook, "Nenhum post encontrado"))
            elif total_comentarios == 0:
                arquivos_com_problemas.append((nome_notebook, "Posts sem comentários"))
                
        except json.JSONDecodeError as e:
            print(f"❌ Erro ao ler JSON do arquivo {arquivo.name}: {e}")
            arquivos_com_problemas.append((arquivo.name, f"JSON inválido: {e}"))
        except Exception as e:
            print(f"❌ Erro inesperado no arquivo {arquivo.name}: {e}")
            arquivos_com_problemas.append((arquivo.name, f"Erro: {e}"))
    
    # Criar DataFrame para visualização
    df = pd.DataFrame(estatisticas)
    
    if df.empty:
        print("⚠️ Nenhum dado válido encontrado nos arquivos!")
        return
    
    # Ordenar por número de posts (decrescente)
    df = df.sort_values('num_posts', ascending=False)
    
    # Exibir tabela principal
    print("\n📈 ESTATÍSTICAS POR NOTEBOOK")
    print("=" * 100)
    
    # Configurar exibição do pandas
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', None)
    pd.set_option('display.max_colwidth', 30)
    
    # Selecionar colunas para exibição
    colunas_exibir = ['notebook', 'num_posts', 'total_comentarios', 'media_comentarios_post', 'posts_sem_comentarios']
    print(df[colunas_exibir].to_string(index=False))
    
    # Resumo geral
    print("\n" + "=" * 100)
    print("📊 RESUMO GERAL")
    print("=" * 100)
    print(f"📁 Total de arquivos analisados: {len(arquivos)}")
    print(f"📝 Total de notebooks com dados: {len(df[df['num_posts'] > 0])}")
    print(f"🗑️  Notebooks sem posts: {len(df[df['num_posts'] == 0])}")
    print(f"📄 Total de posts únicos: {total_posts_geral}")
    print(f"💬 Total de comentários: {total_comentarios_geral}")
    print(f"📊 Média de posts por notebook: {total_posts_geral/len(df):.2f}")
    print(f"💬 Média de comentários por post: {total_comentarios_geral/total_posts_geral:.2f}" if total_posts_geral > 0 else "💬 Média de comentários por post: N/A")
    
    # Top 10 notebooks com mais posts
    print("\n🏆 TOP 10 NOTEBOOKS COM MAIS POSTS")
    print("=" * 100)
    top_posts = df.nlargest(10, 'num_posts')[['notebook', 'num_posts', 'total_comentarios']]
    for idx, row in top_posts.iterrows():
        print(f"  {row['notebook']}: {row['num_posts']} posts | {row['total_comentarios']} comentários")
    
    # Top 10 notebooks com mais comentários
    print("\n💬 TOP 10 NOTEBOOKS COM MAIS COMENTÁRIOS")
    print("=" * 100)
    top_comentarios = df.nlargest(10, 'total_comentarios')[['notebook', 'total_comentarios', 'num_posts']]
    for idx, row in top_comentarios.iterrows():
        print(f"  {row['notebook']}: {row['total_comentarios']} comentários | {row['num_posts']} posts")
    
    # Arquivos com problemas
    if arquivos_com_problemas:
        print("\n⚠️ ARQUIVOS COM PROBLEMAS/POTENCIAIS ISSUES")
        print("=" * 100)
        for nome, problema in arquivos_com_problemas:
            print(f"  ❌ {nome[:50]}: {problema}")
    
    # Distribuição de posts
    print("\n📊 DISTRIBUIÇÃO DE POSTS")
    print("=" * 100)
    bins = [0, 1, 5, 10, 20, 50, float('inf')]
    labels = ['0', '1-4', '5-9', '10-19', '20-49', '50+']
    df['categoria_posts'] = pd.cut(df['num_posts'], bins=bins, labels=labels, right=False)
    distribuicao = df['categoria_posts'].value_counts().sort_index()
    for categoria, count in distribuicao.items():
        print(f"  {categoria:>10} posts: {count:>3} notebooks ({count/len(df)*100:.1f}%)")
    
    # Salvar relatório detalhado
    relatorio_path = CAMINHO_ENTRADA / "relatorio_analise_notebooks.xlsx"
    with pd.ExcelWriter(relatorio_path, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Estatisticas', index=False)
        
        # Criar sheet de resumo
        resumo = pd.DataFrame({
            'Métrica': ['Total arquivos', 'Total notebooks com dados', 'Total posts', 'Total comentários', 
                       'Média posts/notebook', 'Média comentários/post'],
            'Valor': [len(arquivos), len(df[df['num_posts'] > 0]), total_posts_geral, total_comentarios_geral,
                     f"{total_posts_geral/len(df):.2f}", f"{total_comentarios_geral/total_posts_geral:.2f}" if total_posts_geral > 0 else "N/A"]
        })
        resumo.to_excel(writer, sheet_name='Resumo', index=False)
    
    print(f"\n✅ Relatório detalhado salvo em: {relatorio_path}")
    
    return df

def visualizar_amostra(arquivo_especifico=None):
    """
    Visualiza uma amostra detalhada de um arquivo específico.
    
    Args:
        arquivo_especifico: Nome do arquivo ou None para escolher interativamente
    """
    if arquivo_especifico:
        arquivos = [CAMINHO_ENTRADA / arquivo_especifico]
    else:
        arquivos = list(CAMINHO_ENTRADA.glob("*.json"))
        
        if not arquivos:
            print("Nenhum arquivo encontrado")
            return
        
        print("\n📂 ARQUIVOS DISPONÍVEIS:")
        for i, arquivo in enumerate(arquivos[:20], 1):  # Limitar a 20
            print(f"  {i}. {arquivo.name}")
        
        try:
            escolha = int(input("\nEscolha o número do arquivo para analisar (0 para cancelar): "))
            if escolha == 0:
                return
            arquivo_especifico = arquivos[escolha - 1]
        except (ValueError, IndexError):
            print("Opção inválida!")
            return
    
    try:
        with open(arquivo_especifico, 'r', encoding='utf-8') as f:
            dados = json.load(f)
        
        print(f"\n🔍 ANALISANDO: {arquivo_especifico.name}")
        print("=" * 80)
        print(f"Modelo Original: {dados.get('modelo_original', 'N/A')}")
        print(f"Modelo Busca: {dados.get('modelo_busca_utilizado', 'N/A')}")
        print(f"Total Posts API: {dados.get('total_posts_encontrados', 'N/A')}")
        print(f"Posts salvos: {len(dados.get('posts', []))}")
        
        posts = dados.get('posts', [])
        for i, post in enumerate(posts[:5], 1):  # Mostrar primeiros 5 posts
            print(f"\n  📌 Post {i}: {post.get('titulo', 'Sem título')[:100]}")
            print(f"     ID: {post.get('id')}")
            print(f"     Comentários: {len(post.get('comentarios', []))}")
            print(f"     Score: {post.get('score')}")
            
            # Mostrar primeiros 2 comentários
            for j, coment in enumerate(post.get('comentarios', [])[:2], 1):
                conteudo = coment.get('conteudo', '')[:100]
                print(f"        💬 Comentário {j}: {conteudo}...")
        
        if len(posts) > 5:
            print(f"\n  ... e mais {len(posts) - 5} posts")
            
    except Exception as e:
        print(f"Erro ao analisar {arquivo_especifico}: {e}")

if __name__ == "__main__":
    # Executar análise completa
    df = analisar_arquivos_json()
    
    # Opcional: visualizar um arquivo específico
    resposta = input("\n\nDeseja visualizar um arquivo específico em detalhes? (s/N): ").lower()
    if resposta == 's':
        visualizar_amostra()