# Relatório de Auditoria Comparativa Nativa (DeepEval)

- **Data de Execução:** 20260616_2211
- **Modelo Avaliador (Juiz):** `qwen3:4b-instruct`
- **Modelo Base RAG (Gerador):** `phi3.5:latest`
- **Fase Contextual:** Tradicionais (20) | Comportamentais (14) | Temporais (20)

## 📊 Tabela Resumo das Médias

| Métrica Base | Média V1 (Vanilla) | Média V9 (Temporal) | Variação Líquida |
|---|---|---|---|
| Faithfulness | 0.719 | 0.677 | 🔴 -0.042 |
| Answer_Relevancy | 0.850 | 0.746 | 🔴 -0.104 |
| Contextual_Relevancy | 0.343 | 0.343 | ⚪ +0.000 |
| Contextual_Precision | 0.408 | 0.408 | ⚪ +0.000 |
| Contextual_Recall | 0.500 | 0.500 | ⚪ +0.000 |
| **Behavioral Guardrails (G-Eval)** | 0.943 | 0.836 | 🔴 -0.107 |
| **Temporal Consistency (G-Eval)** | 0.900 | 0.775 | 🔴 -0.125 |
