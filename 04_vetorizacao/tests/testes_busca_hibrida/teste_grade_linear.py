#!/usr/bin/env python3
"""
teste_grade_linear.py - Testa grade fina de pesos para fusão linear.
Gera tabela de Precisão@k e MRR para diferentes combinações.
Uso: python teste_grade_linear.py --ground_truth gt.json [--step 0.1] [--k 5]
"""

import json
import subprocess
import tempfile
import sys
from pathlib import Path
import argparse
from collections import defaultdict

from core.paths import VETORIZATION_SCRIPT

SCRIPT_BUSCAR = VETORIZATION_SCRIPT / "buscarHibridaV2.py"
K = 5
STEP = 0.1

def carregar_ground_truth(arquivo_gt):
    with open(arquivo_gt, 'r', encoding='utf-8') as f:
        return json.load(f)

def executar_busca(consulta, peso_denso, peso_esparso, k):
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as tmp:
        tmp_path = tmp.name

    args = [
        sys.executable, str(SCRIPT_BUSCAR),
        '--consulta', consulta,
        '--peso_denso', str(peso_denso),
        '--peso_esparso', str(peso_esparso),
        '--k', str(k),
        '--saida', tmp_path,
        '--quiet',
        '--fusion', 'linear'
    ]
    try:
        subprocess.run(args, check=True, capture_output=True, text=True, encoding='utf-8')
        with open(tmp_path, 'r', encoding='utf-8') as f:
            resultados = json.load(f)
        return [r['id'] for r in resultados]
    except subprocess.CalledProcessError as e:
        print(f"❌ Erro ao executar busca para consulta: {consulta[:50]}...", file=sys.stderr)
        print(f"   Código de saída: {e.returncode}", file=sys.stderr)
        print(f"   Saída de erro: {e.stderr}", file=sys.stderr)
        raise
    finally:
        Path(tmp_path).unlink(missing_ok=True)

def calcular_metricas(resultados_por_consulta, ground_truth, k):
    metricas = defaultdict(list)
    for item in ground_truth:
        consulta = item['consulta']
        relevantes = set(item['relevantes'])
        ids_obtidos = resultados_por_consulta.get(consulta, [])
        
        k_efetivo = min(k, len(ids_obtidos))
        if k_efetivo > 0:
            acertos = sum(1 for id_ in ids_obtidos[:k_efetivo] if id_ in relevantes)
            precisao = acertos / k_efetivo
        else:
            precisao = 0.0
        metricas['precisao@k'].append(precisao)
        
        posicao = None
        for i, id_ in enumerate(ids_obtidos, 1):
            if id_ in relevantes:
                posicao = i
                break
        if posicao is not None:
            mrr = 1.0 / posicao
        else:
            mrr = 0.0
        metricas['mrr'].append(mrr)
    
    resultados = {}
    for metrica, valores in metricas.items():
        resultados[metrica] = sum(valores) / len(valores) if valores else 0.0
    return resultados

def main():
    parser = argparse.ArgumentParser(description='Testa grade fina de pesos para fusão linear')
    parser.add_argument('--ground_truth', required=True, help='Arquivo JSON com ground truth')
    parser.add_argument('--step', type=float, default=STEP, help='Passo para variação dos pesos (ex: 0.1)')
    parser.add_argument('--k', type=int, default=K, help='Número de resultados por busca')
    args = parser.parse_args()
    
    k = args.k
    step = args.step
    ground_truth = carregar_ground_truth(args.ground_truth)
    
    # Gerar combinações: denso de 1.0 a 0.0 com passo step
    combinacoes = []
    denso = 1.0
    while denso >= 0:
        esparso = 1.0 - denso
        combinacoes.append((round(denso, 2), round(esparso, 2)))
        denso -= step
    
    print(f"🔍 Testando {len(combinacoes)} combinações de pesos (step={step})")
    print("   (fusão linear)\n")
    print(" Peso Dens | Peso Esp | Precisão@k |   MRR")
    print("-----------|----------|------------|--------")
    
    melhores = {}
    for denso, esparso in combinacoes:
        print(f"   {denso:.2f}    |   {esparso:.2f}   |", end='', flush=True)
        resultados_por_consulta = {}
        erro = False
        for item in ground_truth:
            consulta = item['consulta']
            try:
                ids = executar_busca(consulta, denso, esparso, k)
                resultados_por_consulta[consulta] = ids
            except Exception:
                erro = True
                break
        if erro:
            print("    ERRO")
            continue
        metricas = calcular_metricas(resultados_por_consulta, ground_truth, k)
        precisao = metricas['precisao@k']
        mrr = metricas['mrr']
        print(f"   {precisao:.4f}    |  {mrr:.4f}")
        melhores[(denso, esparso)] = metricas
    
    if melhores:
        melhor_combinacao = max(melhores.items(), key=lambda x: x[1]['mrr'])
        print("\n✅ Melhor combinação (por MRR):")
        print(f"   Pesos: denso={melhor_combinacao[0][0]}, esparso={melhor_combinacao[0][1]}")
        print(f"   Precisão@{k}={melhor_combinacao[1]['precisao@k']:.4f}, MRR={melhor_combinacao[1]['mrr']:.4f}")

if __name__ == "__main__":
    main()