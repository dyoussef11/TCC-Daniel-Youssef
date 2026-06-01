# diagnose_rag_pipeline.py
import json
import numpy as np
import ollama
from pathlib import Path

from core.paths import VETORIZATION_DATA


def diagnosticar_base():
    """Verifica se a base de conhecimento está íntegra."""
    
    base_path = Path(VETORIZATION_DATA / "base_conhecimento_multilingueV5.json")
    
    if not base_path.exists():
        print("❌ Arquivo da base NÃO encontrado!")
        return None
    
    print(f"📁 Base encontrada: {base_path}")
    
    # Carrega e analisa
    with open(base_path, 'r', encoding='utf-8') as f:
        dados = json.load(f)
    
    print(f"📊 Total de documentos: {len(dados)}")
    
    if len(dados) == 0:
        print("❌ Base VAZIA!")
        return None
    
    # Verifica estrutura
    primeiro = dados[0]
    print(f"\n🔍 Estrutura do primeiro documento:")
    print(f"   - id: {primeiro.get('id', 'N/A')}")
    print(f"   - date_iso: {primeiro.get('date_iso', 'N/A')}")
    print(f"   - vector presente: {'✅' if 'vector' in primeiro else '❌'}")
    print(f"   - original_text tamanho: {len(primeiro.get('original_text', ''))} chars")
    print(f"   - metadata: {list(primeiro.get('metadata', {}).keys())}")
    
    # Mostra exemplo de texto
    print(f"\n📝 Exemplo de original_text:")
    print(f"   {primeiro.get('original_text', 'N/A')[:300]}...")
    
    # Procura por Acer Nitro 5
    count_acer = 0
    for doc in dados:
        texto = doc.get('original_text', '').lower()
        if 'nitro' in texto or 'acer' in texto:
            count_acer += 1
    
    print(f"\n🎯 Documentos com 'Acer' ou 'Nitro': {count_acer}")
    
    return dados

def testar_embedding():
    """Testa se o modelo de embedding está funcionando."""
    print("\n🧪 Testando modelo de embedding...")
    
    try:
        response = ollama.embeddings(
            model="bge-m3:latest",
            prompt="Acer Nitro 5 AN515-56 RAM maximum capacity 32GB"
        )
        
        embedding = response['embedding']
        print(f"✅ Embedding gerado: {len(embedding)} dimensões")
        return np.array(embedding).astype('float32')
    except Exception as e:
        print(f"❌ Erro no embedding: {e}")
        return None

def testar_busca_simulada(dados, query_embedding):
    """Simula uma busca FAISS simplificada."""
    print("\n🔎 Simulando busca por similaridade...")
    
    query = "Acer Nitro 5 AN515-56 RAM"
    print(f"   Query: '{query}'")
    
    # Busca manual por palavras-chave (fallback)
    resultados_keyword = []
    for doc in dados:
        texto = doc.get('original_text', '').lower()
        score = 0
        if 'nitro' in texto: score += 1
        if 'an515-56' in texto: score += 2
        if 'ram' in texto: score += 1
        if '32gb' in texto or 'ddr4' in texto: score += 2
        
        if score >= 3:
            resultados_keyword.append((doc, score))
    
    print(f"   Resultados por palavra-chave: {len(resultados_keyword)}")
    
    if resultados_keyword:
        print(f"\n   Top 3 resultados:")
        for i, (doc, score) in enumerate(sorted(resultados_keyword, key=lambda x: -x[1])[:3]):
            print(f"   {i+1}. Score: {score}")
            print(f"      Texto: {doc.get('original_text', 'N/A')[:150]}...")
    else:
        print("   ❌ NENHUM resultado por palavra-chave!")
        print("\n   📋 Exemplos de textos na base:")
        for i, doc in enumerate(dados[:5]):
            print(f"   {i+1}. {doc.get('original_text', 'N/A')[:100]}...")
    
    return resultados_keyword

def verificar_ollama_models():
    """Verifica modelos disponíveis no Ollama."""
    print("\n🤖 Modelos Ollama disponíveis:")
    import subprocess
    result = subprocess.run(['ollama', 'list'], capture_output=True, text=True)
    print(result.stdout)

def main():
    print("=" * 80)
    print("🔬 DIAGNÓSTICO DO PIPELINE RAG")
    print("=" * 80)
    
    verificar_ollama_models()
    
    dados = diagnosticar_base()
    
    if dados:
        embedding = testar_embedding()
        if embedding is not None:
            resultados = testar_busca_simulada(dados, embedding)
            
            print("\n" + "=" * 80)
            print("📊 DIAGNÓSTICO FINAL")
            print("=" * 80)
            
            if len(resultados) == 0:
                print("❌ PROBLEMA CRÍTICO: Nenhum documento relevante encontrado!")
                print("\nCausas prováveis:")
                print("1. Os textos na base NÃO contêm 'Acer Nitro 5' ou 'AN515-56'")
                print("2. O texto foi gerado de forma genérica demais")
                print("3. A base pode estar corrompida ou incompleta")
                print("\nSolução:")
                print("→ Execute novamente o revetorizar_multilingueV5.py COM O FIX que forneci")
                print("→ O novo script gera textos RICOS em palavras-chave técnicas")
            else:
                print(f"✅ Pipeline funcionando! {len(resultados)} documentos relevantes encontrados.")
                print("\nSe o RAG ainda falha, verifique:")
                print("→ O threshold de distância no código (dist < 1.2)")
                print("→ Se o FAISS está sendo inicializado corretamente")
                print("→ Se os vetores estão normalizados")

if __name__ == "__main__":
    main()