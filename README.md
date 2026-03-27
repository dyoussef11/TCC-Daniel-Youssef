# 💻 Specialist Time-Aware RAG Engine (Ollama + BGE-M3)

### Sistema de Recuperação de Conhecimento e Análise de Sentimento para Suporte Técnico

Este projeto consiste numa engine de **RAG (Retrieval-Augmented Generation)** de alta fidelidade, desenvolvida para processar e responder a dúvidas técnicas complexas sobre hardware. O sistema utiliza critérios de **temporalidade** e **regionalidade** para gerar respostas precisas, focando especialmente no ecossistema de portáteis de alto desempenho.

---

## ⚠️ Status do Ciclo de Vida do Projeto

* **`1 - Web Scraping` & `legacy/` [DESCONTINUADOS]:** As ferramentas de recolha ativa, incluindo o diretório `legacy/scrapy-sites`, foram oficialmente descontinuadas. O projeto transitou da fase de aquisição de dados para a fase de inteligência, processamento e validação.
* **Engine RAG [ATIVO]:** Desenvolvimento focado no motor de busca semântica, otimização de modelos locais e validação de prompts.
* **Base de Conhecimento [OBSERVAÇÃO]:** Embora fontes nacionais e oficiais tenham sido mapeadas no planeamento, **a base de dados atual integrada ao RAG é composta majoritariamente por dados extraídos do Reddit**.

---

## 🚀 Arquitetura e Fluxo de Dados

O pipeline transforma discussões orgânicas em respostas técnicas estruturadas, otimizadas para hardware de entrada.



### 1. Gestão de Dados (Camadas de Processamento)
A organização dos dados segue o fluxo de refinação:
* **Dados Brutos (Raw):** Conteúdo original extraído (JSON/CSV). Contém o ruído típico de fóruns e metadados brutos.
* **Dados Limpos e Processados:** Texto normalizado e enriquecido via NER (Named Entity Recognition), com identificação de GPUs, CPUs e modelos de notebooks.

### 2. Busca Semântica e Re-ranking Temporal
* **Vetorização (Embeddings):** Uso do modelo **BGE-M3** (1024 dimensões) via Ollama para capturar jargões técnicos.
* **Banco Vetorial:** Implementação via **FAISS** (`IndexFlatL2`) para buscas de alta performance.
* **Consciência Temporal:** Algoritmo que prioriza informações recentes, garantindo que soluções de hardware atuais tenham precedência sobre posts obsoletos.

### 3. IA Local e Otimização (Edge AI)
Validado numa **NVIDIA GTX 1050 Ti 4GB**, utilizando a família **Qwen 2.5 / 3**:
* **Quantização Q6_K:** Nível de compressão ideal para manter o rigor técnico sem exceder a VRAM da GPU.
* **Performance:** Respostas geradas entre 40s e 55s em ambiente totalmente offline.

---

## 📂 Organização do Ecossistema (Diretórios)

| Diretório | Descrição e Propósito |
| :--- | :--- |
| `0 - Dataset dos notebooks gamer` | Contém as "regras de ouro" (`hardware_rules.json`), mapeamentos de marcas e datasets de referência (Flipkart/Kruggle). |
| `2 - Processamento & NER` | Scripts de tratamento que preparam os dados brutos para a inteligência artificial. |
| `5 - RAG Engine` | Núcleo da aplicação: orquestração FAISS, dicionário de sinónimos e lógica de chat. |
| `legacy/` | Contém scripts e spiders de scraping antigos que não são mais utilizados na execução atual. |
| `scripts_e_beachmark/` | Ferramentas de medição de desempenho, contagem de modelos e testes de temperatura da GPU. |
| `Data/` | Armazena os índices vetoriais (`Vetorization`) e relatórios de performance (`Validation`). |

---

## 📊 Fontes de Conhecimento

A engine é alimentada primordialmente por:
* **Reddit (r/all):** Principal fonte ativa para problemas de hardware e experiências de upgrade.
* *Nota: Outras fontes (Dell, Asus, Adrenaline) permanecem mapeadas nos ficheiros de configuração, mas não estão integradas no dataset de teste atual do RAG.*

---

## ✅ Metodologia de Validação (TCC)
- [x] Transição de Scraping (Legacy) para Engine RAG Local.
- [x] Implementação de Re-ranking Temporal (Recency Bias).
- [x] Estudo de Viabilidade em Hardware Restrito (Benchmarking 1050 Ti).
- [x] Redução de Alucinações através de Prompts de "Rigor Técnico".

---
**Projeto desenvolvido para o estudo de LLMs aplicados à Recuperação de Informação e Suporte Técnico.**