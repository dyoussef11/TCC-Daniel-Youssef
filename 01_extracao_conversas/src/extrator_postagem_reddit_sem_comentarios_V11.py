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
from extractors.reddit_serviceV13 import RedditServiceV13Async

# =================================================================
# CONFIGURAÇÕES
# =================================================================
DIRETORIO_BRUTO = EXTRACAO_DATA / "dados_brutos" / 'brutoV12'
DIRETORIO_LOGS = EXTRACAO_DATA / 'logs' / 'logs7'
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
        """Prioridade: modelo_busca_praw > modelo_generico > modelo_original"""
        if modelo_busca_praw and str(modelo_busca_praw).strip():
            query_base = TextProcessor.normalizar(str(modelo_busca_praw)).lower()
            query_base = query_base.replace('_', ' ').strip()
            return query_base

        if modelo_generico and str(modelo_generico).strip():
            query_base = TextProcessor.normalizar(str(modelo_generico)).lower()
            query_base = query_base.replace('_', ' ').strip()
            return query_base

        modelo = TextProcessor.normalizar(modelo_original).lower()
        modelo = re.sub(r'\bgaming\b|\bnotebook\b|\blaptop\b', '', modelo).strip()
        query_parts = []
        for p in modelo.split():
            if len(query_parts) >= 3:
                break
            if sum(c.isdigit() for c in p) > 4:
                continue
            query_parts.append(p)
        return " ".join(query_parts) if query_parts else modelo

    @staticmethod
    def extrair_sku(modelo_limpo):
        """Extrai SKU alfanumérico de 4-8 caracteres (ex: fb0157ax)"""
        modelo = modelo_limpo.lower().replace('_', ' ')
        match = re.search(r'\b([a-z0-9]{4,8})\b', modelo)
        return match.group(1) if match else None

    @classmethod
    def validar_presenca_modelo_leve(cls, tarefa, posts_sem_comentarios):
        """
        Valida usando apenas título + selftext.
        Prioriza SKU; se não houver, exige 2 palavras-chave.
        """
        modelo_limpo = tarefa['modelo_limpo']
        modelo_alvo = cls.normalizar(modelo_limpo).lower().replace('_', ' ')
        sku_alvo = cls.extrair_sku(modelo_limpo)

        palavras_principais = [p for p in modelo_alvo.split() if len(p) > 3 and not p.isdigit()]
        palavras_principais = palavras_principais[:2]

        filtrados = []
        for post in posts_sem_comentarios:
            texto = f"{post['titulo']} {post.get('selftext', '')}".lower()

            if sku_alvo and sku_alvo in texto:
                filtrados.append(post)
                continue

            if len(palavras_principais) >= 2:
                matches = sum(1 for palavra in palavras_principais if palavra in texto)
                if matches >= 2:
                    filtrados.append(post)
                    continue

            if modelo_alvo in texto and len(modelo_alvo) > 10:
                frases_genericas = ["looking for", "thinking about", "should i get"]
                if not any(gen in texto for gen in frases_genericas):
                    filtrados.append(post)
        return filtrados

# =================================================================
# ORQUESTRADOR – APENAS EXTRAÇÃO LEVE (SEM COMENTÁRIOS)
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
        self.total_comentarios_disponiveis = 0

    async def log(self, mensagem, grupo_prefix=""):
        async with self.print_lock:
            if grupo_prefix:
                prefix = f"[{grupo_prefix:15s}] "
                for linha in mensagem.splitlines():
                    print(f"{prefix}{linha}")
            else:
                print(mensagem)

    async def atualizar_logs_incremental(self):
        async with self.save_lock:
            if self.modelos_sem_resultados:
                pd.DataFrame(self.modelos_sem_resultados).to_csv(DIRETORIO_LOGS / f"PROGRESSO_vazios_{self.session_id}.csv", index=False)
            if self.modelos_com_erro:
                pd.DataFrame(self.modelos_com_erro).to_csv(DIRETORIO_LOGS / f"PROGRESSO_erros_{self.session_id}.csv", index=False)

    async def processar_grupo(self, service, query_final, tarefas_grupo):
        start_time = datetime.datetime.now()
        grupo_prefix = query_final[:15]

        async def grupo_log(msg):
            await self.log(msg, grupo_prefix=grupo_prefix)

        await grupo_log(f"\n{'='*70}")
        await grupo_log(f"🎯 INICIANDO GRUPO: '{query_final}'")
        await grupo_log(f"   📦 Modelos no grupo: {len(tarefas_grupo)}")
        await grupo_log(f"   🕐 Início: {start_time.strftime('%H:%M:%S')}")
        await grupo_log(f"{'='*70}")

        try:
            await grupo_log(f"🔍 Buscando termo: '{query_final}' no Reddit (leve, sem comentários)...")
            busca_start = datetime.datetime.now()

            # posts_sem_comentarios, stats = await service.buscar_termo_generico_leve(
            #     query_final, time_filter=self.time_filter, log_func=grupo_log
            # )
            posts_sem_comentarios, stats = await service.buscar_termo_generico_leve(
                query_final, time_filter=self.time_filter, log_func=grupo_log,
                only_first_group=False   # <-- NOVO
            )

            busca_tempo = (datetime.datetime.now() - busca_start).total_seconds()
            await grupo_log(f"   ⏱️  Busca concluída em {busca_tempo:.1f}s | 📥 Posts brutos: {len(posts_sem_comentarios)}")
            self.total_posts_baixados += len(posts_sem_comentarios)

        except Exception as e:
            busca_tempo = (datetime.datetime.now() - start_time).total_seconds()
            await grupo_log(f"❌ ERRO no grupo '{query_final}' após {busca_tempo:.1f}s: {str(e)[:100]}")
            for t in tarefas_grupo:
                self.modelos_com_erro.append({"id_unico": t['id_unico'], "query": query_final, "erro": str(e)})
            return

        consolidados_grupo = 0
        if not posts_sem_comentarios:
            await grupo_log(f"⚠️ GRUPO VAZIO: '{query_final}' - Nenhum post encontrado na busca")
            for t in tarefas_grupo:
                self.modelos_sem_resultados.append({
                    "id_unico": t['id_unico'],
                    "modelo": t['modelo_limpo'],
                    "query": query_final,
                    "motivo": "Busca genérica vazia"
                })
        else:
            for idx, tarefa in enumerate(tarefas_grupo, 1):
                await grupo_log(f"   📝 Validando modelo {idx}/{len(tarefas_grupo)}: {tarefa['modelo_limpo'][:40]}...")
                posts_validados = TextProcessor.validar_presenca_modelo_leve(tarefa, posts_sem_comentarios)

                if posts_validados:
                    total_comentarios_validados = sum(p['num_comments'] for p in posts_validados)
                    self.total_comentarios_disponiveis += total_comentarios_validados
                    await self._salvar_resultado(query_final, tarefa, posts_validados)
                    consolidados_grupo += 1

                if not posts_validados:
                    await grupo_log(f"      ❌ Sem posts válidos para este modelo")
                    self.modelos_sem_resultados.append({
                        "id_unico": tarefa['id_unico'],
                        "modelo": tarefa['modelo_limpo'],
                        "query": query_final,
                        "motivo": "Modelo não encontrado nos posts (validação leve)"
                    })
                    continue

                await grupo_log(f"      ✅ Encontrados {len(posts_validados)} posts válidos (validados sem comentários)")

                # NÃO carregamos comentários aqui – apenas salvamos os posts com flag
                await self._salvar_resultado(query_final, tarefa, posts_validados)
                consolidados_grupo += 1

        # Footer do grupo
        total_tempo = (datetime.datetime.now() - start_time).total_seconds()
        status_icon = "✅" if consolidados_grupo > 0 else "⚠️"
        barra_len = 30
        proporcao = consolidados_grupo / len(tarefas_grupo) if tarefas_grupo else 0
        barra = "█" * int(proporcao * barra_len) + "░" * (barra_len - int(proporcao * barra_len))

        await grupo_log(f"\n{status_icon} FINALIZANDO GRUPO: '{query_final}'")
        await grupo_log(f"   ⏱️  Tempo total: {total_tempo:.1f}s (busca: {busca_tempo:.1f}s | pós-validação: {total_tempo - busca_tempo:.1f}s)")
        await grupo_log(f"   📊 Aproveitamento: {barra} {consolidados_grupo}/{len(tarefas_grupo)} modelos")
        await grupo_log(f"   📈 Taxa: {(consolidados_grupo/len(tarefas_grupo)*100):.1f}%")
        await grupo_log(f"{'='*70}\n")

        await self.atualizar_logs_incremental()

    async def _salvar_resultado(self, query, tarefa, posts):
        id_notebook = tarefa['id_unico']
        resultado = {
        "modelo_original": tarefa['modelo_limpo'],
        "modelo_generico": tarefa.get('modelo_generico', ''),
        "query_usada": query,
        "id_notebook": id_notebook,
        "total_posts": len(posts),
        "total_comentarios": sum(p['num_comments'] for p in posts),  # novo campo
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

    async def relatorio_resumido(self, pendentes, grupos):
        print("\n" + "="*60)
        print("📊 RELATÓRIO RESUMIDO DE PROCESSAMENTO")
        print("="*60)
        print(f"📌 Total de tarefas pendentes no início: {len(pendentes)}")
        print(f"📌 Total de grupos criados: {len(grupos)}")
        print(f"📌 Grupos processados até agora: {len(self.modelos_sucesso) + len(self.modelos_sem_resultados) + len(self.modelos_com_erro)}")
        sucesso_queries = set(s['query'] for s in self.modelos_sucesso) if self.modelos_sucesso else set()
        vazias_queries = set(s['query'] for s in self.modelos_sem_resultados) if self.modelos_sem_resultados else set()
        erro_queries = set(s['query'] for s in self.modelos_com_erro) if self.modelos_com_erro else set()
        print(f"   ├─ ✅ Grupos com sucesso: {len(sucesso_queries)}")
        print(f"   ├─ ⚠️  Grupos vazios: {len(vazias_queries)}")
        print(f"   └─ ❌ Grupos com erro: {len(erro_queries)}")
        print(f"\n📌 Modelos individuais:")
        print(f"   ├─ ✅ Salvos: {len(self.modelos_sucesso)}")
        print(f"   ├─ ⚠️  Sem resultados: {len(self.modelos_sem_resultados)}")
        print(f"   └─ ❌ Com erro: {len(self.modelos_com_erro)}")
        
        if pendentes:
            print(f"\n🎯 Taxa de aproveitamento: {(len(self.modelos_sucesso)/len(pendentes)*100):.2f}%")
            print(f"   💬 Total de comentários disponíveis nos posts baixados: {self.total_comentarios_disponiveis}")
        print("="*60)

    async def executar(self):
        df = pd.read_csv(CAMINHO_ENTRADA_CSV)
        pendentes = [
            row.to_dict() for _, row in df.iterrows()
            if not (DIRETORIO_BRUTO / f"{TextProcessor.limpar_nome_arquivo(row['id_unico'])}.json").exists()
        ]

        grupos = defaultdict(list)
        for t in pendentes:
            query = TextProcessor.gerar_query_final(
                str(t.get('modelo_limpo', '')),
                t.get('modelo_generico'),
                t.get('modelo_busca_praw')
            )
            grupos[query].append(t)

        print(f"\n🚀 INICIANDO EXTRAÇÃO: {len(grupos)} Grupos | {len(pendentes)} Tarefas")
        print(f"⏱️  Início global: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        global_start = datetime.datetime.now()
        grupos_processados = 0
        total_grupos = len(grupos)

        async with RedditServiceV13Async() as service:
            async def worker(q, tg):
                nonlocal grupos_processados
                async with self.semaphore:
                    await self.processar_grupo(service, q, tg)
                    grupos_processados += 1
                    if grupos_processados % 5 == 0 or grupos_processados == total_grupos:
                        elapsed = (datetime.datetime.now() - global_start).total_seconds()
                        velocidade = grupos_processados / elapsed if elapsed > 0 else 0
                        async with self.print_lock:
                            print(f"\n📈 PROGRESSO GLOBAL: {grupos_processados}/{total_grupos} grupos | {velocidade:.2f} grupos/s | {elapsed:.1f}s decorridos\n")

            tasks = [worker(q, tg) for q, tg in grupos.items()]
            await tqdm.gather(*tasks, desc="🔥 Progresso")

        elapsed_total = (datetime.datetime.now() - global_start).total_seconds()
        print(f"\n{'='*70}")
        print(f"🏁 EXTRATOR FINALIZADO")
        print(f"   ⏱️  Tempo total: {elapsed_total:.1f}s ({elapsed_total/60:.1f}min)")
        print(f"   📊 Grupos processados: {grupos_processados}")
        print(f"   💾 Posts baixados: {self.total_posts_baixados}")
        print(f"{'='*70}\n")

        await self.relatorio_resumido(pendentes, grupos)


# if __name__ == "__main__":
#     pipeline = RedditExtractionPipelineAsync(limite=None, max_concurrency=6, time_filter="all")
#     asyncio.run(pipeline.executar())

if __name__ == "__main__":
    pipeline = RedditExtractionPipelineAsync(limite=None, max_concurrency=6, time_filter="all")
    # Para processar apenas o primeiro grupo, passe um parâmetro ou defina um atributo
    # pipeline.only_first_group = True   # ou crie um parâmetro no construtor
    asyncio.run(pipeline.executar())