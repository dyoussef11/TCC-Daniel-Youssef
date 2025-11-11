# Limpeza dos CSV unificados por tipo > script > 3_separate_datasets.py > ...
from pathlib import Path
import re # Mantido por consistência, embora não seja usado
import pandas as pd
# Importa o módulo de detecção (Mantido por consistência)
from langdetect import detect, DetectorFactory
import sys # Importado para uso do sys.path

# --- Configuração de Caminhos ---
# # 1. Obtém o caminho absoluto da pasta do script atual.
caminho_script = Path(__file__).resolve().parent

# # 2. Acessa a pasta raiz do projeto subindo dois níveis.
caminho_raiz_projeto = caminho_script.parent.parent

# # 3. Adiciona o caminho da raiz ao caminho de busca do Python.
sys.path.append(str(caminho_raiz_projeto))

# Tenta importar as variáveis de configuração
try:
    # Ajuste: A linha abaixo é simulada com base na foto.
    # from config import DIRETORIO_DADOS_LIMPEZA_DATASETS
    from config import DIRETORIO_DADOS_LIMPEZA_DATASETS 
except ImportError:
    print("Erro: Não foi possível importar diretórios de config.py.")
    sys.exit(1)

Coluna_texto = 'Conteudo_Comentario_Limpo'
# Garante que a detecção de idioma seja consistente (Mantido)
DetectorFactory.seed = 42

# ----------------------------------------------------------------------
## 📊 Análise de Tokens para Escolha do Modelo de Sumarização
# ----------------------------------------------------------------------

from transformers import AutoTokenizer

# 1. Carregar o Tokenizador
# O tokenizador do BERT Multilíngue é um padrão para PT-BR e EN.
tokenizer = AutoTokenizer.from_pretrained("bert-base-multilingual-cased")

# 2. Função para Contar Tokens
def contar_tokens(texto):
    if pd.isna(texto) or texto is None:
        return 0
    # O método encode conta o número de tokens.
    return len(tokenizer.encode(str(texto), truncation=False))

Lang_pt_br = 'PT_BR'
# 3. Simular Leitura do DataFrame (Substitua esta seção pela sua lógica real de leitura)
try:
    # Se você for ler um CSV:
    caminho_do_csv = DIRETORIO_DADOS_LIMPEZA_DATASETS / 'dataset_respostas_pt.csv'
    df = pd.read_csv(caminho_do_csv)

    # Verifica se a coluna de texto existe (Substitua 'texto_original' pelo nome real da sua coluna)
    if Coluna_texto not in df.columns:
        print("Erro: A coluna 'texto_original' não foi encontrada no DataFrame.")
        sys.exit(1)

except FileNotFoundError:
    print("Erro: Arquivo CSV não encontrado. Verifique o caminho.")
    sys.exit(1)
except Exception as e:
    print(f"Ocorreu um erro na leitura do DataFrame: {e}")
    sys.exit(1)


# 4. Aplicar a Contagem de Tokens no Dataset
# A conversão para string e a verificação de NaN são feitas dentro da função contar_tokens
print("Calculando o número de tokens para cada texto [{Lang_pt_br}]...")
df['num_tokens'] = df[Coluna_texto].apply(contar_tokens)


# 5. Calcular Estatísticas
media_tokens = df['num_tokens'].mean()
mediana_tokens = df['num_tokens'].median()
max_tokens = df['num_tokens'].max()
percentil_95 = df['num_tokens'].quantile(0.95)


# 6. Imprimir Resultados
print("\n" + "="*50)
print("### Resultados da Análise de Tokens do Dataset [ Lang_pt_br] ###")
print("="*50)

# Imprime as primeiras linhas com a contagem (opcional)
print("Amostra do DataFrame com a contagem de tokens:")
print(df[[Coluna_texto, 'num_tokens']].head())

print("\n--- Estatísticas Chave para Escolha do Modelo [{Lang_pt_br}] ---")
print(f"Média de Tokens por Texto: {media_tokens:.2f}")
print(f"Mediana de Tokens por Texto: {mediana_tokens:.2f}")
print(f"95º Percentil (95% dos textos são menores que): {percentil_95:.0f} tokens")
print(f"Máximo de Tokens por Texto (O fator decisivo): {max_tokens:.0f} tokens")
print("="*50)
print("\nDecisão de Modelo:")
if max_tokens > 16384:
    print("=> RECOMENDAÇÃO: Use modelos de contexto longo (GPT-4, Gemini 1.5, Claude 3) ou Map-Reduce.")
elif max_tokens > 4096:
    print("=> RECOMENDAÇÃO: Use modelos como Llama 3 ou LED, ou implemente Map-Reduce para segurança.")
else:
    print("=> RECOMENDAÇÃO: Modelos padrão (BART, T5, BERTimbau) são suficientes para sumarização direta.")

try:
    # Se você for ler um CSV:
    caminho_do_csv = DIRETORIO_DADOS_LIMPEZA_DATASETS / 'dataset_respostas_en.csv'
    df = pd.read_csv(caminho_do_csv)

    # Verifica se a coluna de texto existe (Substitua 'texto_original' pelo nome real da sua coluna)
    if Coluna_texto not in df.columns:
        print("Erro: A coluna 'texto_original' não foi encontrada no DataFrame.")
        sys.exit(1)

except FileNotFoundError:
    print("Erro: Arquivo CSV não encontrado. Verifique o caminho.")
    sys.exit(1)
except Exception as e:
    print(f"Ocorreu um erro na leitura do DataFrame: {e}")
    sys.exit(1)

Lang_en = 'EN'
# 4. Aplicar a Contagem de Tokens no Dataset
# A conversão para string e a verificação de NaN são feitas dentro da função contar_tokens
print("Calculando o número de tokens para cada texto[{Lang_en}]...")
df['num_tokens'] = df[Coluna_texto].apply(contar_tokens)


# 5. Calcular Estatísticas
media_tokens = df['num_tokens'].mean()
mediana_tokens = df['num_tokens'].median()
max_tokens = df['num_tokens'].max()
percentil_95 = df['num_tokens'].quantile(0.95)


# 6. Imprimir Resultados
print("\n" + "="*50)
print("### Resultados da Análise de Tokens do Dataset [{Lang_en}] ###")
print("="*50)

# Imprime as primeiras linhas com a contagem (opcional)
print("Amostra do DataFrame com a contagem de tokens:")
print(df[[Coluna_texto, 'num_tokens']].head())

print("\n--- Estatísticas Chave para Escolha do Modelo [{Lang_en}] ---")
print(f"Média de Tokens por Texto: {media_tokens:.2f}")
print(f"Mediana de Tokens por Texto: {mediana_tokens:.2f}")
print(f"95º Percentil (95% dos textos são menores que): {percentil_95:.0f} tokens")
print(f"Máximo de Tokens por Texto (O fator decisivo): {max_tokens:.0f} tokens")
print("="*50)
print("\nDecisão de Modelo:")
if max_tokens > 16384:
    print("=> RECOMENDAÇÃO: Use modelos de contexto longo (GPT-4, Gemini 1.5, Claude 3) ou Map-Reduce.")
elif max_tokens > 4096:
    print("=> RECOMENDAÇÃO: Use modelos como Llama 3 ou LED, ou implemente Map-Reduce para segurança.")
else:
    print("=> RECOMENDAÇÃO: Modelos padrão (BART, T5, BERTimbau) são suficientes para sumarização direta.")