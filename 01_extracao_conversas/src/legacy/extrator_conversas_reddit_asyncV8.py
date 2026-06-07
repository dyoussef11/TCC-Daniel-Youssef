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
# from extractors.reddit_serviceV10 import RedditServiceV10Async 
from extractors.reddit_serviceV10Backup import RedditServiceV10Async 

# =================================================================
# CONFIGURAÇÕES E PROCESSADOR
# =================================================================
# DIRETORIO_BRUTO = EXTRACAO_DATA / 'brutoV6'
# DIRETORIO_BRUTO = EXTRACAO_DATA / 'brutoV7'
# DIRETORIO_BRUTO = EXTRACAO_DATA / 'brutoV8'
DIRETORIO_BRUTO = EXTRACAO_DATA / 'brutoV9'
# DIRETORIO_BRUTO = EXTRACAO_DATA / 'brutoV10'
# DIRETORIO_LOGS = EXTRACAO_DATA / 'logs'
# DIRETORIO_LOGS = EXTRACAO_DATA / 'logs3'
DIRETORIO_LOGS = EXTRACAO_DATA / 'logs4'
# DIRETORIO_LOGS = EXTRACAO_DATA / 'logs5'

# CAMINHO_ENTRADA_CSV = DATASET_FINAL_CSV / 'dataset_laptops_UNICOS_V7.csv'
# CAMINHO_ENTRADA_CSV = DATASET_FINAL_CSV / 'dataset_laptops_UNICOS_V8.csv'
CAMINHO_ENTRADA_CSV = DATASET_FINAL_CSV / 'dataset_laptops_UNICOS_V10.csv'

class TextProcessor:
    @staticmethod
    def normalizar(texto):
        return unicodedata.normalize('NFKD', str(texto)).encode('ASCII', 'ignore').decode('ASCII')

    @staticmethod
    def limpar_nome_arquivo(nome):
        nome_limpo = re.sub(r'[\\/*?:"<>|]', '_', str(nome))
        return nome_limpo.strip().replace(' ', '_')

    @staticmethod
    def gerar_query_final(modelo_original, modelo_generico=None, modelo_busca_praw=None):
        """
        Gera query para busca no Reddit.
        PRIORIDADE: modelo_busca_praw > modelo_generico > modelo_original
        """
        # PRIORIDADE 1: Usar modelo_busca_praw (mais específico para busca)
        if modelo_busca_praw and str(modelo_busca_praw) != 'nan' and str(modelo_busca_praw).strip():
            query_base = TextProcessor.normalizar(str(modelo_busca_praw)).lower()
            # Remove underscores e normaliza
            query_base = query_base.replace('_', ' ').strip()
            return query_base
        
        # PRIORIDADE 2: Usar modelo_generico se disponível
        if modelo_generico and str(modelo_generico) != 'nan' and str(modelo_generico).strip():
            query_base = TextProcessor.normalizar(str(modelo_generico)).lower()
            query_base = query_base.replace('_', ' ').strip()
            return query_base
        
        # FALLBACK: Usar modelo_original (comportamento antigo)
        modelo = TextProcessor.normalizar(modelo_original).lower()
        mapa_familias = {
            "ga401": "Zephyrus G14", "ga503": "Zephyrus G15",
            "fx506": "TUF F15", "fx516": "TUF Dash F15",
            "15ach6": "IdeaPad Gaming 3", "15iah7": "IdeaPad Gaming 3"
        }
        for cod, nome in mapa_familias.items():
            if cod in modelo: 
                return nome.lower()
        
        # Remove palavras genéricas
        modelo = re.sub(r'\bgaming\b|\bnotebook\b|\blaptop\b', '', modelo).strip()
        query_parts = []
        for p in modelo.split():
            if len(query_parts) >= 3: 
                break
            if sum(c.isdigit() for c in p) > 4: 
                continue 
            query_parts.append(p)
        
        return " ".join(query_parts) if query_parts else modelo
    
    @classmethod
    def validar_presenca_modelo(cls, tarefa, posts):
        """
        Validação mais rigorosa:
        - Prioriza SKU completo
        - Exige pelo menos 2 identificadores para aceitar
        - Rejeita falsos positivos
        """
        modelo_alvo = cls.normalizar(str(tarefa['modelo_limpo'])).lower().replace('_', ' ')
        
        # Extrai SKU do modelo alvo (ex: "ga401", "15ach6")
        sku_alvo = None
        sku_match = re.search(r'\b([a-z0-9]{4,8})\b', modelo_alvo)
        if sku_match:
            sku_alvo = sku_match.group(1)
        
        # Palavras-chave principais (para fallback)
        palavras_principais = [p for p in modelo_alvo.split() if len(p) > 3 and not p.isdigit()]
        palavras_principais = palavras_principais[:2]  # No máximo 2 palavras principais
        
        filtrados = []
        
        for post in posts:
            comentarios_texto = " ".join([c['conteudo'].lower() for c in post.get('comentarios', [])])
            texto_completo = f"{post['titulo']} {post.get('selftext', '')} {comentarios_texto}".lower()
            
            # CRITÉRIO 1: SKU exato (mais confiável)
            if sku_alvo and sku_alvo in texto_completo:
                # Verifica se não é falso positivo (ex: "401" dentro de "1401")
                print(f"   ✓ Aceito por SKU: '{sku_alvo}' em post {post['id']}")
                if not any(char.isdigit() for char in sku_alvo) or len(sku_alvo) >= 4:
                    filtrados.append(post)
                    continue
            
            # CRITÉRIO 2: Pelo menos 2 palavras principais (para modelos sem SKU claro)
            if len(palavras_principais) >= 2:
                matches = sum(1 for palavra in palavras_principais if palavra in texto_completo)
                if matches >= 2:
                    filtrados.append(post)
                    continue
            
            # CRITÉRIO 3: Modelo completo + contexto (reduz falsos)
            if modelo_alvo in texto_completo and len(modelo_alvo) > 10:
                # Verifica se não é apenas menção genérica
                frases_genericas = ["looking for", "thinking about", "should i get"]
                if not any(gen in texto_completo for gen in frases_genericas):
                    filtrados.append(post)
        
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
        start_time = datetime.datetime.now()
        grupo_id = query_final[:50]  # Para visualização
        
        # HEADER VISUAL DO GRUPO
        await self.log(f"\n{'='*70}")
        await self.log(f"🎯 INICIANDO GRUPO: '{query_final}'")
        await self.log(f"   📦 Modelos no grupo: {len(tarefas_grupo)}")
        await self.log(f"   🕐 Início: {start_time.strftime('%H:%M:%S')}")
        await self.log(f"{'='*70}")
        
        try:
            # Busca Genérica (A "Rede")
            await self.log(f"🔍 Buscando termo: '{query_final}' no Reddit...")
            busca_start = datetime.datetime.now()
            
            posts, stats = await service.buscar_termo_generico(query_final, time_filter=self.time_filter)
            
            busca_end = datetime.datetime.now()
            busca_tempo = (busca_end - busca_start).total_seconds()
            
            await self.log(f"   ⏱️  Busca concluída em {busca_tempo:.1f}s | 📥 Posts brutos: {len(posts)}")
            
            self.total_posts_baixados += len(posts)
        except Exception as e:
            busca_tempo = (datetime.datetime.now() - start_time).total_seconds()
            await self.log(f"❌ ERRO no grupo '{query_final}' após {busca_tempo:.1f}s: {str(e)[:100]}")
            await self._registrar_erro_grupo(query_final, tarefas_grupo, e)
            return

        consolidados_grupo = 0
        if not posts:
            await self.log(f"⚠️ GRUPO VAZIO: '{query_final}' - Nenhum post encontrado na busca")
            self._registrar_vazio_grupo(query_final, tarefas_grupo)
        else:
            # Processa cada tarefa do grupo
            for idx, tarefa in enumerate(tarefas_grupo, 1):
                await self.log(f"   📝 Validando modelo {idx}/{len(tarefas_grupo)}: {tarefa['modelo_limpo'][:40]}...")
                posts_validados = TextProcessor.validar_presenca_modelo(tarefa, posts)
                
                if not posts_validados:
                    await self.log(f"      ❌ Sem posts válidos para este modelo")
                    self._registrar_vazio_individual(query_final, tarefa)
                    continue
                
                await self.log(f"      ✅ Encontrados {len(posts_validados)} posts válidos")
                await self._salvar_resultado(service, query_final, tarefa, posts_validados)
                consolidados_grupo += 1
        
        # FOOTER VISUAL DO GRUPO
        end_time = datetime.datetime.now()
        total_tempo = (end_time - start_time).total_seconds()
        status_icon = "✅" if consolidados_grupo > 0 else "⚠️"
        
        # Barra de progresso visual
        barra_len = 30
        proporcao = consolidados_grupo / len(tarefas_grupo) if tarefas_grupo else 0
        barra = "█" * int(proporcao * barra_len) + "░" * (barra_len - int(proporcao * barra_len))
        
        await self.log(f"\n{status_icon} FINALIZANDO GRUPO: '{query_final}'")
        await self.log(f"   ⏱️  Tempo total: {total_tempo:.1f}s (busca: {busca_tempo:.1f}s | validação: {total_tempo - busca_tempo:.1f}s)")
        await self.log(f"   📊 Aproveitamento: {barra} {consolidados_grupo}/{len(tarefas_grupo)} modelos")
        await self.log(f"   📈 Taxa: {(consolidados_grupo/len(tarefas_grupo)*100):.1f}%")
        await self.log(f"{'='*70}\n")
        
        await self.atualizar_logs_incremental()

    async def _salvar_resultado(self, service, query, tarefa, posts):
        id_notebook = tarefa['id_unico']
        resultado = {
            "modelo_original": tarefa['modelo_limpo'],
            "modelo_generico": tarefa.get('modelo_generico', ''),  # 🔥 NOVO CAMPO
            "query_usada": query,  # 🔥 NOVO: salva qual query foi usada
            "id_notebook": id_notebook,
            "total_posts": len(posts),
            "posts": posts
        }
        nome_arquivo = f"{TextProcessor.limpar_nome_arquivo(id_notebook)}.json"
        async with aiofiles.open(DIRETORIO_BRUTO / nome_arquivo, mode='w', encoding='utf-8') as f:
            await f.write(json.dumps(resultado, ensure_ascii=False, indent=4))
        self.modelos_sucesso.append({
            "id": id_notebook, 
            "query": query, 
            "modelo_generico": tarefa.get('modelo_generico', ''),
            "posts": len(posts)
        })

    def _registrar_vazio_grupo(self, query, tarefas):
        for t in tarefas:
            self.modelos_sem_resultados.append({"id_unico": t['id_unico'], "modelo": t['modelo_limpo'], "query": query, "motivo": "Busca genérica vazia"})

    def _registrar_vazio_individual(self, query, t):
        self.modelos_sem_resultados.append({"id_unico": t['id_unico'], "modelo": t['modelo_limpo'], "query": query, "motivo": "SKU não encontrado nos posts"})

    async def _registrar_erro_grupo(self, query, tarefas, erro):
        for t in tarefas:
            self.modelos_com_erro.append({"id_unico": t['id_unico'], "query": query, "erro": str(erro)})


    async def relatorio_resumido(self, pendentes, grupos):
        print("\n" + "="*60)
        print("📊 RELATÓRIO RESUMIDO DE PROCESSAMENTO")
        print("="*60)
        print(f"📌 Total de tarefas pendentes no início: {len(pendentes)}")
        print(f"📌 Total de grupos criados: {len(grupos)}")
        print(f"📌 Grupos processados até agora: {len(self.modelos_sucesso) + len(self.modelos_sem_resultados) + len(self.modelos_com_erro)}")
        print(f"   ├─ ✅ Grupos com sucesso: {len(set([s['query'] for s in self.modelos_sucesso])) if self.modelos_sucesso else 0}")
        print(f"   ├─ ⚠️  Grupos vazios: {len(set([s['query'] for s in self.modelos_sem_resultados])) if self.modelos_sem_resultados else 0}")
        print(f"   └─ ❌ Grupos com erro: {len(set([s['query'] for s in self.modelos_com_erro])) if self.modelos_com_erro else 0}")
        print(f"\n📌 Modelos individuais:")
        print(f"   ├─ ✅ Salvos: {len(self.modelos_sucesso)}")
        print(f"   ├─ ⚠️  Sem resultados: {len(self.modelos_sem_resultados)}")
        print(f"   └─ ❌ Com erro: {len(self.modelos_com_erro)}")
        print(f"\n🎯 Taxa de aproveitamento: {(len(self.modelos_sucesso)/len(pendentes)*100):.2f}%")
        print("="*60)

    async def executar(self):
        df = pd.read_csv(CAMINHO_ENTRADA_CSV)
        pendentes = [row.to_dict() for _, row in df.iterrows() if not (DIRETORIO_BRUTO / f"{TextProcessor.limpar_nome_arquivo(row['id_unico'])}.json").exists()]
        
        grupos = defaultdict(list)
        for t in pendentes:
            # 🔥 ALTERADO: Passa os três parâmetros
            query = TextProcessor.gerar_query_final(
                str(t.get('modelo_limpo', '')),           # modelo_original
                t.get('modelo_generico'),                 # modelo_generico
                t.get('modelo_busca_praw')                # 🔥 NOVO: modelo_busca_praw
            )
            grupos[query].append(t)

        print(f"\n🚀 INICIANDO EXTRAÇÃO: {len(grupos)} Grupos | {len(pendentes)} Tarefas")
        print(f"⏱️  Início global: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        global_start = datetime.datetime.now()
        grupos_processados = 0
        total_grupos = len(grupos)
        
        async with RedditServiceV10Async() as service:
            async def worker(q, tg):
                nonlocal grupos_processados
                async with self.semaphore:
                    await self.processar_grupo(service, q, tg)
                    grupos_processados += 1
                    # Relatório de progresso a cada 5 grupos
                    if grupos_processados % 5 == 0 or grupos_processados == total_grupos:
                        elapsed = (datetime.datetime.now() - global_start).total_seconds()
                        velocidade = grupos_processados / elapsed if elapsed > 0 else 0
                        print(f"\n📈 PROGRESSO GLOBAL: {grupos_processados}/{total_grupos} grupos | {velocidade:.2f} grupos/s | {elapsed:.1f}s decorridos\n")
            
            tasks = [worker(q, tg) for q, tg in grupos.items()]
            await tqdm.gather(*tasks, desc="🔥 Progresso")
        
        # Relatório final
        elapsed_total = (datetime.datetime.now() - global_start).total_seconds()
        print(f"\n{'='*70}")
        print(f"🏁 EXTRATOR FINALIZADO")
        print(f"   ⏱️  Tempo total: {elapsed_total:.1f}s ({elapsed_total/60:.1f}min)")
        print(f"   📊 Grupos processados: {grupos_processados}")
        print(f"   💾 Posts baixados: {self.total_posts_baixados}")
        print(f"{'='*70}\n")
        
        await self.relatorio_resumido(pendentes, grupos)

        


if __name__ == "__main__":
    pipeline = RedditExtractionPipelineAsync(limite=None, max_concurrency=6, time_filter="all")
    asyncio.run(pipeline.executar())