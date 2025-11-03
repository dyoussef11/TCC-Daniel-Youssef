## Notebook-Forum-Sentimento 💻📊

Projeto de Processamento de Linguagem Natural (PNL) para Análise de Sentimento em dados de fóruns sobre notebooks. O estudo explora as polaridades (positiva/neutro/negativa) das respostas usando as técnicas de representação de texto TF-IDF e em diferentes modelos de classificação.

---

### ✅ Status: Web Scraping de Links (Etapas Concluídas)

Todas as tarefas de coleta de **links de discussão** e implementação da lógica de múltiplos modelos foram **finalizadas** para as seguintes fontes:

| Fórum / Comunidade | Idiomas | Status dos Links (CSV Gerado) |
| :--- | :--- | :--- |
| **Dell Community** | Português / Inglês | ✅ Gerados (`links_discussoes_Dell_Ingles.csv`, etc.) |
| **Clube do Hardware** | Português | ✅ Gerado (`links_discussoes_ClubeHardware.csv`) |
| **Adrenaline** | Português | ✅ Gerado (`links_discussoes_Adrenaline.csv`) |
| **Tom's Guide / Hardware** | Inglês | ✅ Gerados (`links_discussoes_Tom_Guide.csv`, etc.) |
| **Asus** | Português / Inglês | ✅ Gerados (`links_discussoes_Asus_Brasil.csv`, etc.) |
| **Acer** | Português / Inglês | ✅ Gerados (`links_discussoes_Acer_Ingles.csv`, etc.) |
| **HP** | Inglês | ✅ Lógica implementada. |
| **Lenovo** | Português / Inglês | ✅ Lógica implementada. |
| **Linus Tech Tips** | Inglês | ✅ Lógica implementada. |

---

### 📌 TODO: Próximas Etapas (Web Scraping de **Conversas**)

O objetivo principal agora é a **Extração de Perguntas e Respostas** (o conteúdo completo das discussões) a partir dos links coletados.

#### 1. Scripts de Web Scraping de Conversas (Prioridades)

* [ ] **Clube do Hardware**: **Necessita ser consertado** para funcionar corretamente. (O script de extração está em: `2 - Extração de Perguntas e Respostas\script`).
* [x] **Linus Tech Tips (Inglês)**: Está funcionando corretamente.
* [x] **Tom Guide (Inglês)**: Está funcionando corretamente.
* [x] **Tom Hardware (Inglês)**: Está funcionando corretamente.
* [] **Dell (Inglês)**: Está funcionando corretamente.
* [] **Dell (Portugues)**: Está funcionando corretamente.
* [] **Adrenaline (Portugues)**: Está funcionando corretamente.
* [] **Asus(Portugues)**: Está funcionando corretamente.
* [] **Asus(Portugues)**: Está funcionando corretamente.
* [] **Asus(Ingles)**: Está funcionando corretamente.
* [] **Acer(Ingles)**: Está funcionando corretamente.
* [] **Acer(Portugues)**: Está funcionando corretamente.
* [] **HP(Ingles)**: Está funcionando corretamente.
* [] **Lenovo(Ingles)**: Está funcionando corretamente.
* [] **Lenovo(Portugues)**: Está funcionando corretamente.


#### 2. Próximo Fluxo de Processamento (Após a Coleta)

A sequência de trabalho seguirá a estrutura de pastas do projeto após a conclusão da extração de todas as conversas:

* **2 - Extração de Perguntas e Respostas**: Gerar todos os CSVs de conversas completas.
* **3 - Unificação dos CSV**: Consolidar os dados coletados.
* **4 - Classificação de Perguntas**: Classificar perguntas para separar o foco nas respostas.
* **5 - Separação das respostas - Problemas**: Filtrar o dataset.
* ... (Continuação das etapas de limpeza, rotulagem e modelagem).