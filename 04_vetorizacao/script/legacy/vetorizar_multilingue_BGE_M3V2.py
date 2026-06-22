# revetorizar_multilingueV6_OTIMIZADO.py
"""
Vetorização otimizada para BGE-M3 com preservação de:
- Nome canônico do modelo
- Diagnóstico técnico (fault)
- Severidade do problema
- Soluções estruturadas
- Timeline validada
"""

import json
import asyncio
import re
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
import faiss
import numpy as np
from ollama import AsyncClient
from tensorboard import summary
from tqdm.asyncio import tqdm

# ============================================================================
# CONFIGURAÇÕES DE CAMINHO
# ============================================================================

try:
    from core.paths import NER_DATA, VETORIZATION_DATA
    # DIR_ENTRADA = NER_DATA / 'Base_Conhecimento_ResumidaV12_VERIFICADA'
    DIR_ENTRADA = NER_DATA / 'Base_Conhecimento_ResumidaV13_VERIFICADA'
    CAMINHO_SAIDA = VETORIZATION_DATA / 'base_conhecimento_multilingueV9.json'
except ImportError:
    DIR_ENTRADA = Path("./data/Base_Conhecimento_ResumidaV5_VERIFICADA")
    CAMINHO_SAIDA = Path("./data/base_conhecimento_multilingueV7.json")

# ============================================================================
# CONFIGURAÇÕES DE VETORIZAÇÃO
# ============================================================================

CONCORRENCIA_MAXIMA = 8  # Reduzido para não sobrecarregar GPU
MODELO_EMBEDDING = "bge-m3:latest"

# ============================================================================
# FUNÇÕES DE FORMATAÇÃO
# ============================================================================

def validar_timeline(timeline: str, fallback_date: str) -> str:
    """
    Garante que a timeline está no formato YYYY-MM-DD to YYYY-MM-DD.
    Corrige 'present', 'None', e formatos inválidos.
    """
    if not timeline or timeline == 'None' or timeline.strip() == '':
        return f"{fallback_date} to {fallback_date}"
    
    # Remove 'present', 'now', 'ongoing'
    timeline_lower = timeline.lower()
    if any(word in timeline_lower for word in ['present', 'now', 'ongoing', 'current']):
        # Extrai data de início
        match = re.search(r'(\d{4}-\d{2}-\d{2})', timeline)
        if match:
            return f"{match.group(1)} to {fallback_date}"
        return f"{fallback_date} to {fallback_date}"
    
    # Verifica formato YYYY-MM-DD to YYYY-MM-DD
    match = re.search(r'(\d{4}-\d{2}-\d{2})\s+to\s+(\d{4}-\d{2}-\d{2})', timeline)
    if match:
        return timeline
    
    # Tenta extrair pelo menos uma data
    match = re.search(r'(\d{4}-\d{2}-\d{2})', timeline)
    if match:
        return f"{match.group(1)} to {match.group(1)}"
    
    return f"{fallback_date} to {fallback_date}"

def formatar_solucoes_estruturadas(solucoes) -> List[str]:
    """
    Garante que as soluções sejam uma lista de strings limpas.
    """
    if not solucoes:
        return ["No solution documented"]
    
    if isinstance(solucoes, str):
        # Tenta quebrar string em múltiplas soluções
        if ';' in solucoes:
            return [s.strip() for s in solucoes.split(';') if s.strip()]
        elif ',' in solucoes and len(solucoes) > 50:
            return [s.strip() for s in solucoes.split(',') if s.strip()]
        return [solucoes]
    
    if isinstance(solucoes, list):
        resultado = []
        for item in solucoes[:4]:  # Máximo 4 soluções
            if isinstance(item, str):
                resultado.append(item.strip())
            elif isinstance(item, dict):
                # Extrai primeiro valor não vazio
                for v in item.values():
                    if v and str(v).strip():
                        resultado.append(str(v).strip())
                        break
            else:
                resultado.append(str(item).strip())
        return resultado if resultado else ["No solution documented"]
    
    return [str(solucoes)]

def extrair_fault_limpo(fault: str) -> str:
    """Limpa e normaliza o campo detected_fault."""
    if not fault:
        return "None"
    
    fault = str(fault).strip()
    
    # Remove variações de "None"
    if fault.lower() in ['none', 'none - informational query', 'n/a', 'null', '']:
        return "None"
    
    # Limita tamanho
    if len(fault) > 100:
        fault = fault[:97] + "..."
    
    return fault

# def construir_texto_embedding(post: Dict, modelo_ref: str) -> str:
#     """
#     Constrói texto semanticamente rico para BGE-M3.
    
#     Estrutura otimizada:
#     [MODEL] [PROBLEM] [FAULT] [SEVERITY] [SYMPTOMS] [SOLUTIONS] [TIMELINE]
#     """
#     analise = post.get('analise_ia', {})
#     if not analise:
#         return ""
    
#     # Extrai campos com fallbacks
#     summary = analise.get('summary', f"{modelo_ref}, no details available")
#     fault = extrair_fault_limpo(analise.get('detected_fault', 'None'))
#     # severity = analise.get('technical_severity', 'Medium')
#     # intent = analise.get('intent', 'Technical Specifications')
#     timeline_raw = analise.get('discussion_timeline', '')
    
#     ancora = analise.get('ancoragem_temporal', {})
#     post_date = ancora.get('data_post', '2024-01-01')
    
#     # Valida timeline
#     timeline = validar_timeline(timeline_raw, post_date)
    
#     # Formata soluções
#     solucoes = formatar_solucoes_estruturadas(analise.get('suggested_solution'))
#     solucoes_str = " | ".join(solucoes[:4])  # Primeiras 3 soluções
    
#     # 🎯 TEXTO OTIMIZADO PARA BGE-M3
#     # O modelo é repetido 3x para aumentar peso semântico
#     texto = (
#         f"MODEL: {modelo_ref} {modelo_ref} {modelo_ref}. "
#         f"PROBLEM: {summary}. "
#         f"FAULT: {fault}. "
#         f"SOLUTIONS: {solucoes_str}."
#     )
    
#     # Remove espaços extras e normaliza
#     texto = ' '.join(texto.split())
    
#     return texto

def construir_texto_embedding(post: Dict, modelo_ref: str) -> str:
    analise = post.get('analise_ia', {})
    if not analise:
        return ""

    summary = analise.get('summary', '')
    fault = extrair_fault_limpo(analise.get('detected_fault', 'None'))
    solucoes = formatar_solucoes_estruturadas(analise.get('suggested_solution'))
    solucoes_str = " | ".join(solucoes[:4])
    
    # Inclui a timeline (período) para dar contexto temporal ao embedding
    timeline_raw = analise.get('discussion_timeline', '')
    timeline = validar_timeline(timeline_raw, post.get('date_iso', '2024-01-01'))
    
    texto = (
        f"Model: {modelo_ref}. "
        f"Problem: {summary}. "
        f"Diagnosis: {fault}. "
        f"Solutions: {solucoes_str}. "
        f"Period: {timeline}."   # <-- novo campo
    )
    return ' '.join(texto.split())

# ============================================================================
# PROCESSAMENTO DE POSTS
# ============================================================================

async def processar_post(
    client: AsyncClient,
    item: Dict,
    semaphore: asyncio.Semaphore,
    pbar: tqdm,
    retries: int = 3
) -> Optional[Dict]:
    """Processa um único post com retry."""
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
                    pbar.write(f"❌ Falha no post {item['id']}: {str(e)[:50]}")
                    pbar.update(1)
                    return None

# ============================================================================
# PIPELINE PRINCIPAL
# ============================================================================

async def gerar_base_vetorial_otimizada():
    """Pipeline principal de vetorização."""
    print("=" * 70)
    print("🚀 VETORIZAÇÃO OTIMIZADA PARA BGE-M3")
    print("=" * 70)
    
    client = AsyncClient()
    semaphore = asyncio.Semaphore(CONCORRENCIA_MAXIMA)
    
    arquivos = list(DIR_ENTRADA.glob("*.json"))
    if not arquivos:
        print(f"⚠️ Nenhum arquivo encontrado em {DIR_ENTRADA}")
        return
    
    print(f"📁 {len(arquivos)} arquivos de modelo encontrados")
    
    fila_trabalho = []
    stats = {
        "total_posts": 0,
        "com_analise": 0,
        "sem_analise": 0,
        "texto_vazio": 0
    }
    
    # Coleta todos os posts
    for arq_path in arquivos:
        try:
            with open(arq_path, 'r', encoding='utf-8') as f:
                dados_modelo = json.load(f)
        except Exception as e:
            print(f"⚠️ Erro ao ler {arq_path.name}: {e}")
            continue
        
        # modelo_ref = dados_modelo.get('modelo_busca_utilizado', 'Unknown Device')
        modelo_ref = dados_modelo.get('modelo_original', 'Unknown Device')
        posts = dados_modelo.get('posts', [])
        stats["total_posts"] += len(posts)
        
        for post in posts:
            analise = post.get('analise_ia', {})
            if not analise:
                stats["sem_analise"] += 1
                continue
            
            stats["com_analise"] += 1
            
            # Constrói texto rico para embedding
            texto_final = construir_texto_embedding(post, modelo_ref)
            
            if not texto_final or len(texto_final) < 50:
                stats["texto_vazio"] += 1
                continue
            
            ancora = analise.get('ancoragem_temporal', {})
            data_post_original = ancora.get('data_post_original', '2024-01-01')
            data_processamento = ancora.get('data_processamento', '2024-01-01')
            priorizacao_recentes = ancora.get('priorizacao_recentes', False)

            # Opcional: manter timeline original para auditoria, mas NÃO usar no embedding
            timeline_raw = analise.get('discussion_timeline', '')
            
            solucoes = formatar_solucoes_estruturadas(analise.get('suggested_solution'))
            fault = extrair_fault_limpo(analise.get('detected_fault', 'None'))
            
            fila_trabalho.append({
                'id': post.get('id', f"unknown_{len(fila_trabalho)}"),
                'texto_final': texto_final,                           # sem TIMELINE
                'date_iso': data_processamento,                       # data mais recente
                'metadata': {
                    'title': post.get('titulo', 'Untitled Post')[:100],
                    'model': modelo_ref,
                    'summary': analise.get('summary', 'Medium'),
                    'fault': fault,
                    'solutions': solucoes,
                    'temas_cobertos': len(solucoes),
                    # NOVOS CAMPOS TEMPORAIS
                    'data_post_original': data_post_original,
                    'data_processamento': data_processamento,
                    'priorizacao_recentes': priorizacao_recentes,
                    'discussion_timeline_raw': timeline_raw           # opcional
                }
            })
    
    # Relatório de coleta
    print(f"\n📊 COLETA CONCLUÍDA:")
    print(f"   Total de posts: {stats['total_posts']}")
    print(f"   Com análise IA: {stats['com_analise']}")
    print(f"   Sem análise IA: {stats['sem_analise']}")
    print(f"   Texto vazio/inválido: {stats['texto_vazio']}")
    print(f"   Posts para vetorizar: {len(fila_trabalho)}")
    
    if not fila_trabalho:
        print("⚠️ Fila de trabalho vazia. Verifique os dados de entrada.")
        return
    
    # Mostra exemplo do texto gerado
    print(f"\n📝 EXEMPLO DE TEXTO PARA EMBEDDING:")
    print(f"   {fila_trabalho[0]['texto_final'][:300]}...")
    
    # Vetorização
    print(f"\n🔄 INICIANDO VETORIZAÇÃO...")
    with tqdm(total=len(fila_trabalho), desc="Vetorizando", unit="post") as pbar:
        tasks = [processar_post(client, item, semaphore, pbar) for item in fila_trabalho]
        resultados = await asyncio.gather(*tasks)
    
    base_conhecimento = [r for r in resultados if r is not None]
    
    # ============================================================================
# NOVO BLOCO DE SALVAMENTO (substitua a seção atual)
# ============================================================================

    if base_conhecimento:
        CAMINHO_SAIDA.parent.mkdir(parents=True, exist_ok=True)
        
        # 1. Salva o JSON original (para fallback / compatibilidade)
        with open(CAMINHO_SAIDA, 'w', encoding='utf-8') as f:
            json.dump(base_conhecimento, f, ensure_ascii=False, indent=2)
        
        # 2. Extrai vetores e metadados
        vectors = np.array([item['vector'] for item in base_conhecimento], dtype=np.float32)
        metadata_list = []
        for item in base_conhecimento:
            # Mantém todos os campos que os RAGs esperam
            metadata_list.append({
                'id': item['id'],
                'original_text': item['original_text'],
                'date_iso': item['date_iso'],
                'metadata': item['metadata']  # contém data_post_original, etc.
            })
        
        # 3. Salva vetores .npy (carregamento ultrarrápido)
        np.save(CAMINHO_SAIDA.with_suffix('.npy'), vectors)
        
        # 4. Salva metadados .meta.json (bem mais leve que o completo)
        with open(CAMINHO_SAIDA.with_suffix('.meta.json'), 'w', encoding='utf-8') as f:
            json.dump(metadata_list, f, ensure_ascii=False, indent=2)
        
        # 5. Cria e salva índice FAISS
        dimension = vectors.shape[1]
        index = faiss.IndexFlatL2(dimension)
        index.add(vectors)
        faiss.write_index(index, str(CAMINHO_SAIDA.with_suffix('.faiss')))
        
        print(f"\n✨ VETORIZAÇÃO CONCLUÍDA!")
        print(f"   Vetores gerados: {len(base_conhecimento)}")
        print(f"   Arquivos salvos:")
        print(f"     - {CAMINHO_SAIDA} (JSON original)")
        print(f"     - {CAMINHO_SAIDA.with_suffix('.npy')} (vetores)")
        print(f"     - {CAMINHO_SAIDA.with_suffix('.meta.json')} (metadados)")
        print(f"     - {CAMINHO_SAIDA.with_suffix('.faiss')} (índice FAISS)")
    else:
        print("❌ Nenhum vetor foi gerado com sucesso.")

# ============================================================================
# PONTO DE ENTRADA
# ============================================================================

if __name__ == "__main__":
    asyncio.run(gerar_base_vetorial_otimizada())