# Relatório de Auditoria Comparativa Nativa (DeepEval)

- **Data de Execução:** 20260616_1302
- **Modelo Avaliador (Juiz):** `qwen3:4b-instruct`
- **Modelo Base RAG (Gerador):** `phi3:14b`
- **Fase Contextual:** Tradicionais (2) | Comportamentais (22)

## 📊 Tabela Resumo das Médias

| Métrica Base | Média V1 (Vanilla) | Média V9 (Temporal) | Variação Líquida |
|---|---|---|---|
| Faithfulness | 0.333 | 0.583 | 🟢 +0.250 |
| Answer_Relevancy | 0.833 | 0.575 | 🔴 -0.258 |
| Contextual_Relevancy | 0.429 | 0.429 | ⚪ +0.000 |
| Contextual_Precision | 1.000 | 1.000 | ⚪ +0.000 |
| Contextual_Recall | 1.000 | 1.000 | ⚪ +0.000 |
| **Behavioral Guardrails (G-Eval)** | 0.986 | 0.873 | 🔴 -0.114 |
