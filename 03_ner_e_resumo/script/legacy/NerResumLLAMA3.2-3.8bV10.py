import asyncio
import json
from tqdm.asyncio import tqdm as async_tqdm
from openai import AsyncOpenAI

# Importações dos seus novos módulos
from modules_resumo_ner.config import (
    DIR_ENTRADA, DIR_SAIDA_FINAL, DIR_CHECKPOINTS,
    MAX_CONCURRENT, MAX_TEMP, COOLDOWN_TEMP
)
from modules_resumo_ner.gpu_health import monitorar_temperatura, get_gpu_temperature
from modules_resumo_ner.inference import extrair_seguro
from modules_resumo_ner.data_handler import verificar_checkpoint_valido

# async def processar_arquivo_modelo(arq_path, client, semaphore, stats):
#     """Lê um arquivo de modelo e processa seus posts."""
#     try:
#         with open(arq_path, 'r', encoding='utf-8') as f:
#             dados_modelo = json.load(f)
#     except:
#         return
    
#     modelo_nome = dados_modelo.get('modelo_busca_utilizado', 'Unknown')
#     posts = dados_modelo.get('posts', [])
#     posts_processados = []

#     for post in posts:
#         p_id = str(post.get('id'))
#         # Tenta extrair (vai usar cache automaticamente se existir)
#         analise = await extrair_seguro(client, semaphore, post, modelo_nome, p_id, stats)
        
#         if analise:
#             post['analise_ia'] = analise
#             posts_processados.append(post)

#     if posts_processados:
#         dados_modelo['posts'] = posts_processados
#         output_path = DIR_SAIDA_FINAL / f"NER_{arq_path.name}"
#         with open(output_path, 'w', encoding='utf-8') as f:
#             json.dump(dados_modelo, f, indent=2, ensure_ascii=False)

async def processar_arquivo_modelo(arq_path, client, semaphore, stats):
    """Lê um arquivo de modelo e processa seus posts."""
    try:
        with open(arq_path, 'r', encoding='utf-8') as f:
            dados_modelo = json.load(f)
    except:
        return
    
    modelo_nome = dados_modelo.get('modelo_busca_utilizado', 'Unknown')
    posts = dados_modelo.get('posts', [])
    posts_processados = []

    for post in posts:
        p_id = str(post.get('id'))
        checkpoint_path = DIR_CHECKPOINTS / f"{p_id}.json"
        
        # --- NOVA LOGICA DE VERIFICAÇÃO DIRETA NO ENTRY ---
        if checkpoint_path.exists():
            valido, data = verificar_checkpoint_valido(checkpoint_path)
            if valido:
                post['analise_ia'] = data
                posts_processados.append(post)
                stats["checkpoints_validos"] += 1
                continue # Pula para o proximo post sem chamar a extração/IA
        
        # Se nao existe checkpoint, chama a IA (Llama 3.2)
        analise = await extrair_seguro(client, semaphore, post, modelo_nome, p_id, stats)
        
        if analise:
            post['analise_ia'] = analise
            posts_processados.append(post)

    if posts_processados:
        dados_modelo['posts'] = posts_processados
        output_path = DIR_SAIDA_FINAL / f"NER_{arq_path.name}"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(dados_modelo, f, indent=2, ensure_ascii=False)

            
async def workflow_principal():
    # Inicialização
    client = AsyncOpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    stats = {"checkpoints_validos": 0, "processados_agora": 0, "falhas": 0, "pausas_temperatura": 0}
    
    # Criar pastas se não existirem
    DIR_SAIDA_FINAL.mkdir(parents=True, exist_ok=True)
    DIR_CHECKPOINTS.mkdir(parents=True, exist_ok=True)

    print(f"🚀 Iniciando Processamento NER (Modo Seguro)")
    print(f"🌡️ Limite GPU: {MAX_TEMP}°C | Concorrência: {MAX_CONCURRENT}")

    # Monitor de Temperatura (Tarefa de fundo)
    monitor_task = asyncio.create_task(monitorar_temperatura(stats, MAX_TEMP, COOLDOWN_TEMP))
    
    arquivos = list(DIR_ENTRADA.glob("*.json"))
    
    for arq_path in async_tqdm(arquivos, desc="Processando Modelos"):

        output_path = DIR_SAIDA_FINAL / f"NER_{arq_path.name}"
        if output_path.exists():
            continue
        await processar_arquivo_modelo(arq_path, client, semaphore, stats)

        # Log rápido de status
        temp = get_gpu_temperature()
        print(f" - Último: {arq_path.name} | GPU: {temp}°C | Cache: {stats['checkpoints_validos']}")

    # Finalização
    monitor_task.cancel()
    print(f"\n✅ Concluído!")
    print(f"📊 Relatório: {stats['processados_agora']} novos, {stats['checkpoints_validos']} do cache, {stats['pausas_temperatura']} pausas térmicas.")

if __name__ == "__main__":
    try:
        asyncio.run(workflow_principal())
    except KeyboardInterrupt:
        print("\n⚠️ Interrompido pelo usuário. O progresso está salvo nos checkpoints.")