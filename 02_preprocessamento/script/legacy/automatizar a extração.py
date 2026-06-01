import os
import json
import pandas as pd
from pathlib import Path

# ============================================
# CONFIGURAÇÕES DE CAMINHO (Mantendo o seu padrão)
# ============================================
# Caso rode fora da estrutura 'core.paths', comente a linha abaixo e use caminhos absolutos
from core.paths import PREPROCESSAMENTO_DATA 

PASTA_LIMPOS = PREPROCESSAMENTO_DATA / "Dados_Limpos_IniciaisV8"
PASTA_SAIDA = PREPROCESSAMENTO_DATA / "analise_estatisticaV3"

# O número mágico estatístico para sua amostra
AMOSTRA_POR_CATEGORIA = 55 

def abrir_json_seguro(caminho):
    """Reaproveitando sua função de leitura segura para evitar erros de encoding"""
    try:
        with open(caminho, 'r', encoding='utf-8') as f:
            return json.load(f)
    except UnicodeDecodeError:
        for enc in ['latin-1', 'cp1252', 'iso-8859-1']:
            try:
                with open(caminho, 'r', encoding=enc) as f:
                    return json.load(f)
            except:
                continue
        with open(caminho, 'r', encoding='utf-8', errors='ignore') as f:
            return json.load(f)

def gerar_planilha_auditoria():
    os.makedirs(PASTA_SAIDA, exist_ok=True)
    arquivos = [f for f in os.listdir(PASTA_LIMPOS) if f.endswith('.json')]
    todos_posts = []

    print(f"🔍 Lendo arquivos e coletando posts para auditoria...")
    
    for arquivo in arquivos:
        caminho_completo = PASTA_LIMPOS / arquivo
        dados = abrir_json_seguro(caminho_completo)
        
        if not dados:
            continue
            
        for post in dados.get('posts', []):
            cat = post.get('categoria', 'nao_categorizado')
            
            # Ignora os não categorizados, queremos auditar as 7 categorias principais
            if cat != 'nao_categorizado':
                todos_posts.append({
                    'Categoria Detectada': cat,
                    'Termos que dispararam a regra': ", ".join(post.get('termos_especificos', [])),
                    'Arquivo de Origem': arquivo,
                    'Título do Post': post.get('titulo', ''),
                    # Limitamos a 1500 caracteres para a planilha não ficar pesada/impossível de ler
                    'Conteúdo do Post': str(post.get('conteudo_post', '')),
                    # Deixamos a coluna de auditoria em branco para você preencher no Excel
                    'Auditoria Humana (Sim/Não/Incerto)': ''
                })

    # Converte tudo para um DataFrame do Pandas
    df_todos = pd.DataFrame(todos_posts)
    print(f"✅ Total de {len(df_todos)} posts categorizados carregados na memória.")
    
    print(f"📊 Realizando o sorteio estratificado ({AMOSTRA_POR_CATEGORIA} por categoria)...")
    
    # Faz o sorteio de 55 posts por categoria (random_state=42 garante que se você rodar de novo, sorteia os mesmos)
    amostra_final = df_todos.groupby('Categoria Detectada', group_keys=False).apply(
        lambda x: x.sample(n=min(len(x), AMOSTRA_POR_CATEGORIA), random_state=42)
    )
    
    # Ordena por categoria para facilitar a sua leitura (você lê todos de bateria, depois todos de tela, etc.)
    amostra_final = amostra_final.sort_values('Categoria Detectada').reset_index(drop=True)

    # Tenta salvar em Excel (muito melhor para ler textos)
    caminho_excel = PASTA_SAIDA / "Planilha_Auditoria_Padrao_Ouro.xlsx"
    caminho_csv = PASTA_SAIDA / "Planilha_Auditoria_Padrao_Ouro.csv"
    
    try:
        
        # Fallback para CSV caso não tenha a biblioteca de Excel
        amostra_final.to_csv(caminho_csv, index=False, encoding='utf-8-sig', sep=';')
        print(f"🎯 SUCESSO! Planilha de auditoria gerada em: {caminho_csv}")
        print("💡 Dica: Para exportar direto como .xlsx na próxima, instale o openpyxl rodando: pip install openpyxl")
    except ImportError:
        # Requer a biblioteca 'openpyxl' (pip install openpyxl)
        amostra_final.to_excel(caminho_excel, index=False)
        print(f"🎯 SUCESSO! Planilha de auditoria gerada em: {caminho_excel}")
        print("-> Abra o arquivo no Excel, ajuste a largura das colunas e ative a 'Quebra de Texto Automática' para ler melhor.")

if __name__ == "__main__":
    gerar_planilha_auditoria()