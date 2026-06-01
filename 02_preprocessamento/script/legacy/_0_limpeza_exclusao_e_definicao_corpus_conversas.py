import os
import json
import re
from multiprocessing import Manager
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm
from core.paths import EXTRACAO_DATA_BRUTO, PREPROCESSAMENTO_DATA

# --- CONFIGURAÇÕES DE CAMINHO ---
CAMINHO_ENTRADA = EXTRACAO_DATA_BRUTO
CAMINHO_SAIDA = PREPROCESSAMENTO_DATA / "Dados_Limpos_IniciaisV2"

def limpar_texto_conservador(texto):
    """Remove URLs e excesso de espaços/quebras de linha."""
    if not texto: return ""
    # Remove URLs (http, https, www)
    texto = re.sub(r'http\S+|www\S+|https\S+', '', texto, flags=re.MULTILINE)
    texto = texto.replace('\t', ' ')
    texto = re.sub(r'\n+', ' ', texto) 
    texto = re.sub(r'\s+', ' ', texto).strip()
    return texto

def eh_ruido_real(autor, conteudo):
    """Filtra bots conhecidos, posts deletados ou conteúdo muito curto."""
    if not conteudo or len(str(conteudo).strip()) < 2: return True
    autor_str = str(autor).lower() if autor else ""
    conteudo_str = str(conteudo).lower()
    
    bots = ["automoderator", "visualmod", "remindmebot"]
    if any(bot in autor_str for bot in bots): return True
    if conteudo_str.strip() in ["[deleted]", "[removed]"]: return True
    return False

def processar_um_arquivo(arquivo, global_ids):
    """
    Processa um arquivo individual consultando e alimentando 
    o dicionário de IDs global para evitar duplicatas.
    """
    try:
        caminho_in = CAMINHO_ENTRADA / arquivo
        caminho_out = CAMINHO_SAIDA / arquivo
        
        with open(caminho_in, 'r', encoding='utf-8') as f:
            dados = json.load(f)
        
        posts_limpos = []

        for post in dados.get('posts', []):
            p_id = post.get('id')
            
            # --- DEDUPLICAÇÃO GLOBAL ---
            # Verifica se o ID já existe no dicionário compartilhado entre processos
            if p_id in global_ids or eh_ruido_real(post.get('author'), post.get('conteudo_post')):
                continue
            
            comentarios_ok = []
            for coment in post.get('comentarios', []):
                # Limpa e valida cada comentário
                if not eh_ruido_real(coment.get('autor'), coment.get('conteudo')):
                    txt = limpar_texto_conservador(coment.get('conteudo'))
                    if len(txt) > 2:
                        coment['conteudo'] = txt
                        comentarios_ok.append(coment)

            # --- REGRA DE NEGÓCIO: Só mantém posts com interação (comentários) ---
            if len(comentarios_ok) > 0:
                post['titulo'] = limpar_texto_conservador(post.get('titulo'))
                post['conteudo_post'] = limpar_texto_conservador(post.get('conteudo_post'))
                post['comentarios'] = comentarios_ok
                
                posts_limpos.append(post)
                # Registra o ID globalmente para que outros arquivos não o processem novamente
                global_ids[p_id] = True

        # Salva apenas se o arquivo resultante não estiver vazio
        if len(posts_limpos) > 0:
            dados['posts'] = posts_limpos
            with open(caminho_out, 'w', encoding='utf-8') as f:
                json.dump(dados, f, indent=4, ensure_ascii=False)
            return True
        else:
            return f"Vazio após limpeza/deduplicação: {arquivo}"
            
    except Exception as e:
        return f"Erro no arquivo {arquivo}: {e}"

def executar_limpeza_paralela():
    """Gerencia o processamento paralelo e a memória compartilhada."""
    if not os.path.exists(CAMINHO_SAIDA): 
        os.makedirs(CAMINHO_SAIDA)
        
    arquivos = [f for f in os.listdir(CAMINHO_ENTRADA) if f.endswith('.json')]
    
    # Manager().dict() é a forma mais estável de compartilhar um 'set' de IDs entre processos
    with Manager() as manager:
        global_ids = manager.dict() 
        
        print(f"🧹 Iniciando limpeza e deduplicação global em {len(arquivos)} arquivos...")
        
        with ProcessPoolExecutor() as executor:
            # Mapeia os arquivos para os núcleos da CPU
            futures = {
                executor.submit(processar_um_arquivo, arq, global_ids): arq 
                for arq in arquivos
            }
            
            # Barra de progresso tqdm
            for future in tqdm(as_completed(futures), total=len(arquivos), desc="Processando", unit="arq"):
                resultado = future.result()
                if resultado is not True:
                    # Opcional: printar arquivos que ficaram vazios ou deram erro
                    pass 

    print(f"\n✅ Limpeza concluída! Dados salvos em: {CAMINHO_SAIDA}")

if __name__ == "__main__":
    executar_limpeza_paralela()