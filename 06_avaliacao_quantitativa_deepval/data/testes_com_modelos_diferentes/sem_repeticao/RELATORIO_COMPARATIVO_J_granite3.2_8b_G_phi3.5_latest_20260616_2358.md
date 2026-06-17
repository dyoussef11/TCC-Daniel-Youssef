# Relatório de Auditoria Comparativa Nativa (DeepEval)

- **Data de Execução:** 20260616_2358
- **Modelo Avaliador (Juiz):** `granite3.2:8b`
- **Modelo Base RAG (Gerador):** `phi3.5:latest`
- **Fase Contextual:** Tradicionais (20) | Comportamentais (14) | Temporais (20)

## 📊 Tabela Resumo das Médias

| Métrica Base | Média V1 (Vanilla) | Média V9 (Temporal) | Variação Líquida |
|---|---|---|---|
| Faithfulness | 0.579 | 0.526 | 🔴 -0.053 |
| Answer_Relevancy | 0.444 | 0.502 | 🟢 +0.057 |
| Contextual_Relevancy | 0.255 | 0.255 | ⚪ +0.000 |
| Contextual_Precision | 0.800 | 0.800 | ⚪ +0.000 |
| Contextual_Recall | 0.550 | 0.550 | ⚪ +0.000 |
| **Behavioral Guardrails (G-Eval)** | 0.800 | 0.750 | 🔴 -0.050 |
| **Temporal Consistency (G-Eval)** | 0.720 | 0.565 | 🔴 -0.155 |
