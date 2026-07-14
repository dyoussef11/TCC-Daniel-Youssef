# extrair_ids.py
import json
import subprocess
import sys

consulta = sys.argv[1] if len(sys.argv) > 1 else "What was the maximum RAM capacity of the Dell G15 5530 in March 2024?"

# Executa busca com pesos 1.0/0.0 (apenas densa) ou 0.0/1.0 (apenas esparsa)
# Altere conforme desejar
cmd = [
    sys.executable, "buscarHibridaV2.py",
    "--consulta", consulta,
    "--peso_denso", "1.0",
    "--peso_esparso", "0.0",
    "--k", "5",
    "--quiet"  # suprime saída
]
import tempfile
with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tmp:
    tmp_path = tmp.name
cmd.extend(["--saida", tmp_path])

subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8')
with open(tmp_path, 'r', encoding='utf-8') as f:
    resultados = json.load(f)

print("IDs retornados:")
for i, r in enumerate(resultados, 1):
    print(f"{i}. {r['id']}")
    print(f"   {r['texto'][:100]}...")