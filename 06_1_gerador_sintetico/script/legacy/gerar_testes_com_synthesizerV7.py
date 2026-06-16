import json
import asyncio
from pathlib import Path
import pandas as pd

# Importação dos caminhos do seu projeto
from core.paths import NER_DATA

from langchain_core.documents import Document
from langchain_community.llms import Ollama
from langchain_community.embeddings import OllamaEmbeddings

# 1. Importações oficiais do Ragas 0.4.3
from ragas.testset.synthesizers.generate import TestsetGenerator
from ragas.testset.synthesizers.single_hop.specific import SingleHopSpecificQuerySynthesizer
from ragas.testset.synthesizers.multi_hop import (
    MultiHopAbstractQuerySynthesizer,
    MultiHopSpecificQuerySynthesizer,
)

async def gerar_testset_ragas():
    # Configuração dos Caminhos de Entrada e Saída
    dir_entrada = NER_DATA / "Base_Conhecimento_ResumidaV12_VERIFICADA"
    dir_saida = Path("06_1_gerador_sintetico/data")
    dir_saida.mkdir(parents=True, exist_ok=True)
    caminho_final_json = dir_saida / "rag_testset_vostro.json"
    
    if not dir_entrada.exists():
        raise FileNotFoundError(f"Diretório de entrada não encontrado: {dir_entrada}")
    
    json_files = list(dir_entrada.glob("*.json"))
    if not json_files:
        print(f"⚠️ Nenhum arquivo JSON de origem encontrado em: {dir_entrada}")
        return

    documents = []
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
                
                documents.append(Document(page_content=conteudo_documento, metadata=metadata))
        except Exception as e:
            print(f"⚠️ Erro ao processar o arquivo {file_path.name}: {e}")

    print(f"📊 Total de {len(documents)} sub-documentos preparados para o Ragas.")
    if not documents:
        return

    # 3. Inicialização dos wrappers do Ollama via LangChain
    generator_llm = Ollama(model="granite4.1:8b-q4_K_M", base_url="http://localhost:11434")
    generator_embeddings = OllamaEmbeddings(model="bge-m3:latest", base_url="http://localhost:11434")

    # 4. Instanciar os Synthesizers passando o LLM local
    single_hop = SingleHopSpecificQuerySynthesizer(llm=generator_llm)
    multi_hop_abstract = MultiHopAbstractQuerySynthesizer(llm=generator_llm)
    multi_hop_specific = MultiHopSpecificQuerySynthesizer(llm=generator_llm)

    # Configuração de acordo com o tipo QueryDistribution (List[Tuple[BaseSynthesizer, float]])
    query_dist = [
        (single_hop, 0.40),
        (multi_hop_abstract, 0.30),
        (multi_hop_specific, 0.30)
    ]

    # 5. Inicializar o TestsetGenerator (Ajustado estritamente à assinatura do método)
    print("⚡ Inicializando o TestsetGenerator (Ollama local)...")
    generator = TestsetGenerator.from_langchain(
        llm=generator_llm,
        embedding_model=generator_embeddings
    )

    print("⚡ Iniciando a geração sintética baseada em Hops...")
    
    # 6. Gerar os testes usando os nomes de parâmetros corretos da assinatura: testset_size e query_distribution
    testset = generator.generate_with_langchain_docs(
        documents=documents,
        testset_size=100,
        query_distribution=query_dist
    )

    # 7. Conversão para Pandas e Salvamento em JSON na pasta data
    df_testes = testset.to_pandas()
    
    df_testes.to_json(
        caminho_final_json, 
        orient="records", 
        force_ascii=False, 
        indent=2
    )
    
    print(f"✅ Conjunto de testes salvo com sucesso em: {caminho_final_json}")

if __name__ == "__main__":
    asyncio.run(gerar_testset_ragas())