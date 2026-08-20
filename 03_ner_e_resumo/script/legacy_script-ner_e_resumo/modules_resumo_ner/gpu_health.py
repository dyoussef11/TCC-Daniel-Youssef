
import asyncio
import subprocess

def get_gpu_temperature():
    try:
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=temperature.gpu', '--format=csv,noheader,nounits'],
            capture_output=True, text=True, timeout=5
        )
        return int(result.stdout.strip()) if result.returncode == 0 else None
    except:
        return None

async def monitorar_temperatura(stats, max_temp, cooldown_temp):
    while True:
        temp = get_gpu_temperature()
        if temp and temp > max_temp:
            stats["pausas_temperatura"] += 1
            print(f"\n🌡️ GPU a {temp}°C! Pausando até {cooldown_temp}°C...")
            while temp > cooldown_temp:
                await asyncio.sleep(10)
                temp = get_gpu_temperature() or temp
            print(f"❄️ Retomando...")
        await asyncio.sleep(5)