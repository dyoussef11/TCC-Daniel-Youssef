import subprocess
import sys
from pathlib import Path

def run_step(step_folder, script_name):
    script_path = Path(__file__).parent / step_folder / "src" / script_name
    print(f"\n{'='*60}")
    print(f"🚀 EXECUTANDO: {step_folder}")
    print(f"{'='*60}")
    
    # Roda o script usando o interpretador atual do .venv
    result = subprocess.run([sys.executable, str(script_path)], cwd=Path(__file__).parent / step_folder)
    
    if result.returncode != 0:
        print(f"❌ Erro na etapa {step_folder}. Interrompendo pipeline.")
        sys.exit(1)

if __name__ == "__main__":
    # Menu simples para escolher o que rodar
    print("--- GERENCIADOR DO PROJETO ---")
    print("1. Extração (Reddit)")
    print("2. Pré-processamento")
    print("3. Pipeline Completo (1 ao 6)")
    
    choice = input("\nEscolha uma opção: ")

    if choice == "1":
        run_step("2 - Extração de conversas", "main.py")
    elif choice == "2":
        run_step("3 - Pre-processamento dados", "main.py")
    # Adicione os outros conforme criar os scripts