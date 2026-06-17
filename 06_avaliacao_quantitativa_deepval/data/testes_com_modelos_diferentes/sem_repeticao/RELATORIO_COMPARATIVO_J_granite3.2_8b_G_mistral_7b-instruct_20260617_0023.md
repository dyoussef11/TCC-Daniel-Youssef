# Relatório de Auditoria Comparativa Nativa (DeepEval)

- **Data de Execução:** 20260617_0023
- **Modelo Avaliador (Juiz):** `granite3.2:8b`
- **Modelo Base RAG (Gerador):** `mistral:7b-instruct`
- **Fase Contextual:** Tradicionais (20) | Comportamentais (14) | Temporais (20)

## 📊 Tabela Resumo das Médias

| Métrica Base | Média V1 (Vanilla) | Média V9 (Temporal) | Variação Líquida |
|---|---|---|---|
| Faithfulness | 0.508 | 0.504 | ⚪ -0.005 |
| Answer_Relevancy | 0.461 | 0.550 | 🟢 +0.089 |
| Contextual_Relevancy | 0.255 | 0.255 | ⚪ +0.000 |
| Contextual_Precision | 0.800 | 0.800 | ⚪ +0.000 |
| Contextual_Recall | 0.550 | 0.550 | ⚪ +0.000 |
| **Behavioral Guardrails (G-Eval)** | 0.807 | 0.757 | 🔴 -0.050 |
| **Temporal Consistency (G-Eval)** | 0.810 | 0.560 | 🔴 -0.250 |
