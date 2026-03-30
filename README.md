# 💻 Specialist Time-Aware RAG Engine (V8 Hybrid Auditor)

### Framework de RAG Temporal para Mitigação de Alucinações por Obsolescência em Hardware

Este projeto apresenta uma arquitetura avançada de **Retrieval-Augmented Generation (RAG)** focada na resolução de um problema crítico em domínios técnicos: a **obsolescência informacional**. Diferente de sistemas RAG convencionais, esta engine integra sensibilidade temporal e auditoria lógica de série para garantir que assistentes de suporte não sugiram drivers ou especificações ultrapassadas.

---

## 🎯 Conceitos Centrais

### 1. Motor de Decaimento Linear (LinearV3)
Para resolver o fenômeno do **Borrão Semântico** (onde problemas técnicos de 2021 e 2026 parecem idênticos para o FAISS), implementamos uma taxa de obsolescência parametrizada em **4% ao ano**. Isso garante que, em caso de "empate técnico" vetorial, a solução mais recente tenha prioridade no re-ranqueamento.

### 2. Protocolo V8 & SKU-Lock
Mecanismo de auditoria híbrida que impõe uma trava lógica de entidade. O sistema é instruído a:
* **Invalidar Inferências de Série:** Não assume que o que funciona para o Nitro AN515-58 funciona para o AN515-56.
* **Zero-Trust Grounding:** Prefere a omissão segura ("Informação não encontrada") à alucinação baseada no conhecimento interno do modelo.

---

## 🚀 Pipeline de Processamento (6 Estágios)

O fluxo de dados transforma discussões informais do Reddit e Dell em **Relatórios Técnicos Densos**:

| Estágio | Operação | Objetivo Técnico |
| :--- | :--- | :--- |
| **00 - Referência** | `dataset_laptops_UNICOS_V3` | Consolidação de "Golden Rules" e especificações canônicas para ancoragem. |
| **01 - Extração** | `reddit_serviceV2.py` | Captura de relatos reais (Reddit/Dell) sobre falhas e upgrades térmicos. |
| **02 - Pre-proc** | `filtro_tecnico_conversas` | Saneamento do corpus e aplicação de thresholds de volumetria amostral. |
| **03 - NER & Resumo** | `NerResumLLAMA3.2V7` | Uso de SLMs para converter chats em relatórios com tags de intent e gravidade. |
| **04 - Vetorização** | `BGE-M3 Multilingual` | Indexação densa com suporte a múltiplos idiomas e busca híbrida. |
| **05 - Time-Aware** | `RAG_LinearV7.py` | Execução do motor RAG com re-ranking cronológico e lógica de auditoria. |
| **06 - Avaliação** | `custom_evaluatorV2.py` | Auditoria via DeepEval (LLM-as-a-Judge) com limpeza heurística de JSON. |

---

## 🛠️ Stack Tecnológico & Otimização Local

Desenvolvido para ser executado em ambientes restritos (**GTX 1050 Ti 4GB**), o sistema utiliza:

* **Modelos Compactos (SLMs):** `Llama 3.2 3B` (NER) e `Qwen 3 4B-Instruct` (Geração).
* **Orquestração de VRAM:** Implementação de `asyncio.Semaphore(1)` para processamento serial, evitando estouro de memória durante a geração de justificativas (*reasons*) de auditoria.
* **Post-Processing:** Camada de reparo heurístico para saídas de modelos de 4B, garantindo a integridade dos vereditos da métrica.

---

## 📊 Framework de Auditoria (DeepEval V3)

A eficácia do sistema é validada por uma suíte de testes rigorosa:
* **`TC_STATIC`:** Verifica se o RAG respeita limites físicos (ex: slots de SSD).
* **`TC_CONFLICT`:** Testa se o sistema prioriza o driver de 2026 sobre o de 2021.
* **`TC_HYBRID`:** Confronta o conhecimento paramétrico (interno) do modelo com o dado recuperado, forçando o uso exclusivo do contexto [RAG].



## 📂 Organização do Repositório

```bash
.
├── 00_datasets_referencia/      # Datasets canônicos e scripts de filtragem gamer.
├── 01_extracao_conversas/       # Scrapers especializados (Reddit/Dell) e análise temática.
├── 02_preprocessamento/         # Limpeza, indexação e gráficos de sensibilidade.
├── 03_ner_e_resumo/             # Pipeline de extração de entidades e sumarização técnica.
├── 04_vetorizacao/              # Geração de índices FAISS com BGE-M3.
├── 05_validacao_time_aware/     # O núcleo do RAG: Motores Vanilla vs LinearV7.
├── 06_avaliacao_quantitativa/   # Suíte DeepEval, logs de métricas e simuladores de decaimento.
├── core/                        # Centralização de caminhos e bootstrap do sistema.
└── run_pipeline.py              # Orquestrador geral do fluxo.


---

## 🛠️ Stack Tecnológico & Otimização Local

Desenvolvido para ser executado em ambientes restritos (**GTX 1050 Ti 4GB**), o sistema utiliza:

* **Modelos Compactos (SLMs):** `Llama 3.2 3B` (NER) e `Qwen 3 4B-Instruct` (Geração).
* **Orquestração de VRAM:** Implementação de `asyncio.Semaphore(1)` para processamento serial, evitando estouro de memória durante a geração de justificativas (*reasons*) de auditoria.
* **Post-Processing:** Camada de reparo heurístico para saídas de modelos de 4B, garantindo a integridade dos vereditos da métrica.

---