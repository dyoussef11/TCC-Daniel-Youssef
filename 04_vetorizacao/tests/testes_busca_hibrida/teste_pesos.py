#!/usr/bin/env python3
"""
teste_pesos.py - Testa diferentes combinações de pesos para busca híbrida
Uso: python teste_pesos.py --ground_truth gt.json
"""

import json
import subprocess
import tempfile
import sys
from pathlib import Path
import argparse
from collections import defaultdict

from core.paths import VETORIZATION_SCRIPT

# =============================================================================
# CONFIGURAÇÕES
# =============================================================================
# SCRIPT_BUSCAR = Path(__file__).parent / "buscarHibrida.py"   # agora aponta para buscar.py
SCRIPT_BUSCAR = VETORIZATION_SCRIPT / "buscarHibridaV2.py"   # agora aponta para buscar.py
K = 5
# =============================================================================

def carregar_ground_truth(arquivo_gt):
    with open(arquivo_gt, 'r', encoding='utf-8') as f:
        dados = json.load(f)
    return dados

def executar_busca(consulta, peso_denso, peso_esparso, k):
    """
    Executa o script buscar.py com os argumentos fornecidos e retorna os IDs dos resultados.
    Em caso de erro, lança exceção com a mensagem de erro.
    """
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tmp:
        tmp_path = tmp.name

    args = [
        sys.executable, str(SCRIPT_BUSCAR),
        '--consulta', consulta,
        '--peso_denso', str(peso_denso),
        '--peso_esparso', str(peso_esparso),
        '--k', str(k),
        '--saida', tmp_path,
        '--quiet'   # suprime saída no console
    ]
    try:
        subprocess.run(args, check=True, capture_output=True, text=True, encoding='utf-8')
        with open(tmp_path, 'r', encoding='utf-8') as f:
            resultados = json.load(f)
        return [r['id'] for r in resultados]
    except subprocess.CalledProcessError as e:
        print(f"❌ Erro ao executar busca para consulta: {consulta[:50]}...")
        print(f"   Código de saída: {e.returncode}")
        print(f"   Saída de erro: {e.stderr}")
        raise
    finally:
        # Remove arquivo temporário
        Path(tmp_path).unlink(missing_ok=True)

def calcular_metricas(resultados_por_consulta, ground_truth, k):
    metricas = defaultdict(list)
    for item in ground_truth:
        consulta = item['consulta']
        relevantes = set(item['relevantes'])
        ids_obtidos = resultados_por_consulta.get(consulta, [])
        
        # Precisão@K
        k_efetivo = min(k, len(ids_obtidos))
        if k_efetivo > 0:
            acertos = sum(1 for id_ in ids_obtidos[:k_efetivo] if id_ in relevantes)
            precisao = acertos / k_efetivo
        else:
            precisao = 0.0
        metricas['precisao@k'].append(precisao)
        
        # MRR
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
    parser = argparse.ArgumentParser(description='Testa pesos da busca híbrida')
    parser.add_argument('--ground_truth', required=True, help='Arquivo JSON com ground truth')
    parser.add_argument('--pesos', nargs=2, type=float, action='append',
                        help='Par de pesos (denso, esparso) a testar. Pode ser repetido.')
    parser.add_argument('--k', type=int, default=K, help='Número de resultados por busca')
    args = parser.parse_args()
    
    k = args.k
    
    # Carrega ground truth
    ground_truth = carregar_ground_truth(args.ground_truth)
    
    # Define combinações de pesos se não fornecidas
    if not args.pesos:
        combinacoes = [
            (1.0, 0.0),
            (0.9, 0.1),
            (0.8, 0.2),
            (0.7, 0.3),
            (0.6, 0.4),
            (0.5, 0.5),
            (0.4, 0.6),
            (0.3, 0.7),
            (0.2, 0.8),
            (0.1, 0.9),
            (0.0, 1.0)
        ]
    else:
        combinacoes = args.pesos
    
    # Executa para cada combinação
    melhores = {}
    for denso, esparso in combinacoes:
        print(f"\n🔍 Testando pesos: denso={denso}, esparso={esparso}")
        resultados_por_consulta = {}
        for item in ground_truth:
            consulta = item['consulta']
            print(f"   Executando consulta: {consulta[:50]}...")
            try:
                ids = executar_busca(consulta, denso, esparso, k)
                resultados_por_consulta[consulta] = ids
            except Exception:
                # Se falhar, pula essa consulta
                continue
        metricas = calcular_metricas(resultados_por_consulta, ground_truth, k)
        print(f"   📊 Resultados: Precisão@{k}={metricas['precisao@k']:.4f}, MRR={metricas['mrr']:.4f}")
        melhores[(denso, esparso)] = metricas
    
    # Encontra a melhor combinação (baseado em MRR)
    if melhores:
        melhor_combinacao = max(melhores.items(), key=lambda x: x[1]['mrr'])
        print("\n✅ Melhor combinação (por MRR):")
        print(f"   Pesos: denso={melhor_combinacao[0][0]}, esparso={melhor_combinacao[0][1]}")
        print(f"   Precisão@{k}={melhor_combinacao[1]['precisao@k']:.4f}, MRR={melhor_combinacao[1]['mrr']:.4f}")
    else:
        print("Nenhuma combinação foi testada com sucesso.")

if __name__ == "__main__":
    main()