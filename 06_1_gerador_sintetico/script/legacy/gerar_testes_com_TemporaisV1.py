#!/usr/bin/env python3
"""
gerar_testes_temporais_com_chunks.py
Geração de dataset sintético TEMPORAL usando Ragas 0.4.3 + ChatOllamaJson
Inclui data explícita no chunk.
"""

import json
import sys
from pathlib import Path
from typing import List

from langchain_core.documents import Document
from langchain_ollama import OllamaEmbeddings
from ragas.testset import TestsetGenerator
from custom_chat_ollama_json import ChatOllamaJson   # seu wrapper JSON
from core.paths import NER_DATA

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



def carregar_chunks_temporais(limit: int = 50) -> List[Document]:
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

            # ===== PONTO CRÍTICO: DATA EXPLÍCITA =====
            data_original = analise.get('ancoragem_temporal', {}).get('data_post_original', '')
            if not data_original:
                data_original = post.get('data_post', '2024-01-01')
            data_str = data_original[:10]   # YYYY-MM-DD

            texto = f"[DATE: {data_str}]\nModelo: {modelo}\nTópico: {titulo}\nResumo: {resumo}\nSoluções: {solucoes_str}"

            if len(texto.strip()) >= 50:
                chunks.append(Document(
                    page_content=texto,
                    metadata={
                        "model": modelo,
                        "intent": analise.get('intent', 'unknown'),
                        "severity": analise.get('technical_severity', 'Medium'),
                        "data_post_original": data_original,
                        "discussion_timeline": analise.get('discussion_timeline', '')
                    }
                ))
                contador += 1
    print(f"✅ {len(chunks)} chunks temporais carregados.")
    return chunks


def main():
    print("\n" + "="*60)
    print(" GERADOR DE TESTES TEMPORAIS (RAGAS + CHUNKS COM DATA)")
    print("="*60 + "\n")

    chunks = carregar_chunks_temporais(limit=SAMPLE_SIZE)
    if len(chunks) < 2:
        print("⚠️ Chunks insuficientes.")
        return

    print(f"🤖 Conectando LLM ({MODELO_LLM})...")
    llm = ChatOllamaJson(
        model=MODELO_LLM,
        base_url=URL_OLLAMA,
        temperature=0.0
    )

    print(f"📊 Conectando Embeddings ({MODELO_EMB})...")
    embed = OllamaEmbeddings(model=MODELO_EMB, base_url=URL_OLLAMA)

    print("⚙️ Inicializando Gerador do Ragas...")
    generator = TestsetGenerator.from_langchain(
        llm=llm,
        embedding_model=embed
    )

    print(f"\n🚀 Gerando {TEST_SIZE} casos de teste com consciência temporal...")
    testset = generator.generate_with_chunks(
        chunks=chunks,
        testset_size=TEST_SIZE
    )

    df = testset.to_pandas()
    csv_path = Path("testes_ragas_temporais.csv")
    df.to_csv(csv_path, index=False, encoding='utf-8')
    print(f"✅ CSV salvo: {csv_path} ({len(df)} linhas)")

    # Converte para DeepEval
    from deepeval.test_case import LLMTestCase
    test_cases = []
    for idx, row in df.iterrows():
        ctx = row.get('contexts', [])
        if isinstance(ctx, list) and ctx:
            ctx = [str(ctx[0])]
        elif isinstance(ctx, str):
            ctx = [ctx]
        else:
            ctx = ["(vazio)"]

        test_cases.append({
            "input": row.get('question', '(sem pergunta)'),
            "expected_output": row.get('ground_truth', row.get('reference', '(vazio)')),
            "retrieval_context": ctx,
            "metadata": {
                "id": f"RAGAS_TEMP_{idx}",
                "test_type": "temporal",
                "reference_date": "2026-01-01",   # data de referência futura
                "original_chunk_date": row.get('metadata', {}).get('data_post_original', '')
            }
        })

    output_dir = Path("06_1_gerador_sintetico/data")
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "test_cases_temporais.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(test_cases, f, indent=2, ensure_ascii=False)

    print(f"✨ {len(test_cases)} casos temporais salvos em: {json_path}")
    print("\n🏁 Execução concluída. Use esses testes para avaliar o RAG Temporal (V9).")

if __name__ == "__main__":
    main()