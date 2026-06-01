import json
import faiss
import numpy as np
import ollama
import asyncio
import pandas as pd
import re
from datetime import datetime
from pathlib import Path
from core.paths import VETORIZATION_DATA, VALIDACAO_CONFIG

# Configurações de Data
now = datetime.now()
formatted_date = now.strftime("%Y-%m-%d")

# Configurações de Caminho
JSON_PATH = VETORIZATION_DATA / 'base_conhecimento_multilingueV5.json'
SINONIMOS_PATH = VALIDACAO_CONFIG / 'dictionary_synonyms_refinedV3.json'
REF_DATE = f"{formatted_date}"

# Casos de Teste (Pode adicionar mais aqui)
TEST_CASES = [
    {"modelo": "Nitro 5", "pergunta": "Qual a RAM máxima do Acer Nitro 5?"},
    {"modelo": "TUF Gaming F15", "pergunta": "O Asus TUF F15 suporta upgrade de SSD?"},
    {"modelo": "Legion 5", "pergunta": "Qual a tela do Lenovo Legion 5?"},
    {"modelo": "Victus 15", "pergunta": "Qual a placa de vídeo do HP Victus 15?"}
]

def expandir_query_logic(query, dicionario):
    query_norm = query.lower()
    expansao = []
    for nome_canonico, apelidos in dicionario.items():
        termos_busca = set(apelidos)
        termos_busca.add(nome_canonico)
        for termo in termos_busca:
            termo_limpo = termo.lower()
            if termo_limpo in query_norm or (len(termo_limpo) > 5 and termo_limpo.replace("acer ", "").replace("asus ", "") in query_norm):
                novos = [a for a in apelidos if a.lower() not in query_norm]
                expansao.extend(novos)
                break 
    expansao_unique = list(dict.fromkeys(expansao))
    return f"{query} ({', '.join(expansao_unique)})" if expansao_unique else query

def calcular_rank_detalhado(indices, distances, base_dados, ref_dt):
    resultados = []
    for i, idx in enumerate(indices[0]):
        if idx == -1: continue
        doc = base_dados[idx]
        dist_orig = distances[0][i]
        
        # Lógica Temporal
        doc_date_str = doc.get('date_iso', '2024-01-01')[:10]
        try:
            doc_dt = datetime.strptime(doc_date_str, "%Y-%m-%d")
        except:
            doc_dt = datetime(2024, 1, 1)
            
        diff_years = max(0, (ref_dt - doc_dt).days / 365.25)
        penalty = 1.0 + (diff_years * 0.04)
        score_final = dist_orig * penalty
        
        resultados.append({
            "ID": idx,
            "Título": (doc.get('metadata', {}).get('title') or "N/A")[:30],
            "Data": doc_date_str,
            "Dist_Pura": round(dist_orig, 4),
            "Score_Temporal": round(score_final, 4)
        })
    # Retorna o Top 5 ordenado pelo Score Temporal
    return pd.DataFrame(resultados).sort_values("Score_Temporal").head(5)

async def rodar_auditoria_em_lote_detalhada():
    print(f"--- 🧪 INICIANDO AUDITORIA EM LOTE (Ref: {REF_DATE}) ---")
    
    with open(JSON_PATH, 'r', encoding='utf-8') as f:
        base_dados = json.load(f)
    with open(SINONIMOS_PATH, 'r', encoding='utf-8') as f:
        sinonimos = json.load(f)
    
    ref_dt = datetime.strptime(REF_DATE, "%Y-%m-%d")
    
    # Setup FAISS
    exemplo = base_dados[0]
    vector_key = 'embedding' if 'embedding' in exemplo else 'vector'
    dimensao = len(exemplo[vector_key])
    index = faiss.IndexFlatL2(dimensao)
    vectors = np.array([d[vector_key] for d in base_dados]).astype('float32')
    index.add(vectors)

    for case in TEST_CASES:
        print(f"\n" + "="*80)
        print(f"📌 MODELO: {case['modelo']}")
        
        query_orig = case['pergunta']
        query_exp = expandir_query_logic(query_orig, sinonimos)
        
        print(f"🔹 ORIGINAL:  {query_orig}")
        print(f"🔸 EXPANDIDA: {query_exp}\n")
        
        # Embeddings
        emb_orig = ollama.embeddings(model="bge-m3:latest", prompt=query_orig)['embedding']
        emb_exp = ollama.embeddings(model="bge-m3:latest", prompt=query_exp)['embedding']
        
        # Busca
        d_orig, i_orig = index.search(np.array([emb_orig]).astype('float32'), k=50)
        d_exp, i_exp = index.search(np.array([emb_exp]).astype('float32'), k=50)
        
        # Gerar Tabelas
        df_orig = calcular_rank_detalhado(i_orig, d_orig, base_dados, ref_dt)
        df_exp = calcular_rank_detalhado(i_exp, d_exp, base_dados, ref_dt)
        
        print("📋 RANKING: QUERY ORIGINAL + TEMPO")
        print(df_orig[["Título", "Data", "Dist_Pura", "Score_Temporal"]].to_string(index=True))
        
        print("\n🚀 RANKING: QUERY EXPANDIDA (V3) + TEMPO")
        print(df_exp[["Título", "Data", "Dist_Pura", "Score_Temporal"]].to_string(index=True))
        
        # Conclusão do Caso
        top_orig = set(df_orig["ID"])
        top_exp = set(df_exp["ID"])
        print(f"\n📊 CONCLUSÃO {case['modelo']}:")
        print(f"- Estabilidade: {len(top_orig.intersection(top_exp))}/5")
        print(f"- Novos Docs no Top 5: {len(top_exp - top_orig)}")

if __name__ == "__main__":
    asyncio.run(rodar_auditoria_em_lote_detalhada())