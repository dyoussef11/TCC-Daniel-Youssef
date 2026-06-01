import os
import json
import re
from multiprocessing import Manager
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm
from core.paths import EXTRACAO_CONFIG, EXTRACAO_DATA, PREPROCESSAMENTO_DATA

# --- CONFIGURAÇÕES DE CAMINHO ---
CAMINHO_ENTRADA = EXTRACAO_DATA / "brutoV6"
CAMINHO_SAIDA = PREPROCESSAMENTO_DATA / "Dados_Limpos_IniciaisV7"



def limpar_texto_suporte_tecnico(texto):
    """
    Limpeza otimizada para manter o contexto de hardware e suporte.
    """
    if not texto: 
        return ""

    # 1. PLACEHOLDERS DE EVIDÊNCIA
    # Substitui links por tags que informam ao sumarizador que há uma prova visual
    texto = re.sub(r'http\S+|www\S+|https\S+', '[URL_EVIDENCIA]', texto)

    # 2. PRESERVAÇÃO DE TERMOS TÉCNICOS
    # Remove caracteres especiais "sujos", mas mantém hifens (i7-11800H), 
    # pontos de versão e o símbolo de grau (C/F) para temperaturas.
    # Primeiro, removemos o que não é ASCII (emojis e ruídos visuais)
    texto = re.sub(r'[^\x00-\x7f]', r'', texto)
    
    # 3. NORMALIZAÇÃO DE ESTRUTURA
    # Converte tabs em espaços e remove quebras de linha excessivas
    # para evitar que o sumarizador perca a conexão entre frases.
    texto = texto.replace('\t', ' ')
    texto = re.sub(r'\n+', '\n', texto)
    
    # 4. DENSIDADE DE INFORMAÇÃO
    # Remove espaços duplos e limpa as extremidades
    texto = re.sub(r' +', ' ', texto).strip()
    
    return texto

def eh_post_critico(titulo, search_groups):
    """
    Verifica se o título contém termos de alta relevância técnica.[cite: 8, 14]
    Isso evita descartar posts que não têm comentários mas são reclamações diretas.
    """
    texto_titulo = titulo.lower()
    for categoria in search_groups.values():
        if any(termo.lower() in texto_titulo for termo in categoria):
            return True
    return False

def processar_um_arquivo(arquivo, global_ids, search_groups):
    try:
        caminho_in = CAMINHO_ENTRADA / arquivo
        caminho_out = CAMINHO_SAIDA / arquivo
        
        with open(caminho_in, 'r', encoding='utf-8') as f:
            dados = json.load(f)
        
        posts_limpos = []

        for post in dados.get('posts', []):
            p_id = post.get('id')
            
            # DEDUPLICAÇÃO GLOBAL[cite: 14]
            if p_id in global_ids:
                continue
            
            titulo_original = post.get('titulo', '')
            conteudo_original = post.get('conteudo_post', '')
            
            # Processamento dos comentários
            comentarios_ok = []
            for coment in post.get('comentarios', []):
                txt = limpar_texto_suporte_tecnico(coment.get('conteudo'))
                # Mantém se tiver conteúdo após a limpeza
                if len(txt) > 5: 
                    coment['conteudo'] = txt
                    comentarios_ok.append(coment)

            # NOVA REGRA: Mantém se tiver comentários OU se o título for tecnicamente crítico[cite: 8, 14, 15]
            if len(comentarios_ok) > 0 or eh_post_critico(titulo_original, search_groups):
                post['titulo'] = limpar_texto_suporte_tecnico(titulo_original)
                post['conteudo_post'] = limpar_texto_suporte_tecnico(conteudo_original)
                post['comentarios'] = comentarios_ok
                
                posts_limpos.append(post)
                global_ids[p_id] = True

        if len(posts_limpos) > 0:
            dados['posts'] = posts_limpos
            with open(caminho_out, 'w', encoding='utf-8') as f:
                json.dump(dados, f, indent=4, ensure_ascii=False)
            return True
        return f"Vazio: {arquivo}"
            
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

    # Carrega os grupos de busca para validar posts críticos (sem comentários mas importantes)
    try:
        # Ajuste o caminho para o seu arquivo de configuração real
        config_path = EXTRACAO_CONFIG / "extractor_settings_extendedV6.json"
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            search_groups = config["reddit_params"]["search_groups"]
    except Exception as e:
        print(f"⚠️ Erro ao carregar search_groups: {e}. Usando filtro vazio.")
        search_groups = {}

    # Manager().dict() permite que os IDs processados sejam compartilhados entre os núcleos da CPU
    with Manager() as manager:
        global_ids = manager.dict() 
        
        print(f"🧹 Iniciando limpeza técnica e deduplicação global em {len(arquivos)} arquivos...")
        print(f"   (Preservando placeholders de URL e entidades de hardware)")
        
        with ProcessPoolExecutor() as executor:
            # Mapeia os arquivos para processamento paralelo[cite: 14]
            futures = {
                executor.submit(processar_um_arquivo, arq, global_ids, search_groups): arq 
                for arq in arquivos
            }
            
            arquivos_vazios = 0
            for future in tqdm(as_completed(futures), total=len(arquivos), desc="Limpando Corpus", unit="arq"):
                resultado = future.result()
                if resultado is not True:
                    if "Vazio" in str(resultado):
                        arquivos_vazios += 1

    print(f"\n✅ Limpeza técnica concluída!")
    print(f"   📁 Dados salvos em: {CAMINHO_SAIDA}")
    print(f"   📊 Arquivos processados: {len(arquivos)}")
    print(f"   🗑️  Arquivos descartados por serem irrelevantes: {arquivos_vazios}")

# O bloco principal é indispensável para multiprocessing no Windows[cite: 14]
if __name__ == "__main__":
    executar_limpeza_paralela()