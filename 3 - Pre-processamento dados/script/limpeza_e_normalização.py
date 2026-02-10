import sys
import json
import re
import html
from datetime import datetime
from pathlib import Path

# --- CONFIGURAÇÕES E CAMINHOS ---
# --- CONFIGURAÇÕES E CAMINHOS ---
caminho_script = Path(__file__).resolve().parent
caminho_raiz_projeto = caminho_script.parent.parent 
sys.path.append(str(caminho_raiz_projeto))



from config import DIRETORIO_DADOS_PRE_PROCESSAMENTO, DIRETORIO_DADOS_EXTRACAO_QA
# Caminho para a pasta onde estão os arquivos brutos
DIRETORIO_BRUTO  = DIRETORIO_DADOS_EXTRACAO_QA / 'bruto'
# Caminho para a pasta de saída (onde será salvo o arquivo unificado)
DIRETORIO_PROCESSADO = DIRETORIO_DADOS_EXTRACAO_QA / 'processado'

CAMINHO_SAIDA_JSON = DIRETORIO_DADOS_PRE_PROCESSAMENTO / 'reddit_notebook_dados_limpos.json'

# --- FUNÇÕES ---

def limpar_texto(texto):
    """
    Limpa o texto forçando conversão para string e removendo lixo.
    """
    if texto is None: return ""
    if not isinstance(texto, str): return str(texto)
    
    try: texto = html.unescape(texto)
    except: pass

    texto = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', texto)
    texto = re.sub(r'https?://\S+|www\.\S+', '', texto)
    texto = texto.replace('_', ' ') 
    texto = re.sub(r'[^\w\s.,!?\-]', '', texto)
    texto = re.sub(r'\s+-\s+', ' ', texto) 
    
    return ' '.join(texto.split()).lower()

def enriquecer_tempo(obj_dict, chave_data):
    """
    Adiciona metadados de tempo e retorna o objeto datetime se possível.
    """
    keys_tempo = ['ano', 'mes', 'dia', 'hora', 'trimestre', 'semana', 'semestre', 'dia_semana', 'timestamp']
    data_str = obj_dict.get(chave_data)
    dt = None

    if data_str and isinstance(data_str, str):
        formatos = ["%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"]
        for fmt in formatos:
            try:
                dt = datetime.fromisoformat(data_str.replace('Z', '+00:00'))
                break
            except ValueError:
                try:
                    dt = datetime.strptime(data_str, fmt)
                    break
                except ValueError: continue
    
    if dt:
        obj_dict['ano'] = dt.year
        obj_dict['mes'] = dt.month
        obj_dict['dia'] = dt.day
        obj_dict['hora'] = dt.hour
        obj_dict['trimestre'] = (dt.month - 1) // 3 + 1
        obj_dict['semana'] = dt.isocalendar()[1]
        obj_dict['semestre'] = 1 if dt.month <= 6 else 2
        obj_dict['dia_semana'] = dt.strftime('%A')
        obj_dict['timestamp'] = dt.timestamp()
    else:
        for k in keys_tempo:
            if k not in obj_dict: obj_dict[k] = None
            
    return dt

# --- CARREGAMENTO E CONSOLIDAÇÃO ---
dados_totais = []
arquivos_json = list(DIRETORIO_BRUTO.glob('*.json'))

print(f"Localizados {len(arquivos_json)} arquivos na pasta bruto.")

for caminho_arq in arquivos_json:
    print(f"Lendo arquivo: {caminho_arq.name}...")
    with open(caminho_arq, 'r', encoding='utf-8') as f:
        conteudo = json.load(f)
        # Se o arquivo for uma lista, estende a lista principal, se for dict, adiciona
        if isinstance(conteudo, list):
            dados_totais.extend(conteudo)
        else:
            dados_totais.append(conteudo)

# --- CONFIGURAÇÃO DE FILTROS ---
autores_ignorar = {"[deleted]", "[removed]", "[Deletado]", "AutoModerator", "DellCares"} 
textos_ignorar = {"[deleted]", "[removed]", ""}
frases_bot = ["I am a bot", "action was performed automatically"]

posts_processados = 0

# --- PROCESSAMENTO ---
print("Iniciando limpeza, enriquecimento e ordenação de todos os dados...")

for item in dados_totais:
    # 1. Metadados do Item (Busca)
    if 'meta_data' in item:
        enriquecer_tempo(item['meta_data'], 'data_extracao')

    # 2. Processar Posts
    if 'posts' in item:
        for post in item['posts']:
            posts_processados += 1
            
            # Limpeza
            post['titulo_limpo'] = limpar_texto(post.get('titulo'))
            post['conteudo_texto_limpo'] = limpar_texto(post.get('conteudo_texto'))
            
            # Data
            enriquecer_tempo(post, 'data_publicacao')

            # Comentários
            if 'comentarios' in post:
                comentarios_limpos = []
                textos_vistos_neste_post = set()
                
                for comentario in post['comentarios']:
                    texto_orig = comentario.get('conteudo') or ""
                    autor = comentario.get('autor_comentario', '')

                    if autor in autores_ignorar: continue
                    if texto_orig in textos_ignorar: continue
                    if any(bot in texto_orig for bot in frases_bot): continue

                    texto_tratado = limpar_texto(texto_orig)
                    
                    if len(texto_tratado) < 2: continue
                    if texto_tratado in textos_vistos_neste_post: continue
                    
                    comentario['conteudo_limpo'] = texto_tratado
                    enriquecer_tempo(comentario, 'data_publicacao')
                    
                    textos_vistos_neste_post.add(texto_tratado)
                    comentarios_limpos.append(comentario)
                
                # Ordenar comentários (Antigo -> Novo)
                comentarios_limpos.sort(key=lambda x: x.get('timestamp') or 0)
                
                post['comentarios'] = comentarios_limpos
                post['total_comentarios'] = len(comentarios_limpos)

        # Ordenação dos Posts por timestamp
        item['posts'].sort(key=lambda p: p.get('timestamp') or 0)

# --- SALVAMENTO ---
print(f"\nSalvando {posts_processados} posts unificados e processados...")
CAMINHO_SAIDA_JSON.parent.mkdir(parents=True, exist_ok=True)
with open(CAMINHO_SAIDA_JSON, 'w', encoding='utf-8') as f:
    json.dump(dados_totais, f, ensure_ascii=False, indent=4)

print(f"Sucesso! Arquivo consolidado salvo em: {CAMINHO_SAIDA_JSON}")