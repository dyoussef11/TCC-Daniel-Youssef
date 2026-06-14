#!/usr/bin/env python3
"""
gerar_testes_com_synthesizerV6.py
Geração de dataset sintético com Ragas 0.4.3 + checkpoint por lotes
"""

import json
import sys
import re
import pandas as pd
from pathlib import Path
from typing import List

from langchain_core.documents import Document
# from langchain_ollama import OllamaEmbeddings
from ragas.embeddings import HuggingFaceEmbeddings
from ragas.testset import TestsetGenerator
from custom_chat_ollama_json import ChatOllamaJson
from core.paths import NER_DATA
from ragas.run_config import RunConfig

# ========= CONFIG =========
DIR_ENTRADA = NER_DATA / "Base_Conhecimento_ResumidaV12_VERIFICADA"
SAMPLE_SIZE = 400
TEST_SIZE = 100
MODELO_LLM = "phi3:14b"
MODELO_EMB = "bge-m3:latest"
URL_OLLAMA = "http://localhost:11434"
BATCH_SIZE = 100          # chunks por lote (ajuste conforme sua memória)
CHECKPOINT_CSV = r'06_1_gerador_sintetico/data/testes_ragas_parcial.csv'   # arquivo para salvar progresso

# ------------------------------------------------------------
# (mantenha aqui a função clean_text e carregar_chunks iguais ao seu código)

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

# ------------------------------------------------------------

def main():
    print("\n" + "="*60)
    print(" GERADOR DE TESTES SINTÉTICOS COM CHECKPOINT POR LOTES")
    print("="*60 + "\n")

    # 1. Carregar chunks
    chunks = carregar_chunks(limit=SAMPLE_SIZE)
    if len(chunks) < 2:
        print("⚠️ Chunks insuficientes.")
        return

    # 2. Modelos
    print(f"🤖 Conectando LLM ({MODELO_LLM})...")
    llm = ChatOllamaJson(model=MODELO_LLM, base_url=URL_OLLAMA, temperature=0.0)

    print(f"📊 Conectando Embeddings ({MODELO_EMB})...")
    # embed = OllamaEmbeddings(model=MODELO_EMB, base_url=URL_OLLAMA)
    # embed = HuggingFaceEmbeddings(model_name="BAAI/bge-m3")
    embed = HuggingFaceEmbeddings(
    model="BAAI/bge-m3",           # ou "all-MiniLM-L6-v2" para mais velocidade
    normalize_embeddings=True,     # parâmetro direto, não dentro de dict
    device="cuda",                 # ou "cpu" se não tiver GPU
    batch_size=32                  # opcional, ajuste conforme sua memória
    )

    # 3. Gerador
    print("⚙️ Inicializando Gerador do Ragas...")
    generator = TestsetGenerator.from_langchain(llm=llm, embedding_model=embed)

    # 4. Divisão em lotes
    num_batches = (len(chunks) + BATCH_SIZE - 1) // BATCH_SIZE
    # Distribui os TEST_SIZE entre os lotes (pelo menos 1 por lote)
    tests_per_batch = max(1, TEST_SIZE // num_batches)
    print(f"Total de chunks: {len(chunks)} -> {num_batches} lotes de até {BATCH_SIZE} chunks")
    print(f"Gerando até {tests_per_batch} testes por lote (total alvo: {TEST_SIZE})\n")

    all_dfs = []
    # Verifica se já existe um checkpoint parcial
    if Path(CHECKPOINT_CSV).exists():
        print(f"📀 Checkpoint encontrado: {CHECKPOINT_CSV}. Será retomado a partir do último lote bem-sucedido.")
        existing_df = pd.read_csv(CHECKPOINT_CSV)
        all_dfs.append(existing_df)
        start_batch = len(existing_df) // tests_per_batch  # aproximado
        print(f"Retomando do lote {start_batch+1}...")
    else:
        start_batch = 0

    for i in range(start_batch, num_batches):
        start_idx = i * BATCH_SIZE
        end_idx = min((i+1)*BATCH_SIZE, len(chunks))
        batch_chunks = chunks[start_idx:end_idx]
        print(f"\n--- Lote {i+1}/{num_batches} | Chunks {start_idx+1}-{end_idx} ({len(batch_chunks)} chunks) ---")
        
        try:
            testset = generator.generate_with_chunks(
                chunks=batch_chunks,
                testset_size=tests_per_batch,
                run_config=RunConfig(max_retries=5)
            )
            df_batch = testset.to_pandas()
            all_dfs.append(df_batch)
            
            # Salva checkpoint após cada lote
            df_intermediate = pd.concat(all_dfs, ignore_index=True)
            df_intermediate.to_csv(CHECKPOINT_CSV, index=False, encoding='utf-8')
            print(f"✅ Lote {i+1} concluído. Acumulado: {len(df_intermediate)} casos.")
            
        except Exception as e:
            print(f"❌ Falha no lote {i+1}: {e}")
            print(f"Progresso salvo em {CHECKPOINT_CSV}. Corrija o erro e execute novamente.")
            sys.exit(1)

    # 5. Consolidar resultado final
    if not all_dfs:
        print("Nenhum teste gerado.")
        return
    
    df_final = pd.concat(all_dfs, ignore_index=True)
    # Limita exatamente a TEST_SIZE (caso tenha gerado mais)
    if len(df_final) > TEST_SIZE:
        df_final = df_final.head(TEST_SIZE)
    
    csv_final = NER_DATA / "testes_ragas.csv"
    df_final.to_csv(csv_final, index=False, encoding='utf-8')
    print(f"\n✅ CSV final salvo: {csv_final} ({len(df_final)} linhas)")

    # 6. Converter para DeepEval (igual ao seu código original)
    test_cases = []
    for idx, row in df_final.iterrows():
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