import asyncio
import time
import pandas as pd
import psutil
import subprocess
import os
from pathlib import Path

from core.paths import VALIDACAO_SCRIPT, AVALIACAO_SCRIPT
import sys
sys.path.append(str(VALIDACAO_SCRIPT))
sys.path.append(str(AVALIACAO_SCRIPT / "eval_modules"))

# Importando seus módulos existentes
from eval_modules.rag_manager import ComparativeRAGManager
from eval_modules.eval_config import EvalConfig
from eval_modules.helpers import Timer

def get_gpu_vram_usage():
    """Obtém o uso atual de VRAM via nvidia-smi."""
    try:
        # Executa o comando nvidia-smi para obter o uso de memória em MiB
        result = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,nounits,noheader"],
            encoding='utf-8'
        )
        return int(result.strip())
    except Exception:
        return 0

def get_ram_usage():
    """Obtém o uso atual de RAM do sistema em MB."""
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / (1024 * 1024)

async def simulate_load_with_resources(rag_manager, query_list, concurrency):
    """Executa queries e monitora o pico de recursos."""
    tasks = []
    for i in range(concurrency):
        query = query_list[i % len(query_list)]
        tasks.append(rag_manager.temporal.search(query, "2026-03-12"))
    
    start_time = time.perf_counter()
    
    # Monitoramento em background simples (captura inicial)
    ram_start = get_ram_usage()
    vram_start = get_gpu_vram_usage()
    
    responses = await asyncio.gather(*tasks)
    
    end_time = time.perf_counter()
    
    # Captura final (geralmente o pico após o processamento)
    ram_end = get_ram_usage()
    vram_end = get_gpu_vram_usage()
    
    return {
        "duration": end_time - start_time,
        "ram_peak": max(ram_start, ram_end),
        "vram_peak": max(vram_start, vram_end)
    }

async def run_performance_test():
    config = EvalConfig()
    rag_manager = ComparativeRAGManager(config.base_path, config)
    
    print(f"🚀 Benchmark V9 + Monitoramento de Recursos")
    print(f"💻 Setup: i7-8750h | GTX 1050 Ti | CPU: {psutil.cpu_count()} cores")
    print("-" * 70)

    results = []
    TEST_QUERIES = [
        "What is the maximum RAM for Acer Nitro 5 AN515-56?",
        "Why does my laptop thermal throttle during gaming?",
        "Does Dell G7 7588 support NVMe SSDs?"
    ]
    CONCURRENCY_LEVELS = [1, 2, 4, 8]

    for level in CONCURRENCY_LEVELS:
        print(f"📊 Testando concorrência nível: {level}...")
        
        # Warm-up
        if level == 1:
            await rag_manager.temporal.search(TEST_QUERIES[0], "2026-03-12")

        metrics = await simulate_load_with_resources(rag_manager, TEST_QUERIES, level)
        
        avg_latency = metrics["duration"] / level
        
        results.append({
            "Concorrência": level,
            "Tempo Total (s)": round(metrics["duration"], 2),
            "Latência Média (s)": round(avg_latency, 2),
            "Req/seg (TPS)": round(level / metrics["duration"], 3),
            "RAM Pico (MB)": round(metrics["ram_peak"], 2),
            "VRAM Pico (MiB)": metrics["vram_peak"]
        })

    # Exibição e Salvamento
    df = pd.DataFrame(results)
    print("\n" + "="*70)
    print("📈 RESULTADOS DO BENCHMARK COM RECURSOS")
    print("="*70)
    print(df.to_string(index=False))
    
    output_file = config.output_dir / "performance_resources_v9.csv"
    df.to_csv(output_file, index=False)
    print(f"\n✅ Dados salvos em: {output_file}")

if __name__ == "__main__":
    asyncio.run(run_performance_test())