import json
import pandas as pd
import re
import datetime
import asyncio
import aiofiles
import unicodedata
from collections import defaultdict
from pathlib import Path
from tqdm.asyncio import tqdm 

from core.paths import EXTRACAO_DATA, DATASET_FINAL_CSV
from extractors.reddit_serviceV9 import RedditServiceV9Async 

DIRETORIO_BRUTO = EXTRACAO_DATA / 'brutoV6'
DIRETORIO_LOGS = EXTRACAO_DATA / 'logs'
CAMINHO_ENTRADA_CSV = DATASET_FINAL_CSV / 'dataset_laptops_GAMER_ONLY_V2.csv'

class ExtractionUtils:
    @staticmethod
    def limpar_nome_arquivo(nome):
        nome_limpo: str = re.sub(r'[\\/*?:"<>|]', '_', str(nome))
        return nome_limpo.strip().replace(' ', '_')

class RedditExtractionPipelineAsync:
    def __init__(self, limite=None, max_concurrency=4, time_filter="all"):
        self.limite = limite
        self.time_filter = time_filter 
        self.utils = ExtractionUtils()
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.print_lock = asyncio.Lock()  # para logs organizados
        
        DIRETORIO_BRUTO.mkdir(parents=True, exist_ok=True)
        DIRETORIO_LOGS.mkdir(parents=True, exist_ok=True)
        
        self.modelos_sem_resultados = []
        self.modelos_com_erro = []
        self.modelos_sucesso = []
        self.start_time = None

    async def log(self, *args, **kwargs):
        """Método seguro para imprimir sem entrelaçar logs."""
        async with self.print_lock:
            print(*args, **kwargs)

    @staticmethod
    def normalizar(texto):
        """Remove acentos, caracteres invisíveis e converte para ASCII."""
        return unicodedata.normalize('NFKD', str(texto)).encode('ASCII', 'ignore').decode('ASCII')

    @staticmethod
    def gerar_query_final(modelo_original):
        """Gera termo genérico removendo SKUs, números e caracteres especiais."""
        modelo = RedditExtractionPipelineAsync.normalizar(modelo_original)
        modelo = modelo.lower()
        modelo = re.sub(r'\bgaming\b', '', modelo, flags=re.IGNORECASE)
        # Remove palavras com 3+ dígitos consecutivos (ex.: códigos de modelo)
        modelo = re.sub(r'\b\w*\d{3,}\w*\b', '', modelo)
        # Remove pontuação e caracteres especiais
        modelo = re.sub(r'[^\w\s]', ' ', modelo)
        modelo = re.sub(r'\s+', ' ', modelo).strip()
        # Pega no máximo as 3 primeiras palavras significativas (ignorando palavras curtas ou só números)
        partes = modelo.split()
        partes_filtradas = [p for p in partes if len(p) > 2 and not p.isdigit()]
        return " ".join(partes_filtradas[:3]) if partes_filtradas else " ".join(partes[:3])

    def preparar_tarefas(self):
        df = pd.read_csv(CAMINHO_ENTRADA_CSV)
        if self.limite:
            df = df.head(self.limite)
            
        tarefas_pendentes = []
        for _, row in df.iterrows():
            nome_arq = f"{self.utils.limpar_nome_arquivo(row['id_unico'])}.json"
            if not (DIRETORIO_BRUTO / nome_arq).exists():
                tarefas_pendentes.append({
                    'modelo_limpo': row['modelo_limpo'], 
                    'id_unico': row['id_unico'],
                    'marca': row.get('marca', 'N/A'),
                    'modelo_completo': row.get('modelo_completo', row['modelo_limpo'])
                })
        
        print(f"✅ Total no CSV: {len(df)} | 🚀 Pendentes: {len(tarefas_pendentes)}")
        return tarefas_pendentes

    async def processar_grupo(self, service, query_final, tarefas_grupo):
        """Busca uma vez para o grupo e distribui posts entre os modelos do grupo."""
        await self.log(f"\n{'─'*50}")
        await self.log(f"🎯 Grupo: '{query_final}' ({len(tarefas_grupo)} modelos)")

        try:
            posts = await service.buscar_termo_generico(query_final, time_filter=self.time_filter)
        except Exception as e:
            # Erro na busca genérica – registra erro para todos os modelos do grupo
            for tarefa in tarefas_grupo:
                info_erro = {
                    "id_unico": tarefa['id_unico'],
                    "modelo_original": tarefa['modelo_limpo'],
                    "query_utilizada": query_final,
                    "marca": tarefa.get('marca', 'N/A'),
                    "modelo_completo": tarefa.get('modelo_completo', tarefa['modelo_limpo']),
                    "timestamp": datetime.datetime.now().isoformat(),
                    "erro": str(e),
                    "tipo_erro": type(e).__name__
                }
                self.modelos_com_erro.append(info_erro)
            await self.log(f"❌ ERRO na busca do grupo: {str(e)[:100]}")
            return

        if not posts:
            for tarefa in tarefas_grupo:
                info_falta = {
                    "id_unico": tarefa['id_unico'],
                    "modelo_original": tarefa['modelo_limpo'],
                    "query_utilizada": query_final,
                    "marca": tarefa.get('marca', 'N/A'),
                    "modelo_completo": tarefa.get('modelo_completo', tarefa['modelo_limpo']),
                    "timestamp": datetime.datetime.now().isoformat(),
                    "time_filter": self.time_filter,
                    "motivo": "Nenhum post encontrado com comentários válidos"
                }
                self.modelos_sem_resultados.append(info_falta)
            return

        # Para cada modelo, filtra os posts que mencionam o modelo_limpo original ou seu SKU
        for tarefa in tarefas_grupo:
            modelo_original_str = self.normalizar(str(tarefa['modelo_limpo'])).lower()
            # Extrai possível SKU (última parte alfanumérica, geralmente após último hífen)
            sku_match = re.search(r'[a-z0-9]+$', modelo_original_str)
            sku = sku_match.group() if sku_match else modelo_original_str.split()[-1]
            
            id_notebook = tarefa['id_unico']

            posts_filtrados = []
            for post in posts:
                texto = (post['titulo'] + ' ' + post.get('selftext', '')).lower()
                if modelo_original_str in texto or sku in texto:
                    posts_filtrados.append(post)

            if not posts_filtrados:
                info_falta = {
                    "id_unico": id_notebook,
                    "modelo_original": tarefa['modelo_limpo'],
                    "query_utilizada": query_final,
                    "marca": tarefa.get('marca', 'N/A'),
                    "modelo_completo": tarefa.get('modelo_completo', tarefa['modelo_limpo']),
                    "timestamp": datetime.datetime.now().isoformat(),
                    "time_filter": self.time_filter,
                    "motivo": "Modelo não encontrado nos posts do grupo"
                }
                self.modelos_sem_resultados.append(info_falta)
                continue

            # Prepara resultado e salva
            limites = await service.consultar_limites_api()
            resultado = {
                "modelo_original": tarefa['modelo_limpo'],
                "modelo_busca_utilizado": query_final,
                "id_notebook": id_notebook,
                "marca": tarefa.get('marca', 'N/A'),
                "modelo_completo": tarefa.get('modelo_completo', tarefa['modelo_limpo']),
                "data_extracao": datetime.datetime.now().timestamp(),
                "config_time_filter": self.time_filter,
                "api_health_at_extraction": limites,
                "total_posts_encontrados": len(posts_filtrados),
                "posts": posts_filtrados
            }

            nome_arquivo = f"{self.utils.limpar_nome_arquivo(id_notebook)}.json"
            async with aiofiles.open(DIRETORIO_BRUTO / nome_arquivo, mode='w', encoding='utf-8') as f:
                await f.write(json.dumps(resultado, ensure_ascii=False, indent=4))

            self.modelos_sucesso.append({
                "id_unico": id_notebook,
                "query_utilizada": query_final,
                "total_posts": len(posts_filtrados),
                "arquivo": nome_arquivo
            })
            await self.log(f"💾 Salvo: {nome_arquivo} ({len(posts_filtrados)} posts)")

        # Progresso parcial
        await self.salvar_progresso_parcial()

    async def salvar_progresso_parcial(self):
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        if len(self.modelos_sem_resultados) > 0 and len(self.modelos_sem_resultados) % 50 == 0:
            arquivo_parcial = DIRETORIO_LOGS / f"sem_resultados_parcial_{timestamp}.json"
            with open(arquivo_parcial, 'w', encoding='utf-8') as f:
                json.dump({
                    "data_extracao": datetime.datetime.now().isoformat(),
                    "total_ate_agora": len(self.modelos_sem_resultados),
                    "modelos": self.modelos_sem_resultados
                }, f, ensure_ascii=False, indent=4)
            await self.log(f"\n📋 Progresso parcial salvo: {len(self.modelos_sem_resultados)} sem resultados")

    def salvar_relatorios(self):
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if self.modelos_sem_resultados:
            arquivo_faltas = DIRETORIO_LOGS / f"modelos_sem_resultados_{timestamp}.json"
            with open(arquivo_faltas, 'w', encoding='utf-8') as f:
                json.dump({
                    "data_extracao": datetime.datetime.now().isoformat(),
                    "total_modelos_sem_resultados": len(self.modelos_sem_resultados),
                    "time_filter_utilizado": self.time_filter,
                    "modelos": self.modelos_sem_resultados
                }, f, ensure_ascii=False, indent=4)
            
            df_faltas = pd.DataFrame(self.modelos_sem_resultados)
            csv_faltas = DIRETORIO_LOGS / f"modelos_sem_resultados_{timestamp}.csv"
            df_faltas.to_csv(csv_faltas, index=False, encoding='utf-8')
            
            print(f"\n📋 Relatório de modelos sem resultados:")
            print(f"   Total: {len(self.modelos_sem_resultados)}")
            print(f"   JSON: {arquivo_faltas}")
            print(f"   CSV:  {csv_faltas}")
        
        if self.modelos_com_erro:
            arquivo_erros = DIRETORIO_LOGS / f"modelos_com_erro_{timestamp}.json"
            with open(arquivo_erros, 'w', encoding='utf-8') as f:
                json.dump({
                    "data_extracao": datetime.datetime.now().isoformat(),
                    "total_modelos_com_erro": len(self.modelos_com_erro),
                    "erros": self.modelos_com_erro
                }, f, ensure_ascii=False, indent=4)
            
            df_erros = pd.DataFrame(self.modelos_com_erro)
            csv_erros = DIRETORIO_LOGS / f"modelos_com_erro_{timestamp}.csv"
            df_erros.to_csv(csv_erros, index=False, encoding='utf-8')
            
            print(f"\n⚠️  Relatório de modelos com erro:")
            print(f"   Total: {len(self.modelos_com_erro)}")
            print(f"   JSON: {arquivo_erros}")
            print(f"   CSV:  {csv_erros}")
        
        tempo_total = datetime.datetime.now() - self.start_time if self.start_time else datetime.timedelta()
        resumo = {
            "data_extracao": datetime.datetime.now().isoformat(),
            "tempo_total": str(tempo_total),
            "time_filter": self.time_filter,
            "total_processados": len(self.modelos_sucesso) + len(self.modelos_sem_resultados) + len(self.modelos_com_erro),
            "sucesso": len(self.modelos_sucesso),
            "sem_resultados": len(self.modelos_sem_resultados),
            "com_erro": len(self.modelos_com_erro),
            "taxa_sucesso": f"{(len(self.modelos_sucesso) / max(1, len(self.modelos_sucesso) + len(self.modelos_sem_resultados) + len(self.modelos_com_erro))) * 100:.1f}%"
        }
        
        arquivo_resumo = DIRETORIO_LOGS / f"resumo_extracao_{timestamp}.json"
        with open(arquivo_resumo, 'w', encoding='utf-8') as f:
            json.dump(resumo, f, ensure_ascii=False, indent=4)
        
        print(f"\n{'='*60}")
        print(f"📊 RESUMO FINAL DA EXTRAÇÃO")
        print(f"{'='*60}")
        print(f"⏱️  Tempo total: {tempo_total}")
        print(f"✅ Sucesso: {resumo['sucesso']}")
        print(f"⏭️  Sem resultados: {resumo['sem_resultados']}")
        print(f"❌ Com erro: {resumo['com_erro']}")
        print(f"📈 Taxa de sucesso: {resumo['taxa_sucesso']}")
        print(f"{'='*60}")

    async def executar(self):
        tarefas = self.preparar_tarefas()
        if not tarefas:
            print("✅ Nenhuma tarefa pendente!")
            return

        # Agrupar por query_final
        grupos = defaultdict(list)
        for t in tarefas:
            query_final = self.gerar_query_final(str(t['modelo_limpo']))
            grupos[query_final].append(t)

        await self.log(f"\n🔁 Agrupamento: {len(tarefas)} tarefas em {len(grupos)} termos genéricos únicos")
        self.start_time = datetime.datetime.now()

        async with RedditServiceV9Async() as service:
            # Processa cada grupo com concorrência controlada pelo semáforo
            async def worker(query_final, tarefas_grupo):
                async with self.semaphore:
                    await self.processar_grupo(service, query_final, tarefas_grupo)

            tasks = [worker(qf, tf) for qf, tf in grupos.items()]
            for f in tqdm.as_completed(tasks, total=len(tasks), desc="🔥 Grupos"):
                await f

        self.salvar_relatorios()

if __name__ == "__main__":
    pipeline = RedditExtractionPipelineAsync(limite=None, max_concurrency=4, time_filter="all")
    asyncio.run(pipeline.executar())