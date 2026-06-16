# Relatório de Auditoria Comparativa Nativa (DeepEval)

- **Data de Execução:** 20260611_1452
- **Modelo Avaliador (Juiz):** `granite3.2:8b`
- **Modelo Base RAG (Gerador):** `mistral:7b-instruct`
- **Fase Contextual:** Tradicionais (2) | Comportamentais (14)

## 📊 Tabela Resumo das Médias

| Métrica Base | Média V1 (Vanilla) | Média V9 (Temporal) | Variação Líquida |
|---|---|---|---|
| Faithfulness | 0.583 | 0.583 | ⚪ +0.000 |
| Answer_Relevancy | 0.583 | 0.800 | 🟢 +0.217 |
| Contextual_Relevancy | 0.473 | 0.473 | ⚪ +0.000 |
| Contextual_Precision | 0.958 | 0.958 | ⚪ +0.000 |
| Contextual_Recall | 0.750 | 0.750 | ⚪ +0.000 |
| **Behavioral Guardrails (G-Eval)** | 0.421 | 0.207 | 🔴 -0.214 |
