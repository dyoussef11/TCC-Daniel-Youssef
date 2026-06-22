#!/usr/bin/env python3
"""
vetorizar_multilingue_BGE_M3.py
Vetorização otimizada para BGE-M3 com:
- Mapeamento de nomes de modelos a partir do dataset_laptops_UNICOS_V10.csv
- Preservação de metadados temporais (data_post_original, data_processamento, priorizacao_recentes)
- Geração de arquivos .npy (vetores), .meta.json (metadados) e .faiss (índice FAISS)
- Concorrência assíncrona controlada
"""

import asyncio
import json
import re
import numpy as np
import faiss
from pathlib import Path
from typing import List, Dict, Optional
from ollama import AsyncClient
from tqdm.asyncio import tqdm

# Importa as funções de mapeamento do módulo externo (já testado)
from mapeamento_modelos import carregar_mapeamento_por_modelo_limpo, obter_nome_modelo
from variacoes_nomes import construir_texto_embedding 

# ============================================================================
# CONFIGURAÇÕES DE CAMINHO
# ============================================================================

try:
    from core.paths import NER_DATA, VETORIZATION_DATA, DATASET_FINAL_CSV
    DIR_ENTRADA = NER_DATA / 'Base_Conhecimento_ResumidaV13_VERIFICADA'
    CAMINHO_SAIDA = VETORIZATION_DATA / 'base_conhecimento_multilingueV9.json'
    CAMINHO_CSV = Path(DATASET_FINAL_CSV) / "dataset_laptops_UNICOS_V10.csv"
except ImportError:
    # Fallback para execução isolada
    DIR_ENTRADA = Path("./data/Base_Conhecimento_ResumidaV5_VERIFICADA")
    CAMINHO_SAIDA = Path("./data/base_conhecimento_multilingueV9.json")
    CAMINHO_CSV = Path("./dataset_laptops_UNICOS_V10.csv")

# ============================================================================
# CONFIGURAÇÕES DE VETORIZAÇÃO
# ============================================================================

CONCORRENCIA_MAXIMA = 8   # Ajuste conforme sua GPU
MODELO_EMBEDDING = "bge-m3:latest"

# ============================================================================
# FUNÇÕES DE FORMATAÇÃO (auxiliares)
# ============================================================================

def validar_timeline(timeline: str, fallback_date: str) -> str:
    """
    Garante que a timeline está no formato YYYY-MM-DD to YYYY-MM-DD.
    Corrige 'present', 'None', e formatos inválidos.
    """
    if not timeline or timeline == 'None' or timeline.strip() == '':
        return f"{fallback_date} to {fallback_date}"
    
    timeline_lower = timeline.lower()
    if any(word in timeline_lower for word in ['present', 'now', 'ongoing', 'current']):
        match = re.search(r'(\d{4}-\d{2}-\d{2})', timeline)
        if match:
            return f"{match.group(1)} to {fallback_date}"
        return f"{fallback_date} to {fallback_date}"
    
    match = re.search(r'(\d{4}-\d{2}-\d{2})\s+to\s+(\d{4}-\d{2}-\d{2})', timeline)
    if match:
        return timeline
    
    match = re.search(r'(\d{4}-\d{2}-\d{2})', timeline)
    if match:
        return f"{match.group(1)} to {match.group(1)}"
    
    return f"{fallback_date} to {fallback_date}"

def formatar_solucoes_estruturadas(solucoes) -> List[str]:
    """Garante que as soluções sejam uma lista de strings limpas."""
    if not solucoes:
        return ["No solution documented"]
    if isinstance(solucoes, str):
        if ';' in solucoes:
            return [s.strip() for s in solucoes.split(';') if s.strip()]
        elif ',' in solucoes and len(solucoes) > 50:
            return [s.strip() for s in solucoes.split(',') if s.strip()]
        return [solucoes]
    if isinstance(solucoes, list):
        resultado = []
        for item in solucoes[:4]:
            if isinstance(item, str):
                resultado.append(item.strip())
            elif isinstance(item, dict):
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
    if fault.lower() in ['none', 'none - informational query', 'n/a', 'null', '']:
        return "None"
    if len(fault) > 100:
        fault = fault[:97] + "..."
    return fault

# def construir_texto_embedding(post: Dict, nome_modelo: str) -> str:
#     """
#     Constrói texto semanticamente rico para BGE-M3.
#     Inclui o nome do modelo (já com marca), sumário, fault, soluções.
#     """
#     analise = post.get('analise_ia', {})
#     if not analise:
#         return ""
    
#     summary = analise.get('summary', f"{nome_modelo}, no details available")
#     fault = extrair_fault_limpo(analise.get('detected_fault', 'None'))
#     solucoes = formatar_solucoes_estruturadas(analise.get('suggested_solution'))
#     solucoes_str = " | ".join(solucoes[:3])
    
#     texto = (
#         f"MODEL: {nome_modelo} {nome_modelo} {nome_modelo}. "
#         f"PROBLEM: {summary}. "
#         f"FAULT: {fault}. "
#         f"SOLUTIONS: {solucoes_str}."
#     )
#     return ' '.join(texto.split())

# ============================================================================
# PROCESSAMENTO DE POSTS (ASSÍNCRONO)
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
    """Pipeline principal de vetorização com mapeamento de nomes."""
    print("=" * 70)
    print("🚀 VETORIZAÇÃO OTIMIZADA PARA BGE-M3 (COM MAPEAMENTO DE NOMES)")
    print("=" * 70)
    
    # Carrega o mapeamento do CSV
    mapa_modelos = carregar_mapeamento_por_modelo_limpo(CAMINHO_CSV)
    
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
        "texto_vazio": 0,
        "modelos_mapeados": 0,
        "modelos_fallback": 0
    }
    
    # Coleta todos os posts
    for arq_path in arquivos:
        try:
            with open(arq_path, 'r', encoding='utf-8') as f:
                dados_modelo = json.load(f)
        except Exception as e:
            print(f"⚠️ Erro ao ler {arq_path.name}: {e}")
            continue
        
        modelo_original = dados_modelo.get('modelo_original', '')
        modelo_generico = dados_modelo.get('modelo_generico', '')
        
        # Extrai marca do nome do arquivo (fallback)
        nome_arquivo = arq_path.stem
        partes = nome_arquivo.split('_')
        marca_arquivo = partes[1] if len(partes) > 1 else ''
        if marca_arquivo.lower() == 'na' and modelo_generico:
            if '_' in modelo_generico:
                marca_arquivo = modelo_generico.split('_')[0]
        
        # Obtém o nome tratado (agora sem modelo_generico, conforme módulo)
        nome_modelo = obter_nome_modelo(
            modelo_original=modelo_original,
            marca_arquivo=marca_arquivo,
            mapa_por_modelo_limpo=mapa_modelos
        )
        
        # Contabiliza mapeamento
        if modelo_original in mapa_modelos:
            stats["modelos_mapeados"] += 1
        else:
            stats["modelos_fallback"] += 1
        
        posts = dados_modelo.get('posts', [])
        stats["total_posts"] += len(posts)
        
        for post in posts:
            analise = post.get('analise_ia', {})
            if not analise:
                stats["sem_analise"] += 1
                continue
            
            stats["com_analise"] += 1
            
            texto_final = construir_texto_embedding(post, nome_modelo)
            if not texto_final or len(texto_final) < 50:
                stats["texto_vazio"] += 1
                continue
            
            ancora = analise.get('ancoragem_temporal', {})
            data_post_original = ancora.get('data_post_original', '2024-01-01')
            data_processamento = ancora.get('data_processamento', '2024-01-01')
            priorizacao_recentes = ancora.get('priorizacao_recentes', False)
            
            timeline_raw = analise.get('discussion_timeline', '')
            solucoes = formatar_solucoes_estruturadas(analise.get('suggested_solution'))
            fault = extrair_fault_limpo(analise.get('detected_fault', 'None'))
            
            fila_trabalho.append({
                'id': post.get('id', f"unknown_{len(fila_trabalho)}"),
                'texto_final': texto_final,
                'date_iso': data_processamento,
                'metadata': {
                    'title': post.get('titulo', 'Untitled Post')[:100],
                    'model': nome_modelo,
                    'summary': analise.get('summary', ''),
                    'fault': fault,
                    'solutions': solucoes,
                    'temas_cobertos': len(solucoes),
                    'data_post_original': data_post_original,
                    'data_processamento': data_processamento,
                    'priorizacao_recentes': priorizacao_recentes,
                    'discussion_timeline_raw': timeline_raw
                }
            })
    
    # Relatório de coleta
    print(f"\n📊 COLETA CONCLUÍDA:")
    print(f"   Total de posts: {stats['total_posts']}")
    print(f"   Com análise IA: {stats['com_analise']}")
    print(f"   Sem análise IA: {stats['sem_analise']}")
    print(f"   Texto vazio/inválido: {stats['texto_vazio']}")
    print(f"   Modelos mapeados com sucesso: {stats['modelos_mapeados']}")
    print(f"   Modelos fallback: {stats['modelos_fallback']}")
    print(f"   Posts para vetorizar: {len(fila_trabalho)}")
    
    if not fila_trabalho:
        print("⚠️ Fila de trabalho vazia. Verifique os dados de entrada.")
        return
    
    # Exemplo do primeiro texto
    print(f"\n📝 EXEMPLO DE TEXTO PARA EMBEDDING:")
    print(f"   {fila_trabalho[0]['texto_final'][:300]}...")
    
    # Vetorização
    print(f"\n🔄 INICIANDO VETORIZAÇÃO...")
    with tqdm(total=len(fila_trabalho), desc="Vetorizando", unit="post") as pbar:
        tasks = [processar_post(client, item, semaphore, pbar) for item in fila_trabalho]
        resultados = await asyncio.gather(*tasks)
    
    base_conhecimento = [r for r in resultados if r is not None]
    
    if not base_conhecimento:
        print("❌ Nenhum vetor foi gerado com sucesso.")
        return
    
    # ========================================================================
    # SALVAMENTO DOS ARQUIVOS OTIMIZADOS
    # ========================================================================
    
    CAMINHO_SAIDA.parent.mkdir(parents=True, exist_ok=True)
    
    # 1. JSON original (compatibilidade)
    with open(CAMINHO_SAIDA, 'w', encoding='utf-8') as f:
        json.dump(base_conhecimento, f, ensure_ascii=False, indent=2)
    
    # 2. Vetores .npy
    vectors = np.array([item['vector'] for item in base_conhecimento], dtype=np.float32)
    npy_path = CAMINHO_SAIDA.with_suffix('.npy')
    np.save(npy_path, vectors)
    
    # 3. Metadados .meta.json
    metadata_list = [
        {
            'id': item['id'],
            'original_text': item['original_text'],
            'date_iso': item['date_iso'],
            'metadata': item['metadata']
        }
        for item in base_conhecimento
    ]
    meta_path = CAMINHO_SAIDA.with_suffix('.meta.json')
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(metadata_list, f, ensure_ascii=False, indent=2)
    
    # 4. Índice FAISS
    dimension = vectors.shape[1]
    index = faiss.IndexFlatL2(dimension)
    index.add(vectors)
    faiss_path = CAMINHO_SAIDA.with_suffix('.faiss')
    faiss.write_index(index, str(faiss_path))
    
    print(f"\n✨ VETORIZAÇÃO CONCLUÍDA!")
    print(f"   Vetores gerados: {len(base_conhecimento)}")
    print(f"   Taxa de sucesso: {len(base_conhecimento)/len(fila_trabalho)*100:.1f}%")
    print(f"   Arquivos salvos:")
    print(f"     - {CAMINHO_SAIDA} (JSON original)")
    print(f"     - {npy_path} (vetores .npy)")
    print(f"     - {meta_path} (metadados .meta.json)")
    print(f"     - {faiss_path} (índice FAISS)")

# ============================================================================
# PONTO DE ENTRADA
# ============================================================================

if __name__ == "__main__":
    asyncio.run(gerar_base_vetorial_otimizada())