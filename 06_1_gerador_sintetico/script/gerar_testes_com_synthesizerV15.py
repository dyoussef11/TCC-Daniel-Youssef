import json
import random
from pathlib import Path
from typing import List, Optional
from langchain_core.documents import Document
from langchain_ollama import ChatOllama, OllamaEmbeddings
from ragas.testset import TestsetGenerator

from core.paths import NER_DATA

# ============================================================
# 1. Função para carregar todos os documentos a partir de uma pasta
# ============================================================
def carregar_documentos_de_jsons(diretorio: str) -> List[Document]:
    """
    Percorre todos os arquivos .json no diretório, extrai o campo 'analise_ia'
    de cada post e retorna uma lista de Document.
    """
    path_dir = Path(diretorio)
    json_files = list(path_dir.glob("*.json"))
    if not json_files:
        raise ValueError(f"Nenhum arquivo .json encontrado em {diretorio}")

    documentos = []

    for json_path in json_files:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        modelo_original = data.get("modelo_original", "unknown_sku")
        modelo_generico = data.get("modelo_generico", "unknown_series")

        for post in data.get("posts", []):
            analise = post.get("analise_ia", {})
            if not analise:
                continue

            # Conteúdo APENAS com os campos da análise (como você definiu)
            conteudo = f"""
            Produto: {modelo_original} (série {modelo_generico})
            Título do post: {post.get('titulo', '')}
            Resumo da análise: {analise.get('summary', '')}
            Intenção do usuário: {analise.get('intent', '')}
            Falha detectada: {analise.get('detected_fault', 'Nenhuma')}
            Severidade técnica: {analise.get('technical_severity', 'Baixa')}
            Soluções sugeridas: {', '.join(analise.get('suggested_solution', []))}
            """

            metadata = {
                "source": json_path.name,
                "post_id": post.get("id", "unknown"),
                "categoria": post.get("categoria", "geral"),
                "modelo_sku": modelo_original,
                "data_post": post.get("data_post", 0)
            }

            documentos.append(Document(page_content=conteudo, metadata=metadata))

    print(f"✅ Total de documentos extraídos: {len(documentos)}")
    return documentos


# ============================================================
# 2. (Opcional) Amostragem aleatória – se quiser reduzir o número
# ============================================================
def amostrar_documentos(documentos: List[Document], n: Optional[int] = None) -> List[Document]:
    """
    Seleciona aleatoriamente 'n' documentos da lista.
    Se n for None ou maior que o total, retorna a lista original.
    """
    if n is None or n >= len(documentos):
        return documentos
    return random.sample(documentos, n)


# ============================================================
# 3. Configuração do RAGAS + Ollama (local)
# ============================================================
def configurar_ragas_ollama(
    modelo_llm: str = "granite4.1:8b-q4_K_M",
    modelo_embed: str = "bge-m3:latest",
    base_url: str = "http://localhost:11434"
):
    llm = ChatOllama(base_url=base_url, model=modelo_llm)
    embeddings = OllamaEmbeddings(base_url=base_url, model=modelo_embed)
    generator = TestsetGenerator.from_langchain(
        llm=llm,
        # critic_llm=llm,
        embedding_model=embeddings
    )
    return generator


# ============================================================
# 4. Execução principal
# ============================================================
if __name__ == "__main__":
    # --- Parâmetros ajustáveis ---
    DIR_JSONS = NER_DATA /"Base_Conhecimento_ResumidaV12_VERIFICADA"   # <-- altere aqui
    NUM_DOCS_USAR = 10        # Quantos documentos usar (aleatório). Se None, usa todos.
    TEST_SIZE = 5            # Número de testes a gerar (perguntas + respostas)
    # DISTRIBUICAO = {
    #     "simple": 0.5,
    #     "reasoning": 0.25,
    #     "multi_context": 0.25
    # }
    distribuicao = [
    ("simple", 0.5),
    ("reasoning", 0.25),
    ("multi_context", 0.25)
    ]   

    # 1. Carrega todos os documentos
    todos_docs = carregar_documentos_de_jsons(DIR_JSONS)

    if not todos_docs:
        print("❌ Nenhum documento válido encontrado.")
        exit()

    # 2. (Opcional) Amostragem aleatória para limitar a quantidade
    docs_para_usar = amostrar_documentos(todos_docs, NUM_DOCS_USAR)
    print(f"📄 Usando {len(docs_para_usar)} documentos (amostragem aleatória).")

    # 3. Configura o gerador RAGAS
    generator = configurar_ragas_ollama()

    # 4. Gera o test set
    print(f"🔄 Gerando {TEST_SIZE} testes a partir dos documentos...")
    testset = generator.generate_with_langchain_docs(
        docs_para_usar,
        testset_size=TEST_SIZE,
        # query_distribution=DISTRIBUICAO
        query_distribution=distribuicao
    )

    # 5. Salva e visualiza resultados
    df = testset.to_pandas()
    print("\n--- Primeiros 5 testes gerados ---")
    print(df[["user_input", "reference"]].head())

    # Exporta para CSV e JSON
    testset.to_csv("testes_analise_ia_multi_json.csv")
    testset.to_json("testes_analise_ia_multi_json.json")
    print("✅ Dataset salvo em CSV e JSON.")