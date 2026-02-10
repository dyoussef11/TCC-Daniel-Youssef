
# import sys
# import os
# import re  # IMPORTANTE: para limpar caracteres como '*'
# import json
# import datetime
# from pathlib import Path
# from tqdm import tqdm  # pip install tqdm

# # --- FIX DE IMPORTAÇÃO ---
# caminho_projeto = Path(__file__).resolve().parent.parent
# if str(caminho_projeto) not in sys.path:
#     sys.path.insert(0, str(caminho_projeto))
# # -------------------------

# from src.extractors.reddit_service import RedditService
# from src.core.model_loader import ModelLoader

# # --- FUNÇÃO PARA CORRIGIR O ERRO DE NOME DE ARQUIVO (Errno 22) ---
# def limpar_nome_arquivo(nome):
#     # Remove caracteres que o Windows proíbe: \ / * ? : " < > |
#     return re.sub(r'[\\/*?:"<>|]', "", str(nome)).replace(" ", "_").strip()

# def main():
#     print("\n" + "="*40)
#     print("=== INICIANDO EXTRAÇÃO DE CONVERSAS (REDDIT) ===")
#     print("="*40)
    
#     caminho_raiz_geral = caminho_projeto.parent 
    
#     try:
#         reddit = RedditService()
#     except Exception as e:
#         print(f"❌ Erro ao conectar ao Reddit: {e}")
#         return
    
#     loader = ModelLoader(reddit.config)
#     caminho_csv = caminho_raiz_geral / "0 - Dataset dos notebooks gamer" / "dataset_final_csv" / "dataset_laptops_GAMER_ONLY.csv"
    
#     if not caminho_csv.exists():
#         print(f"❌ Erro: Dataset não encontrado em {caminho_csv}")
#         return

#     modelos_data = loader.carregar_modelos_preparados(caminho_csv)
#     print(f"📦 Encontrados {len(modelos_data)} modelos gamer.\n")

#     # --- LOOP COM BARRA DE PROGRESSO E LÓGICA DE CONTINUAR ---
#     for item in tqdm(modelos_data, desc="Extraindo Laptops", unit="laptop"):
#         original = item['original']
#         busca = item['busca']
        
#         # Correção do Nome do Arquivo para evitar OSError [Errno 22]
#         safe_name = limpar_nome_arquivo(busca.lower())
#         nome_arquivo = f"{safe_name}.json"
        
#         pasta_saida = caminho_projeto / reddit.config["paths"]["output_bruto"]
#         pasta_saida.mkdir(parents=True, exist_ok=True)
#         caminho_saida = pasta_saida / nome_arquivo

#         # LÓGICA DE RESUME: Pula se o arquivo já existir
#         if caminho_saida.exists():
#             continue 

#         posts = reddit.buscar_modelo(busca)
        
#         dados_finais = {
#             "metadados": {
#                 "modelo_original": original,
#                 "keyword_busca": busca,
#                 "data_extracao": datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
#                 "total_posts": len(posts)
#             },
#             "resultados": posts
#         }

#         with open(caminho_saida, 'w', encoding='utf-8') as f:
#             json.dump(dados_finais, f, indent=4, ensure_ascii=False)

# if __name__ == "__main__":
#     main()

import sys
import json
import re
import html
from datetime import datetime
from pathlib import Path

caminho_script = Path(__file__).resolve().parent
caminho_raiz_projeto = caminho_script.parent.parent 
sys.path.append(str(caminho_raiz_projeto))



from config import DIRETORIO_DADOS_PRE_PROCESSAMENTO, DIRETORIO_DADOS_EXTRACAO_QA
# Caminho para a pasta onde estão os arquivos brutos
DIRETORIO_BRUTO  = DIRETORIO_DADOS_EXTRACAO_QA / 'bruto'
# Caminho para a pasta de saída (onde será salvo o arquivo unificado)
DIRETORIO_PROCESSADO = DIRETORIO_DADOS_EXTRACAO_QA / 'processado'


CAMINHO_SAIDA_JSON = DIRETORIO_PROCESSADO / 'reddit_notebook_dados_limpos.json'

# --- FUNÇÕES DE LIMPEZA E NORMALIZAÇÃO ---

def simplificar_nome_notebook(nome_arquivo):
    """
    Remove extensões, códigos de SKU e especificações técnicas do nome do arquivo.
    Ex: 'acer_nitro_5_an515-58_nh.qfhsi.008.json' -> 'acer_nitro_5'
    """
    # 1. Remove a extensão e converte para minúsculo
    nome = nome_arquivo.lower().replace('.json', '')
    
    # 2. Padrões que indicam início de lixo ou specs técnicas
    padroes_limpeza = [
        r'_intel_core.*', r'_amd_ryzen.*', r'_rtx.*', r'_gtx.*',
        r'_-.*', r'_\d+gb.*', r'_\d+th_gen.*', r'_\(.*\)',
        r'_nh\..*', r'_nx\..*', r'_8gb.*', r'_16gb.*', r'_512gb.*',
        r'_an\d+.*', r'_ph\d+.*', r'_g[1-5]-.*'
    ]
    
    for padrao in padroes_limpeza:
        nome = re.split(padrao, nome, flags=re.IGNORECASE)[0]
    
    # 3. Limpeza final de underlines e espaços
    nome = nome.strip('_').strip().replace('_', ' ')
    
    return nome

def limpar_texto(texto):
    if texto is None: return ""
    if not isinstance(texto, str): return str(texto)
    try: texto = html.unescape(texto)
    except: pass
    
    texto = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', texto)
    texto = re.sub(r'https?://\S+|www\.\S+', '', texto)
    texto = texto.replace('_', ' ') 
    texto = re.sub(r'[^\w\s.,!?\-]', '', texto)
    return ' '.join(texto.split()).lower()

def enriquecer_tempo(obj_dict, chave_data):
    data_str = obj_dict.get(chave_data)
    dt = None
    if data_str and isinstance(data_str, str):
        try:
            dt = datetime.fromisoformat(data_str.replace('Z', '+00:00'))
        except ValueError:
            pass
    
    if dt:
        obj_dict.update({
            'ano': dt.year, 'mes': dt.month, 'dia': dt.day,
            'timestamp': dt.timestamp(), 'dia_semana': dt.strftime('%A')
        })
    return dt

# --- PROCESSAMENTO ---

dados_totais = []
arquivos_json = list(DIRETORIO_BRUTO.glob('*.json'))

# Termos para ignorar acessórios (opcional)
termos_acessorios = ['mouse', 'pad', 'headphone', 'cable', 'battery', 'keyboard', 'amplifier', 'earbuds']

print(f"🔍 Localizados {len(arquivos_json)} arquivos para processar.")

for caminho_arq in arquivos_json:
    nome_limpo = simplificar_nome_notebook(caminho_arq.name)
    
    # Filtro: Pula se for acessório
    if any(termo in nome_limpo for termo in termos_acessorios):
        continue

    with open(caminho_arq, 'r', encoding='utf-8') as f:
        try:
            conteudo = json.load(f)
            
            # Padroniza para lista para processar igual
            itens_arquivo = conteudo if isinstance(conteudo, list) else [conteudo]
            
            for item in itens_arquivo:
                # Adiciona o nome simplificado ao JSON
                item['modelo_referencia'] = nome_limpo
                
                if 'posts' in item:
                    for post in item['posts']:
                        post['titulo_limpo'] = limpar_texto(post.get('titulo'))
                        post['conteudo_texto_limpo'] = limpar_texto(post.get('conteudo_texto'))
                        enriquecer_tempo(post, 'data_publicacao')

                        if 'comentarios' in post:
                            comentarios_limpos = []
                            for com in post['comentarios']:
                                # Filtros de autor e lixo aqui (mantidos do original)
                                com['conteudo_limpo'] = limpar_texto(com.get('conteudo'))
                                if len(com['conteudo_limpo']) > 2:
                                    enriquecer_tempo(com, 'data_publicacao')
                                    comentarios_limpos.append(com)
                            
                            comentarios_limpos.sort(key=lambda x: x.get('timestamp') or 0)
                            post['comentarios'] = comentarios_limpos
                    
                    item['posts'].sort(key=lambda p: p.get('timestamp') or 0)
                
                dados_totais.append(item)
                
        except Exception as e:
            print(f"❌ Erro ao ler {caminho_arq.name}: {e}")

# --- SALVAMENTO ---
DIRETORIO_PROCESSADO.mkdir(parents=True, exist_ok=True)
with open(CAMINHO_SAIDA_JSON, 'w', encoding='utf-8') as f:
    json.dump(dados_totais, f, ensure_ascii=False, indent=4)

print(f"\n✅ Sucesso! Arquivo consolidado e limpo em: {CAMINHO_SAIDA_JSON}")
print(f"📊 Total de modelos processados: {len(dados_totais)}")