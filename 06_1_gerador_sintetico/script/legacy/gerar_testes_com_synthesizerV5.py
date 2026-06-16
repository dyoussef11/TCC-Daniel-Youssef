#!/usr/bin/env python3
"""
gerar_testes_estavel.py
Geração de dataset sintético otimizada para Ragas + Ollama (JSON estruturado) + BGE-M3
"""

import json
import sys
import re
import pandas as pd
from pathlib import Path
from typing import List

# Importações corrigidas para o ecossistema moderno do Ragas
from langchain_core.documents import Document
from langchain_ollama import ChatOllama
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import HuggingFaceEmbeddings
from ragas.testset import TestsetGenerator

from core.paths import NER_DATA

# ========= CONFIGURAÇÕES =========
DIR_ENTRADA = NER_DATA / "Base_Conhecimento_ResumidaV12_VERIFICADA"
SAMPLE_SIZE = 400
TEST_SIZE = 100
MODELO_LLM = "phi3:14b"
MODELO_EMB = "BAAI/bge-m3"
URL_OLLAMA = "http://localhost:11434"
BATCH_SIZE = 50  # Reduzido levemente para evitar gargalo de contexto no Ollama
CHECKPOINT_CSV = Path('06_1_gerador_sintetico/data/testes_ragas_parcial.csv')


# ------------------------------------------------------------
# FUNÇÕES DE LIMPEZA E CARGA DE DADOS
# ------------------------------------------------------------
def clean_text(text: str) -> str:
    """Garante que o texto não quebre o parser de JSON do Ollama ou Ragas."""
    if not isinstance(text, str):
        text = str(text)
    # Remove caracteres de controle problemáticos
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    # Sanitiza aspas duplas internas para não quebrar estruturas JSON geradas
    text = text.replace('"', "'")
    text = ' '.join(text.split())
    return text if len(text.strip()) >= 10 else "[EMPTY CHUNK]"


def carregar_chunks(limit: int = 50) -> List[Document]:
    chunks = []
    contador = 0
    for json_path in DIR_ENTRADA.glob("*.json"):
        if contador >= limit:
            break
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                dados = json.load(f)
        except Exception:
            continue

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
            texto_limpo = clean_text(texto)

            if texto_limpo != "[EMPTY CHUNK]":
                chunks.append(Document(
                    page_content=texto_limpo,
                    metadata={
                        "model": str(modelo),
                        "intent": str(analise.get('intent', 'unknown')),
                        "severity": str(analise.get('technical_severity', 'Medium'))
                    }
                ))
                contador += 1
                
    print(f"✅ {len(chunks)} chunks carregados com sucesso.")
    return chunks


# ------------------------------------------------------------
# EXECUÇÃO PRINCIPAL
# ------------------------------------------------------------
# ------------------------------------------------------------
# EXECUÇÃO PRINCIPAL
# ------------------------------------------------------------
def main():
    print("\n" + "="*60)
    print(" PIPELINE OTIMIZADO: RAGAS + OLLAMA JSON + BGE-M3")
    print("="*60 + "\n")

    # 1. Carrega os Chunks nativos do LangChain
    chunks = carregar_chunks(limit=SAMPLE_SIZE)
    if len(chunks) < 2:
        print("❌ Chunks insuficientes para gerar testes.")
        return

    # 2. Inicialização dos Modelos
    print(f"🤖 Configurando Ollama ({MODELO_LLM}) com JSON estruturado...")
    native_ollama = ChatOllama(
        model=MODELO_LLM,
        base_url=URL_OLLAMA,
        temperature=0.0,
        format="json" 
    )
    
    # SOLUÇÃO DO IMPORT: Caminho correto e atualizado para evitar warnings e erros
    from ragas.llms.base import LangchainLLMWrapper
    ragas_llm = LangchainLLMWrapper(langchain_llm=native_ollama)

    print(f"📊 Carregando BGE-M3 localmente via Ragas HuggingFace...")
    # Caminho estável do embedding configurado corretamente
    ragas_embed = HuggingFaceEmbeddings(
    model="BAAI/bge-m3",           # ou "all-MiniLM-L6-v2" para mais velocidade
    normalize_embeddings=True,     # parâmetro direto, não dentro de dict
    device="cuda",                 # ou "cpu" se não tiver GPU
    batch_size=32                  # opcional, ajuste conforme sua memória
    )

    # 3. Construindo o gerador Ragas
    print("⚙️ Inicializando TestsetGenerator...")
    # Inicialização padrão aceita pela API estável do Ragas
    generator = TestsetGenerator(
        llm=ragas_llm,
        embedding_model=ragas_embed
    )

    # 4. Cálculo e Distribuição de Lotes
    num_batches = (len(chunks) + BATCH_SIZE - 1) // BATCH_SIZE
    tests_per_batch = max(1, TEST_SIZE // num_batches)
    
    print(f"-> {num_batches} lotes de até {BATCH_SIZE} chunks.")
    print(f"-> Alvo por lote: {tests_per_batch} testes (Total final desejado: {TEST_SIZE})\n")

    all_dfs = []
    CHECKPOINT_CSV.parent.mkdir(parents=True, exist_ok=True)
    
    if CHECKPOINT_CSV.exists():
        print(f"📀 Checkpoint recuperado de {CHECKPOINT_CSV}. Retomando...")
        existing_df = pd.read_csv(CHECKPOINT_CSV)
        all_dfs.append(existing_df)
        start_batch = min(len(existing_df) // tests_per_batch, num_batches - 1)
        print(f"⏩ Retomando a partir do Lote {start_batch + 1}")
    else:
        start_batch = 0

    # 5. Loop de Geração por Lotes
    for i in range(start_batch, num_batches):
        start_idx = i * BATCH_SIZE
        end_idx = min((i + 1) * BATCH_SIZE, len(chunks))
        batch_chunks = chunks[start_idx:end_idx]
        
        print(f"\n--- Lote {i+1}/{num_batches} | Processando {len(batch_chunks)} chunks ---")
        
        try:
            # Geração adaptada utilizando o fluxo estável com chunks nativos
            testset = generator.generate_with_chunks(
                chunks=batch_chunks,
                testset_size=tests_per_batch
            )
            
            df_batch = testset.to_pandas()
            all_dfs.append(df_batch)
            
            # Atualiza o Checkpoint
            df_intermediate = pd.concat(all_dfs, ignore_index=True).drop_duplicates(subset=['question'])
            df_intermediate.to_csv(CHECKPOINT_CSV, index=False, encoding='utf-8')
            print(f"✅ Lote {i+1} salvo. Total acumulado: {len(df_intermediate)} linhas.")
            
        except Exception as e:
            print(f"❌ Erro crítico no lote {i+1}: {e}")
            print("O progresso anterior foi mantido. Ajuste os parâmetros e rode novamente.")
            sys.exit(1)

    # 6. Consolidação e formatação para o DeepEval
    if not all_dfs:
        print("⚠️ Nenhum dado gerado.")
        return

    df_final = pd.concat(all_dfs, ignore_index=True).drop_duplicates(subset=['question'])
    if len(df_final) > TEST_SIZE:
        df_final = df_final.head(TEST_SIZE)

    csv_final = NER_DATA / "testes_ragas_final.csv"
    df_final.to_csv(csv_final, index=False, encoding='utf-8')
    print(f"\n💾 Dataset final salvo em CSV: {csv_final}")

    # Transformação estruturada para DeepEval
    test_cases_deepeval = []
    for idx, row in df_final.iterrows():
        ctx = row.get('contexts', [])
        if isinstance(ctx, list):
            ctx_list = [str(c) for c in ctx if c]
        elif isinstance(ctx, str):
            ctx_list = [ctx]
        else:
            ctx_list = ["(Sem contexto recuperado)"]

        ground_truth = row.get('ground_truth', row.get('reference', '(Sem Ground Truth)'))
        
        test_cases_deepeval.append({
            "input": str(row.get('question', '(Pergunta não gerada)')),
            "expected_output": str(ground_truth),
            "retrieval_context": ctx_list,
            "metadata": {
                "id": f"RAGAS_GEN_{idx:04d}",
                "test_type": "sintetico_ragas",
                "model_origin": str(row.get('metadata', {}).get('model', 'generic')) if isinstance(row.get('metadata'), dict) else "generic"
            }
        })

    json_path = Path("06_1_gerador_sintetico/data/test_cases_ragas.json")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(test_cases_deepeval, f, indent=2, ensure_ascii=False)

    print(f"✨ Pronto! {len(test_cases_deepeval)} Casos convertidos com sucesso para o DeepEval em: {json_path}")

if __name__ == "__main__":
    main()