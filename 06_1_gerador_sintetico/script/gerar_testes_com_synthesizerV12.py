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

# WRAPPER DO RAGAS PARA CORRIGIR INCOMPATIBILIDADE DE EMBEDDING
from ragas.embeddings import LangchainEmbeddingsWrapper

async def carregar_testes_existentes(caminho_json: Path) -> list:
    """Carrega os testes já gerados salvos no arquivo JSON para o checkpoint."""
    if caminho_json.exists():
        try:
            with open(caminho_json, "r", encoding="utf-8") as f:
                dados = json.load(f)
                if isinstance(dados, list):
                    return dados
        except Exception as e:
            print(f"⚠️ Erro ao ler checkpoint existente (criando novo): {e}")
    return []

def salvar_checkpoint(caminho_json: Path, novos_testes_df: pd.DataFrame, testes_anteriores: list):
    """Mescla os novos testes com os anteriores e atualiza o arquivo JSON."""
    novos_testes_dict = novos_testes_df.to_dict(orient="records")
    todos_testes = testes_anteriores + novos_testes_dict
    
    with open(caminho_json, "w", encoding="utf-8") as f:
        json.dump(todos_testes, f, ensure_ascii=False, indent=2)
    
    print(f"💾 Checkpoint salvo! Total acumulado: {len(todos_testes)} testes.")

async def gerar_testset_ragas():
    # Configuração dos Caminhos de Entrada e Saída
    dir_entrada = NER_DATA / "Base_Conhecimento_ResumidaV12_VERIFICADA"
    dir_saida = Path("06_1_gerador_sintetico/data")
    dir_saida.mkdir(parents=True, exist_ok=True)
    caminho_final_json = dir_saida / "rag_testsets.json"
    
    # Meta de geração total
    TOTAL_TESTES_DESEJADO = 1
    TAMANHO_LOTE = 10  
    
    # 1. Verificar progresso anterior (Checkpoint)
    testes_acumulados = await carregar_testes_existentes(caminho_final_json)
    testes_concluidos = len(testes_acumulados)
    
    if testes_concluidos >= TOTAL_TESTES_DESEJADO:
        print(f"✅ Geração já concluída anteriormente! {testes_concluidos}/{TOTAL_TESTES_DESEJADO} testes encontrados.")
        return

    print(f"🔄 Checkpoint: {testes_concluidos}/{TOTAL_TESTES_DESEJADO} concluídos.")

    if not dir_entrada.exists():
        raise FileNotFoundError(f"Diretório de entrada não encontrado: {dir_entrada}")
    
    json_files = list(dir_entrada.glob("*.json"))
    if not json_files:
        print(f"⚠️ Nenhum arquivo JSON de origem encontrado em: {dir_entrada}")
        return

    raw_documents = []
    print(f"📂 Lendo arquivos de: {dir_entrada}")

    # 2. Carregar e estruturar os documentos
    for file_path in json_files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            modelo_original = data.get("modelo_original", "unknown_sku")
            modelo_generico = data.get("modelo_generico", "unknown_series")
            
            for post in data.get("posts", []):
                analise = post.get("analise_ia", {})
                if not analise:
                    continue
                
                conteudo_documento = f"""
                Original Model SKU: {modelo_original}
                Generic Line/Series: {modelo_generico}
                Post Title/Context: {post.get('titulo', '')}
                Post Selftext: {post.get('selftext', '')}
                AI Analysis Summary: {analise.get('summary', '')}
                User Intent: {analise.get('intent', '')}
                Detected Fault: {analise.get('detected_fault', 'None')}
                Technical Severity: {analise.get('technical_severity', 'Low')}
                Discussion Timeline: {analise.get('discussion_timeline', '')}
                Suggested Solutions: {', '.join(analise.get('suggested_solution', []))}
                """
                
                metadata = {
                    "source": str(file_path.name),
                    "post_id": post.get("id", "unknown"),
                    "category": post.get("categoria", "general"),
                    "model_sku": modelo_original
                }
                
                raw_documents.append(Document(page_content=conteudo_documento, metadata=metadata))
        except Exception as e:
            print(f"⚠️ Erro ao processar o arquivo {file_path.name}: {e}")

    if not raw_documents:
        print("⚠️ Nenhum documento válido extraído.")
        return

    # Amostragem enxuta aleatória para evitar sobrecarga no Grafo
    max_docs_para_ragas = min(len(raw_documents), 1)
    documents = random.sample(raw_documents, max_docs_para_ragas)
    print(f"✂️ Utilizando amostragem de {len(documents)} documentos.")

    # 3. Inicialização dos modelos do Ollama atualizados
    generator_llm = OllamaLLM(model="granite4.1:8b-q4_K_M", base_url="http://localhost:11434", temperature=0.0, format='json')
    
    # Criamos o embedding nativo do LangChain e encapsulamos com o Wrapper do Ragas
    langchain_embeddings = OllamaEmbeddings(model="bge-m3:latest", base_url="http://localhost:11434")
    generator_embeddings = LangchainEmbeddingsWrapper(langchain_embeddings)

    # 4. Instanciar os Synthesizers APENAS com o LLM (conforme a assinatura da classe)
    single_hop = SingleHopSpecificQuerySynthesizer(llm=generator_llm)
    multi_hop_abstract = MultiHopAbstractQuerySynthesizer(llm=generator_llm)
    multi_hop_specific = MultiHopSpecificQuerySynthesizer(llm=generator_llm)

    query_dist = [
        (single_hop, 0.40),
        (multi_hop_abstract, 0.30),
        (multi_hop_specific, 0.30)
    ]

    # Aproveitando a RTX 3090 com 8 workers paralelos
    config_execucao = RunConfig(
        timeout=240,      
        max_workers=8  
    )

    # 5. Inicializar o TestsetGenerator padrão com o embedding envelopado
    print("⚡ Inicializando o TestsetGenerator (Ollama local)...")
    
    generator = TestsetGenerator(
        llm=generator_llm,
        embedding_model=generator_embeddings
    )

    # 6. Loop de Geração Incremental
    while testes_concluidos < TOTAL_TESTES_DESEJADO:
        restantes = TOTAL_TESTES_DESEJADO - testes_concluidos
        tamanho_lote_atual = min(TAMANHO_LOTE, restantes)
        
        print(f"\n🚀 [Progresso: {testes_concluidos}/{TOTAL_TESTES_DESEJADO}] Gerando lote de {tamanho_lote_atual} perguntas...")
        
        try:
            testset_lote = generator.generate_with_langchain_docs(
                documents=documents,
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