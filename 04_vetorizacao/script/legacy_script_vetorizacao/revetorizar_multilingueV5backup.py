import json
import asyncio
import re
from pathlib import Path
from ollama import AsyncClient
from tqdm.asyncio import tqdm

# --- CONFIGURAÇÃO ---
try:
    from core.paths import NER_DATA, VETORIZATION_DATA
    DIR_ENTRADA = NER_DATA / 'Base_Conhecimento_ResumidaV2'
    CAMINHO_SAIDA = VETORIZATION_DATA / 'base_conhecimento_multilingueV5.json'
except ImportError:
    DIR_ENTRADA = Path("./data/Base_Conhecimento_ResumidaV2")
    CAMINHO_SAIDA = Path("./data/base_conhecimento_multilingueV5.json")

class VectorProcessor:
    def __init__(self, model="bge-m3:latest", max_concurrency=5):
        self.model = model
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.client = AsyncClient()

    @staticmethod
    def clean_text(text):
        """Remove espaços extras e quebras de linha."""
        return re.sub(r'\s+', ' ', str(text)).strip()

    def format_solutions(self, solutions):
        """Converte suggested_solution em string formatada."""
        if not solutions:
            return "N/A"
        if isinstance(solutions, str):
            return self.clean_text(solutions)
        
        if isinstance(solutions, list):
            items = []
            for item in solutions:
                if isinstance(item, dict):
                    items.append(" ".join(str(v) for v in item.values()))
                else:
                    items.append(str(item))
            return self.clean_text(", ".join(items))
        
        return self.clean_text(str(solutions))

    async def process_item(self, item, pbar, retries=3):
        """Processa um único item com lógica de retry."""
        async with self.semaphore:
            for attempt in range(retries):
                try:
                    response = await self.client.embeddings(
                        model=self.model, 
                        prompt=item['texto_final']
                    )
                    pbar.update(1)
                    return {
                        **item,
                        'vector': response['embedding'],
                        'original_text': item.pop('texto_final') # Remove para economizar espaço se desejar
                    }
                except Exception as e:
                    if attempt == retries - 1:
                        pbar.write(f"❌ Falha definitiva ID {item['id']}: {e}")
                        pbar.update(1)
                        return None
                    await asyncio.sleep(2 ** attempt) # Exponential backoff

    def prepare_queue(self):
        """Lê arquivos e prepara a fila de processamento."""
        queue = []
        files = list(DIR_ENTRADA.glob("*.json"))
        
        for file_path in files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                device_model = data.get('modelo_busca_utilizado', 'Unknown Device')
                
                for post in data.get('posts', []):
                    analysis = post.get('analise_ia', {})
                    if not analysis: continue

                    sol_str = self.format_solutions(analysis.get('suggested_solution'))
                    timeline = analysis.get('discussion_timeline', 'N/A')
                    post_date = analysis.get('ancoragem_temporal', {}).get('data_post', '2024-01-01')

                    # Formato narrativo para melhor performance em RAG
                    text_final = (
                        f"Technical document regarding the {device_model} model. "
                        f"Validity or discussion timeframe is {timeline}. "
                        f"Situation summary: {analysis.get('summary', 'N/A')}. "
                        f"Recommended resolution: {sol_str}."
                    )

                    queue.append({
                        'id': post.get('id'),
                        'texto_final': text_final,
                        'date_iso': post_date,
                        'metadata': {
                            'title': post.get('titulo', 'Untitled'),
                            'model': device_model,
                            'timeline': timeline,
                            'solution': sol_str
                        }
                    })
            except Exception as e:
                print(f"⚠️ Erro ao ler arquivo {file_path}: {e}")
        return queue

    async def run(self):
        print(f"--- 🚀 INICIANDO VETORIZAÇÃO ({self.model}) ---")
        
        queue = self.prepare_queue()
        if not queue:
            print("⚠️ Nenhuma tarefa encontrada.")
            return

        print(f"📦 Total de posts: {len(queue)}")
        
        with tqdm(total=len(queue), desc="Processando", unit="post") as pbar:
            tasks = [self.process_item(item, pbar) for item in queue]
            results = await asyncio.gather(*tasks)

        final_data = [r for r in results if r is not None]
        
        if final_data:
            CAMINHO_SAIDA.parent.mkdir(parents=True, exist_ok=True)
            with open(CAMINHO_SAIDA, 'w', encoding='utf-8') as f:
                json.dump(final_data, f, ensure_ascii=False, indent=4)
            print(f"\n✨ SUCESSO! {len(final_data)} vetores salvos.")

if __name__ == "__main__":
    # processor = VectorProcessor(max_concurrency=CONCORRENCIA_MAXIMA)
    processor = VectorProcessor()
    asyncio.run(processor.run())