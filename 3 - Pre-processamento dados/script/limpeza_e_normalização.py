import sys
import json
import re
import html
from datetime import datetime
from pathlib import Path
from tqdm import tqdm
import shutil
import re
import html

# --- BOOTSTRAP DE CAMINHO DO PROJETO ---
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.paths import (
    EXTRACAO_DATA, 
    PREPROCESSAMENTO_DATA 
)



DIRETORIO_BRUTO = EXTRACAO_DATA / 'bruto'
DIRETORIO_CHECKPOINT = PREPROCESSAMENTO_DATA / 'checkpoints'
CAMINHO_SAIDA_JSON = PREPROCESSAMENTO_DATA / 'reddit_notebook_dados_limpos.json'

# --- 2. SERVIÇO DE LIMPEZA E FILTRAGEM ---
class TextCleanerService:
    """Responsável por toda a higienização de strings e filtros de ruído."""
    AUTORES_IGNORAR = {"[deleted]", "[removed]", "[Deletado]", "AutoModerator", "DellCares"}
    TEXTOS_IGNORAR = {"[deleted]", "[removed]", ""}
    FRASES_BOT = ["I am a bot", "action was performed automatically"]

    @staticmethod
    def limpar(texto):
    
        if texto is None: return ""
        if not isinstance(texto, str): return str(texto)
        
        # 1. Descodificar entidades HTML (ex: &amp; para &, &#x200B; para espaço vazio)
        try:
            texto = html.unescape(texto)
        except:
            pass

        # 2. Remover placeholders de imagens do Reddit
        # Exemplo: *Processing img vb9k9foz8r1f1...*
        texto = re.sub(r'\*Processing img [^*]+\.\.\.\*', ' ', texto)

        # 3. Remover e-mails
        texto = re.sub(r'\S+@\S+\.\S+', ' ', texto)

        # 4. Remover menções a usuários e subreddits (u/username e r/subreddit)
        texto = re.sub(r'\b[ur]/[A-Za-z0-9_]+\b', ' ', texto)

        # 5. Remover links Markdown mantendo apenas o texto âncora [Texto](Link)
        texto = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', texto)

        # 6. Remover URLs remanescentes (http, https, www)
        texto = re.sub(r'https?://\S+|www\.\S+', ' ', texto)

        # 7. Remover Emojis e caracteres não-ASCII
        # Abordagem agressiva para remover símbolos gráficos, mantendo o foco no texto técnico.
        texto = texto.encode('ascii', 'ignore').decode('ascii')

        # 8. Normalizar separadores e pontuação ruidosa
        # Substituímos underscores e barras verticais que costumam poluir títulos de posts.
        texto = texto.replace('_', ' ').replace('|', ' ')

        # 9. Manter apenas alfanuméricos e pontuação essencial
        # Mantemos o apóstrofo (') para inglês e o hífen (-) para modelos de hardware (ex: i7-12700H).
        # Removemos símbolos de moedas ($, €), asteriscos e aspas.
        texto = re.sub(r"[^\w\s.,!?\-']", ' ', texto)

        # 10. Limpeza final: Minúsculas e normalização de espaços em branco
        texto = ' '.join(texto.split()).lower()

        return texto

    def deve_ignorar(self, autor, texto):
        if autor in self.AUTORES_IGNORAR: return True
        if texto in self.TEXTOS_IGNORAR: return True
        if any(bot in texto for bot in self.FRASES_BOT): return True
        return False

# --- 3. SERVIÇO DE ENRIQUECIMENTO TEMPORAL ---
class TimeEnricherService:
    """Responsável por tratar datas e gerar metadados temporais."""
    @staticmethod
    def enriquecer(obj_dict, chave_data):
        data_str = obj_dict.get(chave_data)
        if not (data_str and isinstance(data_str, str)): return None
        
        try:
            dt = datetime.fromisoformat(data_str.replace('Z', '+00:00'))
            obj_dict.update({
                'ano': dt.year, 'mes': dt.month, 'dia': dt.day,
                'timestamp': dt.timestamp(), 'dia_semana': dt.strftime('%A')
            })
            return dt
        except:
            return None

# --- 4. ORQUESTRADOR DO PRÉ-PROCESSAMENTO ---
class RedditPreprocessor:
    def __init__(self):
        self.cleaner = TextCleanerService()
        self.time_service = TimeEnricherService()
        DIRETORIO_CHECKPOINT.mkdir(parents=True, exist_ok=True)

    def processar_item(self, item):
        """Processa a estrutura de posts e comentários recursivamente."""
        if 'posts' not in item: return item

        for post in item['posts']:
            post['titulo_limpo'] = self.cleaner.limpar(post.get('titulo'))
            post['conteudo_texto_limpo'] = self.cleaner.limpar(post.get('conteudo_texto'))
            self.time_service.enriquecer(post, 'data_publicacao')

            if 'comentarios' in post:
                coments_orig = post['comentarios']
                coments_processados = []
                vistos = set()

                for com in coments_orig:
                    texto = com.get('conteudo') or ""
                    autor = com.get('autor_comentario')
                    
                    if self.cleaner.deve_ignorar(autor, texto): continue
                    
                    limpo = self.cleaner.limpar(texto)
                    if len(limpo) > 2 and limpo not in vistos:
                        com['conteudo_limpo'] = limpo
                        self.time_service.enriquecer(com, 'data_publicacao')
                        vistos.add(limpo)
                        coments_processados.append(com)
                
                # Ordena comentários por tempo
                coments_processados.sort(key=lambda x: x.get('timestamp') or 0)
                post['comentarios'] = coments_processados
        
        # Ordena posts por tempo
        item['posts'].sort(key=lambda p: p.get('timestamp') or 0)
        return item

    def consolidar(self):
        """Une todos os checkpoints no arquivo final."""
        print("\n📦 Consolidando checkpoints no arquivo final...")
        dados_finais = []
        arquivos = list(DIRETORIO_CHECKPOINT.glob('*.json'))
        
        for arq in tqdm(arquivos, desc="Consolidando"):
            with open(arq, 'r', encoding='utf-8') as f:
                dados = json.load(f)
                if isinstance(dados, list): dados_finais.extend(dados)
                else: dados_finais.append(dados)

        with open(CAMINHO_SAIDA_JSON, 'w', encoding='utf-8') as f:
            json.dump(dados_finais, f, ensure_ascii=False, indent=4)
        
        # print(f"✅ Dataset final salvo em: {CAMINHO_SAIDA_JSON}")
        # shutil.rmtree(DIRETORIO_CHECKPOINT)

    def executar(self):
        arquivos_brutos = list(DIRETORIO_BRUTO.glob('*.json'))
        if not arquivos_brutos:
            print(f"⚠️ Nenhum arquivo encontrado em {DIRETORIO_BRUTO}")
            return

        print(f"🔍 Localizados {len(arquivos_brutos)} arquivos para pré-processamento.")
        pbar = tqdm(arquivos_brutos, desc="⚙️ Processando Notebooks", unit="arq")

        for caminho_arq in pbar:
            caminho_check = DIRETORIO_CHECKPOINT / caminho_arq.name
            if caminho_check.exists(): continue
            
            pbar.set_postfix(arquivo=caminho_arq.name[:15])

            try:
                with open(caminho_arq, 'r', encoding='utf-8') as f:
                    conteudo = json.load(f)

                if isinstance(conteudo, list):
                    processado = [self.processar_item(i) for i in conteudo]
                else:
                    processado = self.processar_item(conteudo)

                with open(caminho_check, 'w', encoding='utf-8') as f:
                    json.dump(processado, f, ensure_ascii=False, indent=4)

            except Exception as e:
                print(f"\n❌ Erro ao processar {caminho_arq.name}: {e}")

        self.consolidar()

if __name__ == "__main__":
    pipeline = RedditPreprocessor()
    pipeline.executar()