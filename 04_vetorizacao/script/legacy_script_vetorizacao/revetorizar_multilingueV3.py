import json
import asyncio
from pathlib import Path
from ollama import AsyncClient
from tqdm.asyncio import tqdm

# --- CONFIGURAÇÃO DE CAMINHOS ---
try:
    from core.paths import NER_DATA, VETORIZATION_DATA
    DIR_ENTRADA = NER_DATA / 'Base_Conhecimento_ResumidaV2'
    CAMINHO_SAIDA = VETORIZATION_DATA / 'base_conhecimento_multilingueV3.json'
except ImportError:
    DIR_ENTRADA = Path("./data/Base_Conhecimento_ResumidaV2")
    CAMINHO_SAIDA = Path("./data/base_conhecimento_multilingueV3.json")

CONCORRENCIA_MAXIMA = 5
MODELO_EMBEDDING = "bge-m3:latest"

def formatar_solucoes(solucoes):
    """
    Converte suggested_solution em string, lidando com strings, 
    listas de strings ou listas de dicionários.
    """
    if not solucoes:
        return "N/A"
    if isinstance(solucoes, str):
        return solucoes
    if isinstance(solucoes, list):
        itens_limpos = []
        for item in solucoes:
            if isinstance(item, str):
                itens_limpos.append(item)
            elif isinstance(item, dict):
                # Extrai apenas os valores do dicionário se a IA gerou objetos
                itens_limpos.append(" ".join(str(v) for v in item.values()))
            else:
                itens_limpos.append(str(item))
        return ", ".join(itens_limpos)
    return str(solucoes)

async def processar_post(client, item, semaphore, pbar, retries=3):
    async with semaphore:
        for tentativa in range(retries):
            try:
                response = await client.embeddings(
                    model=MODELO_EMBEDDING, 
                    prompt=item['texto_final']
                )
                pbar.update(1)
                return {
                    'id': item['id'],
                    'vector': response['embedding'],
                    'original_text': item['texto_final'],
                    'date_iso': item['date_iso'],
                    'metadata': item['metadata']
                }
            except Exception as e:
                if tentativa < retries - 1:
                    await asyncio.sleep((tentativa + 1) * 2)
                else:
                    pbar.write(f"❌ Falha definitiva no post {item['id']}: {e}")
                    pbar.update(1)
                    return None

async def gerar_base_vetorial():
    print(f"--- 🚀 INICIANDO VETORIZAÇÃO (BGE-M3) ---")
    client = AsyncClient()
    semaphore = asyncio.Semaphore(CONCORRENCIA_MAXIMA)
    
    arquivos = list(DIR_ENTRADA.glob("*.json"))
    if not arquivos:
        print(f"⚠️ Nenhum arquivo encontrado.")
        return

    fila_trabalho = []

    for arq_path in arquivos:
        try:
            with open(arq_path, 'r', encoding='utf-8') as f:
                dados_modelo = json.load(f)
        except Exception as e:
            continue
        
        modelo_ref = dados_modelo.get('modelo_busca_utilizado', 'Unknown Device')
        
        for post in dados_modelo.get('posts', []):
            analise = post.get('analise_ia', {})
            if not analise: continue

            timeline = analise.get('discussion_timeline', 'N/A')
            ancora = analise.get('ancoragem_temporal', {})
            data_str = ancora.get('data_post', '2024-01-01')

            # --- CORREÇÃO DO ERRO AQUI ---
            # Usamos a função auxiliar para garantir que vire string, mesmo que contenha dicts
            solucoes_str = formatar_solucoes(analise.get('suggested_solution'))

            texto_final = (
                f"TIMELINE: {timeline}. " 
                f"MODEL: {modelo_ref}. "
                f"TITLE: {post.get('titulo', 'Untitled')}. "
                f"INTENT: {analise.get('intent', 'N/A')}. "
                f"SEVERITY: {analise.get('technical_severity', 'N/A')}. "
                f"FAULT: {analise.get('detected_fault', 'N/A')}. "
                f"SUMMARY: {analise.get('summary', 'N/A')}. "
                f"RESOLUTION: {solucoes_str}."
            ).strip()

            fila_trabalho.append({
                'id': post.get('id'),
                'texto_final': texto_final,
                'date_iso': data_str,
                'metadata': {
                    'title': post.get('titulo', 'Untitled Post'),
                    'model': modelo_ref,
                    'severity': analise.get('technical_severity', 'N/A'),
                    'fault': analise.get('detected_fault', 'N/A'),
                    'timeline': timeline,
                    'solution': solucoes_str  # <--- ADICIONE ESTA LINHA                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        
                }
            })

    if not fila_trabalho:
        print("⚠️ Fila de trabalho vazia.")
        return

    print(f"📦 Total de posts para vetorizar: {len(fila_trabalho)}")
    with tqdm(total=len(fila_trabalho), desc="Vetorizando", unit="post") as pbar:
        tasks = [processar_post(client, item, semaphore, pbar) for item in fila_trabalho]
        resultados = await asyncio.gather(*tasks)

    base_conhecimento = [r for r in resultados if r is not None]
    if base_conhecimento:
        CAMINHO_SAIDA.parent.mkdir(parents=True, exist_ok=True)
        with open(CAMINHO_SAIDA, 'w', encoding='utf-8') as f:
            json.dump(base_conhecimento, f, ensure_ascii=False, indent=4)
        print(f"\n✨ SUCESSO! {len(base_conhecimento)} vetores salvos.")

if __name__ == "__main__":
    asyncio.run(gerar_base_vetorial())