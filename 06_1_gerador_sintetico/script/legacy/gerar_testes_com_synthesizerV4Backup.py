#!/usr/bin/env python3
"""
gerar_testes_com_synthesizerV6.py
Geração de dataset sintético com Ragas 0.4.3
"""

import json
import sys
from pathlib import Path
from typing import List

from langchain_core.documents import Document
from langchain_ollama import ChatOllama, OllamaEmbeddings
from ragas.testset import TestsetGenerator
from ragas.testset.graph import Node, NodeType
from custom_chat_ollama_json import ChatOllamaJson

from core.paths import NER_DATA  # only needed if you still want graph utilities


# ========= CONFIG =========
DIR_ENTRADA = NER_DATA / "Base_Conhecimento_ResumidaV12_VERIFICADA"
SAMPLE_SIZE = 400
TEST_SIZE = 100
MODELO_LLM = "mistral:7b-instruct"
MODELO_EMB = "bge-m3:latest"
URL_OLLAMA = "http://localhost:11434"


import re

def clean_text(text: str) -> str:
    """
    Remove caracteres não imprimíveis e garante que o texto seja seguro para embedding.
    Se após limpeza ficar muito curto, retorna um placeholder.
    """
    if not isinstance(text, str):
        text = str(text)
    # Remove caracteres de controle (exceto \n, \r, \t)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    # Remove espaços e quebras excessivas
    text = ' '.join(text.split())
    if len(text.strip()) < 10:
        return "[EMPTY CHUNK - PLACEHOLDER]"
    return text


def carregar_chunks(limit: int = 50) -> List[Document]:
    """
    Carrega os JSONs e cria uma lista de LangChain Document.
    Cada chunk corresponde a um post, tratado como um fragmento pré‑quebrado.
    """
    chunks = []
    contador = 0
    for json_path in DIR_ENTRADA.glob("*.json"):
        if contador >= limit:
            break
        with open(json_path, 'r', encoding='utf-8') as f:
            dados = json.load(f)
        modelo = dados.get('modelo_original', 'unknown')
        for post in dados.get('posts', []):
            if contador >= limit:
                break
            analise = post.get('analise_ia', {})
            if not analise:
                continue
            titulo = post.get('titulo', '')
            resumo = analise.get('summary', '')
            solucoes = analise.get('suggested_solution', [])
            solucoes_str = " | ".join(solucoes[:3]) if solucoes else "No solution"
            texto = f"Modelo: {modelo}\nTópico: {titulo}\nResumo: {resumo}\nSoluções: {solucoes_str}"
            
            # --- LIMPEZA CRÍTICA ---
            texto_limpo = clean_text(texto)
            # ---

            if len(texto_limpo.strip()) >= 10:
                chunks.append(Document(
                    page_content=texto_limpo,
                    metadata={
                        "model": modelo,
                        "intent": analise.get('intent', 'unknown'),
                        "severity": analise.get('technical_severity', 'Medium'),
                        "data_post": analise.get('ancoragem_temporal', {}).get('data_post_original', '')
                    }
                ))
                contador += 1
    print(f"✅ {len(chunks)} chunks carregados e limpos.")
    return chunks


def main():
    print("\n" + "="*60)
    print(" GERADOR DE TESTES SINTÉTICOS COM PRE‑CHUNKS (RAGAS 0.4.3)")
    print("="*60 + "\n")

    # 1. Carregar dados como chunks
    chunks = carregar_chunks(limit=SAMPLE_SIZE)
    if len(chunks) < 2:
        print("⚠️ Chunks insuficientes para gerar testes.")
        return

    # 2. Modelos
    print(f"🤖 Conectando LLM ({MODELO_LLM})...")
    llm = ChatOllamaJson(
        model=MODELO_LLM,
        base_url=URL_OLLAMA,
        temperature=0.0
    )


    print(f"📊 Conectando Embeddings ({MODELO_EMB})...")
    embed = OllamaEmbeddings(model=MODELO_EMB, base_url=URL_OLLAMA)

    # 3. Inicializar gerador
    print("⚙️ Inicializando Gerador do Ragas...")
    generator = TestsetGenerator.from_langchain(
        llm=llm,
        embedding_model=embed
    )

    # 4. Gerar testset com chunks
    print(f"\n🚀 Gerando {TEST_SIZE} casos de teste com chunks pre‑quebrados...")
    testset = generator.generate_with_chunks(
        chunks=chunks,
        testset_size=TEST_SIZE
    )

    # 5. Exportar
    df = testset.to_pandas()
    df.to_csv("testes_ragas.csv", index=False, encoding='utf-8')
    print(f"✅ CSV salvo: testes_ragas.csv ({len(df)} linhas)")

    # 6. Converter para DeepEval
    test_cases = []
    for idx, row in df.iterrows():
        ctx = row.get('contexts', [])
        if isinstance(ctx, list) and ctx:
            ctx = [str(ctx[0])]
        elif isinstance(ctx, str):
            ctx = [ctx]
        else:
            ctx = ["(vazio)"]

        ground_truth = row.get('ground_truth', row.get('reference', '(vazio)'))

        test_cases.append({
            "input": row.get('question', '(sem pergunta)'),
            "expected_output": ground_truth,
            "retrieval_context": ctx,
            "metadata": {
                "id": f"RAGAS_{idx}",
                "test_type": "traditional",
                "reference_date": "2024-01-01"
            }
        })

    output_dir = Path("06_1_gerador_sintetico/data")
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "test_cases_ragas.json"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(test_cases, f, indent=2, ensure_ascii=False)

    print(f"✨ {len(test_cases)} casos DeepEval salvos em: {json_path}")
    print("\n🏁 Execução concluída com sucesso.")


if __name__ == "__main__":
    main()