import shutil

from transformers import AutoModelForSequenceClassification, AutoTokenizer, pipeline
import os

from core.paths import MODELS

# Defina um caminho local no seu projeto
# Ex: C:/Users/Daniel Youssef/.../modelos/roberta_sentiment
model_path_obj = MODELS / "roberta_sentiment"
model_path_obj.mkdir(parents=True, exist_ok=True)
model_path = str(model_path_obj)

# 2. VERIFICAÇÃO DE INTEGRIDADE
# Se a pasta existe mas o arquivo de pesos não, deletamos para baixar de novo
weights_file = os.path.join(model_path, "model.safetensors")
if os.path.exists(model_path) and not os.path.exists(weights_file):
    print("📁 Pasta encontrada, mas sem pesos. Limpando para redownload...")
    shutil.rmtree(model_path)

# 3. DOWNLOAD OU CARREGAMENTO
if not os.path.exists(model_path):
    print("🚀 Baixando RoBERTa em formato seguro (Safetensors)...")
    model_name = "cardiffnlp/twitter-roberta-base-sentiment-latest"
    
    # Forçamos o uso de safetensors para ignorar a vulnerabilidade do torch.load
    model = AutoModelForSequenceClassification.from_pretrained(model_name, use_safetensors=True)
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    
    os.makedirs(model_path, exist_ok=True)
    model.save_pretrained(model_path)
    tokenizer.save_pretrained(model_path)
    print("✅ Modelo salvo com sucesso localmente!")
else:
    print("✅ Carregando modelo do disco local...")

# 4. INICIALIZAÇÃO DO PIPELINE
# Usando a 1050 Ti (device=0) para processar os comentários do Reddit
sentiment_task = pipeline(
    "sentiment-analysis", 
    model=model_path, 
    tokenizer=model_path, 
    device=0 
)

# 5. TESTE
exemplo = "It's been 30 mint my laptop is stuck in Black screen and not re-start 😭"
print(sentiment_task(exemplo))