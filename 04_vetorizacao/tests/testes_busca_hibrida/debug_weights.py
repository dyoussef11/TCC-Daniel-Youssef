# debug_weights.py
import subprocess
import json
import tempfile
from pathlib import Path

consulta = "What was the maximum RAM capacity of the Dell G15 5530 in March 2024?"
peso_denso = 0.95
peso_esparso = 0.05
k = 5

with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tmp:
    tmp_path = tmp.name

cmd = [
    "python", "buscarHibridaV2.py",
    "--consulta", consulta,
    "--peso_denso", str(peso_denso),
    "--peso_esparso", str(peso_esparso),
    "--k", str(k),
    "--saida", tmp_path,
    "--quiet",
    "--fusion", "linear"
]
subprocess.run(cmd, check=True)

with open(tmp_path, 'r') as f:
    resultados = json.load(f)

print("IDs retornados:", [r['id'] for r in resultados])
for r in resultados:
    print(f"ID: {r['id']}")
    print(f"Texto: {r['texto'][:150]}...")
    print("-" * 40)