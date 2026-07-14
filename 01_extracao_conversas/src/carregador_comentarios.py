import json
import asyncio
import aiofiles
from pathlib import Path
from tqdm.asyncio import tqdm
from core.paths import EXTRACAO_DATA, DATASET_FINAL_CSV
from extractors.reddit_serviceV12 import RedditServiceV12Async

# Configurações
DIRETORIO_BRUTO = EXTRACAO_DATA / 'brutoV11'
LIMITE_COMENTARIOS_POR_POST = 100   # quantos comentários baixar por post
CONCORRENCIA = 5                    # número de requisições simultâneas

class CommentLoader:
    def __init__(self, max_concurrency=5, comment_limit=100):
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.comment_limit = comment_limit
        self.total_posts_atualizados = 0
        self.total_erros = 0

    async def processar_arquivo(self, service, arquivo_path):
        """Carrega comentários para todos os posts de um arquivo JSON."""
        async with self.semaphore:
            try:
                # Lê o JSON
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
                    continue  # já tem comentários

                post_id = post.get('id')
                if not post_id:
                    continue

                print(f"  Carregando comentários do post {post_id}...")
                comentarios = await service.carregar_comentarios_por_id(post_id, limit=self.comment_limit)
                post['comentarios'] = comentarios
                post['comentarios_carregados'] = True
                alterado = True
                self.total_posts_atualizados += 1

            if alterado:
                # Salva o arquivo atualizado
                try:
                    async with aiofiles.open(arquivo_path, 'w', encoding='utf-8') as f:
                        await f.write(json.dumps(dados, ensure_ascii=False, indent=4))
                    print(f"  ✅ Atualizado: {arquivo_path.name}")
                except Exception as e:
                    print(f"  ❌ Erro ao salvar {arquivo_path.name}: {e}")
                    self.total_erros += 1

    async def executar(self):
        # Lista todos os arquivos .json no diretório bruto
        arquivos = list(DIRETORIO_BRUTO.glob("*.json"))
        print(f"📁 Encontrados {len(arquivos)} arquivos JSON para processar.")

        async with RedditServiceV12Async() as service:
            tasks = []
            for arquivo in arquivos:
                tasks.append(self.processar_arquivo(service, arquivo))

            # Executa com barra de progresso
            await tqdm.gather(*tasks, desc="⏳ Carregando comentários")

        print("\n✅ Processamento concluído!")
        print(f"   📊 Total de posts com comentários carregados: {self.total_posts_atualizados}")
        print(f"   ❌ Total de erros: {self.total_erros}")

if __name__ == "__main__":
    loader = CommentLoader(max_concurrency=CONCORRENCIA, comment_limit=LIMITE_COMENTARIOS_POR_POST)
    asyncio.run(loader.executar())