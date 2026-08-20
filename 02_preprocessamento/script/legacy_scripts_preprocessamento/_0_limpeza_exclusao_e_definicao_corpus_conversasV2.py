import os
import json
import re
from multiprocessing import Manager
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm
from core.paths import EXTRACAO_DATA_BRUTO_ANTIGO, PREPROCESSAMENTO_DATA

# --- CONFIGURAÇÕES DE CAMINHO ---
CAMINHO_ENTRADA = EXTRACAO_DATA_BRUTO_ANTIGO
CAMINHO_SAIDA = PREPROCESSAMENTO_DATA / "Dados_Limpos_IniciaisV3"

def limpar_texto_conservador(texto):
    """Remove URLs e excesso de espaços/quebras de linha."""
    if not texto: 
        return ""
    # Remove URLs (http, https, www)
    texto = re.sub(r'http\S+|www\S+|https\S+', '', texto, flags=re.MULTILINE)
    texto = texto.replace('\t', ' ')
    texto = re.sub(r'\n+', ' ', texto) 
    texto = re.sub(r'\s+', ' ', texto).strip()
    return texto

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
            
            # --- DEDUPLICAÇÃO GLOBAL (NOVO: não feito pelo RedditService) ---
            if p_id in global_ids:
                continue
            
            # Validação básica do post (sem refiltrar o que o RedditService já fez)
            conteudo_post = post.get('conteudo_post', '')
            titulo = post.get('titulo', '')
            
            # Se o post não tem conteúdo E não tem título, pode ser descartado
            if not conteudo_post and not titulo:
                continue
            
            # --- PROCESSAMENTO DOS COMENTÁRIOS ---
            comentarios_ok = []
            for coment in post.get('comentarios', []):
                # Apenas limpeza de texto, sem refiltragem de conteúdo
                txt = limpar_texto_conservador(coment.get('conteudo'))
                if len(txt) > 3:  # Mantém comentários com pelo menos 3 caracteres após limpeza
                    coment['conteudo'] = txt
                    comentarios_ok.append(coment)

            # --- REGRA DE NEGÓCIO: Só mantém posts com interação (comentários) ---
            # Esta é uma regra complementar importante não aplicada na extração
            if len(comentarios_ok) > 0:
                # Limpa título e conteúdo do post
                post['titulo'] = limpar_texto_conservador(titulo)
                post['conteudo_post'] = limpar_texto_conservador(conteudo_post)
                post['comentarios'] = comentarios_ok
                
                posts_limpos.append(post)
                # Registra o ID globalmente para evitar duplicatas entre arquivos
                global_ids[p_id] = True

        # Salva apenas se o arquivo resultante não estiver vazio
        if len(posts_limpos) > 0:
            dados['posts'] = posts_limpos
            with open(caminho_out, 'w', encoding='utf-8') as f:
                json.dump(dados, f, indent=4, ensure_ascii=False)
            return True
        else:
            return f"Vazio após pós-processamento: {arquivo}"
            
    except Exception as e:
        return f"Erro no arquivo {arquivo}: {e}"

def executar_limpeza_paralela():
    """Gerencia o processamento paralelo e a memória compartilhada."""
    if not os.path.exists(CAMINHO_SAIDA): 
        os.makedirs(CAMINHO_SAIDA)
        
    arquivos = [f for f in os.listdir(CAMINHO_ENTRADA) if f.endswith('.json')]
    
    if not arquivos:
        print(f"⚠️ Nenhum arquivo JSON encontrado em: {CAMINHO_ENTRADA}")
        return
    
    # Manager().dict() para compartilhar IDs entre processos
    with Manager() as manager:
        global_ids = manager.dict() 
        
        print(f"🧹 Iniciando pós-processamento e deduplicação global em {len(arquivos)} arquivos...")
        print(f"   (Preservando filtros já aplicados pelo RedditService)")
        
        with ProcessPoolExecutor() as executor:
            # Mapeia os arquivos para os núcleos da CPU
            futures = {
                executor.submit(processar_um_arquivo, arq, global_ids): arq 
                for arq in arquivos
            }
            
            # Barra de progresso tqdm
            arquivos_vazios = 0
            for future in tqdm(as_completed(futures), total=len(arquivos), desc="Pós-processando", unit="arq"):
                resultado = future.result()
                if resultado is not True and resultado is not None:
                    if "Vazio" in str(resultado):
                        arquivos_vazios += 1
                    # Opcional: printar detalhes em modo debug
                    # print(f"   ℹ️ {resultado}")

    print(f"\n✅ Pós-processamento concluído!")
    print(f"   📁 Dados salvos em: {CAMINHO_SAIDA}")
    print(f"   📊 Arquivos processados: {len(arquivos)}")
    print(f"   🗑️  Arquivos vazios (descartados): {arquivos_vazios}")
    print(f"\n📌 OBS: Apenas posts com pelo menos 1 comentário foram mantidos (regra de negócio)")

if __name__ == "__main__":
    executar_limpeza_paralela()