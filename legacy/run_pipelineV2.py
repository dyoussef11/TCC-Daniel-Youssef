
import subprocess
import sys
from pathlib import Path

# Bootstrap + paths centralizados
from core.paths import (
    AVALIACAO,
    AVALIACAO_SCRIPT,
    DATASET_GAMER,
    DATASET_SCRIPTS,
    DATASET_UTILS,
    EXTRACAO,
    EXTRACAO_SRC,
    NER_SCRIPT,
    PREPROCESSAMENTO,
    NER,
    PREPROCESSAMENTO_SCRIPT,
    PREPROCESSAMENTO_UTILS,
    VETORIZATION,
    VETORIZATION_SCRIPT,
)

def run_script(script_path: Path, working_dir: Path, step_name: str):
    """Executa um script Python e interrompe o processo em caso de erro."""
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

def etapa_dataset():
    """Gera os datasets base (Geral e depois Gamer)."""
    # 1. Primeiro o Geral
    run_script(
        script_path=DATASET_SCRIPTS / "processador_datasets_laptops_V2.py",
        working_dir=DATASET_GAMER,
        step_name="Criação de Dataset - Versão Geral",
    )
    # 2. Depois o Filtro Gamer (depende do Geral)
    run_script(
        script_path=DATASET_SCRIPTS / "gamer_laptop_filter_V2.py",
        working_dir=DATASET_GAMER,
        step_name="Criação de Dataset - Versão Gamer",
    )
    

def etapa_extracao():
    """Extrai conversas do Reddit."""
    run_script(
        script_path=EXTRACAO_SRC / "extrator_conversas_reddit.py",
        working_dir=EXTRACAO,
        step_name="Extração de Conversas (Reddit)",
    )

def etapa_preprocessamento():
    """Executa a sequência completa de limpeza e organização de dados."""
    base_path_script = PREPROCESSAMENTO_SCRIPT 
    
    # Lista ordenada de scripts para execução sequencial
    scripts_limpeza = [
        ("_0_limpeza_exclusao_e_definicao_corpus_conversas.py", "Limpeza e Definição de Corpus"),
        ("_1_analise_prevalencia_vader_tematicaV2.py", "Exclusão de Posts sem Interação"),
        ("_2_filtro_qualidade_validado_cientificamente.py", "Geração dos Gráficos Estatísticos")
        
    ]

    for script_nome, descricao in scripts_limpeza:
        run_script(
            script_path=base_path_script / script_nome,
            working_dir=PREPROCESSAMENTO,
            step_name=f"Pré-processamento: {descricao}",
        )

def etapa_resumo_ner_llama3_2_3_8b():
    """Executa o NER e Resumo usando Llama 3.2: 3.8B"""
    run_script(
        script_path=NER_SCRIPT / "NerResumLLAMA3.2-3.8bV7.py",
        working_dir=NER,
        step_name="Resumo NER - Llama3.2: 3.8B",
    )

def etapa_vetorizacao():
    """Gera os embeddings das conversas via BGE-M3."""
    run_script(
        script_path=VETORIZATION_SCRIPT / "revetorizar_multilingueV6.py",
        working_dir=VETORIZATION,
        step_name="Vetorização das Conversas - (BGE-M3)",
    )

def etapa_avaliacao_de_comparacao_rags():
    """Avalia o RAG utilizando um Juiz LLM (DeepEval)."""
    run_script(
        script_path=AVALIACAO_SCRIPT / "evaluate_rag_deepeval_TemporalVSNãoTemporalV6.py",
        working_dir=AVALIACAO,
        step_name="Avaliação dos RAGS (BaseLine Vs Hybrid Auditor) - Com Juiz LLM",
    )

def pipeline_completo():
    """Executa todas as etapas na ordem lógica de dependência."""
    print("\n" + "!"*60)
    print("INICIANDO PIPELINE COMPLETO")
    print("!"*60)
    
    etapa_dataset()
    etapa_extracao()
    etapa_preprocessamento()
    etapa_resumo_ner_llama3_2_3_8b()
    etapa_vetorizacao()
    etapa_avaliacao_de_comparacao_rags()
    
    print("\n✅ PIPELINE FINALIZADO COM SUCESSO!")


# ==========================================================
# MENU CLI
# ==========================================================

def main():
    while True:
        print("\n" + "="*30)
        print("   GERENCIADOR DO PROJETO")
        print("="*30)
        print("1. Geração de Dataset único (Geral -> Gamer)")
        print("2. Extração de Conversas (Reddit)")
        print("3. Pré-processamento de conversas (Sequência de 6 passos)")
        print("4. Resumo Ner (Llama 3.2)")
        print("5. Vetorização dos resumos ner(BGE-M3)")
        print("6. Avaliação dos RAGS (Juiz LLM)")
        print("7. [PIPELINE COMPLETO] - Passos 1 ao 6")
        print("0. Sair")

        choice = input("\nEscolha uma opção: ").strip()

        if choice == "1":
            etapa_dataset()
        elif choice == "2":
            etapa_extracao()
        elif choice == "3":
            etapa_preprocessamento()
        elif choice == "4":
            etapa_resumo_ner_llama3_2_3_8b()
        elif choice == "5":
            etapa_vetorizacao()
        elif choice == "6":
            etapa_avaliacao_de_comparacao_rags()
        elif choice == "7":
            pipeline_completo()
        elif choice == "0":
            print("Encerrando...")
            break
        else:
            print("❌ Opção inválida.")


if __name__ == "__main__":
    main()