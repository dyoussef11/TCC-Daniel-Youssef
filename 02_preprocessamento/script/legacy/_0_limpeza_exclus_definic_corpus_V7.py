import os
import json
import re
from datetime import datetime
from multiprocessing import Manager
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm
from core.paths import EXTRACAO_CONFIG, EXTRACAO_DATA, PREPROCESSAMENTO, PREPROCESSAMENTO_DATA

# --- CONFIGURAÇÕES DE CAMINHO ---
CAMINHO_ENTRADA = EXTRACAO_DATA / "brutoV9"
CAMINHO_SAIDA = PREPROCESSAMENTO_DATA / "Dados_Limpos_IniciaisV11"
CAMINHO_LOG = PREPROCESSAMENTO / "Logs2"


def limpar_texto_suporte_tecnico(texto):
    """
    Limpeza otimizada para manter contexto de hardware e suporte.
    Preserva acentos, símbolos técnicos (×, μ, °, ², etc.) e placeholders de URL.
    Remove apenas emojis e caracteres de controle não essenciais.
    """
    if not texto:
        return ""

    # 1. Substitui URLs por placeholder
    texto = re.sub(r'http\S+|www\S+|https\S+', '[URL_EVIDENCIA]', texto)

    # 2. Remove emojis (blocos Unicode comuns)
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # símbolos & pictogramas
        "\U0001F680-\U0001F6FF"  # transporte & mapas
        "\U0001F700-\U0001F77F"  # alquimia
        "\U0001F780-\U0001F7FF"  # geometria
        "\U0001F800-\U0001F8FF"  # setas suplementares
        "\U0001F900-\U0001F9FF"  # símbolos suplementares
        "\U0001FA00-\U0001FA6F"  # xadrez & símbolos
        "\U0001FA70-\U0001FAFF"  # objetos & bandeiras
        "\U00002702-\U000027B0"  # dingbats
        "\U000024C2-\U0001F251"
        "]+", flags=re.UNICODE
    )
    texto = emoji_pattern.sub(r'', texto)

    # 3. Mantém caracteres úteis: ASCII imprimível + acentos + símbolos técnicos
    # Símbolos técnicos comuns em hardware (pode ser expandido)
    tech_symbols = r'×μΩ°²³¹€£¥©®™←→↑↓•·—–…'
    # Padrão que permite:
    # - ASCII imprimível (espaço a ~)
    # - Quebras de linha, tab, retorno de carro
    # - Letras acentuadas Latin-1 Supplement (À-ÿ)
    # - Símbolos técnicos definidos
    keep_pattern = r'[ -~\n\r\tÀ-ÿ' + re.escape(tech_symbols) + r']'
    texto = re.sub(r'[^' + keep_pattern[1:-1] + r']', '', texto)

    # 4. Normalização de espaços e quebras (mesmo comportamento anterior)
    texto = texto.replace('\t', ' ')
    texto = re.sub(r'\n+', '\n', texto)
    texto = re.sub(r' +', ' ', texto).strip()
    return texto

def eh_post_critico(titulo, search_groups):
    """
    Verifica se o título contém termos de alta relevância técnica.
    """
    texto_titulo = titulo.lower()
    for categoria in search_groups.values():
        if any(termo.lower() in texto_titulo for termo in categoria):
            return True
    return False

def processar_um_arquivo(arquivo, global_ids, search_groups, discard_log):
    """
    Processa um único arquivo JSON.
    Registra no discard_log qualquer post descartado e o motivo.
    Retorna True se o arquivo gerou pelo menos um post limpo, senão False.
    """
    try:
        caminho_in = CAMINHO_ENTRADA / arquivo
        caminho_out = CAMINHO_SAIDA / arquivo

        with open(caminho_in, 'r', encoding='utf-8') as f:
            dados = json.load(f)

        posts_limpos = []

        for post in dados.get('posts', []):
            p_id = post.get('id')
            titulo_original = post.get('titulo', '')
            conteudo_original = post.get('conteudo_post', '')

            # --- DEDUPLICAÇÃO GLOBAL ---
            if p_id in global_ids:
                discard_log.append({
                    "arquivo": arquivo,
                    "post_id": p_id,
                    "titulo_original": titulo_original,
                    "motivo": "ID duplicado globalmente"
                })
                continue

            # --- FILTRAGEM DOS COMENTÁRIOS ---
            comentarios_ok = []
            for coment in post.get('comentarios', []):
                txt = limpar_texto_suporte_tecnico(coment.get('conteudo'))
                if len(txt) > 5:
                    coment['conteudo'] = txt
                    comentarios_ok.append(coment)

            # --- DECISÃO DE MANTER O POST ---
            if len(comentarios_ok) > 0 or eh_post_critico(titulo_original, search_groups):
                # Mantém o post
                post['titulo'] = limpar_texto_suporte_tecnico(titulo_original)
                post['conteudo_post'] = limpar_texto_suporte_tecnico(conteudo_original)
                post['comentarios'] = comentarios_ok

                posts_limpos.append(post)
                global_ids[p_id] = True
            else:
                # Descarta o post
                discard_log.append({
                    "arquivo": arquivo,
                    "post_id": p_id,
                    "titulo_original": titulo_original,
                    "motivo": "Sem comentários válidos (após limpeza) e título não crítico"
                })

        # --- SALVA O ARQUIVO SE HOUVER PELO MENOS UM POST LIMPO ---
        if len(posts_limpos) > 0:
            dados['posts'] = posts_limpos
            with open(caminho_out, 'w', encoding='utf-8') as f:
                json.dump(dados, f, indent=4, ensure_ascii=False)
            return True
        else:
            return False

    except Exception as e:
        discard_log.append({
            "arquivo": arquivo,
            "post_id": None,
            "titulo_original": None,
            "motivo": f"Erro no processamento do arquivo: {str(e)}"
        })
        return False

def executar_limpeza_paralela():
    """Gerencia o processamento paralelo, a memória compartilhada e o registro de descartes."""
    # Criar diretórios de saída, se não existirem
    os.makedirs(CAMINHO_SAIDA, exist_ok=True)
    os.makedirs(CAMINHO_LOG, exist_ok=True)

    arquivos = [f for f in os.listdir(CAMINHO_ENTRADA) if f.endswith('.json')]

    if not arquivos:
        print(f"⚠️ Nenhum arquivo JSON encontrado em: {CAMINHO_ENTRADA}")
        return

    # Carrega os grupos de busca para identificar posts críticos
    try:
        config_path = EXTRACAO_CONFIG / "extractor_settings_extendedV6.json"
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            search_groups = config["reddit_params"]["search_groups"]
    except Exception as e:
        print(f"⚠️ Erro ao carregar search_groups: {e}. Usando filtro vazio.")
        search_groups = {}

    with Manager() as manager:
        global_ids = manager.dict()      # IDs vistos globalmente
        discard_log = manager.list()     # Lista compartilhada de descartes

        print(f"🧹 Iniciando limpeza técnica e deduplicação global em {len(arquivos)} arquivos...")
        print(f"   (Preservando placeholders de URL, acentos e símbolos técnicos)")

        with ProcessPoolExecutor() as executor:
            futures = {
                executor.submit(processar_um_arquivo, arq, global_ids, search_groups, discard_log): arq
                for arq in arquivos
            }

            arquivos_vazios = 0
            for future in tqdm(as_completed(futures), total=len(arquivos), desc="Limpando Corpus", unit="arq"):
                sucesso = future.result()
                if not sucesso:
                    arquivos_vazios += 1

        # --- SALVA O LOG DE DESCARTES (mesmo que vazio) ---
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path = CAMINHO_LOG / f"discard_log_{timestamp}.json"
        with open(log_path, 'w', encoding='utf-8') as f:
            json.dump(list(discard_log), f, indent=2, ensure_ascii=False)

        ultimo_log_path = CAMINHO_LOG / "discard_log_latest.json"
        with open(ultimo_log_path, 'w', encoding='utf-8') as f:
            json.dump(list(discard_log), f, indent=2, ensure_ascii=False)

    print(f"\n✅ Limpeza técnica concluída!")
    print(f"   📁 Dados limpos salvos em: {CAMINHO_SAIDA}")
    print(f"   📊 Arquivos processados: {len(arquivos)}")
    print(f"   🗑️  Arquivos totalmente descartados (sem posts relevantes): {arquivos_vazios}")
    print(f"   📝 Log detalhado de posts descartados: {log_path}")
    print(f"   📝 Último log (sempre com mesmo nome): {ultimo_log_path}")

if __name__ == "__main__":
    executar_limpeza_paralela()