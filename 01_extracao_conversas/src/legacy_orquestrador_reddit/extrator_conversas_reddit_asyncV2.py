import json
import pandas as pd
import re
import datetime
import asyncio
import aiofiles
from pathlib import Path
from tqdm.asyncio import tqdm 

# Importando suas configurações de caminhos
from core.paths import EXTRACAO_DATA, DATASET_FINAL_CSV
from extractors.reddit_serviceV8 import RedditServiceV8Async 

DIRETORIO_BRUTO = EXTRACAO_DATA / 'brutoV4'
DIRETORIO_LOGS = EXTRACAO_DATA / 'logs'  # NOVO: diretório para logs
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
        
        self.semaphore = asyncio.Semaphore(max_concurrency)
        
        DIRETORIO_BRUTO.mkdir(parents=True, exist_ok=True)
        DIRETORIO_LOGS.mkdir(parents=True, exist_ok=True)  # NOVO: criar diretório de logs
        
        # NOVO: Inicializa listas para tracking
        self.modelos_sem_resultados = []
        self.modelos_com_erro = []
        self.modelos_sucesso = []
        self.start_time = None

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
                    'id_unico': row['id_unico'],
                    # NOVO: Adiciona mais informações do CSV se disponíveis
                    'marca': row.get('marca', 'N/A'),
                    'modelo_completo': row.get('modelo_completo', row['modelo_limpo'])
                })
        
        print(f"✅ Total no CSV: {len(df)} | 🚀 Pendentes: {len(tarefas_pendentes)}")
        return tarefas_pendentes

    async def processar_modelo(self, service, tarefa):
        """Worker Assíncrono: Gerencia a busca e o salvamento com trava de concorrência."""
        async with self.semaphore:
            id_notebook = tarefa['id_unico']
            modelo_original = str(tarefa['modelo_limpo'])
            marca = tarefa.get('marca', 'N/A')
            modelo_completo = tarefa.get('modelo_completo', modelo_original)
            
            # Limpeza de SKU
            modelo_busca = re.sub(r'-[a-z0-9]{5,}', '', modelo_original)
            modelo_busca = re.sub(r'\bgaming\b', '', modelo_busca, flags=re.IGNORECASE)
            
            termos = modelo_busca.split()
            modelo_busca = " ".join(termos[:4]) if len(termos) > 4 else " ".join(termos)
            query_final = modelo_busca.strip()

            # NOVO: ID curto para logs
            id_curto = id_notebook[:30] if len(id_notebook) > 30 else id_notebook
            
            # NOVO: Linha separadora mais compacta
            print(f"\n{'─'*50}")
            print(f"🎯 [{id_curto}] Query: '{query_final}'")

            try:
                # NOVO: Passa o ID para o serviço usar nos logs
                posts = await service.buscar_modelo(query_final, time_filter=self.time_filter, task_id=id_curto)
                
                if not posts:
                    info_falta = {
                        "id_unico": id_notebook,
                        "modelo_original": modelo_original,
                        "query_utilizada": query_final,
                        "marca": marca,
                        "modelo_completo": modelo_completo,
                        "timestamp": datetime.datetime.now().isoformat(),
                        "time_filter": self.time_filter,
                        "motivo": "Nenhum post encontrado com comentários válidos"
                    }
                    self.modelos_sem_resultados.append(info_falta)
                    await self.salvar_progresso_parcial()
                    return id_notebook

                # Coleta metadados da API de forma assíncrona
                limites = await service.consultar_limites_api()

                resultado = {
                    "modelo_original": modelo_original,
                    "modelo_busca_utilizado": query_final,
                    "id_notebook": id_notebook,
                    "marca": marca,
                    "modelo_completo": modelo_completo,
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
                
                self.modelos_sucesso.append({
                    "id_unico": id_notebook,
                    "query_utilizada": query_final,
                    "total_posts": len(posts),
                    "arquivo": nome_arquivo
                })
                print(f"💾 Salvo: {nome_arquivo}")
                    
            except Exception as e:
                info_erro = {
                    "id_unico": id_notebook,
                    "modelo_original": modelo_original,
                    "query_utilizada": query_final,
                    "marca": marca,
                    "modelo_completo": modelo_completo,
                    "timestamp": datetime.datetime.now().isoformat(),
                    "erro": str(e),
                    "tipo_erro": type(e).__name__
                }
                self.modelos_com_erro.append(info_erro)
                print(f"❌ ERRO: {str(e)[:100]}")
            
            return id_notebook
        
    
    async def salvar_progresso_parcial(self):
        """Salva progresso parcial a cada 50 modelos processados."""
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if len(self.modelos_sem_resultados) > 0 and len(self.modelos_sem_resultados) % 50 == 0:
            arquivo_parcial = DIRETORIO_LOGS / f"sem_resultados_parcial_{timestamp}.json"
            with open(arquivo_parcial, 'w', encoding='utf-8') as f:
                json.dump({
                    "data_extracao": datetime.datetime.now().isoformat(),
                    "total_ate_agora": len(self.modelos_sem_resultados),
                    "modelos": self.modelos_sem_resultados
                }, f, ensure_ascii=False, indent=4)
            print(f"\n📋 Progresso parcial salvo: {len(self.modelos_sem_resultados)} sem resultados")

    def salvar_relatorios(self):
        """NOVO: Salva relatórios detalhados dos modelos não encontrados e erros."""
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 1. Relatório de modelos sem resultados
        if self.modelos_sem_resultados:
            arquivo_faltas = DIRETORIO_LOGS / f"modelos_sem_resultados_{timestamp}.json"
            with open(arquivo_faltas, 'w', encoding='utf-8') as f:
                json.dump({
                    "data_extracao": datetime.datetime.now().isoformat(),
                    "total_modelos_sem_resultados": len(self.modelos_sem_resultados),
                    "time_filter_utilizado": self.time_filter,
                    "modelos": self.modelos_sem_resultados
                }, f, ensure_ascii=False, indent=4)
            
            # Também salva como CSV para fácil análise
            df_faltas = pd.DataFrame(self.modelos_sem_resultados)
            csv_faltas = DIRETORIO_LOGS / f"modelos_sem_resultados_{timestamp}.csv"
            df_faltas.to_csv(csv_faltas, index=False, encoding='utf-8')
            
            print(f"\n📋 Relatório de modelos sem resultados:")
            print(f"   Total: {len(self.modelos_sem_resultados)}")
            print(f"   JSON: {arquivo_faltas}")
            print(f"   CSV:  {csv_faltas}")
        
        # 2. Relatório de erros
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
        
        # 3. Resumo geral da extração
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

        self.start_time = datetime.datetime.now()  # NOVO: marca início
        
        async with RedditServiceV8Async() as service:
            tasks = [self.processar_modelo(service, t) for t in tarefas]
            
            for f in tqdm.as_completed(tasks, total=len(tasks), desc="🔥 Extraindo (Async)"):
                await f
        
        # NOVO: Salva relatórios ao final
        self.salvar_relatorios()

if __name__ == "__main__":
    pipeline = RedditExtractionPipelineAsync(limite=None, max_concurrency=4, time_filter="all")
    asyncio.run(pipeline.executar())