# Relatório de Auditoria Comparativa Nativa (DeepEval)

- **Data de Execução:** 20260617_0112
- **Modelo Avaliador (Juiz):** `granite3.2:8b`
- **Modelo Base RAG (Gerador):** `phi3:14b`
- **Fase Contextual:** Tradicionais (20) | Comportamentais (14) | Temporais (20)

## 📊 Tabela Resumo das Médias

| Métrica Base | Média V1 (Vanilla) | Média V9 (Temporal) | Variação Líquida |
|---|---|---|---|
| Faithfulness | 0.554 | 0.450 | 🔴 -0.104 |
| Answer_Relevancy | 0.437 | 0.551 | 🟢 +0.114 |
| Contextual_Relevancy | 0.255 | 0.255 | ⚪ +0.000 |
| Contextual_Precision | 0.800 | 0.800 | ⚪ +0.000 |
| Contextual_Recall | 0.550 | 0.550 | ⚪ +0.000 |
| **Behavioral Guardrails (G-Eval)** | 0.821 | 0.743 | 🔴 -0.079 |
| **Temporal Consistency (G-Eval)** | 0.725 | 0.515 | 🔴 -0.210 |
