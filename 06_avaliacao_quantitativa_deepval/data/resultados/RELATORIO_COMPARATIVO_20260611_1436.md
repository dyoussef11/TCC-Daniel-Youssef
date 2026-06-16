# Relatório de Auditoria Comparativa Nativa (DeepEval)

- **Data de Execução:** 20260611_1436
- **Modelo Avaliador (Juiz):** `mistral:7b-instruct`
- **Modelo Base RAG (Gerador):** `qwen3.5:9b`
- **Fase Contextual:** Tradicionais (2) | Comportamentais (14)

## 📊 Tabela Resumo das Médias

| Métrica Base | Média V1 (Vanilla) | Média V9 (Temporal) | Variação Líquida |
|---|---|---|---|
| Faithfulness | 0.750 | 0.875 | 🟢 +0.125 |
| Answer_Relevancy | 0.833 | 0.333 | 🔴 -0.500 |
| Contextual_Relevancy | 0.467 | 0.467 | ⚪ +0.000 |
| Contextual_Precision | 1.000 | 1.000 | ⚪ +0.000 |
| Contextual_Recall | 1.000 | 1.000 | ⚪ +0.000 |
| **Behavioral Guardrails (G-Eval)** | 0.071 | 0.064 | ⚪ -0.007 |
