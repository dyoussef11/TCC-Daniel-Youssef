import subprocess
import sys
from pathlib import Path

# Bootstrap + paths centralizados
from core.paths import (
    AVALIACAO,
    AVALIACAO_SCRIPT,
    DATASET_GAMER,
    DATASET_SCRIPTS,
    EXTRACAO,
    EXTRACAO_SRC,
    EXTRACAO_SRC_EXTRACTORS,
    NER,
    NER_SCRIPT,
    PREPROCESSAMENTO,
    PREPROCESSAMENTO_SCRIPT,
    VETORIZATION,
    VETORIZATION_SCRIPT,
)


def run_script(script_path: Path, working_dir: Path, step_name: str,
               extra_pythonpath: Path = None):
    """
    Executa um script Python em um subprocesso, interrompendo o pipeline
    em caso de erro.

    Args:
        script_path: caminho absoluto do script .py a executar.
        working_dir: diretório de trabalho (cwd) do subprocesso.
        step_name: nome legível da etapa (para logs).
        extra_pythonpath: se fornecido, adiciona ao PYTHONPATH do subprocesso.
    """
    print(f"\n{'=' * 70}")
    print(f"🚀 EXECUTANDO: {step_name}")
    print(f"   Script : {script_path}")
    print(f"   CWD    : {working_dir}")
    print(f"{'=' * 70}")

    if not script_path.exists():
        print(f"❌ Script não encontrado: {script_path}")
        sys.exit(1)

    # Prepara ambiente (opcionalmente injeta PYTHONPATH extra)
    env = None
    if extra_pythonpath is not None:
        import os
        env = os.environ.copy()
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (
            f"{extra_pythonpath}{os.pathsep}{existing}"
            if existing else str(extra_pythonpath)
        )

    result = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=str(working_dir),
        env=env,
        # Sem captura: deixa o script filho imprimir em tempo real
        # (mais fácil de acompanhar o progresso via tqdm)
    )

    if result.returncode != 0:
        print(f"\n❌ Erro na etapa '{step_name}' (exit code {result.returncode}).")
        print("   Pipeline interrompido.")
        sys.exit(result.returncode)


# ==========================================================
# ETAPAS DO PIPELINE
# ==========================================================

def etapa_dataset():
    """
    Gera o dataset único de laptops (Kaggle → Gamer → enriquecido).

    Ordem lógica (baseada nos arquivos reais do repositório):
      1. pre_process_underline_em_notebooksV4.py  → cria *_limpo.csv com
         a coluna 'modelo_completo_limpo' em 'limpos_underline/'.
      2. unifica_notebooks_com_underline_csv.py   → consolida tudo em
         'laptops_centralizado_modelos.csv'.
      3. main_processsamento.py                   → gera o dataset final
         enriquecido (UNICOS_V10) usando motor + limpador + config.
    """
    run_script(
        script_path=DATASET_SCRIPTS / "pre_process_underline_em_notebooksV4.py",
        working_dir=DATASET_GAMER,
        step_name="Dataset (1/3) — Pré-processamento dos CSVs brutos",
    )
    run_script(
        script_path=DATASET_SCRIPTS / "unifica_notebooks_com_underline_csv.py",
        working_dir=DATASET_GAMER,
        step_name="Dataset (2/3) — Unificação em CSV centralizado",
    )
    run_script(
        script_path=DATASET_SCRIPTS / "main_processsamento.py",
        working_dir=DATASET_GAMER,
        step_name="Dataset (3/3) — Geração do dataset final (UNICOS_V10)",
    )


def etapa_extracao():
    """
    Extrai posts do Reddit em duas fases:
      1. Busca leve (sem comentários) por todos os modelos pendentes.
      2. Carga de comentários sob demanda, com retry/backoff.

    Observação: os scripts importam `from extractors.xxx import ...`, então
    passamos `01_extracao_conversas/src` via PYTHONPATH para que o pacote
    `extractors` seja resolvido.
    """
    run_script(
        script_path=EXTRACAO_SRC_EXTRACTORS / "extrator_postagem_reddit_sem_comentarios_V11.py",
        working_dir=EXTRACAO,
        step_name="Extração (1/2) — Posts leves do Reddit",
        extra_pythonpath=EXTRACAO_SRC,
    )
    run_script(
        script_path=EXTRACAO_SRC_EXTRACTORS / "carregador_comentarios_para_brutos.py",
        working_dir=EXTRACAO,
        step_name="Extração (2/2) — Carga de comentários sob demanda",
        extra_pythonpath=EXTRACAO_SRC,
    )


def etapa_preprocessamento():
    """Limpeza técnica do corpus (deduplicação global + limpeza de texto)."""
    run_script(
        script_path=PREPROCESSAMENTO_SCRIPT / "_0_limpeza_exclus_definic_corpus_V10.py",
        working_dir=PREPROCESSAMENTO,
        step_name="Pré-processamento — Limpeza e definição de corpus",
    )


def etapa_ner_resumo():
    """
    NER + sumarização via SLM.
    Modelo padrão: Llama 3.1 8B (com parser de fallback robusto).
    Alternativa  : Granite 3.2 8B (mesma interface, mesmo prompt).
    """
    run_script(
        script_path=NER_SCRIPT / "ner_resumo_llama_3.1.py",
        working_dir=NER,
        step_name="NER + Resumo — Llama 3.1:8B (fallback robusto)",
    )


def etapa_vetorizacao():
    """Gera embeddings BGE-M3 + índice FAISS (.npy, .meta.json, .faiss)."""
    run_script(
        script_path=VETORIZATION_SCRIPT / "vetorizacao_multilingue_bge_m3_V3.py",
        working_dir=VETORIZATION,
        step_name="Vetorização — BGE-M3 + FAISS",
    )


def etapa_avaliacao_de_comparacao_rags():
    """Compara Vanilla vs Temporal via DeepEval (LLM-as-a-Judge)."""
    run_script(
        script_path=AVALIACAO_SCRIPT / "evaluate_deepeval_unified_comparative_Repete_N_Modelos_NVezesV6.py",
        working_dir=AVALIACAO,
        step_name="Avaliação — Vanilla vs Temporal (DeepEval + Juiz LLM)",
    )


def pipeline_completo():
    """Executa todas as etapas na ordem lógica de dependência."""
    print("\n" + "!" * 70)
    print("  INICIANDO PIPELINE COMPLETO")
    print("!" * 70)

    etapa_dataset()
    etapa_extracao()
    etapa_preprocessamento()
    etapa_ner_resumo()
    etapa_vetorizacao()
    etapa_avaliacao_de_comparacao_rags()

    print("\n✅ PIPELINE FINALIZADO COM SUCESSO!")


# ==========================================================
# MENU CLI
# ==========================================================

def main():
    menu_options = {
        "1": ("Dataset unificado (Geral → Gamer → UNICOS_V10)", etapa_dataset),
        "2": ("Extração de conversas do Reddit (posts + comentários)", etapa_extracao),
        "3": ("Pré-processamento (limpeza técnica do corpus)", etapa_preprocessamento),
        "4": ("NER + Resumo (Llama 3.1:8B)", etapa_ner_resumo),
        "5": ("Vetorização (BGE-M3 + FAISS)", etapa_vetorizacao),
        "6": ("Avaliação comparativa dos RAGs (Juiz LLM / DeepEval)", etapa_avaliacao_de_comparacao_rags),
        "7": ("[PIPELINE COMPLETO] — Etapas 1 a 6", pipeline_completo),
    }

    while True:
        print("\n" + "=" * 70)
        print("   GERENCIADOR DO PIPELINE — TCC")
        print("   RAG com Consciência Temporal para Suporte Técnico de Hardware")
        print("=" * 70)
        for key, (desc, _) in menu_options.items():
            print(f"  {key}. {desc}")
        print("  0. Sair")
        print("=" * 70)

        choice = input("\nEscolha uma opção: ").strip()

        if choice == "0":
            print("Encerrando...")
            break

        if choice in menu_options:
            _, func = menu_options[choice]
            try:
                func()
            except KeyboardInterrupt:
                print("\n⚠️  Interrompido pelo usuário.")
                break
        else:
            print("❌ Opção inválida.")


if __name__ == "__main__":
    main()