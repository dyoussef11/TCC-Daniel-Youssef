import asyncio
import pandas as pd
import sys
import gc
import time
from datetime import datetime
from tqdm import tqdm
import pynvml  # Gerenciador de monitoramento NVIDIA

# Configuração de caminhos e imports originais
from core.paths import VETORIZATION_DATA, AVALIACAO_DATA, VALIDACAO_SCRIPT
sys.path.append(str(VALIDACAO_SCRIPT))

from RAGNaoTemporal_CPUMode import VanillaRAG
from RAG_Temporal_V8_CPUMode import SpecialistTimeAwareRAG
from custom_evaluatorV2Backup import OllamaEvaluator
from dataset_avaliacaoV3 import TEST_SUITE
from deepeval.test_case import LLMTestCase
from deepeval.metrics import (
    ContextualPrecisionMetric, 
    ContextualRelevancyMetric,
    ContextualRecallMetric,
    FaithfulnessMetric, 
    AnswerRelevancyMetric
)

# --- CONFIGURAÇÃO DE SEGURANÇA ---
MAX_TEMP = 77  # Temperatura em °C para pausar (Throttling preventivo)
COOL_DOWN_TEMP = 70  # Temperatura para retomar a execução
CONCURRENT_METRICS = 1 
semaphore = asyncio.Semaphore(CONCURRENT_METRICS)

class HardwareMonitor:
    def __init__(self):
        try:
            pynvml.nvmlInit()
            self.handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            self.enabled = True
        except Exception as e:
            print(f"⚠️ NVML não inicializado: {e}")
            self.enabled = False

    def get_stats(self):
        if not self.enabled: return 0, 0
        temp = pynvml.nvmlDeviceGetTemperature(self.handle, pynvml.NVML_TEMPERATURE_GPU)
        mem = pynvml.nvmlDeviceGetMemoryInfo(self.handle)
        mem_used_gb = mem.used / 1024**3
        return temp, mem_used_gb

    async def check_thermal_safety(self, pbar=None):
        if not self.enabled: return
        temp, mem = self.get_stats()
        if temp >= MAX_TEMP:
            msg = f"🌡️ ALERTA: GPU em {temp}°C! Resfriando até {COOL_DOWN_TEMP}°C..."
            if pbar: pbar.write(msg)
            else: print(msg)
            
            while temp > COOL_DOWN_TEMP:
                await asyncio.sleep(5)
                temp, _ = self.get_stats()
            
            if pbar: pbar.write("❄️ Resfriamento concluído. Retomando...")

async def measure_with_reason(metric, test_case, monitor):
    async with semaphore:
        try:
            # Monitora antes de cada chamada pesada ao Ollama
            await monitor.check_thermal_safety()
            
            await asyncio.to_thread(metric.measure, test_case)
            score = float(metric.score)
            
            reason = "N/A"
            if hasattr(metric, 'reason') and metric.reason:
                reason = metric.reason
            elif hasattr(metric, 'verdicts') and metric.verdicts:
                reasons = []
                for v in metric.verdicts:
                    r = getattr(v, 'reason', None) or (v.get('reason') if isinstance(v, dict) else None)
                    if r: reasons.append(r)
                reason = " | ".join(reasons) if reasons else "No reasons provided."
            
            return score, str(reason).replace('\n', ' ')
        except Exception as e:
            print(f"⚠️ Erro na métrica {type(metric).__name__}: {str(e)}")
            return 0.0, f"Erro: {str(e)}"

async def duelo_auditor_completo():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    csv_path = AVALIACAO_DATA / f"METRICAS_DETALHADAS_{timestamp}_MONITORADO.csv"
    txt_path = AVALIACAO_DATA / f"RELATORIO_TECNICO_{timestamp}_MONITORADO.txt"
    
    monitor = HardwareMonitor()
    
    print(f"\n--- 🚀 INICIANDO DUELO TÉCNICO (Hardware Monitor Ativo) ---")
    
    # avaliador = OllamaEvaluator(model_name="phi3.5:3.8b-mini-instruct-q4_K_M")
    avaliador = OllamaEvaluator(model_name="qwen3:4b-instruct")
    # base_path = VETORIZATION_DATA / 'base_conhecimento_multilingueV5.json'
    base_path = VETORIZATION_DATA / 'base_conhecimento_multilingueV7.json'
    
    rag_v1 = VanillaRAG(base_path)
    rag_v8 = SpecialistTimeAwareRAG(base_path, variant_name="V8_HYBRID_AUDITOR")

    metrics = {
        "C_Precision": ContextualPrecisionMetric(threshold=0.7, model=avaliador, include_reason=True),
        "C_Relevancia": ContextualRelevancyMetric(threshold=0.7, model=avaliador, include_reason=True),
        "C_Recall": ContextualRecallMetric(threshold=0.6, model=avaliador, include_reason=True),
        "Faithfulness": FaithfulnessMetric(threshold=0.8, model=avaliador, include_reason=True),
        "Answer_Rel": AnswerRelevancyMetric(threshold=0.7, model=avaliador, include_reason=True)
    }

    results_table = []
    
    with open(txt_path, 'w', encoding='utf-8') as f_report:
        f_report.write(f"RELATÓRIO COM MONITORAMENTO DE HARDWARE\nData: {timestamp}\n{'='*80}\n\n")

        pbar = tqdm(TEST_SUITE, desc="Auditando")
        for tc in pbar:
            # Telemetria Inicial
            temp, vram = monitor.get_stats()
            pbar.set_postfix({"GPU Temp": f"{temp}°C", "VRAM": f"{vram:.1f}GB"})

            # 1. Geração das Respostas (Consumo de GPU)
            res_v1 = await rag_v1.search(tc["input"])
            await monitor.check_thermal_safety(pbar)
            gc.collect() 

            res_v8 = await rag_v8.search(tc["input"], tc.get("reference_date", "2026-03-12"))
            await monitor.check_thermal_safety(pbar)
            gc.collect()

            # 2. Preparação dos Casos
            case_v1 = LLMTestCase(
                input=tc["input"], 
                actual_output=res_v1["answer"], 
                retrieval_context=res_v1["sources"][:5],
                expected_output=tc.get("expected_output")
            )
            case_v8 = LLMTestCase(
                input=tc["input"], 
                actual_output=res_v8["answer"], 
                retrieval_context=res_v8["sources"][:5],
                expected_output=tc.get("expected_output")
            )

            # 3. Avaliação Sequencial
            results_v1 = {}
            results_v8 = {}
            for name, m in metrics.items():
                results_v8[name] = await measure_with_reason(m, case_v8, monitor)
                results_v1[name] = await measure_with_reason(m, case_v1, monitor)

            # 4. Logs e Salvamento
            row = {"ID": tc['id'], "Query": tc["input"], "Final_Temp": temp}
            f_report.write(f"ID: {tc['id']} | Query: {tc['input']} | GPU: {temp}°C\n")
            
            for name in metrics.keys():
                s1, r1 = results_v1[name]
                s8, r8 = results_v8[name]
                row[f"V1_{name}"] = s1
                row[f"V8_{name}"] = s8
                f_report.write(f"\nMétrica: {name}\n")
                f_report.write(f"  \n[V1] Score: {s1:.2f} | Reason: {r1}\n")
                f_report.write(f"  \n[V8] Score: {s8:.2f} | Reason: {r8}\n")

            results_table.append(row)
            pd.DataFrame(results_table).to_csv(csv_path, index=False)
            f_report.write("-" * 60 + "\n")
            f_report.flush()
            gc.collect()

    pynvml.nvmlShutdown()
    print(f"\n✅ Concluído. Resultados: {csv_path}")

if __name__ == "__main__":
    asyncio.run(duelo_auditor_completo())