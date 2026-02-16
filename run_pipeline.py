import subprocess
import sys
from pathlib import Path

# --- BOOTSTRAP DE CAMINHO DO PROJETO ---
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Bootstrap + paths centralizados
from core.paths import (
    EXTRACAO,
    PREPROCESSAMENTO,
    NER,
    VETORIZATION,
)


def run_script(script_path: Path, working_dir: Path, step_name: str):
    print(f"\n{'='*60}")
    print(f"🚀 EXECUTANDO: {step_name}")
    print(f"{'='*60}")

    result = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=working_dir,
    )

    if result.returncode != 0:
        print(f"❌ Erro na etapa {step_name}. Interrompendo pipeline.")
        sys.exit(1)


# ==========================================================
# DEFINIÇÃO DAS ETAPAS DO PIPELINE
# ==========================================================

def etapa_extracao():
    run_script(
        script_path=EXTRACAO / "src" / "main.py",
        working_dir=EXTRACAO,
        step_name="Extração de Conversas",
    )


def etapa_preprocessamento():
    run_script(
        script_path=PREPROCESSAMENTO / "script" / "limpeza_e_normalização.py",
        working_dir=PREPROCESSAMENTO,
        step_name="Pré-processamento",
    )


def etapa_ner_llama3_2_1b():
    run_script(
        script_path=NER / "main_alternativo.py", # Usando llama3.2:1b
        # script_path=NER / "main.py", # Usando llama3.2:latest
        # script_path=NER / "main_alternativo.py", # Usando llama3.2:1b
        working_dir=NER,
        step_name="NER com resumo",
    )

def etapa_ner_llama3_2_latest():
    run_script(
        # script_path=NER / "main.py", # Usando llama3.2:latest
        script_path=NER / "main copy.py", # Usando llama3.2:latest
        working_dir=NER,
        step_name="NER com resumo",
    )

def etapa_rag():
    run_script(
        script_path=VETORIZATION / "script" / "Revetorizar_Multilingue.py",
        working_dir=VETORIZATION,
        step_name="5 - Vetorizacao_das_conversas",
    )


def pipeline_completo():
    etapa_extracao()
    etapa_preprocessamento()
    etapa_ner_llama3_2_1b()
    etapa_ner_llama3_2_latest()
    etapa_rag()


# ==========================================================
# MENU CLI
# ==========================================================

def main():
    print("\n--- GERENCIADOR DO PROJETO ---")
    print("1. Extração (Reddit)")
    print("2. Pré-processamento")
    print("3. NER com resumo_das_conversas - llama3_2_1b")
    print("4. NER com resumo_das_conversas - llama3_2_latest")
    print("4. Sistema time-aware rag")
    print("4. Sistema time-aware rag")
    print("5. Pipeline Completo (1 → 4)")

    choice = input("\nEscolha uma opção: ").strip()

    if choice == "1":
        etapa_extracao()
    elif choice == "2":
        etapa_preprocessamento()
    elif choice == "3":
        etapa_ner_llama3_2_1b()
    elif choice == "4":
        etapa_ner_llama3_2_latest()
    elif choice == "5":
        etapa_rag()
    elif choice == "6":
        pipeline_completo()
    else:
        print("❌ Opção inválida.")


if __name__ == "__main__":
    main()
