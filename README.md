# 💻 RAG com Consciência Temporal para Suporte Técnico de Hardware

## 📖 Trabalho de Conclusão de Curso (TCC)

**Título:** *Recuperação Aumentada por Geração com Consciência Temporal para Suporte Técnico de Hardware*

Este repositório contém a implementação completa do TCC, que propõe uma arquitetura de **Retrieval-Augmented Generation (RAG)** sensível ao tempo para mitigar o problema de **obsolescência informacional** em domínios técnicos. Diferente de sistemas RAG convencionais, esta engine integra decaimento temporal, trava lógica de SKU e auditoria de alucinações para garantir que assistentes de suporte não sugiram drivers, especificações ou soluções ultrapassadas.

> **Nota para a banca e futuros mantenedores:** este README foi escrito para servir como documentação de transferência de conhecimento. Após a apresentação, qualquer pessoa deve ser capaz de reproduzir o pipeline, entender as decisões de projeto e estender o trabalho a partir das instruções abaixo.

---

## 🎯 Motivação e Problema

Modelos de linguagem treinados em dados históricos tendem a **misturar informações de diferentes gerações de hardware**. Um sintoma clássico é o **Borrão Semântico**: para o FAISS, uma discussão sobre um problema de 2021 e outra de 2026 parecem idênticas, pois o espaço vetorial não codifica a passagem do tempo.

Este TCC ataca três frentes:

1. **Decaimento temporal controlado** – re-ranqueamento que penaliza documentos antigos proporcionalmente à sua idade.
2. **SKU-Lock (Trava de Entidade)** – o sistema não infere especificações de um modelo a partir de outro da mesma série (ex.: não usa o Nitro AN515-58 para responder sobre o AN515-56).
3. **Auditoria de Alucinação e Fallback Híbrido** – quando a base externa não cobre o SKU consultado, o sistema admite a ausência antes de recorrer ao conhecimento interno do LLM.

A validação é feita por **LLM-as-a-Judge** com DeepEval, comparando a engine Vanilla (baseline) contra a engine Temporal (proposta).

---

## 🧠 Conceitos Centrais

### 1. Motor de Decaimento Temporal (LinearV3)

A pontuação final de um documento recuperado é:

$$
S_{final} = S_{vetorial} \times \left(1 + \left(1 - e^{-\lambda \cdot \Delta t}\right) \cdot \alpha\right)
$$

Implementado com uma taxa parametrizada em **4% ao ano** (`yearly_penalty_rate = 0.04`). Em caso de empate vetorial, o documento mais recente vence.

### 2. Protocolo de SKU-Lock

O motor impõe uma **trava lógica de entidade**:

- **Série sem SKU** → o sistema é proibido de responder especificações e deve pedir o modelo exato.
- **SKU específico** → usa contexto externo; se ausente, admite e só então recorre ao conhecimento interno.
- **Comparações** → exige documentação de ambos os SKUs; se faltar, sinaliza que parte da resposta é baseada em conhecimento geral.

### 3. Pipeline Híbrido (SLMs em Hardware Restrito)

Todo o pipeline foi projetado para rodar em **GTX 1050 Ti (4 GB VRAM)**, usando modelos compactos orquestrados via **Ollama**:

| Etapa | Modelo | Papel |
|---|---|---|
| NER & Sumarização | `granite3.2:8b` / `llama3.1:8b` | Extrair entidades técnicas e sumarizar threads |
| Embeddings | `bge-m3:latest` | Vetorização multilíngue (1024 dim) |
| Geração | `phi3.5:latest` / `qwen3:4b-instruct` | Resposta final |
| Juiz LLM | `qwen3:4b-instruct` | Avaliação DeepEval |

---

## ⚙️ Instalação e Setup

### 1. Ambiente Virtual

Requer **Python 3.12.10**:
- https://www.python.org/downloads/release/python-31210/

```bash
python -m venv .venv
.\.venv\Scripts\activate      # Windows
source .venv/bin/activate     # Linux/macOS
```

### 2. Dependências e Módulo Core

```bash
pip install -r requirements.txt
pip install -e .
```

O `pip install -e .` registra o pacote `core` como módulo editável, permitindo importações como:

```python
from core.paths import DATASET_CONFIG, DATASET_GAMER, NER_DATA, ...
```

### 3. Ollama e Modelos

Instale o [Ollama](https://ollama.com/) e baixe os modelos:

```bash
ollama pull bge-m3:latest
ollama pull granite3.2:8b
ollama pull llama3.1:8b
ollama pull phi3.5:latest
ollama pull phi3:14b
ollama pull qwen3:4b-instruct
ollama pull qwen3.5:9b
ollama pull mistral:7b-instruct
```

### 4. Credenciais Reddit (PRAW)

1. Navegue até `01_extracao_conversas/src/extractors/`.
2. Renomeie `praw.ini.example` → `praw.ini`.
3. Preencha `client_id`, `client_secret` e `user_agent`.

Sem isso, o pipeline de extração não funciona, mas as etapas seguintes podem ser testadas com logs pré-existentes.

### 5. Descompactação da Base Vetorial

A base vetorizada é grande e está compactada:

```bash
cd 04_vetorizacao/data/
bunzip2 base_conhecimento_multilingueV2.json.bz2
```

---

## 🛠️ Pipeline de Processamento (6 Estágios)

O fluxo completo transforma discussões informais do Reddit em relatórios técnicos densos, com ancoragem temporal.

| Estágio | Script Principal | Objetivo Técnico |
|---|---|---|
| **00 – Referência** | `unifica_notebooks_com_underline_csv.py` + `pre_process_underline_em_notebooksV4.py` | Consolidar especificações canônicas de laptops em `dataset_laptops_UNICOS_V10.csv` |
| **01 – Extração** | `extrator_postagem_reddit_sem_comentarios_V11.py` + `carregador_comentarios_para_brutos.py` | Captura via PRAW (posts leves + comentários sob demanda) |
| **02 – Pré-processamento** | `_0_limpeza_exclus_definic_corpus_V10.py` | Limpeza, deduplicação global e thresholds de volumetria |
| **03 – NER & Resumo** | `ner_resumo_granite_3.2.py` / `ner_resumo_llama_3.1.py` | Extração de entidades e sumarização via SLMs |
| **04 – Vetorização** | `vetorizacao_multilingue_bge_m3_V3.py` | Indexação densa com BGE-M3 + FAISS |
| **05 – RAG Temporal** | `RAG_Temporal_V9_3.py` | Motor RAG com re-ranking cronológico e SKU-Lock |
| **06 – Avaliação** | `evaluate_deepeval_unified_comparative_Repete_N_Modelos_NVezesV6.py` | Auditoria comparativa Vanilla vs Temporal |

---

## 📂 Organização do Repositório

```bash
.
├── 00_datasets_referencia/      # Datasets canônicos e scripts de unificação
│   ├── unifica_notebooks_com_underline_csv.py
│   ├── pre_process_underline_em_notebooksV4.py
│   ├── main_processsamento.py
│   ├── motor_processamento.py
│   ├── limpador_processamento.py
│   └── configuracao_processamento.py
├── 01_extracao_conversas/
│   └── src/
│       ├── core_extration/
│       │   └── base_extractor.py
│       └── extractors/
│           ├── reddit_serviceV13.py
│           ├── extrator_postagem_reddit_sem_comentarios_V11.py
│           └── carregador_comentarios_para_brutos.py
├── 02_preprocessamento/
│   └── _0_limpeza_exclus_definic_corpus_V10.py
├── 03_ner_e_resumo/
│   ├── ner_resumo_granite_3.2.py
│   └── ner_resumo_llama_3.1.py
├── 04_vetorizacao/
│   ├── vetorizacao_multilingue_bge_m3_V3.py
│   ├── mapeamento_nome_modelos.py
│   └── variacao_nome_modelo.py
├── 05_validacao_time_aware/
│   ├── RAG_BaseLineV2.py                 # Engine Vanilla (baseline)
│   ├── RAG_Temporal_V9_3.py              # Engine Temporal (proposta)
│   ├── prompt_rag_temporal_hybrid_V9.json
│   └── prompt_rag_vanilla_V1.json
├── 06_avaliacao_quantitativa/
│   ├── evaluate_deepeval_unified_comparative_Repete_N_Modelos_NVezesV6.py
│   ├── dataset_avaliacaoV4.py
│   └── custom_evaluatorV4.py
├── core/                                 # Caminhos e bootstrap
│   └── paths.py
└── run_pipeline.py                       # Orquestrador central com menu CLI
```

---

## 🚀 Como Executar

### Orquestrador Central

```bash
python run_pipeline.py
```

Menu interativo com as opções:

| Opção | Ação |
|---|---|
| **1** | Gerar datasets base (Geral → Gamer) |
| **3** | Executar os 6 passos de pré-processamento (limpeza + thresholds + indexação) |
| **7** | Pipeline Completo (encadeia todos os estágios na ordem correta) |

### Execução Manual por Estágio

**Estágio 00 – Unificação de datasets:**
```bash
python 00_datasets_referencia/pre_process_underline_em_notebooksV4.py
python 00_datasets_referencia/unifica_notebooks_com_underline_csv.py
python 00_datasets_referencia/main_processsamento.py
```

**Estágio 01 – Extração Reddit (requer PRAW):**
```bash
python 01_extracao_conversas/src/extractors/extrator_postagem_reddit_sem_comentarios_V11.py
python 01_extracao_conversas/src/extractors/carregador_comentarios_para_brutos.py
```

**Estágio 02 – Limpeza técnica:**
```bash
python 02_preprocessamento/_0_limpeza_exclus_definic_corpus_V10.py
```

**Estágio 03 – NER & Sumarização:**
```bash
python 03_ner_e_resumo/ner_resumo_llama_3.1.py
# ou
python 03_ner_e_resumo/ner_resumo_granite_3.2.py
```

**Estágio 04 – Vetorização:**
```bash
python 04_vetorizacao/vetorizacao_multilingue_bge_m3_V3.py
```

**Estágio 05 – Consulta RAG:**
```python
from RAG_Temporal_V9_3 import SpecialistTimeAwareRAG

rag = SpecialistTimeAwareRAG("caminho/para/base_conhecimento_multilingueV9.json")
resultado = await rag.search(
    "What is the maximum RAM for Dell G15 5530?",
    ref_date="2026-06-23"
)
print(resultado["answer"])
```

**Estágio 06 – Avaliação comparativa:**
```bash
python 06_avaliacao_quantitativa/evaluate_deepeval_unified_comparative_Repete_N_Modelos_NVezesV6.py
```

---

## 🔬 Metodologia de Avaliação

A avaliação segue uma abordagem **LLM-as-a-Judge** com três suítes:

### Suíte Tradicional (`TRADITIONAL_TEST_SUITE`)
20 casos de Q&A com SKUs específicos, medidos por métricas DeepEval nativas:
- **Faithfulness** – fidelidade ao contexto recuperado
- **Answer Relevancy** – relevância da resposta
- **Contextual Relevancy / Precision / Recall** – qualidade da recuperação

### Suíte Comportamental (`BEHAVIORAL_TEST_SUITE`)
9 casos que verificam o cumprimento das regras operacionais (SKU-Lock, fallback honesto, saída limpa). Avaliada por três métricas G-Eval:
- **Mixed Guardrails** – detecção de tipo de query e cumprimento das regras
- **Temporal Reranking Enforcement** – resistência à obsolescência
- **Smart Fallback Triggering** – honestidade quando falta documentação

### Suíte Temporal (`CHRONOQA_TEMPORAL_SUITE`)
20 casos inspirados no benchmark ChronoQA, cobrindo:
- Perguntas **absolutas** ("em março de 2024...")
- **Agregadas** (contagens)
- **Relativas** ("último modelo com...")
- **Comparativas** entre gerações
- **Futuras** (deve recusar especular)
- **Atemporais** (conceitos que não envelhecem)

Cada caso é repetido **N vezes** (padrão: 10) para medir estabilidade. O script principal compara **V1 (Vanilla)** contra **V9 (Temporal)** e gera relatórios em CSV, TXT e Markdown na pasta `06_avaliacao_quantitativa/`.

---

## 📊 Estrutura dos Relatórios

Após a avaliação, são gerados três arquivos por combinação (juiz, gerador):

- `DEEPEVAL_MIXED_NATIVE_COMPARATIVE_COM_REPETICAO_*.csv` – dados brutos com todas as métricas, scores, razões e verbose logs.
- `RELATORIO_COMPARATIVO_COM_REPETICAO_*.txt` – relatório legível com fórmulas de cálculo passo a passo.
- `RELATORIO_COMPARATIVO_COM_REPETICAO_*.md` – versão Markdown com tabelas-resumo.

---

## 🧩 Notas para Futuros Mantenedores

### Arquitetura de Prompts

Os prompts ficam em `05_validacao_time_aware/*.json`. Para criar uma nova variante:
1. Copie `prompt_rag_temporal_hybrid_V9.json`.
2. Altere `system_role` e `constraints`.
3. Passe o novo nome via `variant_name` no construtor de `SpecialistTimeAwareRAG`.

### Adicionando Novos SKUs ao Dataset Canônico

Edite `mapeamento_arquivos_aprimorado.json` e re-execute os scripts do Estágio 00. O `mapeamento_nome_modelos.py` fará o match automático entre os nomes originais e o dataset unificado.

### Trocando o Modelo Juiz

Em `06_avaliacao_quantitativa/evaluate_deepeval_unified_comparative_Repete_N_Modelos_NVezesV6.py`, o parâmetro `evaluator_model` no `EvalConfig` controla o juiz. Recomenda-se usar famílias diferentes entre juiz e gerador (evita auto-preferência).

### Onde Está o "Segredo" do SKU-Lock

O SKU-Lock é implementado em **duas camadas**:
1. **Prompt** (`constraints` no JSON) – instrui o LLM a pedir o SKU em queries de série.
2. **Detector** (`QueryExpander.has_specific_sku` em `RAG_Temporal_V9_3.py`) – bloqueia expansão de query quando detecta padrão de SKU.

Se quiser reforçar o bloqueio, adicione padrões regex em `sku_patterns`.

### Persistência de Checkpoints

A etapa de NER usa checkpoints em `03_ner_e_resumo/checkpoints_*` para evitar reprocessar. Para forçar reprocessamento, apague os arquivos `*.json` dessa pasta.

### Limitações Conhecidas

- **VRAM restrita**: o pipeline foi otimizado para 4 GB. Em GPUs maiores, aumente `MAX_CONCURRENT` em `ner_resumo_llama_3.1.py`.
- **Dependência do Ollama**: a engine não roda sem o servidor local do Ollama ativo.
- **Base vetorial estática**: novas discussões exigem re-vetorização completa (Etapa 04).

---

## 🛠️ Stack Tecnológico

| Camada | Tecnologia |
|---|---|
| **Linguagem** | Python 3.12.10 |
| **LLMs locais** | Ollama (granite3.2, llama3.1, phi3.5, qwen3, bge-m3) |
| **Indexação vetorial** | FAISS (IndexFlatL2, 1024 dim) |
| **Processamento de dados** | Pandas, NumPy, ijson |
| **Avaliação** | DeepEval com juiz LLM customizado |
| **Extração** | PRAW (Reddit API) + AsyncIO |
| **Comunicação assíncrona** | asyncio + aiofiles + semáforos |

---

## ⚖️ Licença e Anonimização

Este repositório foi originalmente preparado para **avaliação por pares em regime Double-Blind**. A versão atual é a **versão de defesa**, apresentada publicamente para a banca do TCC intitulado:

> *Recuperação Aumentada por Geração com Consciência Temporal para Suporte Técnico de Hardware*

Após a defesa, o código é disponibilizado para consulta e extensão acadêmica. Citações ao trabalho devem referenciar o autor e a instituição conforme ficha catalográfica oficial.

---

## 📚 Referências Centrais do Trabalho

- **Lewis et al. (2020)** – *Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks* (NeurIPS).
- **Es et al. (2023)** – *RAGAS: Automated Evaluation of Retrieval Augmented Generation*.
- **Chen et al. (2024)** – *ChronoQA: A Benchmark for Temporal Reasoning in QA* (inspiração para a suíte temporal).
- **Liu et al. (2023)** – *Lost in the Middle: How Language Models Use Long Contexts*.
- **Documentação DeepEval** – https://docs.confident-ai.com/

---

## ✉️ Contato e Suporte

Para dúvidas sobre o código ou para reportar problemas de reprodução, abra uma *issue* neste repositório. Para questões acadêmicas, consulte a ficha catalográfica do TCC na biblioteca institucional.