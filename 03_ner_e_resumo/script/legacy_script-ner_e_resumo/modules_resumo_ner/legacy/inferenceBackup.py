
import asyncio
import json
import aiofiles
from datetime import datetime
from .data_handler import reparar_json_malformado, verificar_checkpoint_valido
from .config import PROMPT_LLAMA_EXTRACTION, DIR_CHECKPOINTS

async def extrair_seguro(client, semaphore, post, modelo_nome, post_id, stats):
    """Realiza a inferência com retry e controle de concorrência."""
    checkpoint_path = DIR_CHECKPOINTS / f"{post_id}.json"
    
    # 1. Verifica Cache/Checkpoint
    if checkpoint_path.exists():
        valido, data_ou_erro = verificar_checkpoint_valido(checkpoint_path)
        if valido:
            stats["checkpoints_validos"] += 1
            return data_ou_erro
        checkpoint_path.unlink() # Remove se estiver corrompido

    # 2. Prepara Dados (Trimming para economizar Context Window)
    titulo = post.get('titulo', 'N/A')
    corpo = post.get('conteudo_post', 'N/A')
    comentarios = " ".join([c.get('conteudo', '') for c in post.get('comentarios', [])])
    
    ts = post.get('data_post')
    post_date = datetime.fromtimestamp(float(ts)).strftime('%Y-%m-%d') if ts else "2024-01-01"
    
    prompt = PROMPT_LLAMA_EXTRACTION.format(
        modelo_nome=modelo_nome,
        post_date=post_date,
        titulo=titulo,
        corpo=corpo,
        comentarios=comentarios
    )

    # 3. Execução com Semáforo
    for tentativa in range(2):
        try:
            async with semaphore:
                response = await client.chat.completions.create(
                    model="llama3.2:3b",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    extra_query={
                        "num_ctx": 2048,
                        "num_predict": 150,
                    },
                    response_format={"type": "json_object"}
                )
            
            content = response.choices[0].message.content
            try:
                analise = json.loads(content)
            except:
                analise = reparar_json_malformado(content)
            
            # Adiciona metadados de ancoragem
            analise['ancoragem_temporal'] = {"data_post": post_date, "periodo_referencia": post_date[:7]}
            
            if isinstance(analise.get('suggested_solution'), str):
                analise['suggested_solution'] = [analise['suggested_solution']]
            
            # Salva Checkpoint
            async with aiofiles.open(checkpoint_path, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(analise, ensure_ascii=False))
            
            stats["processados_agora"] += 1
            await asyncio.sleep(3.0) # Respiro para a GPU
            return analise
            
        except Exception as e:
            if tentativa == 1:
                stats["falhas"] += 1
                return None
            await asyncio.sleep(3.0)
    return None