
import sys
import json
import pandas as pd
import re
import html
import time
import shutil
from pathlib import Path
from tqdm import tqdm 

# --- BOOTSTRAP DE CAMINHO DO PROJETO ---
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.paths import (

EXTRACAO_DATA,
DATASET_FINAL_CSV
)


from extractors.reddit_service import RedditService


DIRETORIO_BRUTO = EXTRACAO_DATA / 'bruto'
DIRETORIO_PROCESSADO = EXTRACAO_DATA / 'processado'
CAMINHO_ENTRADA_CSV = DATASET_FINAL_CSV / 'dataset_laptops_GAMER_ONLY.csv'
CAMINHO_SAIDA_JSON = DIRETORIO_PROCESSADO / 'reddit_notebook_dados_limpos.json'

# --- 3. SERVIÇO DE UTILITÁRIOS ---
class ExtractionUtils:
    @staticmethod
    def limpar_nome_arquivo(nome):
        """Remove caracteres proibidos pelo sistema operacional."""
        nome_limpo = re.sub(r'[\\/*?:"<>|]', '_', str(nome))
        return nome_limpo.strip().replace(' ', '_')

# --- 4. ORQUESTRADOR DA PIPELINE ---
class RedditExtractionPipeline:
    def __init__(self, limite=1):
        self.reddit = RedditService()
        self.limite = limite
        self.utils = ExtractionUtils()
        
        # Garante a existência das pastas de saída
        DIRETORIO_BRUTO.mkdir(parents=True, exist_ok=True)
        DIRETORIO_PROCESSADO.mkdir(parents=True, exist_ok=True)

    def preparar_tarefas(self):
        """Carrega os modelos do CSV respeitando o limite configurado."""
        print(f"📖 Lendo modelos de: {CAMINHO_ENTRADA_CSV.name}")
        df = pd.read_csv(CAMINHO_ENTRADA_CSV)
        
        if self.limite:
            print(f"⚠️ LIMITE ATIVADO: Processando apenas os primeiros {self.limite} notebooks.")
            df = df.head(self.limite)
            
        return df[['modelo_limpo', 'id_unico']].to_dict('records')

    def processar_modelo(self, tarefa):
        """Executa a busca para um modelo específico e salva o arquivo individual."""
        modelo = tarefa['modelo_limpo']
        id_notebook = tarefa['id_unico']
        
        # Busca via PRAW (agora com comentários e upvotes integrados no service)
        posts_encontrados = self.reddit.buscar_modelo(modelo)
        
        dados_modelo = {
            "modelo_referencia": str(modelo).lower(),
            "id_notebook": id_notebook,
            "total_posts": len(posts_encontrados),
            "posts": []
        }

        # Mapeamento e estruturação dos posts encontrados
        for post in posts_encontrados:
            post_limpo = post.copy()
            # Ajuste de chaves para compatibilidade com os scripts de NER
            post_limpo['titulo'] = post.get('titulo')
            post_limpo['conteudo_texto'] = post.get('texto')
            dados_modelo['posts'].append(post_limpo)

        # Salvamento individual (Checkpoint)
        nome_arquivo = f"{self.utils.limpar_nome_arquivo(id_notebook)}.json"
        with open(DIRETORIO_BRUTO / nome_arquivo, 'w', encoding='utf-8') as f:
            json.dump(dados_modelo, f, ensure_ascii=False, indent=4)
            
        return dados_modelo

    def executar(self):
        tarefas = self.preparar_tarefas()
        dados_consolidados = []
        
        pbar = tqdm(tarefas, desc="🚀 Extraindo Dados", unit="notebook")
        for tarefa in pbar:
            pbar.set_description(f"🔎 Buscando: {tarefa['modelo_limpo'][:20]}")
            try:
                resultado = self.processar_modelo(tarefa)
                dados_consolidados.append(resultado)
            except Exception as e:
                print(f"\n❌ Erro ao processar {tarefa['modelo_limpo']}: {e}")

        # Geração do arquivo final consolidado
        with open(CAMINHO_SAIDA_JSON, 'w', encoding='utf-8') as f:
            json.dump(dados_consolidados, f, ensure_ascii=False, indent=4)
        
        print(f"\n✅ Concluído! Arquivo final gerado: {CAMINHO_SAIDA_JSON.name}")

        # --- LIMPEZA DE CHECKPOINTS (DIRETÓRIO BRUTO) ---
        # if DIRETORIO_BRUTO.exists():
        #     print(f"🧹 Limpando arquivos temporários em: {DIRETORIO_BRUTO}")
        #     shutil.rmtree(DIRETORIO_BRUTO)

if __name__ == "__main__":
    # LIMITE_NOTEBOOKS: Altere para None para processar todo o CSV
    pipeline = RedditExtractionPipeline(limite=50)
    pipeline.executar()