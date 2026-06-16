# Relatório de Auditoria Comparativa Nativa (DeepEval)

- **Data de Execução:** 20260615_1812
- **Modelo Avaliador (Juiz):** `qwen3:4b-instruct`
- **Modelo Base RAG (Gerador):** `phi3.5:latest`
- **Total Interações Avaliadas:** Tradicionais (20) | Comportamentais (220)

## 📊 Tabela Resumo das Médias Consolidadas

| Métrica Base | Média V1 (Vanilla) | Média V9 (Temporal) | Variação Líquida |
|---|---|---|---|
| Faithfulness | 0.508 | 0.592 | 🟢 +0.083 |
| Answer_Relevancy | 0.700 | 0.615 | 🔴 -0.085 |
| Contextual_Relevancy | 0.429 | 0.429 | ⚪ +0.000 |
| Contextual_Precision | 1.000 | 1.000 | ⚪ +0.000 |
| Contextual_Recall | 1.000 | 1.000 | ⚪ +0.000 |
| **Behavioral Guardrails (G-Eval)** | 0.975 | 0.907 | 🔴 -0.068 |
