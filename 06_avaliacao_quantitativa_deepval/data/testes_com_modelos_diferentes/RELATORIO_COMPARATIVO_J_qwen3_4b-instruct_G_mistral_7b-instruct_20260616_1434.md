# Relatório de Auditoria Comparativa Nativa (DeepEval)

- **Data de Execução:** 20260616_1434
- **Modelo Avaliador (Juiz):** `qwen3:4b-instruct`
- **Modelo Base RAG (Gerador):** `mistral:7b-instruct`
- **Fase Contextual:** Tradicionais (2) | Comportamentais (22)

## 📊 Tabela Resumo das Médias

| Métrica Base | Média V1 (Vanilla) | Média V9 (Temporal) | Variação Líquida |
|---|---|---|---|
| Faithfulness | 0.733 | 0.667 | 🔴 -0.067 |
| Answer_Relevancy | 0.733 | 0.575 | 🔴 -0.158 |
| Contextual_Relevancy | 0.429 | 0.429 | ⚪ +0.000 |
| Contextual_Precision | 1.000 | 1.000 | ⚪ +0.000 |
| Contextual_Recall | 1.000 | 1.000 | ⚪ +0.000 |
| **Behavioral Guardrails (G-Eval)** | 0.964 | 0.905 | 🔴 -0.059 |
