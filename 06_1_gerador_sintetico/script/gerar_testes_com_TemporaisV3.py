#!/usr/bin/env python3
"""
gerar_testes_temporais_com_chunks.py
Geração de dataset sintético TEMPORAL usando Ragas 0.4.3 + ChatOllamaJson
Inclui data explícita no chunk + checkpoint por lotes + HuggingFace Embeddings.
"""

import json
import sys
import re
import pandas as pd
from pathlib import Path
from typing import List

from langchain_core.documents import Document
from ragas.embeddings import HuggingFaceEmbeddings
from ragas.testset import TestsetGenerator
from ragas.run_config import RunConfig
from custom_chat_ollama_json import ChatOllamaJson
from core.paths import NER_DATA

# ========= CONFIG =========
DIR_ENTRADA = NER_DATA / "Base_Conhecimento_ResumidaV12_VERIFICADA"
SAMPLE_SIZE = 400
TEST_SIZE = 100
MODELO_LLM = "phi3:14b"                # Alinhado com o synthesizer (mais robusto)
MODELO_EMB = "bge-m3:latest"          # Apenas referência; usaremos HF
URL_OLLAMA = "http://localhost:11434"
BATCH_SIZE = 100
CHECKPOINT_CSV = r'06_1_gerador_sintetico/data/testes_ragas_temporais_parcial.csv'

# ========= LIMPEZA =========
def clean_text(text: str) -> str:
    if not isinstance(text, str):
        text = str(text)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
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

            data_original = analise.get('ancoragem_temporal', {}).get('data_post_original', '')
            if not data_original:
                data_original = post.get('data_post', '2024-01-01')
            data_str = data_original[:10]

            texto = f"[DATE: {data_str}]\nModelo: {modelo}\nTópico: {titulo}\nResumo: {resumo}\nSoluções: {solucoes_str}"
            texto_limpo = clean_text(texto)

            if len(texto_limpo.strip()) >= 10:
                chunks.append(Document(
                    page_content=texto_limpo,
                    metadata={
                        "model": modelo,
                        "intent": analise.get('intent', 'unknown'),
                        "severity": analise.get('technical_severity', 'Medium'),
                        "data_post_original": data_original,
                        "discussion_timeline": analise.get('discussion_timeline', '')
                    }
                ))
                contador += 1
    print(f"✅ {len(chunks)} chunks temporais carregados e limpos.")
    return chunks

def main():
    print("\n" + "="*60)
    print(" GERADOR DE TESTES TEMPORAIS COM CHECKPOINT POR LOTES (HF Embeddings)")
    print("="*60 + "\n")

    chunks = carregar_chunks_temporais(limit=SAMPLE_SIZE)
    if len(chunks) < 2:
        print("⚠️ Chunks insuficientes.")
        return

    print(f"🤖 Conectando LLM ({MODELO_LLM})...")
    llm = ChatOllamaJson(model=MODELO_LLM, base_url=URL_OLLAMA, temperature=0.0)

    print(f"📊 Conectando Embeddings (HuggingFace BAAI/bge-m3, device=cuda)...")
    embed = HuggingFaceEmbeddings(
        model="BAAI/bge-m3",
        normalize_embeddings=True,
        device="cuda",
        batch_size=32
    )

    print("⚙️ Inicializando Gerador do Ragas...")
    generator = TestsetGenerator.from_langchain(llm=llm, embedding_model=embed)

    # ========= CHECKPOINT POR LOTES =========
    num_batches = (len(chunks) + BATCH_SIZE - 1) // BATCH_SIZE
    tests_per_batch = max(1, TEST_SIZE // num_batches)
    print(f"Total de chunks: {len(chunks)} → {num_batches} lotes de até {BATCH_SIZE} chunks")
    print(f"Gerando ~{tests_per_batch} testes por lote (total alvo: {TEST_SIZE})\n")

    all_dfs = []
    start_batch = 0
    if Path(CHECKPOINT_CSV).exists():
        print(f"📀 Checkpoint encontrado: {CHECKPOINT_CSV}. Retomando...")
        existing_df = pd.read_csv(CHECKPOINT_CSV)
        all_dfs.append(existing_df)
        start_batch = len(existing_df) // tests_per_batch
        print(f"Retomando do lote {start_batch+1}")

    for i in range(start_batch, num_batches):
        start_idx = i * BATCH_SIZE
        end_idx = min((i+1)*BATCH_SIZE, len(chunks))
        batch_chunks = chunks[start_idx:end_idx]
        print(f"\n--- Lote {i+1}/{num_batches} | Chunks {start_idx+1}-{end_idx} ({len(batch_chunks)} chunks) ---")

        try:
            testset = generator.generate_with_chunks(
                chunks=batch_chunks,
                testset_size=tests_per_batch,
                run_config=RunConfig(max_retries=5)   # ← adicionado
            )
            df_batch = testset.to_pandas()
            all_dfs.append(df_batch)

            df_intermediate = pd.concat(all_dfs, ignore_index=True)
            df_intermediate.to_csv(CHECKPOINT_CSV, index=False, encoding='utf-8')
            print(f"✅ Lote {i+1} concluído. Acumulado: {len(df_intermediate)} casos.")
        except Exception as e:
            print(f"❌ Falha no lote {i+1}: {e}")
            print(f"Progresso salvo em {CHECKPOINT_CSV}. Corrija o erro e execute novamente.")
            sys.exit(1)

    # ========= CONSOLIDAÇÃO FINAL =========
    if not all_dfs:
        print("Nenhum teste gerado.")
        return

    df_final = pd.concat(all_dfs, ignore_index=True)
    if len(df_final) > TEST_SIZE:
        df_final = df_final.head(TEST_SIZE)

    csv_final = Path("testes_ragas_temporais.csv")
    df_final.to_csv(csv_final, index=False, encoding='utf-8')
    print(f"\n✅ CSV final salvo: {csv_final} ({len(df_final)} linhas)")

    # ========= CONVERSÃO PARA DEEPEVAL =========
    test_cases = []
    for idx, row in df_final.iterrows():
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
                "reference_date": "2026-01-01",
                "original_chunk_date": row.get('metadata', {}).get('data_post_original', '')
            }
        })

    output_dir = Path("06_1_gerador_sintetico/data")
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "test_cases_temporais.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(test_cases, f, indent=2, ensure_ascii=False)

    print(f"✨ {len(test_cases)} casos temporais salvos em: {json_path}")
    print("\n🏁 Execução concluída.")

if __name__ == "__main__":
    main()