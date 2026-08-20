#!/usr/bin/env python3
"""
Benchmark de tempo de resposta para modelos Ollama via custom_evaluatorV4.
Testa cada modelo com perguntas fixas, mede o tempo de geração, e recomenda timeouts.
"""

import asyncio
import time
import statistics
import sys
from typing import Dict, List, Optional

# Adiciona o caminho para importar custom_evaluatorV4
from core.paths import VALIDACAO_SCRIPT, AVALIACAO_SCRIPT
for path in [VALIDACAO_SCRIPT, AVALIACAO_SCRIPT]:
    if str(path) not in sys.path:
        sys.path.append(str(path))

from custom_evaluatorV4 import OllamaEvaluator

# Lista de modelos a testar (todos que aparecem no seu script principal)
MODELOS_A_TESTAR = [
    "phi3.5:latest",
    "qwen3:4b-instruct",
    "mistral:7b-instruct",
    "granite3.2:8b",
    "qwen3.5:9b",
    "phi3:14b"
]

# Perguntas de exemplo (5 perguntas típicas)
PERGUNTAS_EXEMPLO = [
    "Quais são as especificações técnicas do servidor PowerEdge R740?",
    "Qual a diferença entre DDR4 e DDR5?",
    "O que é o Intel Xeon Scalable?",
    "Explique o conceito de RAID 10.",
    "Quais são as opções de armazenamento para o Dell PowerStore?"
]

NUM_REPETICOES = 3  # Cada pergunta é repetida 3 vezes

async def test_modelo(modelo: str, perguntas: List[str], num_reps: int = 3) -> Dict[str, float]:
    """
    Testa um modelo com as perguntas fornecidas.
    Retorna um dicionário com estatísticas de tempo (em segundos).
    """
    evaluator = OllamaEvaluator(model_name=modelo, prompt_version="V1")
    tempos = []

    for pergunta in perguntas:
        for rep in range(num_reps):
            inicio = time.time()
            try:
                # Chamada assíncrona para gerar resposta (sem schema)
                resposta = await evaluator.a_generate(pergunta, schema=None)
                # Se quiser ver a resposta, descomente:
                # print(f"Resposta: {resposta[:50]}...")
            except Exception as e:
                print(f"⚠️ Erro no modelo {modelo} com pergunta '{pergunta[:30]}...': {e}")
                continue
            fim = time.time()
            tempo = fim - inicio
            tempos.append(tempo)
            print(f"{modelo:20} | '{pergunta[:25]}...' | tentativa {rep+1}: {tempo:.2f}s")

    if not tempos:
        return {'media': 0.0, 'desvio': 0.0, 'min': 0.0, 'max': 0.0, 'tempos': []}

    media = sum(tempos) / len(tempos)
    desvio = statistics.stdev(tempos) if len(tempos) > 1 else 0.0
    return {
        'media': media,
        'desvio': desvio,
        'min': min(tempos),
        'max': max(tempos),
        'tempos': tempos
    }

async def main():
    resultados: Dict[str, Optional[Dict]] = {}
    print("🚀 Iniciando benchmark de tempo...\n")
    for modelo in MODELOS_A_TESTAR:
        print(f"\n🔄 Testando modelo: {modelo}")
        try:
            stats = await test_modelo(modelo, PERGUNTAS_EXEMPLO, NUM_REPETICOES)
            resultados[modelo] = stats
        except Exception as e:
            print(f"❌ Falha ao testar {modelo}: {e}")
            resultados[modelo] = None

    # Relatório
    print("\n" + "=" * 100)
    print("📊 RELATÓRIO DE BENCHMARK DE TEMPO")
    print("=" * 100)
    print(f"{'Modelo':<25} | {'Média (s)':>10} | {'Desvio':>10} | {'Mínimo':>10} | {'Máximo':>10} | {'Timeout sugerido':>15}")
    print("-" * 100)

    timeouts = {}
    for modelo, stats in resultados.items():
        if stats is None or not stats['tempos']:
            print(f"{modelo:<25} | {'FALHA':^10}")
            timeouts[modelo] = 600  # fallback
            continue
        media = stats['media']
        desvio = stats['desvio']
        minimo = stats['min']
        maximo = stats['max']
        # Sugestão: média + 5*desvio + 60s de folga, limitado entre 120s e 3600s
        sugerido = media + 5 * desvio + 60
        sugerido = max(120, min(3600, sugerido))
        timeouts[modelo] = int(sugerido)
        print(f"{modelo:<25} | {media:>10.2f} | {desvio:>10.2f} | {minimo:>10.2f} | {maximo:>10.2f} | {sugerido:>15.0f}s")

    print("\n✅ Recomendação de timeouts (em segundos) para usar no script principal:")
    print("TIMEOUTS_POR_MODELO = {")
    for modelo, to in timeouts.items():
        print(f'    "{modelo}": {to},')
    print("}")

    # Salva em arquivo para referência
    with open("06_avaliacao_quantitativa_deepval/tests/timeouts_recomendados.json", "w", encoding="utf-8") as f:
        import json
        json.dump(timeouts, f, indent=2, ensure_ascii=False)

    print("\n💾 Timeouts salvos em 'timeouts_recomendados.json'.")

if __name__ == "__main__":
    asyncio.run(main())