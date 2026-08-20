import json
import pandas as pd
import re
import datetime
import asyncio
import aiofiles # pip install aiofiles para escrita de arquivos async
from pathlib import Path
from tqdm.asyncio import tqdm 

# Importando suas configurações de caminhos
from core.paths import EXTRACAO_DATA, DATASET_FINAL_CSV
# Importe sua classe assíncrona (ajuste o nome do arquivo/classe conforme sua estrutura)
from extractors.reddit_serviceV8 import RedditServiceV8Async 

DIRETORIO_BRUTO = EXTRACAO_DATA / 'brutoV4'
CAMINHO_ENTRADA_CSV = DATASET_FINAL_CSV / 'dataset_laptops_GAMER_ONLY_V2.csv'

class ExtractionUtils:
    @staticmethod
    def limpar_nome_arquivo(nome):
        """Evita erros de sistema de arquivos com nomes de modelos."""
        nome_limpo: str = re.sub(r'[\\/*?:"<>|]', '_', str(nome))
        return nome_limpo.strip().replace(' ', '_')

class RedditExtractionPipelineAsync:
    def __init__(self, limite=None, max_concurrency=4, time_filter="all"):
        self.limite = limite
        self.time_filter = time_filter 
        self.utils = ExtractionUtils()
        
        # O Semáforo controla quantos modelos são pesquisados simultaneamente
        # para evitar bloqueios por excesso de conexões (429)
        self.semaphore = asyncio.Semaphore(max_concurrency)
        
        DIRETORIO_BRUTO.mkdir(parents=True, exist_ok=True)

    def preparar_tarefas(self):
        """Filtra notebooks já processados para permitir retomada."""
        df = pd.read_csv(CAMINHO_ENTRADA_CSV)
        if self.limite:
            df = df.head(self.limite)
            
        tarefas_pendentes = []
        for _, row in df.iterrows():
            nome_arq = f"{self.utils.limpar_nome_arquivo(row['id_unico'])}.json"
            if not (DIRETORIO_BRUTO / nome_arq).exists():
                tarefas_pendentes.append({
                    'modelo_limpo': row['modelo_limpo'], 
                    'id_unico': row['id_unico']
                })
        
        print(f"✅ Total no CSV: {len(df)} | 🚀 Pendentes: {len(tarefas_pendentes)}")
        return tarefas_pendentes

    async def processar_modelo(self, service, tarefa):
        """Worker Assíncrono: Gerencia a busca e o salvamento com trava de concorrência."""
        async with self.semaphore:
            id_notebook = tarefa['id_unico']
            modelo_original = str(tarefa['modelo_limpo'])
            
            # Limpeza de SKU
            modelo_busca = re.sub(r'-[a-z0-9]{5,}', '', modelo_original)
            modelo_busca = re.sub(r'\bgaming\b', '', modelo_busca, flags=re.IGNORECASE)
            
            termos = modelo_busca.split()
            modelo_busca = " ".join(termos[:4]) if len(termos) > 4 else " ".join(termos)
            query_final = modelo_busca.strip()

            # NOVO: Mostra quando começa a processar um modelo
            print(f"\n{'='*60}")
            print(f"🎯 Iniciando: {id_notebook}")
            print(f"   Query: '{query_final}'")
            print(f"{'='*60}")

            try:
                # Chamada assíncrona ao serviço
                posts = await service.buscar_modelo(query_final, time_filter=self.time_filter)
                
                if not posts:
                    print(f"⏭️  Nenhum post encontrado para: {id_notebook}")
                    return id_notebook

                # Coleta metadados da API de forma assíncrona
                limites = await service.consultar_limites_api()

                resultado = {
                    "modelo_original": modelo_original,
                    "modelo_busca_utilizado": query_final,
                    "id_notebook": id_notebook,
                    "data_extracao": datetime.datetime.now().timestamp(), 
                    "config_time_filter": self.time_filter,
                    "api_health_at_extraction": limites,
                    "total_posts_encontrados": len(posts),
                    "posts": posts 
                }

                # Escrita de arquivo assíncrona
                nome_arquivo = f"{self.utils.limpar_nome_arquivo(id_notebook)}.json"
                async with aiofiles.open(DIRETORIO_BRUTO / nome_arquivo, mode='w', encoding='utf-8') as f:
                    await f.write(json.dumps(resultado, ensure_ascii=False, indent=4))
                
                # NOVO: Confirmação de salvamento
                print(f"💾 Salvo: {nome_arquivo} ({len(posts)} posts)")
                    
            except Exception as e:
                print(f"\n{'!'*60}")
                print(f"❌ ERRO CRÍTICO em {id_notebook}")
                print(f"   Query: {query_final}")
                print(f"   Erro: {e}")
                print(f"{'!'*60}")
            
            return id_notebook

    async def executar(self):
        tarefas = self.preparar_tarefas()
        if not tarefas:
            return

        # Inicializa o serviço usando o context manager assíncrono (__aenter__)
        async with RedditServiceV8Async() as service:
            # Cria a lista de corrotinas
            tasks = [self.processar_modelo(service, t) for t in tarefas]
            
            # Executa com barra de progresso adaptada para asyncio
            for f in tqdm.as_completed(tasks, total=len(tasks), desc="🔥 Extraindo (Async)"):
                await f

if __name__ == "__main__":
    # Inicia o loop de eventos do Python
    pipeline = RedditExtractionPipelineAsync(limite=None, max_concurrency=4, time_filter="all")
    asyncio.run(pipeline.executar())