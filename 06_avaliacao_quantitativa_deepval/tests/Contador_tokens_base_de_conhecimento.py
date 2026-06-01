import json
import requests
from pathlib import Path
from core.paths import VETORIZATION_DATA

OLLAMA_URL = "http://localhost:11434"
MODEL_NAME = "bge-m3:latest"

def contar_tokens_ollama(texto):
    """Usa Ollama para estimar tokens via embedding"""
    try:
        # O Ollama retorna erro se o texto for muito longo, 
        # então usamos isso como indicador
        response = requests.post(
            f"{OLLAMA_URL}/api/embeddings",
            json={"model": MODEL_NAME, "prompt": texto[:8000]},  # Limita a 8000 chars
            timeout=10
        )
        
        if response.status_code == 200:
            # Estimativa: BGE-M3 tokeniza ~1.3 tokens por palavra
            return int(len(texto.split()) * 1.3)
        else:
            return len(texto.split())
    except:
        return len(texto.split())

def main():
    print("🔍 Procurando conversa com mais tokens...\n")
    
    # Carregar base
    json_path = VETORIZATION_DATA / 'base_conhecimento_multilingueV5.json'
    with open(json_path, 'r', encoding='utf-8') as f:
        base = json.load(f)
    
    print(f"📚 Total de documentos: {len(base)}\n")
    
    # Analisar cada documento
    max_tokens = 0
    documento_campeao = None
    
    for idx, doc in enumerate(base):
        # Extrair texto
        texto = doc.get('original_text', '')
        if not texto and 'metadata' in doc:
            meta = doc['metadata']
            texto = f"{meta.get('title', '')} {meta.get('model', '')} {meta.get('solution', '')}"
        
        if not texto:
            continue
        
        # Contar tokens via Ollama
        num_tokens = contar_tokens_ollama(texto)
        
        # Mostrar progresso
        if (idx + 1) % 500 == 0:
            print(f"   Processados {idx + 1}/{len(base)} documentos...")
        
        # Verificar se é o novo recorde
        if num_tokens > max_tokens:
            max_tokens = num_tokens
            documento_campeao = {
                'id': doc.get('id', 'N/A'),
                'indice': idx,
                'titulo': doc.get('metadata', {}).get('title', 'Sem título'),
                'modelo': doc.get('metadata', {}).get('model', 'N/A'),
                'data': doc.get('date_iso', 'N/A'),
                'tokens': num_tokens,
                'texto': texto[:500]  # Primeiros 500 chars
            }
            print(f"   🏆 Novo recorde! {num_tokens} tokens - {documento_campeao['titulo']}")
    
    # Resultado final
    print("\n" + "="*60)
    print("🏆 CONVERSA COM MAIOR QUANTIDADE DE TOKENS:")
    print("="*60)
    
    if documento_campeao:
        print(f"\n📌 Índice na base: {documento_campeao['indice']}")
        print(f"📌 ID do documento: {documento_campeao['id']}")
        print(f"📌 Título: {documento_campeao['titulo']}")
        print(f"📌 Modelo: {documento_campeao['modelo']}")
        print(f"📌 Data: {documento_campeao['data']}")
        print(f"📌 Tokens estimados: {documento_campeao['tokens']:,}")
        print(f"\n📝 Início do texto:")
        print("-"*60)
        print(documento_campeao['texto'])
        print("-"*60)
    else:
        print("❌ Nenhum documento encontrado!")
    
    print(f"\n✅ Análise concluída!")

if __name__ == "__main__":
    main()