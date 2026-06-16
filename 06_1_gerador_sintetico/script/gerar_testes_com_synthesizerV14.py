import json
import asyncio
import random
from pathlib import Path
import pandas as pd

# Importação dos caminhos do seu projeto
from core.paths import NER_DATA

from langchain_core.documents import Document
from langchain_ollama import OllamaLLM, OllamaEmbeddings

# Importações oficiais do Ragas 0.4.3
from ragas.testset import TestsetGenerator
from ragas.testset.synthesizers.single_hop.specific import SingleHopSpecificQuerySynthesizer
from ragas.testset.synthesizers.multi_hop import (
    MultiHopAbstractQuerySynthesizer,
    MultiHopSpecificQuerySynthesizer,
)
from ragas.run_config import RunConfig

# Importações de transformação corretas do seu ecossistema
from ragas.testset.graph import KnowledgeGraph, Node
from ragas.testset.transforms import default_transforms_for_prechunked

# WRAPPER DO RAGAS PARA CORRIGIR INCOMPATIBILIDADE DE EMBEDDING
from ragas.embeddings import LangchainEmbeddingsWrapper

async def carregar_testes_existentes(caminho_json: Path) -> list:
    if caminho_json.exists():
        try:
            with open(caminho_json, "r", encoding="utf-8") as f:
                dados = json.load(f)
                if isinstance(dados, list):
                    return dados
        except Exception as e:
            print(f"⚠️ Erro ao ler checkpoint existente: {e}")
    return []

def salvar_checkpoint(caminho_json: Path, novos_testes_df: pd.DataFrame, testes_anteriores: list):
    novos_testes_dict = novos_testes_df.to_dict(orient="records")
    todos_testes = testes_anteriores + novos_testes_dict
    with open(caminho_json, "w", encoding="utf-8") as f:
        json.dump(todos_testes, f, ensure_ascii=False, indent=2)
    print(f"💾 Checkpoint salvo! Total acumulado: {len(todos_testes)} testes.")

async def gerar_testset_ragas():
    dir_entrada = NER_DATA / "Base_Conhecimento_ResumidaV12_VERIFICADA"
    dir_saida = Path("06_1_gerador_sintetico/data")
    dir_saida.mkdir(parents=True, exist_ok=True)
    caminho_final_json = dir_saida / "rag_testsets.json"
    
    TOTAL_TESTES_DESEJADO = 100
    TAMANHO_LOTE = 10  
    
    testes_acumulados = await carregar_testes_existentes(caminho_final_json)
    testes_concluidos = len(testes_acumulados)
    
    if testes_concluidos >= TOTAL_TESTES_DESEJADO:
        print(f"✅ Geração já concluída anteriormente!")
        return

    print(f"🔄 Checkpoint: {testes_concluidos}/{TOTAL_TESTES_DESEJADO} concluídos.")

    json_files = list(dir_entrada.glob("*.json"))
    if not json_files:
        print(f"⚠️ Nenhum arquivo JSON encontrado.")
        return

    raw_documents = []
    print(f"📂 Lendo e aplicando amostragem nos posts internos...")

    for file_path in json_files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            modelo_original = data.get("modelo_original", "unknown_sku")
            modelo_generico = data.get("modelo_generico", "unknown_series")
            
            posts = data.get("posts", [])
            if len(posts) > 15:
                posts = random.sample(posts, 15)
            
            for post in posts:
                analise = post.get("analise_ia", {})
                if not analise:
                    continue
                
                conteudo_documento = f"""
                Original Model SKU: {modelo_original}
                Generic Line/Series: {modelo_generico}
                Post Title: {post.get('titulo', '')}
                Post Selftext: {post.get('selftext', '')}
                Summary: {analise.get('summary', '')}
                Intent: {analise.get('intent', '')}
                Fault: {analise.get('detected_fault', 'None')}
                Solutions: {', '.join(analise.get('suggested_solution', []))}
                """
                
                metadata = {
                    "source": str(file_path.name),
                    "post_id": post.get("id", "unknown"),
                    "model_sku": modelo_original
                }
                
                raw_documents.append(Document(page_content=conteudo_documento, metadata=metadata))
        except Exception as e:
            print(f"⚠️ Erro ao processar o arquivo {file_path.name}: {e}")

    if not raw_documents:
        print("⚠️ Nenhum documento válido extraído.")
        return

    # Amostragem para o Grafo (Pelo menos 25 para criar conexões Multi-Hop sem quebrar)
    max_docs_para_ragas = min(len(raw_documents), 25)
    documents = random.sample(raw_documents, max_docs_para_ragas)
    print(f"✂️ Utilizando amostragem de {len(documents)} documentos.")

    # 3. Inicialização dos modelos do Ollama
    generator_llm = OllamaLLM(model="granite4.1:8b-q4_K_M", base_url="http://localhost:11434", temperature=0.2)
    langchain_embeddings = OllamaEmbeddings(model="bge-m3:latest", base_url="http://localhost:11434")
    generator_embeddings = LangchainEmbeddingsWrapper(langchain_embeddings)

    # 4. Instanciar os Synthesizers APENAS com o LLM
    single_hop = SingleHopSpecificQuerySynthesizer(llm=generator_llm)
    multi_hop_abstract = MultiHopAbstractQuerySynthesizer(llm=generator_llm)
    multi_hop_specific = MultiHopSpecificQuerySynthesizer(llm=generator_llm)

    query_dist = [
        (single_hop, 0.50),
        (multi_hop_abstract, 0.25),
        (multi_hop_specific, 0.25)
    ]

    # Ajustando workers para não sobrecarregar o Ollama
    config_execucao = RunConfig(
        timeout=180,      
        max_workers=4  
    )

    # 🔥 SOLUÇÃO REAL PARA A ASSINATURA DA SUA CLASSE:
    # 1. Criamos um Grafo de Conhecimento vazio
    kg = KnowledgeGraph()
    
    # 2. Convertemos os documentos do Langchain para Nós do Ragas e adicionamos ao Grafo
    for doc in documents:
        node = Node(page_content=doc.page_content, metadata=doc.metadata)
        kg.nodes.append(node)
    
    print("🧠 Aplicando transformações rápidas (Pre-chunked) diretamente no Grafo...")
    # 3. Buscamos o pipeline veloz e executamos manualmente usando a engine do Ragas
    pipeline_veloz = default_transforms_for_prechunked(llm=generator_llm, embedding_model=generator_embeddings)
    
    # O Ragas roda as transformações modificando o objeto 'kg' in-place
    from ragas.testset.engine import apply_transforms
    await apply_transforms(kg, pipeline_veloz, config_execucao)

    # 5. Inicializar o TestsetGenerator passando o grafo JÁ PROCESSADO e sem o 'transforms' proibido
    print("⚡ Inicializando o TestsetGenerator com o Grafo Pré-Construído...")
    generator = TestsetGenerator(
        llm=generator_llm,
        embedding_model=generator_embeddings,
        knowledge_graph=kg # <-- Passamos o grafo pronto aqui!
    )

    # 6. Loop de Geração Incremental
    while testes_concluidos < TOTAL_TESTES_DESEJADO:
        restantes = TOTAL_TESTES_DESEJADO - testes_concluidos
        tamanho_lote_atual = min(TAMANHO_LOTE, restantes)
        
        print(f"\n🚀 [Progresso: {testes_concluidos}/{TOTAL_TESTES_DESEJADO}] Gerando lote de {tamanho_lote_atual} perguntas...")
        
        try:
            # Como o Grafo já está dentro do generator, chamamos a geração passando apenas o tamanho e a distribuição
            testset_lote = generator.generate(
                testset_size=tamanho_lote_atual,
                query_distribution=query_dist,
                run_config=config_execucao
            )
            df_lote = testset_lote.to_pandas()
            salvar_checkpoint(caminho_final_json, df_lote, testes_acumulados)
            
            testes_acumulados = await carregar_testes_existentes(caminho_final_json)
            testes_concluidos = len(testes_acumulados)
            
        except Exception as e:
            print(f"❌ Erro durante a execução do lote: {e}")
            return

    print(f"\n🎉 Concluído com sucesso! Arquivo final pronto em: {caminho_final_json}")

if __name__ == "__main__":
    asyncio.run(gerar_testset_ragas())