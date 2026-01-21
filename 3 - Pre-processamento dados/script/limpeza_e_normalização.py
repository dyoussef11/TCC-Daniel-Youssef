import sys
import json
import re
import html
from datetime import datetime
from pathlib import Path

# --- CONFIGURAÇÕES E CAMINHOS ---
caminho_script = Path(__file__).resolve().parent
caminho_raiz_projeto = caminho_script.parent.parent 
sys.path.append(str(caminho_raiz_projeto))

try:
    from config import DIRETORIO_DADOS_EXTRACAO_QA, DIRETORIO_DADOS_PRE_PROCESSAMENTO
except ImportError:
    print("Aviso: Módulos de configuração não encontrados. Usando caminhos locais.")
    DIRETORIO_DADOS_EXTRACAO_QA = caminho_script / 'dados_saida'
    DIRETORIO_DADOS_PRE_PROCESSAMENTO = caminho_script / 'dados_saida'

CAMINHO_ENTRADA_JSON = DIRETORIO_DADOS_EXTRACAO_QA / 'reddit_dados_estruturados_modelo.json'
CAMINHO_SAIDA_JSON = DIRETORIO_DADOS_PRE_PROCESSAMENTO / 'reddit_dados_limpos_enriquecidos.json'

# --- FUNÇÕES ---

def limpar_texto(texto):
    """
    Limpa o texto forçando conversão para string e removendo lixo.
    """
    if texto is None: return ""
    if not isinstance(texto, str): return str(texto)
    
    # Decodifica HTML
    try: texto = html.unescape(texto)
    except: pass

    # Remove links markdown e URLs
    texto = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', texto)
    texto = re.sub(r'https?://\S+|www\.\S+', '', texto)
    
    # Remove caracteres especiais mantendo pontuação básica
    texto = texto.replace('_', ' ') 
    texto = re.sub(r'[^\w\s.,!?\-]', '', texto)
    texto = re.sub(r'\s+-\s+', ' ', texto) # Hífens soltos
    
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
                dt = datetime.fromisoformat(data_str)
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

# --- CARREGAMENTO ---
print(f"Lendo arquivo: {CAMINHO_ENTRADA_JSON.name}...")
with open(CAMINHO_ENTRADA_JSON, 'r', encoding='utf-8') as f:
    dados = json.load(f)

# --- CONFIGURAÇÃO DE FILTROS ---
autores_ignorar = {"[deleted]", "[removed]", "[Deletado]", "AutoModerator", "DellCares"} 
textos_ignorar = {"[deleted]", "[removed]", ""}
frases_bot = ["I am a bot", "action was performed automatically"]

posts_processados = 0
primeiro_post_verificado = False 

# --- PROCESSAMENTO ---
print("Iniciando limpeza, enriquecimento e ordenação...")

for item in dados:
    # 1. Metadados do Item (Busca)
    if 'meta_data' in item:
        enriquecer_tempo(item['meta_data'], 'data_extracao')

    # 2. Processar Posts
    if 'posts' in item:
        for post in item['posts']:
            posts_processados += 1
            
            # Limpeza
            titulo_original = post.get('titulo') or ""
            conteudo_original = post.get('conteudo_texto') or ""

            post['titulo_limpo'] = limpar_texto(titulo_original)
            post['conteudo_texto_limpo'] = limpar_texto(conteudo_original)
            
            # Debug (apenas 1º post)
            if not primeiro_post_verificado:
                print(f"\n[DEBUG] Verificando 1º Post encontrado:")
                print(f"   -> Título Limpo: '{post['titulo_limpo']}'")
                primeiro_post_verificado = True

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
                
                # Opcional: Ordenar comentários do mais antigo para o novo também
                comentarios_limpos.sort(key=lambda x: x.get('timestamp') or 0)
                
                post['comentarios'] = comentarios_limpos
                post['total_comentarios'] = len(comentarios_limpos)

        # --- ORDENAÇÃO DOS POSTS (NOVA FUNCIONALIDADE) ---
        # Ordena a lista de posts deste modelo baseando-se no timestamp (Crescente: Antigo -> Novo)
        # Se timestamp for None, assume 0 para não quebrar
        item['posts'].sort(key=lambda p: p.get('timestamp') or 0)

# --- SALVAMENTO ---
print(f"\nSalvando {posts_processados} posts processados e ordenados...")
CAMINHO_SAIDA_JSON.parent.mkdir(parents=True, exist_ok=True)
with open(CAMINHO_SAIDA_JSON, 'w', encoding='utf-8') as f:
    json.dump(dados, f, ensure_ascii=False, indent=4)

print(f"Sucesso! Arquivo salvo em: {CAMINHO_SAIDA_JSON}")