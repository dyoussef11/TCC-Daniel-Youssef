import json
import asyncio
import aiofiles
from pathlib import Path
from tqdm.asyncio import tqdm
from core.paths import EXTRACAO_DATA
from extractors.reddit_serviceV13 import RedditServiceV13Async
import random

# Configurações
DIRETORIO_BRUTO = EXTRACAO_DATA / "dados_brutos" / 'brutoV12'
LIMITE_COMENTARIOS_POR_POST = 100
CONCORRENCIA = 5          # reduzido para evitar 429
MAX_TENTATIVAS = 10        # número de retries
BACKOFF_BASE = 30          # segundos

class CommentLoader:
    def __init__(self, max_concurrency=5, comment_limit=100):
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.comment_limit = comment_limit
        self.total_posts_atualizados = 0
        self.total_erros = 0
        self.arquivos_ignorados = 0
        self.arquivos_processados = 0
        self.posts_falhos = []  # lista para registrar IDs que falharam

    async def _analisar_arquivo(self, arquivo_path):
        """Retorna (total_posts, carregados, pendentes) para um arquivo."""
        try:
            async with aiofiles.open(arquivo_path, 'r', encoding='utf-8') as f:
                conteudo = await f.read()
                dados = json.loads(conteudo)
        except Exception as e:
            print(f"Erro ao analisar {arquivo_path.name}: {e}")
            return None, None, None

        posts = dados.get('posts', [])
        total = len(posts)
        carregados = sum(1 for p in posts if p.get('comentarios_carregados', False))
        pendentes = total - carregados
        return total, carregados, pendentes

    async def _carregar_com_retry(self, service, post_id):
        """
        Tenta carregar comentários com backoff exponencial.
        Retorna (comentarios, sucesso).
        """
        for tentativa in range(1, MAX_TENTATIVAS + 1):
            try:
                comentarios = await service.carregar_comentarios_por_id(post_id, limit=self.comment_limit)
                # Se chegou aqui, deu certo
                return comentarios, True
            except Exception as e:
                # Verifica se é 429 (ou qualquer erro de rate limit)
                if "429" in str(e) or "Too Many Requests" in str(e):
                    # Espera com backoff + jitter
                    wait = BACKOFF_BASE * (2 ** (tentativa - 1)) + random.uniform(0, 0.5)
                    print(f"  ⚠️ 429 para {post_id}, tentativa {tentativa}/{MAX_TENTATIVAS}. Aguardando {wait:.1f}s")
                    await asyncio.sleep(wait)
                else:
                    # Outro erro (ex: conexão) – tenta novamente com backoff menor
                    print(f"  ⚠️ Erro inesperado para {post_id}: {e}. Tentativa {tentativa}/{MAX_TENTATIVAS}")
                    await asyncio.sleep(BACKOFF_BASE * tentativa)
        # Esgotou tentativas
        print(f"  ❌ Falha ao carregar comentários para {post_id} após {MAX_TENTATIVAS} tentativas.")
        return None, False

    async def processar_arquivo(self, service, arquivo_path):
        """Carrega comentários para os posts pendentes de um arquivo."""
        async with self.semaphore:
            try:
                async with aiofiles.open(arquivo_path, 'r', encoding='utf-8') as f:
                    conteudo = await f.read()
                    dados = json.loads(conteudo)
            except Exception as e:
                print(f"Erro ao ler {arquivo_path.name}: {e}")
                self.total_erros += 1
                return

            alterado = False
            for post in dados.get('posts', []):
                if post.get('comentarios_carregados', False):
                    continue

                post_id = post.get('id')
                if not post_id:
                    continue

                # Tenta carregar com retry
                comentarios, sucesso = await self._carregar_com_retry(service, post_id)

                if sucesso:
                    post['comentarios'] = comentarios
                    post['comentarios_carregados'] = True
                    alterado = True
                    self.total_posts_atualizados += 1
                    # Pequena pausa entre posts para não sobrecarregar
                    await asyncio.sleep(0.3)  # ajustável
                else:
                    # Não marca como carregado, mas registra o falho
                    self.posts_falhos.append((arquivo_path.name, post_id))
                    self.total_erros += 1
                    # Não altera o arquivo para este post

            if alterado:
                try:
                    async with aiofiles.open(arquivo_path, 'w', encoding='utf-8') as f:
                        await f.write(json.dumps(dados, ensure_ascii=False, indent=4))
                    self.arquivos_processados += 1
                except Exception as e:
                    print(f"❌ Erro ao salvar {arquivo_path.name}: {e}")
                    self.total_erros += 1

    async def executar(self):
        arquivos = list(DIRETORIO_BRUTO.glob("*.json"))
        print(f"📁 Encontrados {len(arquivos)} arquivos JSON.")

        # Análise inicial
        print("🔍 Analisando arquivos...")
        arquivos_para_processar = []
        total_posts_geral = 0
        total_pendentes_geral = 0
        completos = 0

        for arquivo in arquivos:
            total, carregados, pendentes = await self._analisar_arquivo(arquivo)
            if total is None:
                continue
            total_posts_geral += total
            total_pendentes_geral += pendentes
            if pendentes > 0:
                arquivos_para_processar.append((arquivo, total, carregados, pendentes))
            else:
                completos += 1

        arquivos_para_processar.sort(key=lambda x: x[1])  # menor total primeiro

        print(f"   ✅ Arquivos completamente processados: {completos}")
        print(f"   ⏳ Arquivos com pendências: {len(arquivos_para_processar)}")
        print(f"   📊 Total de posts: {total_posts_geral}")
        print(f"   📊 Total de posts pendentes: {total_pendentes_geral}")

        if not arquivos_para_processar:
            print("✅ Todos os arquivos já estão completos. Nada a fazer.")
            return

        print(f"🚀 Iniciando processamento de {len(arquivos_para_processar)} arquivos (concorrência={CONCORRENCIA})...")
        async with RedditServiceV13Async() as service:
            tasks = []
            for arquivo, total, carregados, pendentes in arquivos_para_processar:
                tasks.append(self.processar_arquivo(service, arquivo))

            await tqdm.gather(*tasks, desc="⏳ Carregando comentários")

        # Relatório final
        print("\n✅ Processamento concluído!")
        print(f"   📊 Posts atualizados com sucesso: {self.total_posts_atualizados}")
        print(f"   📁 Arquivos processados (com alterações): {self.arquivos_processados}")
        print(f"   ⏭️  Arquivos ignorados (já completos): {self.arquivos_ignorados}")
        print(f"   ❌ Erros totais (posts que falharam): {self.total_erros}")
        if self.posts_falhos:
            print("   🚫 Posts que falharam (serão ignorados nesta execução):")
            for nome_arq, pid in self.posts_falhos[:10]:  # mostra os primeiros 10
                print(f"      - {nome_arq}: {pid}")
            if len(self.posts_falhos) > 10:
                print(f"      ... e mais {len(self.posts_falhos)-10}")

if __name__ == "__main__":
    loader = CommentLoader(max_concurrency=CONCORRENCIA, comment_limit=LIMITE_COMENTARIOS_POR_POST)
    asyncio.run(loader.executar())