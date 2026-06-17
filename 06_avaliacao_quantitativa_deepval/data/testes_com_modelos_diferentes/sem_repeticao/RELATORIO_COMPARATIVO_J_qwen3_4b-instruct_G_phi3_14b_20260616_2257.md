# Relatório de Auditoria Comparativa Nativa (DeepEval)

- **Data de Execução:** 20260616_2257
- **Modelo Avaliador (Juiz):** `qwen3:4b-instruct`
- **Modelo Base RAG (Gerador):** `phi3:14b`
- **Fase Contextual:** Tradicionais (20) | Comportamentais (14) | Temporais (20)

## 📊 Tabela Resumo das Médias

| Métrica Base | Média V1 (Vanilla) | Média V9 (Temporal) | Variação Líquida |
|---|---|---|---|
| Faithfulness | 0.712 | 0.698 | ⚪ -0.014 |
| Answer_Relevancy | 0.817 | 0.727 | 🔴 -0.090 |
| Contextual_Relevancy | 0.343 | 0.343 | ⚪ +0.000 |
| Contextual_Precision | 0.408 | 0.408 | ⚪ +0.000 |
| Contextual_Recall | 0.500 | 0.500 | ⚪ +0.000 |
| **Behavioral Guardrails (G-Eval)** | 0.929 | 0.821 | 🔴 -0.107 |
| **Temporal Consistency (G-Eval)** | 0.910 | 0.745 | 🔴 -0.165 |
