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

# =================================================================
# CONFIGURAÇÕES E PROCESSADOR
# =================================================================
DIRETORIO_BRUTO = EXTRACAO_DATA / 'brutoV6'
DIRETORIO_LOGS = EXTRACAO_DATA / 'logs'
# CAMINHO_ENTRADA_CSV = DATASET_FINAL_CSV / 'dataset_laptops_GAMER_ONLY_V2.csv'
CAMINHO_ENTRADA_CSV = DATASET_FINAL_CSV / 'dataset_laptops_UNICOS_V5.csv'

class TextProcessor:
    @staticmethod
    def normalizar(texto):
        return unicodedata.normalize('NFKD', str(texto)).encode('ASCII', 'ignore').decode('ASCII')

    @staticmethod
    def limpar_nome_arquivo(nome):
        nome_limpo = re.sub(r'[\\/*?:"<>|]', '_', str(nome))
        return nome_limpo.strip().replace(' ', '_')

    @staticmethod
    def gerar_query_final(modelo_original):
        modelo = TextProcessor.normalizar(modelo_original).lower()
        mapa_familias = {
            "ga401": "Zephyrus G14", "ga503": "Zephyrus G15",
            "fx506": "TUF F15", "fx516": "TUF Dash F15",
            "15ach6": "IdeaPad Gaming 3", "15iah7": "IdeaPad Gaming 3"
        }
        for cod, nome in mapa_familias.items():
            if cod in modelo: return nome.lower()
        modelo = re.sub(r'\bgaming\b|\bnotebook\b|\blaptop\b', '', modelo).strip()
        query_parts = []
        for p in modelo.split():
            if len(query_parts) >= 3: break
            if sum(c.isdigit() for c in p) > 4: continue 
            query_parts.append(p)
        return " ".join(query_parts)

    @classmethod
    def validar_presenca_modelo(cls, tarefa, posts):
        modelo_alvo = cls.normalizar(str(tarefa['modelo_limpo'])).lower()
        sku_match = re.search(r'\b([a-z0-9]{4,6})\b', modelo_alvo)
        sku_base = sku_match.group(1) if sku_match else None
        
        filtrados = []
        for p in posts:
            texto_post = (p['titulo'] + ' ' + p.get('selftext', '')).lower()
            if modelo_alvo in texto_post or (sku_base and sku_base in texto_post):
                filtrados.append(p)
        return filtrados

# =================================================================
# ORQUESTRADOR COM LOGS VISUAIS
# =================================================================
class RedditExtractionPipelineAsync:
    def __init__(self, limite=None, max_concurrency=4, time_filter="all"):
        self.limite = limite
        self.time_filter = time_filter 
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.print_lock = asyncio.Lock()
        self.save_lock = asyncio.Lock()
        
        DIRETORIO_BRUTO.mkdir(parents=True, exist_ok=True)
        DIRETORIO_LOGS.mkdir(parents=True, exist_ok=True)
        
        self.modelos_sucesso = []
        self.modelos_sem_resultados = []
        self.modelos_com_erro = []
        self.total_posts_baixados = 0
        self.start_time = datetime.datetime.now()
        self.session_id = self.start_time.strftime("%Y%m%d_%H%M%S")

    async def log(self, mensagem):
        async with self.print_lock:
            print(mensagem)

    async def atualizar_logs_incremental(self):
        async with self.save_lock:
            if self.modelos_sem_resultados:
                pd.DataFrame(self.modelos_sem_resultados).to_csv(DIRETORIO_LOGS / f"PROGRESSO_vazios_{self.session_id}.csv", index=False)
            if self.modelos_com_erro:
                pd.DataFrame(self.modelos_com_erro).to_csv(DIRETORIO_LOGS / f"PROGRESSO_erros_{self.session_id}.csv", index=False)

    async def processar_grupo(self, service, query_final, tarefas_grupo):
        try:
            # Busca Genérica (A "Rede")[cite: 6]
            posts, stats = await service.buscar_termo_generico(query_final, time_filter=self.time_filter)
            self.total_posts_baixados += len(posts)
        except Exception as e:
            await self._registrar_erro_grupo(query_final, tarefas_grupo, e)
            return

        consolidados_grupo = 0
        if not posts:
            self._registrar_vazio_grupo(query_final, tarefas_grupo)
        else:
            for tarefa in tarefas_grupo:
                posts_validados = TextProcessor.validar_presenca_modelo(tarefa, posts)
                if not posts_validados:
                    self._registrar_vazio_individual(query_final, tarefa)
                    continue
                
                await self._salvar_resultado(service, query_final, tarefa, posts_validados)
                consolidados_grupo += 1
        
        # LOG VISUAL DE CONSOLIDAÇÃO DO GRUPO
        status_icon = "✅" if consolidados_grupo > 0 else "⚠️"
        await self.log(f"{status_icon} GRUPO CONSOLIDADO: '{query_final}' | 📥 Baixados: {len(posts)} | 💎 Aproveitados: {consolidados_grupo}/{len(tarefas_grupo)} modelos")
        
        await self.atualizar_logs_incremental()

    async def _salvar_resultado(self, service, query, tarefa, posts):
        id_notebook = tarefa['id_unico']
        resultado = {
            "modelo_original": tarefa['modelo_limpo'], "id_notebook": id_notebook,
            "total_posts": len(posts), "posts": posts
        }
        nome_arquivo = f"{TextProcessor.limpar_nome_arquivo(id_notebook)}.json"
        async with aiofiles.open(DIRETORIO_BRUTO / nome_arquivo, mode='w', encoding='utf-8') as f:
            await f.write(json.dumps(resultado, ensure_ascii=False, indent=4))
        self.modelos_sucesso.append({"id": id_notebook, "query": query, "posts": len(posts)})

    def _registrar_vazio_grupo(self, query, tarefas):
        for t in tarefas:
            self.modelos_sem_resultados.append({"id_unico": t['id_unico'], "modelo": t['modelo_limpo'], "query": query, "motivo": "Busca genérica vazia"})

    def _registrar_vazio_individual(self, query, t):
        self.modelos_sem_resultados.append({"id_unico": t['id_unico'], "modelo": t['modelo_limpo'], "query": query, "motivo": "SKU não encontrado nos posts"})

    async def _registrar_erro_grupo(self, query, tarefas, erro):
        for t in tarefas:
            self.modelos_com_erro.append({"id_unico": t['id_unico'], "query": query, "erro": str(erro)})

    async def executar(self):
        df = pd.read_csv(CAMINHO_ENTRADA_CSV)
        pendentes = [row.to_dict() for _, row in df.iterrows() if not (DIRETORIO_BRUTO / f"{TextProcessor.limpar_nome_arquivo(row['id_unico'])}.json").exists()]
        
        grupos = defaultdict(list)
        for t in pendentes:
            grupos[TextProcessor.gerar_query_final(str(t['modelo_limpo']))].append(t)

        print(f"\n🚀 INICIANDO EXTRAÇÃO: {len(grupos)} Grupos | {len(pendentes)} Tarefas")
        
        async with RedditServiceV9Async() as service:
            async def worker(q, tg):
                async with self.semaphore: await self.processar_grupo(service, q, tg)
            tasks = [worker(q, tg) for q, tg in grupos.items()]
            await tqdm.gather(*tasks, desc="🔥 Progresso")

        # RESUMO FINAL CONSOLIDADO
        tempo_total = datetime.datetime.now() - self.start_time
        print(f"\n" + "="*50)
        print(f"📊 RELATÓRIO FINAL CONSOLIDADO")
        print(f"="*50)
        print(f"⏱️  Tempo Total: {tempo_total}")
        print(f"📥 Total de Posts analisados: {self.total_posts_baixados}")
        print(f"✅ Modelos salvos com sucesso: {len(self.modelos_sucesso)}")
        print(f"⚠️  Modelos sem correspondência: {len(self.modelos_sem_resultados)}")
        print(f"❌ Modelos com erro técnico: {len(self.modelos_com_erro)}")
        print(f"📈 Taxa de Aproveitamento: {(len(self.modelos_sucesso)/(len(pendentes) or 1))*100:.2f}%")
        print(f"="*50)

if __name__ == "__main__":
    pipeline = RedditExtractionPipelineAsync(limite=None, max_concurrency=4, time_filter="all")
    asyncio.run(pipeline.executar())