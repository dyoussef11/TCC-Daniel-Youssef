# Relatório de Auditoria Comparativa Nativa (DeepEval)

- **Data de Execução:** 20260611_1421
- **Modelo Avaliador (Juiz):** `qwen3:4b-instruct`
- **Modelo Base RAG (Gerador):** `mistral:7b-instruct`
- **Fase Contextual:** Tradicionais (2) | Comportamentais (14)

## 📊 Tabela Resumo das Médias

| Métrica Base | Média V1 (Vanilla) | Média V9 (Temporal) | Variação Líquida |
|---|---|---|---|
| Faithfulness | 0.833 | 0.400 | 🔴 -0.433 |
| Answer_Relevancy | 1.000 | 0.929 | 🔴 -0.071 |
| Contextual_Relevancy | 0.327 | 0.327 | ⚪ +0.000 |
| Contextual_Precision | 0.517 | 0.517 | ⚪ +0.000 |
| Contextual_Recall | 1.000 | 1.000 | ⚪ +0.000 |
| **Behavioral Guardrails (G-Eval)** | 0.914 | 0.229 | 🔴 -0.686 |
