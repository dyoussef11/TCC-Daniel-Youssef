# test_prompt_variations_fixed_final.py
import asyncio
import json
import random
from pathlib import Path
from openai import AsyncOpenAI
from datetime import datetime
import re
from typing import Dict, Any

# --- CONFIGURAÇÃO ---
try:
    from core.paths import PREPROCESSAMENTO_DATA
    DIR_ENTRADA = PREPROCESSAMENTO_DATA / 'Dados_Limpos_IniciaisV10'
except ImportError:
    DIR_ENTRADA = Path("./data/Dados_Limpos_IniciaisV10")

DIR_RESULTADOS = Path("./test_prompt_results")
DIR_RESULTADOS.mkdir(exist_ok=True)

# --- PARÂMETROS DE TESTE ---
NUM_POSTS_TESTE = 5
MODELO = "llama3.1:8b"
TEMPERATURE = 0.2

# Cliente Ollama
client = AsyncOpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama",
    timeout=120.0
)

# =========================================================
# PROMPTS SEGUINDO FORMATO OFICIAL LLAMA 3.1
# =========================================================

def build_llama_prompt(system_prompt: str, user_prompt: str) -> str:
    """Constrói prompt no formato oficial Llama 3.1"""
    return f"""<|begin_of_text|><|start_header_id|>system<|end_header_id|>

{system_prompt}<|eot_id|><|start_header_id|>user<|end_header_id|>

{user_prompt}<|eot_id|><|start_header_id|>assistant<|end_header_id|>

"""

# =========================================================
# SISTEM PROMPTS
# =========================================================

SYSTEM_BASE = """You are a technical laptop support expert. Extract REAL technical information from forum conversations.

CRITICAL RULES:
- Return ONLY valid JSON
- Extract REAL information from the text, NOT placeholders
- Be specific with model numbers, temperatures, error codes
- If information is not present, use null or empty array

RESPONSE MUST BE ONLY THE JSON OBJECT. No extra text before or after."""

# =========================================================
# VARIAÇÃO 1: CONCISO
# =========================================================
USER_CONCISO_TEMPLATE = """Analyze this laptop forum post and extract key technical info.

Device: {modelo}
Title: {titulo}
Problem Description: {corpo}
Community Responses: {comentarios}

Return JSON:
{{
"summary": "one sentence describing the core issue",
"fault": "specific technical fault in 3-5 words",
"solution": "the fix that worked (or 'not found')",
"severity": "Low/Medium/High/Critical"
}}"""

# =========================================================
# VARIAÇÃO 2: PADRÃO
# =========================================================
USER_PADRAO_TEMPLATE = """Extract structured technical information from this laptop discussion.

Device: {modelo}
Title: {titulo}
Original Post: {corpo}
Comments: {comentarios}

Return JSON:
{{
"summary": "2-3 sentences describing problem and symptoms",
"detected_fault": "specific technical fault identified",
"suggested_solution": ["step 1", "step 2", "step 3"],
"technical_severity": "Low/Medium/High/Critical",
"affected_components": ["component1", "component2"]
}}"""

# =========================================================
# VARIAÇÃO 3: DETALHADO
# =========================================================
USER_DETALHADO_TEMPLATE = """Extract DETAILED technical information from this laptop discussion.

Device: {modelo}
Title: {titulo}
Original Post: {corpo}
Comments: {comentarios}

Return JSON with these exact fields:
{{
"summary": "3-4 sentences covering initial problem, symptoms, attempted solutions, final resolution",
"technical_context": {{"cpu": null, "gpu": null, "os": null}},
"root_cause": "technical explanation of what caused the issue",
"diagnostic_steps": ["step1", "step2", "step3"],
"resolution_path": "what ultimately worked",
"technical_severity": "Low/Medium/High/Critical",
"keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5"]
}}"""

# =========================================================
# VARIAÇÃO 4: RICO METADADOS
# =========================================================
USER_RICO_TEMPLATE = """Extract COMPREHENSIVE technical intelligence for RAG database.

Device: {modelo}
Title: {titulo}
Original Post: {corpo}
Comments: {comentarios}

Return JSON with these exact fields:
{{
"summary_short": "one sentence summary",
"summary_detailed": "4-6 sentence technical narrative",
"technical_severity": "Critical/High/Medium/Low",
"hardware": {{"cpu": null, "gpu": null, "ram": null, "storage": null}},
"software": {{"os": null, "drivers": null, "bios": null}},
"symptoms": ["symptom1", "symptom2"],
"root_cause": "technical explanation",
"error_codes": ["code1", "code2"],
"attempted_solutions": ["attempt1", "attempt2"],
"successful_solution": "what worked or null",
"technical_keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5", "keyword6", "keyword7", "keyword8", "keyword9", "keyword10"],
"component_tags": ["tag1", "tag2"],
"resolution_status": "resolved/partial/unresolved",
"confidence_score": 0.0
}}"""

# =========================================================
# FUNÇÕES AUXILIARES
# =========================================================

def extrair_conteudo_post(post: dict) -> tuple:
    """Extrai o melhor conteúdo disponível do post"""
    # Tenta diferentes campos para conteúdo
    corpo = post.get('conteudo_post', '')
    if not corpo:
        corpo = post.get('selftext', '')
    if not corpo:
        corpo = post.get('content', '')
    if not corpo:
        corpo = post.get('description', '')
    
    # Se ainda não tem conteúdo, tenta construir a partir do título
    titulo = post.get('titulo', '')
    
    return corpo, titulo

def extrair_comentarios(post: dict, max_comments: int = 10) -> str:
    """Extrai comentários de forma robusta"""
    comentarios_lista = post.get('comentarios', [])
    if not comentarios_lista:
        # Tenta outros nomes de campo
        comentarios_lista = post.get('comments', [])
    
    if not comentarios_lista:
        return "No comments"
    
    comentarios_texto = []
    for i, comment in enumerate(comentarios_lista[:max_comments]):
        if isinstance(comment, dict):
            conteudo = comment.get('conteudo', comment.get('content', comment.get('text', '')))
            if conteudo:
                comentarios_texto.append(f"Comment {i+1}: {conteudo[:300]}")
        elif isinstance(comment, str):
            comentarios_texto.append(f"Comment {i+1}: {comment[:300]}")
    
    return "\n".join(comentarios_texto) if comentarios_texto else "No comments"

def post_tem_conteudo_valido(post: dict) -> bool:
    """Verifica se o post tem conteúdo útil"""
    corpo, titulo = extrair_conteudo_post(post)
    comentarios = extrair_comentarios(post, max_comments=3)
    
    # Verifica se há conteúdo mínimo
    has_content = len(corpo) > 50 or len(titulo) > 20
    has_comments = comentarios != "No comments"
    
    return has_content or has_comments

def avaliar_para_vetorizacao(extracao: dict, prompt_type: str) -> dict:
    """Avalia quão rico é o conteúdo para vetorização com BGE-M3"""
    
    scores = {}
    text = json.dumps(extracao, ensure_ascii=False)
    
    # 1. Densidade de informação
    scores['info_density'] = min(1.0, len(text) / 2000)
    
    # 2. Riqueza de metadados
    non_null = sum(1 for v in extracao.values() if v and v != [] and v != {} and v is not None)
    total_fields = len(extracao)
    scores['metadata_richness'] = non_null / total_fields if total_fields > 0 else 0
    
    # 3. Especificidade técnica
    text_lower = text.lower()
    tech_patterns = [
        r'\d+°c', r'\d+ghz', r'ddr\d', r'nvme', r'bios',
        r'driver', r'error', r'thermal', r'voltage', r'throttling'
    ]
    tech_matches = sum(1 for pattern in tech_patterns if re.search(pattern, text_lower))
    scores['technical_specificity'] = min(1.0, tech_matches / 5)
    
    # 4. Valor para RAG
    has_solutions = False
    for key in ['suggested_solution', 'resolution_path', 'successful_solution', 'attempted_solutions']:
        if key in extracao and extracao[key]:
            if isinstance(extracao[key], list) and len(extracao[key]) > 0:
                has_solutions = True
                break
            elif isinstance(extracao[key], str) and len(extracao[key]) > 10:
                has_solutions = True
                break
    scores['rag_value'] = 1.0 if has_solutions else 0.5
    
    # 5. Keywords
    keyword_fields = ['keywords', 'technical_keywords', 'component_tags']
    keyword_count = 0
    for field in keyword_fields:
        if field in extracao and isinstance(extracao[field], list):
            keyword_count += len(extracao[field])
    scores['keyword_richness'] = min(1.0, keyword_count / 10)
    
    # 6. Tempo de resolução
    has_status = 'resolution_status' in extracao and extracao['resolution_status']
    scores['temporal_context'] = 1.0 if has_status else 0.3
    
    # Score final ponderado
    weights = {
        'metadata_richness': 0.30,
        'technical_specificity': 0.25,
        'rag_value': 0.20,
        'keyword_richness': 0.15,
        'temporal_context': 0.10
    }
    
    final_score = sum(scores.get(k, 0) * weights.get(k, 0) for k in weights)
    
    return {
        'final_score': final_score,
        'scores': scores,
        'text_length': len(text),
        'non_null_fields': non_null,
        'total_fields': total_fields
    }

def extrair_tamanho_post(post: dict) -> dict:
    """Extrai tamanho do post para referência"""
    corpo, titulo = extrair_conteudo_post(post)
    comentarios = post.get('comentarios', [])
    
    return {
        'corpo_len': len(corpo),
        'titulo_len': len(titulo),
        'num_comentarios': len(comentarios),
        'total_comentarios_len': sum(len(c.get('conteudo', c.get('content', ''))) for c in comentarios if isinstance(c, dict))
    }

# =========================================================
# FUNÇÃO PRINCIPAL DE TESTE
# =========================================================

async def testar_prompt(post: dict, modelo_hardware: str, post_id: str,
                        system_prompt: str, user_template: str, 
                        prompt_name: str, stats: dict):
    """Testa um prompt específico usando formato oficial Llama 3.1"""
    
    titulo = post.get('titulo', '')[:250]
    corpo, _ = extrair_conteudo_post(post)
    corpo = corpo[:2000] if corpo else "No detailed content available"
    comentarios = extrair_comentarios(post, max_comments=8)[:1500]
    
    # Preenche o template do usuário
    try:
        user_prompt = user_template.format(
            modelo=modelo_hardware[:80] if modelo_hardware else "Unknown",
            titulo=titulo if titulo else "No title provided",
            corpo=corpo,
            comentarios=comentarios
        )
    except KeyError as e:
        print(f"    ❌ Erro no template: {e}")
        stats[f"{prompt_name}_fail"] += 1
        return None, None
    except Exception as e:
        print(f"    ❌ Erro ao formatar: {e}")
        stats[f"{prompt_name}_fail"] += 1
        return None, None
    
    # Constrói prompt completo no formato Llama 3.1
    full_prompt = build_llama_prompt(system_prompt, user_prompt)
    
    try:
        response = await client.chat.completions.create(
            model=MODELO,
            messages=[{"role": "user", "content": full_prompt}],
            temperature=TEMPERATURE,
            max_tokens=2500,
            extra_query={
                "num_ctx": 8192,
                "temperature": TEMPERATURE,
                "stop": ["<|eot_id|>", "<|end_of_text|>"]
            }
        )
        
        raw_content = response.choices[0].message.content.strip()
        
        # Tenta extrair JSON
        json_match = re.search(r'\{[\s\S]*\}', raw_content)
        if json_match:
            try:
                resultado = json.loads(json_match.group())
                stats[f"{prompt_name}_success"] += 1
                return resultado, raw_content[:300]
            except json.JSONDecodeError as e:
                print(f"    ⚠️ JSON parse error: {str(e)[:50]}")
                stats[f"{prompt_name}_fail"] += 1
                return {"error": "JSON parse failed"}, raw_content[:300]
        else:
            stats[f"{prompt_name}_fail"] += 1
            return {"error": "No JSON found"}, raw_content[:300]
            
    except Exception as e:
        print(f"    ❌ API error: {str(e)[:80]}")
        stats[f"{prompt_name}_fail"] += 1
        return None, None

async def main():
    print("="*80)
    print("🧪 TESTE DE PROMPTS - FORMATO OFICIAL LLAMA 3.1")
    print("="*80)
    
    # Carrega posts
    arquivos = list(DIR_ENTRADA.glob("*.json"))
    print(f"\n📁 Encontrados {len(arquivos)} arquivos")
    
    all_posts = []
    
    for arq in arquivos[:20]:  # Limita para teste
        try:
            with open(arq, 'r', encoding='utf-8') as f:
                data = json.load(f)
                modelo = data.get('modelo_original', 'Unknown')
                
                for post in data.get('posts', []):
                    if post_tem_conteudo_valido(post):
                        all_posts.append({
                            'post': post,
                            'modelo': modelo,
                            'post_id': str(post.get('id', 'unknown')),
                            'arquivo': arq.name
                        })
        except Exception as e:
            print(f"⚠️ Erro ao ler {arq.name}: {e}")
    
    print(f"📊 Posts com conteúdo válido: {len(all_posts)}")
    
    if not all_posts:
        print("\n❌ Nenhum post com conteúdo encontrado!")
        print("   Verificando estrutura dos dados...")
        
        # Debug: mostra estrutura do primeiro arquivo
        for arq in list(DIR_ENTRADA.glob("*.json"))[:1]:
            try:
                with open(arq, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    print(f"\n   Exemplo de estrutura em {arq.name}:")
                    print(f"   Chaves: {list(data.keys())}")
                    if 'posts' in data and data['posts']:
                        primeiro_post = data['posts'][0]
                        print(f"   Campos do post: {list(primeiro_post.keys())}")
                        corpo, titulo = extrair_conteudo_post(primeiro_post)
                        print(f"   Título: '{titulo[:50]}'")
                        print(f"   Corpo: '{corpo[:50]}' (tamanho: {len(corpo)})")
            except:
                pass
        return
    
    test_posts = random.sample(all_posts, min(NUM_POSTS_TESTE, len(all_posts)))
    
    # Configura prompts
    prompts_config = {
        'conciso': {
            'system': SYSTEM_BASE,
            'user': USER_CONCISO_TEMPLATE
        },
        'padrao': {
            'system': SYSTEM_BASE,
            'user': USER_PADRAO_TEMPLATE
        },
        'detalhado': {
            'system': SYSTEM_BASE,
            'user': USER_DETALHADO_TEMPLATE
        },
        'rico_metadados': {
            'system': SYSTEM_BASE,
            'user': USER_RICO_TEMPLATE
        }
    }
    
    stats = {f"{name}_success": 0 for name in prompts_config}
    stats.update({f"{name}_fail": 0 for name in prompts_config})
    
    resultados = []
    
    print(f"\n🎯 Testando {len(test_posts)} posts × 4 prompts\n")
    
    for idx, post_info in enumerate(test_posts, 1):
        print(f"\n{'='*80}")
        print(f"📝 POST {idx}/{len(test_posts)}")
        print(f"   Modelo: {post_info['modelo'][:50]}")
        print(f"   Título: {post_info['post'].get('titulo', '')[:70]}")
        
        corpo, _ = extrair_conteudo_post(post_info['post'])
        print(f"   Tamanho: corpo={len(corpo)} chars, comentários={len(post_info['post'].get('comentarios', []))}")
        print(f"{'='*80}")
        
        post_result = {
            'post_id': post_info['post_id'],
            'modelo': post_info['modelo'],
            'titulo': post_info['post'].get('titulo', ''),
            'tamanho': extrair_tamanho_post(post_info['post']),
            'prompts': {}
        }
        
        for prompt_name, config in prompts_config.items():
            print(f"\n  🧪 Testando {prompt_name.upper()}...")
            
            resultado, raw_preview = await testar_prompt(
                post_info['post'],
                post_info['modelo'],
                post_info['post_id'],
                config['system'],
                config['user'],
                prompt_name,
                stats
            )
            
            if resultado and 'error' not in resultado:
                avaliacao = avaliar_para_vetorizacao(resultado, prompt_name)
                
                print(f"    ✅ Score: {avaliacao['final_score']:.3f}")
                print(f"       • Metadata: {avaliacao['scores'].get('metadata_richness', 0):.2f}")
                print(f"       • Technical: {avaliacao['scores'].get('technical_specificity', 0):.2f}")
                print(f"       • RAG value: {avaliacao['scores'].get('rag_value', 0):.2f}")
                print(f"       • Keywords: {avaliacao['scores'].get('keyword_richness', 0):.2f}")
                
                post_result['prompts'][prompt_name] = {
                    'resultado': resultado,
                    'avaliacao': avaliacao,
                    'raw_preview': raw_preview
                }
            else:
                error_msg = resultado.get('error', 'No response') if resultado else 'No response'
                print(f"    ❌ Falhou: {error_msg}")
                post_result['prompts'][prompt_name] = {
                    'error': error_msg,
                    'raw_preview': raw_preview
                }
            
            await asyncio.sleep(0.5)
        
        resultados.append(post_result)
        
        # Salva parcial
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        partial_file = DIR_RESULTADOS / f"partial_results_{timestamp}.json"
        with open(partial_file, 'w', encoding='utf-8') as f:
            json.dump(resultados, f, indent=2, ensure_ascii=False)
    
    # Gera relatório
    print("\n" + "="*80)
    print("📊 RELATÓRIO COMPARATIVO")
    print("="*80)
    
    comparativo = {}
    for prompt_name in prompts_config:
        scores = []
        for r in resultados:
            if prompt_name in r['prompts'] and 'avaliacao' in r['prompts'][prompt_name]:
                scores.append(r['prompts'][prompt_name]['avaliacao']['final_score'])
        
        if scores:
            success = stats[f"{prompt_name}_success"]
            total = success + stats[f"{prompt_name}_fail"]
            comparativo[prompt_name] = {
                'media_score': sum(scores) / len(scores),
                'min_score': min(scores),
                'max_score': max(scores),
                'success_rate': success / total if total > 0 else 0,
                'num_analises': len(scores)
            }
    
    if comparativo:
        for prompt_name, metrics in sorted(comparativo.items(), key=lambda x: x[1]['media_score'], reverse=True):
            print(f"\n📌 {prompt_name.upper()}:")
            print(f"   Score médio: {metrics['media_score']:.3f}")
            print(f"   Variação: {metrics['min_score']:.3f} - {metrics['max_score']:.3f}")
            print(f"   Taxa de sucesso: {metrics['success_rate']:.1%}")
            print(f"   Análises: {metrics['num_analises']}")
        
        # Recomendação
        print("\n" + "="*80)
        print("🎯 RECOMENDAÇÃO PARA VETORIZAÇÃO COM BGE-M3")
        print("="*80)
        
        best_prompt = max(comparativo.items(), key=lambda x: x[1]['media_score'])
        print(f"\n✅ Melhor prompt: {best_prompt[0].upper()}")
        print(f"   Score médio: {best_prompt[1]['media_score']:.3f}")
        print(f"   Taxa de sucesso: {best_prompt[1]['success_rate']:.1%}")
    else:
        print("\n❌ Nenhum teste bem-sucedido para gerar recomendação")
    
    # Salva relatório final
    relatorio_final = {
        'timestamp': datetime.now().isoformat(),
        'config': {
            'modelo': MODELO,
            'num_posts': len(test_posts),
            'temperature': TEMPERATURE,
            'prompt_format': 'Llama 3.1 Official'
        },
        'comparativo': comparativo,
        'resultados_detalhados': resultados,
        'stats': stats
    }
    
    final_file = DIR_RESULTADOS / f"relatorio_final_llama31_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(final_file, 'w', encoding='utf-8') as f:
        json.dump(relatorio_final, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 Relatório salvo: {final_file}")
    print(f"📁 Resultados em: {DIR_RESULTADOS}")
    print("\n✨ Teste concluído!")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠️ Teste interrompido")