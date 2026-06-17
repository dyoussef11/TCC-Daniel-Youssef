# Relatório de Auditoria Comparativa Nativa (DeepEval)

- **Data de Execução:** 20260617_0048
- **Modelo Avaliador (Juiz):** `granite3.2:8b`
- **Modelo Base RAG (Gerador):** `qwen3.5:9b`
- **Fase Contextual:** Tradicionais (20) | Comportamentais (14) | Temporais (20)

## 📊 Tabela Resumo das Médias

| Métrica Base | Média V1 (Vanilla) | Média V9 (Temporal) | Variação Líquida |
|---|---|---|---|
| Faithfulness | 0.529 | 0.438 | 🔴 -0.092 |
| Answer_Relevancy | 0.420 | 0.512 | 🟢 +0.092 |
| Contextual_Relevancy | 0.255 | 0.255 | ⚪ +0.000 |
| Contextual_Precision | 0.800 | 0.800 | ⚪ +0.000 |
| Contextual_Recall | 0.550 | 0.550 | ⚪ +0.000 |
| **Behavioral Guardrails (G-Eval)** | 0.843 | 0.721 | 🔴 -0.121 |
| **Temporal Consistency (G-Eval)** | 0.765 | 0.525 | 🔴 -0.240 |
