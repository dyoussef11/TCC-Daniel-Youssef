import subprocess
import sys
from pathlib import Path

# Bootstrap + paths centralizados
from core.paths import (
    EXTRACAO,
    PREPROCESSAMENTO,
    NER,
    RAG,
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


def etapa_ner():
    run_script(
        script_path=NER / "main.py",
        working_dir=NER,
        step_name="NER com resumo",
    )


def etapa_rag():
    run_script(
        script_path=RAG / "script" / "7-Revetorizar_Multilingue.py",
        working_dir=RAG,
        step_name="Sistema Time-Aware RAG",
    )


def pipeline_completo():
    etapa_extracao()
    etapa_preprocessamento()
    etapa_ner()
    etapa_rag()


# ==========================================================
# MENU CLI
# ==========================================================

def main():
    print("\n--- GERENCIADOR DO PROJETO ---")
    print("1. Extração (Reddit)")
    print("2. Pré-processamento")
    print("3. NER com resumo_das_conversas")
    print("4. Sistema time-aware rag")
    print("5. Pipeline Completo (1 → 4)")

    choice = input("\nEscolha uma opção: ").strip()

    if choice == "1":
        etapa_extracao()
    elif choice == "2":
        etapa_preprocessamento()
    elif choice == "3":
        etapa_ner()
    elif choice == "4":
        etapa_rag()
    elif choice == "5":
        pipeline_completo()
    else:
        print("❌ Opção inválida.")


if __name__ == "__main__":
    main()
