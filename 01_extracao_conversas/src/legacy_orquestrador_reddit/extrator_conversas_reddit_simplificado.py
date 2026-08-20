import json
import pandas as pd
import re
import datetime
import asyncio
import aiofiles
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

from core.paths import EXTRACAO_DATA, DATASET_FINAL_CSV
from extractors.reddit_serviceV10Backup import RedditServiceV10Async

# =================================================================
# CONFIGURAÇÕES
# =================================================================
DIRETORIO_BRUTO = EXTRACAO_DATA / 'bruto_simplificado'
DIRETORIO_LOGS = EXTRACAO_DATA / 'logs_simplificado'
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
    def gerar_chave_agrupamento(modelo_original, modelo_generico=None, modelo_busca_praw=None):
        """
        🔥 SIMPLIFICADO: Gera chave para agrupamento.
        Prioridade: modelo_busca_praw > modelo_generico > modelo_original
        """
        if modelo_busca_praw and str(modelo_busca_praw) != 'nan' and str(modelo_busca_praw).strip():
            base = TextProcessor.normalizar(str(modelo_busca_praw)).lower()
            # Remove palavras genéricas para criar chave
            base = re.sub(r'\b(gaming|notebook|laptop|edition)\b', '', base)
            # Pega primeiras 2-3 palavras
            palavras = base.replace('_', ' ').split()[:3]
            return ' '.join(palavras)
        
        if modelo_generico and str(modelo_generico) != 'nan' and str(modelo_generico).strip():
            base = TextProcessor.normalizar(str(modelo_generico)).lower()
            palavras = base.replace('_', ' ').split()[:3]
            return ' '.join(palavras)
        
        modelo = TextProcessor.normalizar(modelo_original).lower()
        # Remove palavras genéricas
        modelo = re.sub(r'\b(gaming|notebook|laptop)\b', '', modelo)
        palavras = modelo.replace('_', ' ').split()[:3]
        return ' '.join(palavras)

    @staticmethod
    def gerar_query_busca(modelo_busca_praw, modelo_generico, modelo_original):
        """
        🔥 Gera a query que será usada para BUSCAR no Reddit.
        Usamos o modelo_busca_praw como prioridade.
        """
        if modelo_busca_praw and str(modelo_busca_praw) != 'nan' and str(modelo_busca_praw).strip():
            return TextProcessor.normalizar(str(modelo_busca_praw)).lower().replace('_', ' ')
        
        if modelo_generico and str(modelo_generico) != 'nan' and str(modelo_generico).strip():
            return TextProcessor.normalizar(str(modelo_generico)).lower().replace('_', ' ')
        
        return TextProcessor.normalizar(modelo_original).lower().replace('_', ' ')

    @classmethod
    def validar_modelo_no_post(cls, modelo, post):
        """Verifica se o modelo aparece no post (título, texto ou comentários)."""
        texto_completo = f"{post['titulo']} {post.get('selftext', '')}".lower()
        
        # Busca pelo modelo_busca_praw
        busca_praw = str(modelo.get('modelo_busca_praw', '')).lower()
        if busca_praw and busca_praw != 'nan':
            if busca_praw.replace('_', ' ') in texto_completo:
                return True
        
        # Busca pelo modelo_generico
        generico = str(modelo.get('modelo_generico', '')).lower()
        if generico and generico != 'nan':
            if generico.replace('_', ' ') in texto_completo:
                return True
        
        # Busca pelo modelo_limpo
        limpo = str(modelo.get('modelo_limpo', '')).lower()
        if limpo and limpo != 'nan':
            if limpo.replace('_', ' ') in texto_completo:
                return True
        
        return False


class RedditExtractionSimplified:
    def __init__(self, max_concurrency: int = 4, time_filter: str = "all"):
        self.max_concurrency = max_concurrency
        self.time_filter = time_filter
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.print_lock = asyncio.Lock()
        
        DIRETORIO_BRUTO.mkdir(parents=True, exist_ok=True)
        DIRETORIO_LOGS.mkdir(parents=True, exist_ok=True)
        
        self.stats = {
            'grupos': 0,
            'total_posts_baixados': 0,
            'modelos_com_dados': set()
        }
        self.start_time = datetime.datetime.now()
    
    async def log(self, mensagem):
        async with self.print_lock:
            timestamp = datetime.datetime.now().strftime("%H:%M:%S")
            print(f"[{timestamp}] {mensagem}")
    
    async def carregar_pendentes(self) -> List[Dict]:
        """Carrega modelos pendentes."""
        df = pd.read_csv(CAMINHO_ENTRADA_CSV)
        
        # Limpa dados
        for col in ['modelo_busca_praw', 'modelo_generico', 'modelo_limpo', 'marca']:
            if col in df.columns:
                df[col] = df[col].fillna('').astype(str)
        
        pendentes = []
        for _, row in df.iterrows():
            id_unico = row['id_unico']
            arquivo = DIRETORIO_BRUTO / f"{TextProcessor.limpar_nome_arquivo(id_unico)}.json"
            if not arquivo.exists():
                pendentes.append(row.to_dict())
        
        await self.log(f"📊 Pendentes: {len(pendentes)} modelos")
        return pendentes
    
    async def agrupar_por_semelhanca(self, modelos: List[Dict]) -> Dict[str, List[Dict]]:
        """
        🔥 CORAÇÃO DA ESTRATÉGIA: Agrupa modelos com nomes semelhantes.
        Um grupo = uma busca no Reddit.
        """
        grupos = defaultdict(list)
        
        for modelo in modelos:
            chave = TextProcessor.gerar_chave_agrupamento(
                modelo.get('modelo_limpo', ''),
                modelo.get('modelo_generico'),
                modelo.get('modelo_busca_praw')
            )
            grupos[chave].append(modelo)
        
        await self.log(f"🏷️  {len(grupos)} grupos formados a partir de {len(modelos)} modelos")
        
        # Mostra os 5 maiores grupos
        maiores = sorted(grupos.items(), key=lambda x: len(x[1]), reverse=True)[:5]
        for chave, lista in maiores:
            representante = lista[0]
            query = TextProcessor.gerar_query_busca(
                representante.get('modelo_busca_praw'),
                representante.get('modelo_generico'),
                representante.get('modelo_limpo')
            )
            await self.log(f"   - '{chave[:40]}': {len(lista)} modelos (busca: '{query}')")
        
        return grupos
    
    async def processar_grupo(self, service, chave: str, modelos: List[Dict]):
        """
        Processa UM grupo:
        1. Escolhe UM representante para buscar
        2. Baixa os posts
        3. Valida quais modelos do grupo aparecem
        """
        inicio = datetime.datetime.now()
        
        # Escolhe o melhor representante (prioriza quem tem modelo_busca_praw)
        representante = None
        for m in modelos:
            if m.get('modelo_busca_praw') and m['modelo_busca_praw'] != '':
                representante = m
                break
        if not representante:
            representante = modelos[0]
        
        # Gera query de busca
        query = TextProcessor.gerar_query_busca(
            representante.get('modelo_busca_praw'),
            representante.get('modelo_generico'),
            representante.get('modelo_limpo')
        )
        
        await self.log(f"\n{'='*60}")
        await self.log(f"🎯 Grupo: {chave[:50]}")
        await self.log(f"   📦 Modelos no grupo: {len(modelos)}")
        await self.log(f"   🔍 Buscando por: '{query}'")
        
        try:
            # 🔥 UMA busca por grupo
            posts, stats = await service.buscar_termo_generico(
                query,
                time_filter=self.time_filter,
                task_id=chave[:30]
            )
            
            await self.log(f"   📥 Posts encontrados: {len(posts)}")
            self.stats['total_posts_baixados'] += len(posts)
            
            if not posts:
                await self.log(f"   ⚠️ Nenhum post encontrado para este grupo")
                return
            
            # 🔥 Para cada modelo no grupo, valida se aparece nos posts
            for modelo in modelos:
                id_unico = modelo['id_unico']
                posts_validos = []
                
                for post in posts:
                    if TextProcessor.validar_modelo_no_post(modelo, post):
                        posts_validos.append(post)
                
                if posts_validos:
                    # Salva resultado
                    resultado = {
                        "modelo_original": modelo.get('modelo_limpo', ''),
                        "modelo_generico": modelo.get('modelo_generico', ''),
                        "modelo_busca_praw": modelo.get('modelo_busca_praw', ''),
                        "id_notebook": id_unico,
                        "query_usada": query,
                        "grupo": chave,
                        "total_posts": len(posts_validos),
                        "posts": posts_validos
                    }
                    
                    arquivo = DIRETORIO_BRUTO / f"{TextProcessor.limpar_nome_arquivo(id_unico)}.json"
                    async with aiofiles.open(arquivo, 'w', encoding='utf-8') as f:
                        await f.write(json.dumps(resultado, ensure_ascii=False, indent=4))
                    
                    self.stats['modelos_com_dados'].add(id_unico)
                    await self.log(f"   ✅ {modelo.get('modelo_limpo', '')[:30]}: {len(posts_validos)} posts")
            
            tempo = (datetime.datetime.now() - inicio).total_seconds()
            await self.log(f"   ⏱️ Grupo processado em {tempo:.1f}s")
            
        except Exception as e:
            await self.log(f"   ❌ Erro: {str(e)[:100]}")
    
    async def executar(self):
        await self.log(f"\n{'='*60}")
        await self.log(f"🚀 PIPELINE SIMPLIFICADO")
        await self.log(f"📅 {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        await self.log(f"{'='*60}\n")
        
        # 1. Carrega pendentes
        pendentes = await self.carregar_pendentes()
        if not pendentes:
            await self.log("✅ Todos os modelos já foram processados!")
            return
        
        # 2. Agrupa por semelhança
        grupos = await self.agrupar_por_semelhanca(pendentes)
        self.stats['grupos'] = len(grupos)
        
        # 3. Processa cada grupo
        async with RedditServiceV10Async() as service:
            tasks = []
            for chave, modelos in grupos.items():
                task = asyncio.create_task(
                    self.processar_grupo(service, chave, modelos)
                )
                tasks.append(task)
                # Limita concorrência
                if len(tasks) >= self.max_concurrency:
                    await asyncio.gather(*tasks)
                    tasks = []
            
            if tasks:
                await asyncio.gather(*tasks)
        
        # 4. Relatório
        tempo_total = (datetime.datetime.now() - self.start_time).total_seconds()
        
        await self.log(f"\n{'='*60}")
        await self.log(f"📊 RELATÓRIO FINAL")
        await self.log(f"{'='*60}")
        await self.log(f"⏱️ Tempo total: {tempo_total:.1f}s ({tempo_total/60:.1f}min)")
        await self.log(f"📊 Grupos processados: {self.stats['grupos']}")
        await self.log(f"📥 Posts baixados: {self.stats['total_posts_baixados']}")
        await self.log(f"✅ Modelos com dados: {len(self.stats['modelos_com_dados'])}")
        
        if pendentes:
            taxa = len(self.stats['modelos_com_dados']) / len(pendentes) * 100
            await self.log(f"📈 Taxa de sucesso: {taxa:.1f}%")
        
        await self.log(f"{'='*60}\n")


if __name__ == "__main__":
    pipeline = RedditExtractionSimplified(
        max_concurrency=4,  # Ajuste conforme sua quota
        time_filter="all"
    )
    asyncio.run(pipeline.executar())