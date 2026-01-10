import sys
import json
import re
import html
from datetime import datetime
from pathlib import Path
import pandas as pd

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

# --- FUNÇÕES AUXILIARES ---

def limpar_texto(texto):
    if not isinstance(texto, str):
        return ""
    
    texto = html.unescape(texto)
    texto = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', texto) # Markdown links
    texto = re.sub(r'https?://\S+|www\.\S+', '', texto)    # URLs
    
    # Remove underscore manual para emojis tipo T_T ou -_-
    texto = texto.replace('_', ' ') 
    
    # Regex agressiva: remove ; : ( ) " ' < > e mantém apenas .,!?-
    texto = re.sub(r'[^\w\s.,!?\-]', '', texto)
    
    # Limpa hífens soltos (ex: o que sobrou de ";-;")
    texto = re.sub(r'\s+-\s+', ' ', texto)
    
    texto = ' '.join(texto.split())
    return texto.lower()

def enriquecer_tempo(obj_dict, chave_data):
    """
    Calcula metadados temporais e insere no dicionário.
    Suporta formatos com ou sem milissegundos.
    """
    data_str = obj_dict.get(chave_data)
    if not data_str:
        return

    dt = None
    formatos = [
        "%Y-%m-%dT%H:%M:%S.%f", # Com milissegundos
        "%Y-%m-%dT%H:%M:%S"     # Sem milissegundos
    ]
    
    for fmt in formatos:
        try:
            # Tenta conversão mais robusta primeiro (Python 3.7+)
            dt = datetime.fromisoformat(data_str)
            break
        except ValueError:
            try:
                # Fallback para strptime
                dt = datetime.strptime(data_str, fmt)
                break
            except ValueError:
                continue
    
    if dt is None:
        return 

    # Insere as novas chaves
    obj_dict['ano'] = dt.year
    obj_dict['mes'] = dt.month
    obj_dict['dia'] = dt.day
    obj_dict['hora'] = dt.hour
    obj_dict['trimestre'] = (dt.month - 1) // 3 + 1
    obj_dict['semana'] = dt.isocalendar()[1]
    obj_dict['semestre'] = 1 if dt.month <= 6 else 2
    obj_dict['dia_semana'] = dt.strftime('%A')
    obj_dict['timestamp'] = dt.timestamp()

# --- CARREGAMENTO ---
with open(CAMINHO_ENTRADA_JSON, 'r', encoding='utf-8') as f:
    dados = json.load(f)

# --- CONFIGURAÇÃO DE FILTROS ---
autores_ignorar = {"[deleted]", "[removed]", "[Deletado]", "AutoModerator", "DellCares"} 
textos_ignorar = {"[deleted]", "[removed]"}
frases_bot = ["I am a bot", "action was performed automatically"]
textos_vistos = set()
comentarios_mantidos_total = 0

# --- PROCESSAMENTO PRINCIPAL ---
for item in dados:
    
    # 1. Enriquecer META DATA (data_extracao)
    if 'meta_data' in item:
        enriquecer_tempo(item['meta_data'], 'data_extracao')

    if 'posts' in item:
        for post in item['posts']:
            
            # 2. Enriquecer POST (data_publicacao)
            # AQUI ESTÁ A CORREÇÃO SOLICITADA
            enriquecer_tempo(post, 'data_publicacao')

            if 'comentarios' in post:
                comentarios_limpos = []
                
                for comentario in post['comentarios']:
                    texto_original = comentario.get('conteudo', '')
                    autor = comentario.get('autor_comentario', '')

                    # --- FILTROS DE LIMPEZA ---
                    if autor in autores_ignorar: continue
                    if texto_original in textos_ignorar: continue
                    if any(frase in texto_original for frase in frases_bot): continue

                    texto_tratado = limpar_texto(texto_original)
                    
                    if not texto_tratado or len(texto_tratado) < 2: continue
                    if texto_tratado in textos_vistos: continue
                    
                    # --- ATUALIZAÇÕES ---
                    comentario['conteudo_limpo'] = texto_tratado
                    
                    # 3. Enriquecer COMENTÁRIO (data_publicacao)
                    enriquecer_tempo(comentario, 'data_publicacao')
                    
                    textos_vistos.add(texto_tratado)
                    comentarios_limpos.append(comentario)
                
                post['comentarios'] = comentarios_limpos
                post['total_comentarios'] = len(comentarios_limpos)
                comentarios_mantidos_total += len(comentarios_limpos)

# --- SALVAMENTO JSON ---
CAMINHO_SAIDA_JSON.parent.mkdir(parents=True, exist_ok=True)
with open(CAMINHO_SAIDA_JSON, 'w', encoding='utf-8') as f:
    json.dump(dados, f, ensure_ascii=False, indent=4)

print(f"Processamento concluído.")
print(f"Total de comentários válidos: {comentarios_mantidos_total}")
print(f"Arquivo salvo em: {CAMINHO_SAIDA_JSON}")

# --- VALIDAÇÃO RÁPIDA (Opcional) ---
# Vamos verificar se o primeiro post realmente recebeu os campos novos
if dados and 'posts' in dados[0] and len(dados[0]['posts']) > 0:
    primeiro_post = dados[0]['posts'][0]
    print("\nVerificação do primeiro post:")
    print(f"Data Original: {primeiro_post.get('data_publicacao')}")
    print(f"Ano Extraído: {primeiro_post.get('ano')}")
    print(f"Semestre: {primeiro_post.get('semestre')}")