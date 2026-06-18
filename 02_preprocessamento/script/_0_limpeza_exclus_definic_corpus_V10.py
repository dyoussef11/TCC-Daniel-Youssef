import os
import json
import re
import csv
from datetime import datetime
from multiprocessing import Manager
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm
from core.paths import EXTRACAO_CONFIG, EXTRACAO_DATA, PREPROCESSAMENTO, PREPROCESSAMENTO_DATA

# --- CONFIGURAÇÕES DE CAMINHO ---
CAMINHO_ENTRADA = EXTRACAO_DATA / "brutoV10"
CAMINHO_SAIDA = PREPROCESSAMENTO_DATA / "Dados_Limpos_IniciaisV12"
CAMINHO_LOG = PREPROCESSAMENTO / "Logs"

# --- CONFIGURAÇÃO DE COMPORTAMENTO ---
DESCARTAR_SEM_COMENTARIOS = True   # Altere para False se preferir manter os que têm título crítico


def limpar_texto_suporte_tecnico(texto):
    # (mesma função anterior, mantida)
    if not texto:
        return ""
    texto = re.sub(r'http\S+|www\S+|https\S+', '[URL_EVIDENCIA]', texto)
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"
        "\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF"
        "\U0001F700-\U0001F77F"
        "\U0001F780-\U0001F7FF"
        "\U0001F800-\U0001F8FF"
        "\U0001F900-\U0001F9FF"
        "\U0001FA00-\U0001FA6F"
        "\U0001FA70-\U0001FAFF"
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "]+", flags=re.UNICODE
    )
    texto = emoji_pattern.sub(r'', texto)
    tech_symbols = r'×μΩ°²³¹€£¥©®™←→↑↓•·—–…'
    keep_pattern = r'[ -~\n\r\tÀ-ÿ' + re.escape(tech_symbols) + r']'
    texto = re.sub(r'[^' + keep_pattern[1:-1] + r']', '', texto)
    texto = texto.replace('\t', ' ')
    texto = texto.replace('\n', ' ')
    texto = re.sub(r'\n+', '\n', texto)
    texto = re.sub(r' +', ' ', texto).strip()
    return texto


def eh_post_critico(titulo, search_groups):
    texto_titulo = titulo.lower()
    for categoria in search_groups.values():
        if any(termo.lower() in texto_titulo for termo in categoria):
            return True
    return False


def processar_um_arquivo(arquivo, global_ids, search_groups, discard_log):
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
            comentarios_originais = post.get('comentarios', [])

            if p_id in global_ids:
                discard_log.append({
                    "arquivo": arquivo,
                    "post_id": p_id,
                    "titulo_original": titulo_original,
                    "motivo": "ID duplicado globalmente"
                })
                continue

            if not comentarios_originais:
                motivo = "Post sem comentários (original vazio)"
                discard_log.append({
                    "arquivo": arquivo,
                    "post_id": p_id,
                    "titulo_original": titulo_original,
                    "motivo": motivo
                })
                if DESCARTAR_SEM_COMENTARIOS:
                    continue

            comentarios_ok = []
            for coment in comentarios_originais:
                txt = limpar_texto_suporte_tecnico(coment.get('conteudo'))
                if len(txt) > 5:
                    coment['conteudo'] = txt
                    comentarios_ok.append(coment)

            if len(comentarios_ok) > 0 or eh_post_critico(titulo_original, search_groups):
                post['titulo'] = limpar_texto_suporte_tecnico(titulo_original)
                post['conteudo_post'] = limpar_texto_suporte_tecnico(conteudo_original)
                post['comentarios'] = comentarios_ok

                posts_limpos.append(post)
                global_ids[p_id] = True
            else:
                if comentarios_originais:
                    discard_log.append({
                        "arquivo": arquivo,
                        "post_id": p_id,
                        "titulo_original": titulo_original,
                        "motivo": "Sem comentários válidos (após limpeza) e título não crítico"
                    })

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
    os.makedirs(CAMINHO_SAIDA, exist_ok=True)
    os.makedirs(CAMINHO_LOG, exist_ok=True)

    arquivos = [f for f in os.listdir(CAMINHO_ENTRADA) if f.endswith('.json')]

    if not arquivos:
        print(f"⚠️ Nenhum arquivo JSON encontrado em: {CAMINHO_ENTRADA}")
        return

    try:
        config_path = EXTRACAO_CONFIG / "extractor_settings_extendedV6.json"
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            search_groups = config["reddit_params"]["search_groups"]
    except Exception as e:
        print(f"⚠️ Erro ao carregar search_groups: {e}. Usando filtro vazio.")
        search_groups = {}

    with Manager() as manager:
        global_ids = manager.dict()
        discard_log = manager.list()

        print(f"🧹 Iniciando limpeza técnica e deduplicação global em {len(arquivos)} arquivos...")
        print(f"   (Preservando placeholders de URL, acentos e símbolos técnicos)")
        print(f"   Configuração: DESCARTAR_SEM_COMENTARIOS = {DESCARTAR_SEM_COMENTARIOS}")

        with ProcessPoolExecutor() as executor:
            futures = {
                executor.submit(processar_um_arquivo, arq, global_ids, search_groups, discard_log): arq
                for arq in arquivos
            }

            arquivos_vazios = 0
            for future in tqdm(as_completed(futures), total=len(arquivos), desc="Limpando Corpus", unit="arq"):
                if not future.result():
                    arquivos_vazios += 1

        # Converte a lista compartilhada para uma lista comum
        discard_list = list(discard_log)

        # --- GERA O RESUMO EM CSV ---
        # Inicializa dicionário para acumular contagens por arquivo
        resumo_por_arquivo = {}
        for entry in discard_list:
            arq = entry["arquivo"]
            motivo = entry.get("motivo", "desconhecido")
            if arq not in resumo_por_arquivo:
                resumo_por_arquivo[arq] = {
                    "total_descartes": 0,
                    "sem_comentarios": 0,
                    "id_duplicado": 0,
                    "sem_validos": 0,
                    "erro": 0,
                    "outros": 0
                }
            resumo_por_arquivo[arq]["total_descartes"] += 1
            if "sem comentários" in motivo:
                resumo_por_arquivo[arq]["sem_comentarios"] += 1
            elif "duplicado" in motivo:
                resumo_por_arquivo[arq]["id_duplicado"] += 1
            elif "Sem comentários válidos" in motivo:
                resumo_por_arquivo[arq]["sem_validos"] += 1
            elif "Erro" in motivo:
                resumo_por_arquivo[arq]["erro"] += 1
            else:
                resumo_por_arquivo[arq]["outros"] += 1

        # Para cada arquivo, precisamos saber quantos posts foram processados (total original)
        # Vamos ler cada arquivo para contar os posts originais (apenas uma vez)
        total_posts_por_arquivo = {}
        for arq in arquivos:
            try:
                with open(CAMINHO_ENTRADA / arq, 'r', encoding='utf-8') as f:
                    dados = json.load(f)
                    total_posts_por_arquivo[arq] = len(dados.get('posts', []))
            except:
                total_posts_por_arquivo[arq] = 0

        # Prepara as linhas do CSV
        linhas = []
        cabecalho = [
            "arquivo",
            "total_posts_originais",
            "descartados_total",
            "descartados_sem_comentarios",
            "descartados_id_duplicado",
            "descartados_sem_comentarios_validos",
            "descartados_erro",
            "descartados_outros",
            "posts_mantidos"
        ]
        totais_gerais = {
            "total_posts_originais": 0,
            "descartados_total": 0,
            "sem_comentarios": 0,
            "id_duplicado": 0,
            "sem_validos": 0,
            "erro": 0,
            "outros": 0,
            "posts_mantidos": 0
        }

        for arq in arquivos:
            total_orig = total_posts_por_arquivo.get(arq, 0)
            info = resumo_por_arquivo.get(arq, {
                "total_descartes": 0,
                "sem_comentarios": 0,
                "id_duplicado": 0,
                "sem_validos": 0,
                "erro": 0,
                "outros": 0
            })
            mantidos = total_orig - info["total_descartes"]
            linha = [
                arq,
                total_orig,
                info["total_descartes"],
                info["sem_comentarios"],
                info["id_duplicado"],
                info["sem_validos"],
                info["erro"],
                info["outros"],
                mantidos
            ]
            linhas.append(linha)

            # Atualiza totais gerais
            totais_gerais["total_posts_originais"] += total_orig
            totais_gerais["descartados_total"] += info["total_descartes"]
            totais_gerais["sem_comentarios"] += info["sem_comentarios"]
            totais_gerais["id_duplicado"] += info["id_duplicado"]
            totais_gerais["sem_validos"] += info["sem_validos"]
            totais_gerais["erro"] += info["erro"]
            totais_gerais["outros"] += info["outros"]
            totais_gerais["posts_mantidos"] += mantidos

        # Adiciona linha de total
        linha_total = [
            "TOTAL",
            totais_gerais["total_posts_originais"],
            totais_gerais["descartados_total"],
            totais_gerais["sem_comentarios"],
            totais_gerais["id_duplicado"],
            totais_gerais["sem_validos"],
            totais_gerais["erro"],
            totais_gerais["outros"],
            totais_gerais["posts_mantidos"]
        ]
        linhas.append(linha_total)

        # Salva o CSV
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path = CAMINHO_LOG / f"resumo_descartes_{timestamp}.csv"
        with open(csv_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f, delimiter=';')
            writer.writerow(cabecalho)
            writer.writerows(linhas)

        # Cópia com nome fixo
        csv_latest_path = CAMINHO_LOG / "resumo_descartes_latest.csv"
        with open(csv_latest_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f, delimiter=';')
            writer.writerow(cabecalho)
            writer.writerows(linhas)

        # --- SALVA O LOG DETALHADO (JSON) ---
        log_path = CAMINHO_LOG / f"discard_log_{timestamp}.json"
        with open(log_path, 'w', encoding='utf-8') as f:
            json.dump(discard_list, f, indent=2, ensure_ascii=False)

        ultimo_log_path = CAMINHO_LOG / "discard_log_latest.json"
        with open(ultimo_log_path, 'w', encoding='utf-8') as f:
            json.dump(discard_list, f, indent=2, ensure_ascii=False)

        # Estatísticas finais (já temos os totais)
        total_descartados_sem_comentarios = totais_gerais["sem_comentarios"]

        print(f"\n✅ Limpeza técnica concluída!")
        print(f"   📁 Dados limpos salvos em: {CAMINHO_SAIDA}")
        print(f"   📊 Arquivos processados: {len(arquivos)}")
        print(f"   🗑️  Arquivos totalmente descartados (sem posts relevantes): {arquivos_vazios}")
        print(f"   📝 Log detalhado de posts descartados: {log_path}")
        print(f"   📝 Último log (sempre com mesmo nome): {ultimo_log_path}")
        print(f"   📊 Resumo em CSV: {csv_path}")
        print(f"   📊 Último resumo: {csv_latest_path}")
        print(f"   🔍 Posts descartados por não terem comentários originais: {total_descartados_sem_comentarios}")

    # Fim do bloco with


if __name__ == "__main__":
    executar_limpeza_paralela()