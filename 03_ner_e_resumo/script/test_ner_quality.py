# test_ner_quality_fixed.py
import asyncio
import json
import random
from pathlib import Path
from openai import AsyncOpenAI
from datetime import datetime
import re

from core.paths import NER_DATA, PREPROCESSAMENTO_DATA

# =========================================================
# CONFIGURAÇÃO SIMPLIFICADA PARA TESTE
# =========================================================
MODELOS_TESTE = [
    "granite3.2:8b",
    "llama3.1:8b"
]

NUM_POSTS_TESTE = 10  # Número de posts para testar por modelo

# Diretórios
DIR_ENTRADA = Path(PREPROCESSAMENTO_DATA/"Dados_Limpos_IniciaisV10")
DIR_RESULTADOS = Path(NER_DATA / "test_results")
DIR_RESULTADOS.mkdir(exist_ok=True)

# Cliente Ollama
client = AsyncOpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama",
    timeout=120.0
)

# =========================================================
# PROMPT (mesmo dos scripts originais)
# =========================================================
PROMPT_EXTRACTION = """<|begin_of_text|><|start_header_id|>system<|end_header_id|>

Extract technical information from laptop forum posts. Return ONLY valid JSON. Extract REAL information from the text, NOT placeholders.<|eot_id|><|start_header_id|>user<|end_header_id|>

Device: {modelo_nome}
Date: {post_date}
Title: {titulo}
Content: {corpo}
Comments: {comentarios}

Analyze the conversation and extract:
1. summary: Start with device name, then describe the actual problem, symptoms, and affected components
2. intent: Choose from "Technical Specifications", "Troubleshooting", "Upgrade Advice", "Compatibility", "Warranty", "Performance"
3. detected_fault: Describe the specific technical fault found, or "None" if no fault
4. suggested_solution: Array of actionable steps (max 4). Extract from comments if present.
5. technical_severity: "Low", "Medium", "High", or "Critical"
6. discussion_timeline: Format as "{post_date} to {post_date}"

CRITICAL: Extract REAL information from the conversation above. Do NOT use placeholders like "PROBLEM - SYMPTOMS" or "fault or None". Use the actual text.

Return ONLY valid JSON. Example format:
{{"summary":"DeviceName, actual problem described from text","intent":"Troubleshooting","detected_fault":"specific issue or None","suggested_solution":["step1","step2"],"technical_severity":"Medium","discussion_timeline":"2024-01-01 to 2024-01-01"}}
<|eot_id|><|start_header_id|>assistant<|end_header_id|>
"""

# =========================================================
# FUNÇÕES AUXILIARES
# =========================================================
def parse_json_response(raw_response: str) -> dict:
    """Parsing robusto do JSON retornado"""
    # Remove markdown
    raw_response = re.sub(r'```json\s*', '', raw_response)
    raw_response = re.sub(r'```\s*', '', raw_response)
    
    # Encontra JSON
    start = raw_response.find('{')
    if start == -1:
        return {"error": "No JSON found", "raw": raw_response[:200]}
    
    # Balanceia chaves
    json_str = raw_response[start:]
    brace_count = 0
    end_pos = 0
    for i, char in enumerate(json_str):
        if char == '{':
            brace_count += 1
        elif char == '}':
            brace_count -= 1
            if brace_count == 0:
                end_pos = i + 1
                break
    
    if end_pos > 0:
        json_str = json_str[:end_pos]
    
    # Limpeza básica
    json_str = re.sub(r',\s*}', '}', json_str)
    json_str = re.sub(r',\s*\]', ']', json_str)
    
    try:
        return json.loads(json_str)
    except:
        return {"error": "JSON parse failed", "raw": json_str[:200]}

def avaliar_qualidade_resposta(resposta: dict) -> dict:
    """Avaliação básica da qualidade da resposta"""
    if "error" in resposta:
        return {"score": 0, "issues": [f"Error: {resposta['error']}"]}
    
    issues = []
    score = 10  # Começa com 10 pontos
    
    # Verifica campos obrigatórios
    required_fields = ['summary', 'intent', 'detected_fault', 'suggested_solution', 'technical_severity']
    for field in required_fields:
        if field not in resposta:
            issues.append(f"Missing field: {field}")
            score -= 2
    
    # Verifica placeholders
    summary = resposta.get('summary', '')
    if any(word in summary.upper() for word in ['PROBLEM', 'SYMPTOMS', '[PROBLEM', 'DESCRIBE']):
        issues.append("Placeholder found in summary")
        score -= 3
    
    # Verifica tamanho do summary
    if len(summary) < 20:
        issues.append("Summary too short (< 20 chars)")
        score -= 2
    elif len(summary) > 500:
        issues.append("Summary too long (> 500 chars)")
        score -= 1
    
    # Verifica soluções
    solutions = resposta.get('suggested_solution', [])
    if not solutions:
        issues.append("No solutions provided")
        score -= 2
    elif len(solutions) > 0:
        # Verifica placeholders em soluções
        bad_solutions = [s for s in solutions if any(p in s.lower() for p in ['step', 'action', 'fix the', 'describe'])]
        if bad_solutions:
            issues.append(f"Placeholder solutions: {bad_solutions[:2]}")
            score -= 2
    
    # Verifica severidade válida
    valid_severities = ['Low', 'Medium', 'High', 'Critical']
    if resposta.get('technical_severity') not in valid_severities:
        issues.append(f"Invalid severity: {resposta.get('technical_severity')}")
        score -= 1
    
    return {"score": max(0, score), "issues": issues}

def salvar_resultado_teste(modelo: str, post_info: dict, resposta: dict, avaliacao: dict):
    """Salva resultado individual do teste"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # Converte o Path para string para evitar erro de serialização
    filename = str(DIR_RESULTADOS / f"test_{modelo.replace(':', '_')}_{post_info['post_id']}_{timestamp}.json")
    
    resultado = {
        "modelo": modelo,
        "timestamp": timestamp,
        "post_info": post_info,
        "resposta_ia": resposta,
        "avaliacao": avaliacao
    }
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(resultado, f, indent=2, ensure_ascii=False)
    
    return filename

# =========================================================
# FUNÇÃO PRINCIPAL DE TESTE
# =========================================================
async def testar_modelo(modelo_nome: str, post: dict, post_id: str, modelo_hardware: str):
    """Testa um modelo específico em um post"""
    
    # Prepara conteúdo
    titulo = post.get('titulo', '')
    corpo = post.get('conteudo_post', post.get('selftext', ''))
    comentarios = " ".join([c.get('conteudo', '') for c in post.get('comentarios', [])])
    
    post_date = post.get('data_post', '2024-01-01')
    if isinstance(post_date, (int, float)):
        post_date = datetime.fromtimestamp(float(post_date)).strftime('%Y-%m-%d')
    
    prompt = PROMPT_EXTRACTION.format(
        modelo_nome=modelo_hardware[:100],
        post_date=post_date,
        titulo=titulo[:500],
        corpo=corpo[:2000] if corpo else "(no content)",
        comentarios=comentarios[:2000] if comentarios else "(no comments)"
    )
    
    print(f"\n  🔄 Enviando para {modelo_nome}...")
    
    try:
        response = await client.chat.completions.create(
            model=modelo_nome,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=2048,
            extra_query={
                "num_ctx": 8192,
                "mirostat": 1,
                "mirostat_tau": 5.0
            }
        )
        
        raw_content = response.choices[0].message.content
        parsed = parse_json_response(raw_content)
        
        return parsed, raw_content
        
    except Exception as e:
        return {"error": str(e)}, f"Exception: {str(e)}"

async def main():
    """Função principal de teste"""
    
    print("="*80)
    print("🧪 TESTE DE QUALIDADE - Comparação de Modelos")
    print("="*80)
    
    # Carrega arquivos de entrada
    arquivos = list(DIR_ENTRADA.glob("*.json"))
    
    if not arquivos:
        print(f"❌ Nenhum arquivo encontrado em {DIR_ENTRADA}")
        print("Verifique o caminho ou ajuste DIR_ENTRADA")
        return
    
    print(f"\n📂 Encontrados {len(arquivos)} arquivos de dados")
    
    # Seleciona alguns posts aleatórios
    all_posts = []
    for arq in arquivos[:5]:  # Lê no máximo 5 arquivos para teste
        try:
            with open(arq, 'r', encoding='utf-8') as f:
                data = json.load(f)
                modelo_nome = data.get('modelo_original', 'Unknown')
                for post in data.get('posts', [])[:NUM_POSTS_TESTE]:
                    all_posts.append({
                        'post': post,
                        'modelo_hardware': modelo_nome,
                        'arquivo': arq.name,
                        'post_id': str(post.get('id', 'unknown'))  # Garante string
                    })
        except Exception as e:
            print(f"⚠️ Erro ao ler {arq.name}: {e}")
    
    if not all_posts:
        print("❌ Nenhum post encontrado")
        return
    
    # Limita número de posts para teste
    test_posts = random.sample(all_posts, min(NUM_POSTS_TESTE, len(all_posts)))
    
    print(f"\n🎯 Testando {len(test_posts)} posts x {len(MODELOS_TESTE)} modelos = {len(test_posts) * len(MODELOS_TESTE)} combinações")
    print("\n" + "="*80)
    
    resultados = []
    
    # Para cada post, testa todos os modelos
    for idx, post_info in enumerate(test_posts, 1):
        print(f"\n📝 POST {idx}/{len(test_posts)}")
        print(f"   Modelo Hardware: {post_info['modelo_hardware']}")
        print(f"   Arquivo: {post_info['arquivo']}")
        print(f"   Post ID: {post_info['post_id']}")
        
        titulo = post_info['post'].get('titulo', 'No title')[:100]
        print(f"   Título: {titulo}...")
        
        for modelo in MODELOS_TESTE:
            resposta, raw = await testar_modelo(
                modelo, 
                post_info['post'], 
                post_info['post_id'],
                post_info['modelo_hardware']
            )
            
            avaliacao = avaliar_qualidade_resposta(resposta)
            
            # Exibe resultado resumido
            score = avaliacao['score']
            score_emoji = "✅" if score >= 7 else "⚠️" if score >= 5 else "❌"
            print(f"\n  {score_emoji} {modelo}: Score {score}/10")
            
            if avaliacao['issues']:
                print(f"     Problemas: {', '.join(avaliacao['issues'][:3])}")
            
            # Mostra o summary gerado
            if 'summary' in resposta and not resposta.get('error'):
                summary = resposta['summary'][:120]
                print(f"     Summary: {summary}...")
            
            # Salva resultado - converte Path para string
            saved_file = salvar_resultado_teste(
                modelo, 
                {
                    'post_id': post_info['post_id'],
                    'titulo': titulo,
                    'modelo_hardware': post_info['modelo_hardware']
                },
                resposta,
                avaliacao
            )
            
            resultados.append({
                'modelo': modelo,
                'post_id': post_info['post_id'],
                'score': score,
                'avaliacao': avaliacao,
                'arquivo': saved_file  # Agora é string, não Path
            })
            
            await asyncio.sleep(1)  # Pequena pausa entre requisições
        
        print("\n" + "-"*40)
    
    # Gera relatório final
    print("\n" + "="*80)
    print("📊 RELATÓRIO FINAL")
    print("="*80)
    
    # Calcula médias por modelo
    for modelo in MODELOS_TESTE:
        scores = [r['score'] for r in resultados if r['modelo'] == modelo]
        if scores:
            media = sum(scores) / len(scores)
            print(f"\n{modelo}:")
            print(f"  Score médio: {media:.2f}/10")
            print(f"  Total testes: {len(scores)}")
            print(f"  Acima de 7: {len([s for s in scores if s >= 7])}")
            print(f"  Abaixo de 5: {len([s for s in scores if s < 5])}")
    
    # Salva relatório consolidado - converte Path para string
    relatorio_path = str(DIR_RESULTADOS / f"relatorio_testes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(relatorio_path, 'w', encoding='utf-8') as f:
        json.dump({
            'config': {
                'modelos': MODELOS_TESTE,
                'num_posts': len(test_posts),
                'timestamp': datetime.now().isoformat()
            },
            'resultados': resultados
        }, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 Resultados salvos em: {DIR_RESULTADOS}")
    print(f"📄 Relatório consolidado: {relatorio_path}")
    print("\n✨ Teste concluído!")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠️ Teste interrompido pelo usuário")
    except Exception as e:
        print(f"\n❌ Erro: {e}")