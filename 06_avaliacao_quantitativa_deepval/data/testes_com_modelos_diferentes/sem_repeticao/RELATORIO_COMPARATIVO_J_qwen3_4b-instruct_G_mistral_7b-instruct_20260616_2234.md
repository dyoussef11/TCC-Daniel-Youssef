# Relatório de Auditoria Comparativa Nativa (DeepEval)

- **Data de Execução:** 20260616_2234
- **Modelo Avaliador (Juiz):** `qwen3:4b-instruct`
- **Modelo Base RAG (Gerador):** `mistral:7b-instruct`
- **Fase Contextual:** Tradicionais (20) | Comportamentais (14) | Temporais (20)

## 📊 Tabela Resumo das Médias

| Métrica Base | Média V1 (Vanilla) | Média V9 (Temporal) | Variação Líquida |
|---|---|---|---|
| Faithfulness | 0.699 | 0.706 | ⚪ +0.007 |
| Answer_Relevancy | 0.837 | 0.757 | 🔴 -0.080 |
| Contextual_Relevancy | 0.343 | 0.343 | ⚪ +0.000 |
| Contextual_Precision | 0.408 | 0.408 | ⚪ +0.000 |
| Contextual_Recall | 0.500 | 0.500 | ⚪ +0.000 |
| **Behavioral Guardrails (G-Eval)** | 0.950 | 0.871 | 🔴 -0.079 |
| **Temporal Consistency (G-Eval)** | 0.890 | 0.735 | 🔴 -0.155 |
