import json
import faiss
import ijson
import numpy as np
import ollama
import asyncio
import re
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, Union
import gc
from functools import lru_cache

from core.paths import VALIDACAO_CONFIG, VETORIZATION_DATA


class SpecialistTimeAwareRAG:
    """
    Engine RAG com Auditoria Silenciosa e Normalização por Sinônimos.
    Aplica penalidade temporal e expansão de SKU para maior precisão técnica.
    
    MODIFICADO: BGE-M3 forçado a rodar na CPU, mantendo o modelo de chat
    (phi3.5) livre para usar GPU se disponível.
    """
    
    def __init__(self, json_path: Union[str, Path], variant_name: str = "V8_HYBRID_AUDITOR", embedding_cache=None) -> None:
        self.dimension: int = 1024  # Dimensão do BGE-M3
        self.caminho_prompts: Path = VALIDACAO_CONFIG / 'prompt_rag_temporal_hybrid_V8Backup.json'
        self.variant_name = variant_name
        self.external_cache = embedding_cache

        print(f"--- 🧠 RAG ENGINE ATIVADA (Variante: {variant_name}) ---")
        
        # ⭐ NOVO: Inicializa cliente CPU para embeddings
        self._init_cpu_embedding_client()
        print(f"✅ BGE-M3 configurado para rodar na CPU")
        
        # 1. Carregar a base de conhecimento
        self.base_dados = []
        try:
            with open(json_path, 'rb') as f:
                for item in ijson.items(f, 'item'):
                    self.base_dados.append(item)
            print(f"✅ Base carregada: {len(self.base_dados)} documentos.")
        except Exception as e:
            print(f"❌ Erro ao carregar base: {e}")
            self.base_dados = []

        # 3. Inicializar Index FAISS
        self.index = faiss.IndexFlatL2(self.dimension)
        if self.base_dados:
            vectors = np.array([d['vector'] for d in self.base_dados]).astype('float32')
            self.index.add(vectors)
            print(f"✅ Index FAISS criado com {self.index.ntotal} vetores")

        # 4. Carregar Prompts
        try:
            with open(self.caminho_prompts, 'r', encoding='utf-8') as f:
                self.prompts = json.load(f)
        except FileNotFoundError:
            print(f"⚠️ Arquivo de prompt não encontrado: {self.caminho_prompts}")
            print("   Usando prompts padrão...")
            self.prompts = {
                self.variant_name: {
                    "system_role": "You are a technical specialist assistant.",
                    "constraints": [
                        "Answer only based on the provided context",
                        "Be concise and technical",
                        "Do not mention the context in your answer"
                    ]
                }
            }

    def _init_cpu_embedding_client(self):
        """
        Inicializa cliente Ollama que força o BGE-M3 a usar apenas CPU.
        """
        # Salva configurações atuais
        original_cuda = os.environ.get('CUDA_VISIBLE_DEVICES')
        original_num_gpu = os.environ.get('OLLAMA_NUM_GPU')
        
        # Força CPU para este cliente
        os.environ['CUDA_VISIBLE_DEVICES'] = '-1'
        os.environ['OLLAMA_NUM_GPU'] = '0'
        
        # Cria o cliente
        from ollama import Client
        self._cpu_ollama_client = Client(host='http://localhost:11434')
        
        # Restaura configurações originais
        if original_cuda is not None:
            os.environ['CUDA_VISIBLE_DEVICES'] = original_cuda
        else:
            os.environ.pop('CUDA_VISIBLE_DEVICES', None)
        
        if original_num_gpu is not None:
            os.environ['OLLAMA_NUM_GPU'] = original_num_gpu
        else:
            os.environ.pop('OLLAMA_NUM_GPU', None)
        
        # Verifica se o modelo bge-m3 está disponível
        try:
            # Teste rápido para verificar se o modelo existe
            test_result = self._cpu_ollama_client.embeddings(model="bge-m3:latest", prompt="test")
            if 'embedding' in test_result:
                print(f"✅ Conexão com BGE-M3 (CPU) estabelecida - dimensão: {len(test_result['embedding'])}")
            else:
                print("⚠️ BGE-M3 respondeu mas formato inesperado")
        except Exception as e:
            print(f"⚠️ Aviso: BGE-M3 pode não estar disponível: {e}")
            print("   Execute: ollama pull bge-m3:latest")
    
    @lru_cache(maxsize=200)
    def _get_embedding_cached(self, query: str) -> np.ndarray:
        """
        Obtém embedding com cache LRU.
        Retorna um array 1D de dimensão 1024.
        """
        # Usa o cliente CPU para gerar o embedding
        result = self._cpu_ollama_client.embeddings(
            model="bge-m3:latest", 
            prompt=query
        )
        
        # Converte para numpy array (1D)
        embedding = np.array(result['embedding'], dtype=np.float32)
        
        # Verifica a dimensão
        if len(embedding) != self.dimension:
            print(f"⚠️ Dimensão inesperada: {len(embedding)} (esperado: {self.dimension})")
        
        return embedding
    
    async def _get_embedding(self, query: str) -> np.ndarray:
        """
        Obtém embedding de forma assíncrona, usando cache externo se disponível.
        """
        # ⭐ Verifica cache externo primeiro
        if self.external_cache:
            cached = self.external_cache.get(query)
            if cached is not None:
                return cached
        
        # Se não estiver no cache, gera novo
        embedding = await asyncio.to_thread(self._get_embedding_cached, query)
        
        # ⭐ Salva no cache externo
        if self.external_cache:
            self.external_cache.set(query, embedding)
        
        return embedding
    
    def get_cache_stats(self) -> Dict[str, int]:
        """Retorna estatísticas do cache de embeddings."""
        cache_info = self._get_embedding_cached.cache_info()
        return {
            "cache_hits": cache_info.hits,
            "cache_misses": cache_info.misses,
            "cache_maxsize": cache_info.maxsize,
            "cache_currsize": cache_info.currsize
        }

    def _extrair_auditoria(self, full_response: str) -> Dict[str, str]:
        audit_match = re.search(r"AUDIT:(.*?)(?=ANSWER:|$)", full_response, re.DOTALL | re.IGNORECASE)
        answer_match = re.search(r"ANSWER:(.*)", full_response, re.DOTALL | re.IGNORECASE)
        
        return {
            "audit_log": audit_match.group(1).strip() if audit_match else "No audit log provided.",
            "clean_answer": answer_match.group(1).strip() if answer_match else full_response.strip()
        }

    async def search(self, query: str, ref_date: str = "2026-03-23"):
        """
        Executa busca RAG.
        - BGE-M3: roda na CPU (forçado)
        - Modelo de chat: usa configuração padrão do Ollama (pode usar GPU)
        """
        ref_dt = datetime.strptime(ref_date, "%Y-%m-%d")
        
        # 1. Embedding (AGORA NA CPU!)
        print(f"🔄 Gerando embedding para: {query[:50]}...")
        query_vector_1d = await self._get_embedding(query)
        
        # Converte para 2D para o FAISS (reshape para (1, dimension))
        query_vector = query_vector_1d.reshape(1, -1)
        print(f"✅ Embedding gerado (dimensão: {query_vector.shape[1]})")

        # 2. Busca no FAISS (k=20)
        distances, indices = self.index.search(query_vector, k=50)
        
        scored_results = []
        for i, idx in enumerate(indices[0]):
            if idx == -1: 
                continue
            
            doc = self.base_dados[idx]
            dist_score = distances[0][i]
            
            # Adicione depois da busca para ver os scores
            
            # Threshold de relevância
            if dist_score > 1.2:
                continue
                
            # Penalidade Temporal
            doc_date_str = doc.get('date_iso', '2024-01-01')[:10]
            doc_dt = datetime.strptime(doc_date_str, "%Y-%m-%d")
            diff_years = max(0, (ref_dt - doc_dt).days / 365.25)
            
            time_penalty = 1.0 + (diff_years * 0.04)
            final_score = dist_score * time_penalty
            
            scored_results.append({
                'doc': doc, 
                'score': final_score,
                'date': doc_date_str
            })
        print(f"📊 Scores encontrados: {distances[0][:5]}")  # Mostra os 5 primeiros
        # 3. Top 10
        scored_results = sorted(scored_results, key=lambda x: x['score'])[:10]
        
        # Se não encontrou nada, afrouxa o threshold
        if len(scored_results) == 0:
            print(f"⚠️ Nenhum resultado com threshold 1.2. Buscando top 5 direto...")
            distances, indices = self.index.search(query_vector, k=5)
            for i, idx in enumerate(indices[0]):
                if idx != -1:
                    doc = self.base_dados[idx]
                    doc_date_str = doc.get('date_iso', '2024-01-01')[:10]
                    scored_results.append({
                        'doc': doc,
                        'score': distances[0][i],
                        'date': doc_date_str
                    })
        
        print(f"📄 Recuperados {len(scored_results)} documentos relevantes")
        
        # 4. Contexto SEM INDENTAÇÃO!
        context_parts = []
        for i, r in enumerate(scored_results):
            meta = r['doc'].get('metadata', {})
            titulo = meta.get('title') or meta.get('model') or f"Source_{i}"
            
            # Trunca texto muito longo
            text = r['doc']['original_text']
            if len(text) > 2000:
                text = text[:2000] + "..."
            
            context_parts.append(
                f"[[ID_{i} | DATE: {r['date']} | TITLE: {titulo}]]\n{text}"
            )
        
        context_str = "\n\n".join(context_parts)

        # 5. Prompt
        variant = self.prompts.get(self.variant_name, {})
        
        constraints_text = "\n".join(f"- {c}" for c in variant.get('constraints', []))
        
        sys_prompt = f"""{variant.get('system_role', 'You are a technical specialist assistant.')}

CRITICAL RULES:
{constraints_text if constraints_text else '- Answer only based on the provided context\n- Be concise and technical\n- Do not mention the context in your answer'}

MANDATORY OUTPUT FORMAT:
AUDIT: [List source IDs used with dates. If internal knowledge needed, state 'Internal knowledge']
ANSWER: [Clean technical response without any tags or meta-commentary]"""

        user_content = f"""CONTEXT:
{context_str}

QUERY: {query}

REFERENCE DATE: {ref_date}

Generate your response following the exact format specified."""

        print("🤖 Gerando resposta com modelo de chat...")
        
        # 6. Usar modelo de chat
        try:
            response = await asyncio.to_thread(
                ollama.chat,
                model="phi3.5:latest",
                messages=[
                    {'role': 'system', 'content': sys_prompt},
                    {'role': 'user', 'content': user_content}
                ],
                options={"temperature": 0.1, "top_p": 0.9},
                keep_alive=0
            )
            
            full_text = response['message']['content']
            extracted = self._extrair_auditoria(full_text)

        except Exception as e:
            print(f"⚠️ Erro no modelo de chat: {e}")
            extracted = {
                "clean_answer": f"Erro ao gerar resposta: {e}",
                "audit_log": "Error during generation"
            }

        # Retorna resultado com informações de diagnóstico
        cache_stats = self.get_cache_stats()
        
        return {
            "answer": extracted["clean_answer"],
            "audit_trail": extracted["audit_log"],
            "titles": [r['doc'].get('metadata', {}).get('title', 'Unknown') for r in scored_results],
            "sources": [r['doc']['original_text'] for r in scored_results],
            "retrieved_metadata": [r['doc'].get('metadata', {}) for r in scored_results],
            "normalized_query": query,
            "diagnostic": {
                "embedding_cache": cache_stats,
                "num_documents_retrieved": len(scored_results),
                "cpu_embeddings": True
            }
        }


# ============================================================================
# SCRIPT DE TESTE
# ============================================================================

async def test_cpu_embeddings():
    """Testa o comportamento do RAG com embeddings na CPU."""
    
    print("\n" + "=" * 70)
    print("🧪 TESTE: BGE-M3 na CPU")
    print("=" * 70)
    
    # Verifica se o modelo está disponível
    print("\n📋 Verificando modelos disponíveis no Ollama:")
    try:
        models = ollama.list()
        for model in models.get('models', [])[:5]:  # Mostra só os primeiros
            print(f"   - {model.get('name', 'unknown')}")
    except Exception as e:
        print(f"   ⚠️ Não foi possível listar modelos: {e}")
    
    # Inicializa o RAG
    print("\n🔧 Inicializando RAG...")
    
    # Verifica se o arquivo da base existe
    # base_path = VETORIZATION_DATA / 'base_conhecimento_multilingueV6_OTIMIZADO.json'
    base_path = VETORIZATION_DATA / 'base_conhecimento_multilingueV7.json'
    if not base_path.exists():
        print(f"❌ Base não encontrada: {base_path}")
        print("   Verifique o caminho ou use um arquivo existente.")
        return
    
    engine = SpecialistTimeAwareRAG(base_path)
    
    # Mostra estatísticas iniciais do cache
    print(f"\n📊 Cache de embeddings:")
    cache_stats = engine.get_cache_stats()
    for key, value in cache_stats.items():
        print(f"   {key}: {value}")
    
    # Teste com múltiplas queries
    perguntas = [
        "Qual a RAM máxima do Helios 300?",
        "Qual processador do notebook Dell G7?",
    ]
    
    for i, pergunta in enumerate(perguntas, 1):
        print(f"\n{'─' * 70}")
        print(f"📝 TESTE {i}: {pergunta}")
        print(f"{'─' * 70}")
        
        start_time = datetime.now()
        try:
            res = await engine.search(pergunta)
            elapsed = (datetime.now() - start_time).total_seconds()
            
            print(f"\n⏱️ Tempo total: {elapsed:.2f} segundos")
            print(f"\n🔍 QUERY: {pergunta}")
            
            print(f"\n📊 Diagnóstico:")
            print(f"   Documentos recuperados: {res['diagnostic']['num_documents_retrieved']}")
            print(f"   Cache hits: {res['diagnostic']['embedding_cache']['cache_hits']}")
            print(f"   Cache misses: {res['diagnostic']['embedding_cache']['cache_misses']}")
            print(f"   Usou CPU para embedding: {res['diagnostic']['cpu_embeddings']}")
            
            print(f"\n🤖 RESPOSTA FINAL:\n{res['answer'][:500]}")  # Limita resposta
            print(f"\n📜 AUDIT TRAIL:\n{res['audit_trail'][:200]}")
            
        except Exception as e:
            print(f"❌ Erro no teste {i}: {e}")
            import traceback
            traceback.print_exc()
    
    # Estatísticas finais do cache
    print(f"\n{'=' * 70}")
    print("📊 ESTATÍSTICAS FINAIS DO CACHE")
    print(f"{'=' * 70}")
    final_cache_stats = engine.get_cache_stats()
    for key, value in final_cache_stats.items():
        print(f"   {key}: {value}")
    
    print(f"\n✅ Teste concluído!")


async def quick_test():
    """Teste rápido para verificar apenas o embedding."""
    
    print("\n" + "=" * 70)
    print("🧪 TESTE RÁPIDO - Apenas Embedding")
    print("=" * 70)
    
    # Testa apenas a função de embedding
    from ollama import Client
    
    print("\n1. Testando cliente CPU...")
    
    # Salva ambiente
    original_cuda = os.environ.get('CUDA_VISIBLE_DEVICES')
    os.environ['CUDA_VISIBLE_DEVICES'] = '-1'
    os.environ['OLLAMA_NUM_GPU'] = '0'
    
    cpu_client = Client()
    
    print("2. Gerando embedding com BGE-M3 na CPU...")
    start = datetime.now()
    
    try:
        result = cpu_client.embeddings(model="bge-m3:latest", prompt="teste de embedding")
        elapsed = (datetime.now() - start).total_seconds()
        
        embedding = result['embedding']
        print(f"✅ Embedding gerado em {elapsed:.2f} segundos")
        print(f"   Dimensão: {len(embedding)}")
        print(f"   Tipo: {type(embedding)}")
        print(f"   Primeiros valores: {embedding[:5]}")
        
    except Exception as e:
        print(f"❌ Erro: {e}")
    
    # Restaura
    if original_cuda is not None:
        os.environ['CUDA_VISIBLE_DEVICES'] = original_cuda
    else:
        os.environ.pop('CUDA_VISIBLE_DEVICES', None)
    
    print("\n✅ Teste rápido concluído!")


if __name__ == "__main__":
    import sys
    
    print("\n" + "=" * 70)
    print("🔧 SCRIPT DE TESTE - BGE-M3 na CPU")
    print("=" * 70)
    
    # Escolha qual teste executar
    print("\nOpções:")
    print("1 - Teste básico completo")
    print("2 - Teste rápido (apenas embedding)")
    
    choice = input("\nEscolha (1/2): ").strip()
    
    if choice == "2":
        asyncio.run(quick_test())
    else:
        asyncio.run(test_cpu_embeddings())