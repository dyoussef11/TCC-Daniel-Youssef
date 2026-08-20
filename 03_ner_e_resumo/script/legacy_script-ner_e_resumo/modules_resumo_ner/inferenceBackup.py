# inference.py (versão final corrigida para Llama 3.2:3B)
import asyncio
import json
import aiofiles
import re
from datetime import datetime
from .data_handler import verificar_checkpoint_valido
from .config import (
    PROMPT_LLAMA_EXTRACTION, DIR_CHECKPOINTS, 
    CHUNK_SIZE, MAX_CHUNKS_PER_POST, KEYWORDS_SOLUCAO
)

def parse_model_response(content: str) -> dict:
    """Parsing ultra-robusto com fallbacks para formatos comuns do Llama 3.2"""
    content = content.strip()
    result = {}
    
    # ESTRATÉGIA 1: Tool call correta (formato que o modelo está retornando)
    # Ex: [extract_technical_analysis(summary="...", intent="...", ...)]
    match = re.search(r'\[extract_technical_analysis\((.*)\)\]', content, re.DOTALL)
    if match:
        args_str = match.group(1)
        
        # Extrai summary
        summary_match = re.search(r'summary="([^"]*)"', args_str)
        if summary_match:
            result['summary'] = summary_match.group(1)
        
        # Extrai intent
        intent_match = re.search(r'intent="([^"]*)"', args_str)
        if intent_match:
            result['intent'] = intent_match.group(1)
        
        # Extrai detected_fault
        fault_match = re.search(r'detected_fault="([^"]*)"', args_str)
        if fault_match:
            result['detected_fault'] = fault_match.group(1)
        
        # Extrai suggested_solution (array)
        sol_match = re.search(r'suggested_solution=\[(.*?)\]', args_str, re.DOTALL)
        if sol_match:
            sol_content = sol_match.group(1)
            # Extrai strings individuais do array
            solucoes = re.findall(r'"([^"]*)"', sol_content)
            result['suggested_solution'] = solucoes
        
        # Extrai technical_severity
        sev_match = re.search(r'technical_severity="([^"]*)"', args_str)
        if sev_match:
            result['technical_severity'] = sev_match.group(1)
        
        # Extrai discussion_timeline
        time_match = re.search(r'discussion_timeline="([^"]*)"', args_str)
        if time_match:
            result['discussion_timeline'] = time_match.group(1)
        
        if result:
            return result
    
    # ESTRATÉGIA 2: JSON direto (sem tool call)
    json_match = re.search(r'\{.*"summary".*\}', content, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group(0))
            if isinstance(data, dict):
                return data
        except:
            pass
    
    # ESTRATÉGIA 3: Formato alternativo com aspas nos parâmetros
    alt_match = re.search(r'\["extract_technical_analysis",\s*"summary=([^"]*)",\s*"intent=([^"]*)",\s*"detected_fault=([^"]*)",\s*"suggested_solution=\[([^\]]*)\]",\s*"technical_severity=([^"]*)",\s*"discussion_timeline=([^"]*)"\]', content, re.DOTALL)
    if alt_match:
        result['summary'] = alt_match.group(1)
        result['intent'] = alt_match.group(2)
        result['detected_fault'] = alt_match.group(3)
        sol_str = alt_match.group(4)
        solucoes = re.findall(r'"([^"]*)"', sol_str)
        result['suggested_solution'] = solucoes
        result['technical_severity'] = alt_match.group(5)
        result['discussion_timeline'] = alt_match.group(6)
        return result
    
    # ESTRATÉGIA 4: Extração bruta por regex (fallback final)
    summary = re.search(r'summary[=:]\s*"([^"]*)"', content)
    if summary:
        result['summary'] = summary.group(1)
    
    intent = re.search(r'intent[=:]\s*"([^"]*)"', content)
    if intent:
        result['intent'] = intent.group(1)
    
    fault = re.search(r'detected_fault[=:]\s*"([^"]*)"', content)
    if fault:
        result['detected_fault'] = fault.group(1)
    
    sol_array = re.search(r'suggested_solution[=:]\s*\[(.*?)\]', content, re.DOTALL)
    if sol_array:
        solucoes = re.findall(r'"([^"]*)"', sol_array.group(1))
        result['suggested_solution'] = solucoes
    
    sev = re.search(r'technical_severity[=:]\s*"([^"]*)"', content)
    if sev:
        result['technical_severity'] = sev.group(1)
    
    time_line = re.search(r'discussion_timeline[=:]\s*"([^"]*)"', content)
    if time_line:
        result['discussion_timeline'] = time_line.group(1)
    
    if result:
        return result
    
    raise ValueError(f"Formato não reconhecido: {content[:200]}")

async def extrair_seguro(client, semaphore, post, modelo_nome, post_id, stats):
    """
    Processa um post individual: verifica checkpoint, divide em chunks,
    chama o modelo Llama 3.2 e consolida os resultados.
    
    Args:
        client: Cliente AsyncOpenAI
        semaphore: Semáforo para controle de concorrência
        post: Dicionário com dados do post
        modelo_nome: Nome canônico do modelo de laptop
        post_id: ID único do post
        stats: Dicionário de estatísticas
        
    Returns:
        Dicionário com a análise IA ou None se falhar
    """
    checkpoint_path = DIR_CHECKPOINTS / f"{post_id}.json"
    
    # Verifica checkpoint existente
    if checkpoint_path.exists():
        valido, data_ou_erro = verificar_checkpoint_valido(checkpoint_path)
        if valido:
            stats["checkpoints_validos"] += 1
            return data_ou_erro

    # 1. Agrega conteúdo textual do post
    texto_completo = f"TITLE: {post.get('titulo', '')}\n"
    texto_completo += f"CONTENT: {post.get('conteudo_post', post.get('selftext', ''))}\n"
    texto_completo += "COMMENTS: " + " ".join([
        c.get('conteudo', '') for c in post.get('comentarios', [])
    ])
    
    # 2. Divisão em Chunks
    chunks = [texto_completo[i:i + CHUNK_SIZE] for i in range(0, len(texto_completo), CHUNK_SIZE)]
    
    # 3. Filtro de Relevância
    # Processa primeiro chunk (contexto), último (conclusão) e chunks com keywords
    chunks_a_processar = []
    for i, chunk in enumerate(chunks):
        e_ancora = (i == 0 or i == len(chunks) - 1)
        tem_keyword = any(kw in chunk.lower() for kw in KEYWORDS_SOLUCAO)
        
        if e_ancora or tem_keyword:
            chunks_a_processar.append(chunk)
            if len(chunks_a_processar) >= MAX_CHUNKS_PER_POST:
                break

    solucoes_totais = []
    analise_final = None

    # 4. Processamento de cada Chunk
    for i, chunk_text in enumerate(chunks_a_processar):
        # Prepara o prompt para este chunk
        prompt = PROMPT_LLAMA_EXTRACTION.format(
            modelo_nome=modelo_nome,
            post_date="2024-01-01",
            titulo=f"(Parte {i+1}) {post.get('titulo', 'N/A')[:50]}",
            corpo=chunk_text,
            comentarios=""
        )

        try:
            async with semaphore:
                # Chama o modelo via API Ollama
                response = await client.chat.completions.create(
                    model="llama3.2:3b",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    max_tokens=512,
                )
            
            content = response.choices[0].message.content

            # DEBUG: Log do que o modelo gerou (remova depois de resolver)
            if i == 0:  # Só loga o primeiro chunk
                print(f"\n  🔍 DEBUG Resposta do modelo para {post_id}:")
                print(f"  {content[:300]}...")
                print(f"  🔍 Fim debug\n")
            
            # Faz o parsing da resposta
            try:
                res_json = parse_model_response(content)
            except ValueError as e:
                print(f"  ⚠️ Erro parsing chunk {i} post {post_id}: {str(e)[:100]}")
                continue
            
            # Coleta soluções deste chunk
            sols = res_json.get('suggested_solution', [])
            if isinstance(sols, list):
                solucoes_totais.extend(sols)
            
            # Usa o primeiro chunk válido como base para metadados
            if not analise_final:
                analise_final = res_json

        except Exception as e:
            print(f"  ⚠️ Erro chunk {i} post {post_id}: {str(e)[:100]}")
            continue
        
        # Pausa para controle térmico da GPU
        await asyncio.sleep(2.0)

    # Se nenhum chunk produziu resultado, retorna None
    if not analise_final:
        stats["falhas"] += 1
        return None

    # 5. Consolidação Final
    # Remove duplicatas e filtra placeholders que o modelo pode ter copiado
    placeholders_solucao = [
        'step 1', 'step 2', 'step 3', 'step 4',
        'action 1', 'action 2', 'action 3', 'action 4',
        'specific fix 1', 'specific fix 2', 'solution step 1', 'solution step 2'
    ]
    analise_final['suggested_solution'] = list(set([
        s for s in solucoes_totais 
        if s and s.strip() and s not in placeholders_solucao
    ]))
    
    # Adiciona metadado de processamento
    analise_final['ancoragem_temporal'] = {
        "data_processamento": datetime.now().strftime('%Y-%m-%d')
    }
    
    # Garante campos obrigatórios com fallbacks
    analise_final.setdefault('detected_fault', 'None')
    analise_final.setdefault('technical_severity', 'Low')
    analise_final.setdefault('discussion_timeline', '2024-01-01 to 2024-01-01')
    
    # Corrige intent se veio com múltiplos valores (modelo copiou todas as opções)
    intent = analise_final.get('intent', 'Troubleshooting')
    if '|' in intent:
        # Pega apenas o primeiro valor
        analise_final['intent'] = intent.split('|')[0].strip()
    
    # Valores válidos para intent
    intent_validos = [
        'Technical Specifications', 'Troubleshooting', 'Upgrade Advice',
        'Compatibility', 'Warranty', 'Performance'
    ]
    if analise_final.get('intent', '') not in intent_validos:
        analise_final['intent'] = 'Troubleshooting'
    
    # Valores válidos para technical_severity
    severidade_validos = ['Low', 'Medium', 'High', 'Critical']
    if analise_final.get('technical_severity', '') not in severidade_validos:
        analise_final['technical_severity'] = 'Low'
    
    # =========================================================
    # VALIDAÇÃO CRÍTICA DO SUMMARY
    # =========================================================
    summary = analise_final.get('summary', '')
    
    # Lista de placeholders que o modelo pode ter mantido
    placeholders_summary = [
        '[problem]', '[symptoms]', '[components]',
        '[problem description]', '[key symptoms]', '[affected components]',
        'brief problem description here', 'problem description',
        'copy the laptop model exactly, then describe the problem',
        'describe the problem'
    ]
    
    # Remove todos os placeholders
    for ph in placeholders_summary:
        summary = summary.replace(ph, '')
    
    # Remove "Unknown" do início
    if summary.startswith('Unknown,'):
        summary = summary.replace('Unknown,', '', 1).strip()
    if summary.startswith('Unknown'):
        summary = summary.replace('Unknown', '', 1).strip()
    
    # Remove caracteres repetidos e limpa
    summary = summary.strip(' -,;:')
    summary = re.sub(r'\s+', ' ', summary)  # Normaliza espaços
    
    # Verifica se o summary começa com o nome do modelo
    if not summary.startswith(modelo_nome):
        # Extrai informação útil do título do post
        titulo = post.get('titulo', '')
        
        # Remove palavras genéricas do título
        palavras_genericas = [
            'Help', 'with', 'getting', 'the', 'my', 'a', 'an', 'is',
            'of', 'in', 'on', 'to', 'for', 'this', 'that', 'it',
            'has', 'have', 'I', 'me', 'please', 'need', 'anyone',
            'someone', 'can', 'how', 'what', 'why', 'when'
        ]
        for palavra in palavras_genericas:
            titulo = re.sub(r'\b' + palavra + r'\b', '', titulo, flags=re.IGNORECASE)
        
        # Limpa espaços extras
        titulo = ' '.join(titulo.split()).strip()
        
        # Monta o summary final
        if summary and len(summary) > 5:
            # Usa o que o modelo gerou (após limpeza)
            analise_final['summary'] = f"{modelo_nome}, {summary}"
        elif titulo and len(titulo) > 3:
            # Usa o título limpo
            analise_final['summary'] = f"{modelo_nome}, {titulo[:120]}"
        else:
            # Fallback genérico
            problema = post.get('categoria', 'technical issue').replace('_', ' ')
            analise_final['summary'] = f"{modelo_nome}, {problema} reported"
    else:
        # Summary já começa com o modelo, só limpa
        analise_final['summary'] = summary
    
    # Garante que detected_fault não ficou com valor placeholder
    fault_placeholders = [
        'specific fault or None', 'specific fault found',
        'describe the fault', 'specific technical fault'
    ]
    if analise_final.get('detected_fault', '') in fault_placeholders:
        analise_final['detected_fault'] = 'None'
    
    # =========================================================
    # SALVA CHECKPOINT
    # =========================================================
    async with aiofiles.open(checkpoint_path, 'w', encoding='utf-8') as f:
        await f.write(json.dumps(analise_final, ensure_ascii=False))
    
    stats["processados_agora"] += 1
    return analise_final