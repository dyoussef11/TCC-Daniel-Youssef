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
from typing import Dict, List, Tuple, Optional, Any

from core.paths import EXTRACAO_CONFIG, EXTRACAO_DATA, DATASET_FINAL_CSV
from extractors.reddit_serviceV10 import RedditServiceV10Async

# =================================================================
# CONFIGURAÇÕES
# =================================================================
DIRETORIO_BRUTO = EXTRACAO_DATA / 'brutoV10_invertido'
DIRETORIO_LOGS = EXTRACAO_DATA / 'logs5_invertido'
CAMINHO_ENTRADA_CSV = DATASET_FINAL_CSV / 'dataset_laptops_UNICOS_V10.csv'
CAMINHO_CONFIG_JSON = EXTRACAO_CONFIG / 'extractor_settings_extendedV6.json'

# =================================================================
# PROCESSADOR DE TEXTO (mantido do seu código original)
# =================================================================
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
        """Gera query para busca no Reddit. Prioridade: modelo_busca_praw > modelo_generico > modelo_original"""
        if modelo_busca_praw and str(modelo_busca_praw) != 'nan' and str(modelo_busca_praw).strip():
            query_base = TextProcessor.normalizar(str(modelo_busca_praw)).lower()
            return query_base.replace('_', ' ').strip()
        
        if modelo_generico and str(modelo_generico) != 'nan' and str(modelo_generico).strip():
            query_base = TextProcessor.normalizar(str(modelo_generico)).lower()
            return query_base.replace('_', ' ').strip()
        
        modelo = TextProcessor.normalizar(modelo_original).lower()
        mapa_familias = {
            "ga401": "Zephyrus G14", "ga503": "Zephyrus G15",
            "fx506": "TUF F15", "fx516": "TUF Dash F15",
            "15ach6": "IdeaPad Gaming 3", "15iah7": "IdeaPad Gaming 3"
        }
        for cod, nome in mapa_familias.items():
            if cod in modelo: 
                return nome.lower()
        
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
    def extrair_identificadores(cls, modelo_limpo):
        """Extrai múltiplos identificadores do modelo_limpo para validação."""
        modelo = cls.normalizar(str(modelo_limpo)).lower().replace('_', ' ')
        identificadores = []
        
        sku_match = re.search(r'\b([a-z0-9]{4,8})\b', modelo)
        if sku_match:
            sku = sku_match.group(1)
            skus_falsos = {"v15", "f15", "tuf", "acer", "dell", "asus", "pro", "air", "book"}
            if sku not in skus_falsos and not sku.isdigit():
                identificadores.append(('sku_completo', sku))
        
        modelo_num_match = re.search(r'\b([a-z]+[0-9]{2,3})\b', modelo)
        if modelo_num_match:
            identificadores.append(('modelo_numero', modelo_num_match.group(1)))
        
        serie_match = re.search(r'\b([a-z0-9]{3,4})\b(?=\s|$)', modelo)
        if serie_match and len(serie_match.group(1)) >= 3:
            identificadores.append(('codigo_serie', serie_match.group(1)))
        
        geracao_match = re.search(r'\b([a-z][0-9])\b', modelo)
        if geracao_match:
            identificadores.append(('geracao', geracao_match.group(1)))
        
        return identificadores

    @classmethod
    def validar_presenca_modelo(cls, tarefa, posts):
        """Valida se o modelo aparece nos posts usando múltiplos identificadores."""
        modelo_alvo_original = cls.normalizar(str(tarefa['modelo_limpo'])).lower()
        modelo_alvo_com_espacos = modelo_alvo_original.replace('_', ' ')
        
        modelo_generico_alvo = cls.normalizar(str(tarefa.get('modelo_generico', ''))).lower() if tarefa.get('modelo_generico') else None
        if modelo_generico_alvo:
            modelo_generico_alvo = modelo_generico_alvo.replace('_', ' ')
        
        identificadores = cls.extrair_identificadores(tarefa['modelo_limpo'])
        
        filtrados = []
        for p in posts:
            comentarios_texto = " ".join([c['conteudo'].lower() for c in p.get('comentarios', [])])
            texto_completo = f"{p['titulo']} {p.get('selftext', '')} {comentarios_texto}".lower()
            
            encontrado = False
            for tipo, identificador in identificadores:
                if identificador in texto_completo:
                    filtrados.append(p)
                    encontrado = True
                    break
            
            if encontrado:
                continue
                
            if modelo_generico_alvo and modelo_generico_alvo in texto_completo:
                termos_vagos = ["thinking of buying", "worth it", "should i buy", "buying advice"]
                if any(vago in texto_completo for vago in termos_vagos):
                    continue
                filtrados.append(p)
                continue
                
            if modelo_alvo_com_espacos in texto_completo:
                filtrados.append(p)
        
        return filtrados

# =================================================================
# GERENCIADOR DE FAMÍLIAS (COALESCÊNCIA INTELIGENTE)
# =================================================================
# =================================================================
# GERENCIADOR DE FAMÍLIAS (COALESCÊNCIA INTELIGENTE) - CORRIGIDO
# =================================================================
class FamilyManager:
    """Agrupa modelos similares para busca coalescida."""
    
    # Palavras-chave que identificam famílias de produtos
    FAMILY_KEYWORDS = {
        'zephyrus': ['zephyrus', 'ga401', 'ga402', 'ga503', 'ga502', 'gu603'],
        'legion': ['legion', 'lenovo legion', 'legion 5', 'legion 7', 'legion pro'],
        'nitro': ['nitro', 'acer nitro', 'an515', 'an517'],
        'omen': ['omen', 'hp omen', 'omen 15', 'omen 16', 'omen 17'],
        'tuf': ['tuf', 'asus tuf', 'fx505', 'fx506', 'fx507', 'fx516', 'fx517'],
        'rog': ['rog', 'asus rog', 'strix', 'scar', 'flow'],
        'vivobook': ['vivobook', 'asus vivobook'],
        'thinkpad': ['thinkpad', 'lenovo thinkpad', 't14', 't15', 'x1', 'e14', 'e15'],
        'ideapad': ['ideapad', 'lenovo ideapad', 'gaming 3'],
        'predator': ['predator', 'acer predator', 'helios', 'triton'],
        'msi': ['msi', 'ge66', 'ge76', 'gp66', 'gp76', 'gs66', 'stealth', 'katana', 'sword'],
        'gigabyte': ['gigabyte', 'aorus', 'aero'],
        'dell': ['dell', 'xps', 'g15', 'g16', 'alienware', 'm15', 'm16'],
        'samsung': ['samsung', 'galaxy book', 'odyssey'],
        'apple': ['macbook', 'mac', 'apple', 'm1', 'm2', 'm3', 'm4']
    }
    
    @staticmethod
    def _safe_str(valor) -> str:
        """Converte qualquer valor para string de forma segura."""
        if pd.isna(valor) or valor is None:
            return ''
        return str(valor).strip().lower()
    
    @classmethod
    def identificar_familia(cls, row: Dict) -> str:
        """Identifica a família do laptop baseado em modelo_busca_praw, modelo_generico e modelo_limpo."""
        
        # Obtém marca de forma segura (trata NaN e float)
        marca_raw = row.get('marca', 'unknown')
        if pd.isna(marca_raw):
            marca = 'unknown'
        else:
            marca = str(marca_raw).lower().strip()
        
        # Tenta primeiro pelo modelo_busca_praw
        busca_praw = cls._safe_str(row.get('modelo_busca_praw', ''))
        if busca_praw and busca_praw != 'nan':
            for familia, keywords in cls.FAMILY_KEYWORDS.items():
                for kw in keywords:
                    if kw in busca_praw:
                        return f"{marca}_{familia}"
        
        # Depois pelo modelo_generico
        generico = cls._safe_str(row.get('modelo_generico', ''))
        if generico and generico != 'nan':
            for familia, keywords in cls.FAMILY_KEYWORDS.items():
                for kw in keywords:
                    if kw in generico:
                        return f"{marca}_{familia}"
        
        # Fallback: usa marca + primeira palavra do modelo_limpo
        modelo_limpo = cls._safe_str(row.get('modelo_limpo', ''))
        if modelo_limpo and modelo_limpo != 'nan':
            primeira_palavra = modelo_limpo.split()[0] if modelo_limpo else 'unknown'
        else:
            primeira_palavra = 'unknown'
        
        # Se marca for unknown, tenta extrair do modelo_limpo
        if marca == 'unknown' and modelo_limpo:
            # Tenta identificar marca a partir do modelo
            for familia, keywords in cls.FAMILY_KEYWORDS.items():
                for kw in keywords:
                    if kw in modelo_limpo:
                        return f"{familia}_{familia}"  # fallback
        
        return f"{marca}_{primeira_palavra}"
    
    @classmethod
    def gerar_query_representativa(cls, modelos: List[Dict], max_por_familia: int = 3) -> str:
        """
        Gera uma query representativa para uma família de modelos.
        Ex: ('zephyrus g14' OR 'zephyrus g15' OR 'ga401')
        """
        queries = []
        for modelo in modelos[:max_por_familia]:
            q = TextProcessor.gerar_query_final(
                modelo.get('modelo_limpo', ''),
                modelo.get('modelo_generico'),
                modelo.get('modelo_busca_praw')
            )
            if q and len(q) > 2:  # Evita queries vazias
                queries.append(f'"{q}"')
        
        if not queries:
            return ""
        
        return f"({' OR '.join(queries)})"
# =================================================================
# PIPELINE INVERTIDO (CORE DA OTIMIZAÇÃO)
# =================================================================
class RedditExtractionPipelineInverted:
    def __init__(self, max_concurrency: int = 6, time_filter: str = "all"):
        self.max_concurrency = max_concurrency
        self.time_filter = time_filter
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.print_lock = asyncio.Lock()
        self.save_lock = asyncio.Lock()
        
        # Carrega configurações do JSON
        self.config = self._carregar_config()
        self.categorias = self.config['reddit_params']['search_groups']
        self.termos_negativos = self.config['reddit_params'].get('negative_terms', [])
        
        # Cria diretórios
        DIRETORIO_BRUTO.mkdir(parents=True, exist_ok=True)
        DIRETORIO_LOGS.mkdir(parents=True, exist_ok=True)
        
        # Estatísticas
        self.modelos_sucesso = []
        self.modelos_sem_resultados = []
        self.modelos_com_erro = []
        self.total_posts_baixados = 0
        self.start_time = datetime.datetime.now()
        self.session_id = self.start_time.strftime("%Y%m%d_%H%M%S")
        
        # Cache de resultados por categoria
        self.cache_posts_por_categoria = {}
    
    def _carregar_config(self) -> Dict:
        """Carrega configurações do arquivo JSON."""
        with open(CAMINHO_CONFIG_JSON, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    async def log(self, mensagem: str, nivel: str = "INFO"):
        """Log com timestamp e nível."""
        async with self.print_lock:
            timestamp = datetime.datetime.now().strftime("%H:%M:%S")
            print(f"[{timestamp}] {nivel}: {mensagem}")
    
    async def carregar_modelos_pendentes(self) -> List[Dict]:
        """Carrega modelos que ainda não foram processados."""
        df = pd.read_csv(CAMINHO_ENTRADA_CSV)
        
        # 🔥 Converte colunas problemáticas para string
        for col in ['marca', 'modelo_limpo', 'modelo_generico', 'modelo_busca_praw']:
            if col in df.columns:
                df[col] = df[col].fillna('').astype(str)
        
        pendentes = []
        
        for _, row in df.iterrows():
            id_unico = row['id_unico']
            nome_arquivo = f"{TextProcessor.limpar_nome_arquivo(id_unico)}.json"
            
            if not (DIRETORIO_BRUTO / nome_arquivo).exists():
                # Converte a row para dict já com strings
                row_dict = row.to_dict()
                # Garante que campos críticos sejam strings
                for col in ['marca', 'modelo_limpo', 'modelo_generico', 'modelo_busca_praw']:
                    if col in row_dict and pd.isna(row_dict[col]):
                        row_dict[col] = ''
                    elif col in row_dict:
                        row_dict[col] = str(row_dict[col])
                pendentes.append(row_dict)
        
        await self.log(f"📊 Carregados {len(pendentes)} modelos pendentes de {len(df)} totais")
        return pendentes
    
    async def agrupar_por_familia(self, modelos: List[Dict]) -> Dict[str, List[Dict]]:
        """Agrupa modelos por família para coalescência."""
        familias = defaultdict(list)
        
        for modelo in modelos:
            familia = FamilyManager.identificar_familia(modelo)
            familias[familia].append(modelo)
        
        await self.log(f"🏷️  Identificadas {len(familias)} famílias únicas")
        
        # Log das 5 maiores famílias
        maiores = sorted(familias.items(), key=lambda x: len(x[1]), reverse=True)[:5]
        for familia, modelos_lista in maiores:
            await self.log(f"   - {familia}: {len(modelos_lista)} modelos")
        
        return familias
    
    def _construir_query_categoria(self, familias: Dict[str, List[Dict]], categoria: str, termos: List[str]) -> str:
        """
        Constrói query para uma categoria específica.
        Formato CORRETO: (termo_categoria1 OR termo_categoria2) AND (modelo1 OR modelo2)
        """
        # 🔥 PARTE 1: Termos da categoria (o que estamos procurando)
        termos_limitados = termos[:8]  # Limita a 8 termos por query
        termos_com_aspas = [f'"{t}"' if ' ' in t else t for t in termos_limitados]
        
        if not termos_com_aspas:
            return ""
        
        parte_categoria = f"({' OR '.join(termos_com_aspas)})"
        
        # 🔥 PARTE 2: Modelos (apenas alguns representativos, não todos!)
        # Pega no máximo 5 famílias, cada uma com 2 modelos
        familias_limitadas = list(familias.items())[:10]  # Reduzido de 20 para 10
        queries_modelos = []
        
        for familia, modelos in familias_limitadas:
            # Pega até 2 modelos por família
            for modelo in modelos[:2]:
                q = TextProcessor.gerar_query_final(
                    modelo.get('modelo_limpo', ''),
                    modelo.get('modelo_generico'),
                    modelo.get('modelo_busca_praw')
                )
                if q and len(q) > 2 and q not in queries_modelos:
                    queries_modelos.append(f'"{q}"')
        
        if not queries_modelos:
            return parte_categoria  # Só busca pelos termos da categoria
        
        # Limita a 20 modelos no total (evita query gigante)
        queries_modelos = queries_modelos[:20]
        parte_modelos = f"({' OR '.join(queries_modelos)})"
        
        # 🔥 PARTE 3: Termos negativos
        if self.termos_negativos:
            negativos_limitados = self.termos_negativos[:10]
            parte_negativa = f"NOT ({' OR '.join(negativos_limitados)})"
        else:
            parte_negativa = ""
        
        # 🔥 QUERY CORRETA: (termos_categoria) AND (modelos) NOT (negativos)
        query = f"{parte_categoria} AND {parte_modelos} {parte_negativa}".strip()
        
        # Se a query ainda for muito longa, simplifica ainda mais
        if len(query) > 1500:
            # Tenta com apenas 10 modelos
            queries_modelos = queries_modelos[:10]
            parte_modelos = f"({' OR '.join(queries_modelos)})"
            query = f"{parte_categoria} AND {parte_modelos} {parte_negativa}".strip()
        
        return query

    async def processar_categoria(
        self, 
        service: RedditServiceV10Async, 
        categoria: str, 
        termos: List[str],
        familias: Dict[str, List[Dict]],
        todos_modelos: List[Dict]
    ) -> int:
        """
        Processa UMA categoria com UMA busca coalescida.
        Retorna número de posts encontrados.
        """
        inicio_categoria = datetime.datetime.now()
        
        await self.log(f"\n{'='*70}")
        await self.log(f"🎯 PROCESSANDO CATEGORIA: '{categoria}'")
        await self.log(f"   📝 Termos: {len(termos)} termos")
        await self.log(f"   🏷️  Famílias: {len(familias)} famílias")
        await self.log(f"{'='*70}")
        
        # Constrói query coalescida
        query = self._construir_query_categoria(familias, categoria, termos)
        
        if not query or len(query) < 20:
            await self.log(f"⚠️ Query muito curta ou inválida para categoria '{categoria}'", "WARNING")
            return 0
        
        await self.log(f"🔍 Query gerada (primeiros 200 chars):")
        await self.log(f"   {query[:200]}...")
        
        try:
            # UMA única busca para toda a categoria
            busca_start = datetime.datetime.now()
            posts, stats = await service.buscar_termo_generico(
                query,
                time_filter=self.time_filter,
                task_id=f"cat_{categoria[:20]}"
            )
            busca_tempo = (datetime.datetime.now() - busca_start).total_seconds()
            
            await self.log(f"   ⏱️  Busca concluída em {busca_tempo:.1f}s")
            await self.log(f"   📥 Posts brutos encontrados: {len(posts)}")
            
            self.total_posts_baixados += len(posts)
            
            if not posts:
                await self.log(f"⚠️ Nenhum post encontrado para categoria '{categoria}'")
                return 0
            
            # Cache os posts para uso nesta categoria
            self.cache_posts_por_categoria[categoria] = posts
            
            # Agora distribui para cada modelo
            await self.log(f"\n📦 Distribuindo posts para {len(todos_modelos)} modelos...")
            
            modelos_validados = 0
            for idx, modelo in enumerate(todos_modelos, 1):
                if idx % 50 == 0:
                    await self.log(f"   Progresso: {idx}/{len(todos_modelos)} modelos")
                
                # Verifica se este modelo já foi processado para esta categoria
                id_unico = modelo['id_unico']
                arquivo_destino = DIRETORIO_BRUTO / f"{TextProcessor.limpar_nome_arquivo(id_unico)}.json"
                
                # Se já existe arquivo, carrega e atualiza
                if arquivo_destino.exists():
                    async with aiofiles.open(arquivo_destino, 'r', encoding='utf-8') as f:
                        conteudo = json.loads(await f.read())
                    existing_posts = conteudo.get('posts', [])
                else:
                    existing_posts = []
                    conteudo = {
                        "modelo_original": modelo.get('modelo_limpo', ''),
                        "modelo_generico": modelo.get('modelo_generico', ''),
                        "id_notebook": id_unico,
                        "posts": []
                    }
                
                # Filtra posts que contêm este modelo
                posts_validados = TextProcessor.validar_presenca_modelo(modelo, posts)
                
                if posts_validados:
                    modelos_validados += 1
                    
                    # Adiciona metadados da categoria aos posts
                    for post in posts_validados:
                        post['categoria_origem'] = categoria
                        post['termos_categoria'] = termos[:5]
                    
                    # Mescla com posts existentes (evita duplicatas por ID)
                    ids_existentes = {p['id'] for p in existing_posts}
                    novos_posts = [p for p in posts_validados if p['id'] not in ids_existentes]
                    
                    if novos_posts:
                        existing_posts.extend(novos_posts)
                        conteudo['posts'] = existing_posts
                        conteudo['total_posts'] = len(existing_posts)
                        
                        # Salva arquivo atualizado
                        async with aiofiles.open(arquivo_destino, 'w', encoding='utf-8') as f:
                            await f.write(json.dumps(conteudo, ensure_ascii=False, indent=4))
                        
                        # Registra sucesso
                        self.modelos_sucesso.append({
                            "id": id_unico,
                            "categoria": categoria,
                            "novos_posts": len(novos_posts),
                            "total_posts": len(existing_posts)
                        })
                        
                        await self.log(f"      ✅ {modelo['modelo_limpo'][:30]}... +{len(novos_posts)} posts (total: {len(existing_posts)})", "DEBUG")
            
            tempo_total = (datetime.datetime.now() - inicio_categoria).total_seconds()
            await self.log(f"\n✅ Categoria '{categoria}' finalizada em {tempo_total:.1f}s")
            await self.log(f"   📊 Modelos com posts: {modelos_validados}/{len(todos_modelos)}")
            await self.log(f"   📈 Taxa de aproveitamento: {(modelos_validados/len(todos_modelos)*100):.1f}%")
            
            return len(posts)
            
        except Exception as e:
            await self.log(f"❌ Erro ao processar categoria '{categoria}': {str(e)}", "ERROR")
            return 0
    
    async def executar(self):
        """Executa o pipeline invertido."""
        
        await self.log(f"\n{'🚀'*35}")
        await self.log(f"INICIANDO PIPELINE INVERTIDO V11")
        await self.log(f"📅 Início: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        await self.log(f"⚙️  Configurações:")
        await self.log(f"   - Concorrência máxima: {self.max_concurrency}")
        await self.log(f"   - Time filter: {self.time_filter}")
        await self.log(f"   - Categorias: {len(self.categorias)}")
        await self.log(f"{'🚀'*35}\n")
        
        # 1. Carrega modelos pendentes
        modelos_pendentes = await self.carregar_modelos_pendentes()
        
        if not modelos_pendentes:
            await self.log("✅ Todos os modelos já foram processados!")
            return
        
        # 2. Agrupa por família
        familias = await self.agrupar_por_familia(modelos_pendentes)
        
        # 3. Processa cada categoria
        async with RedditServiceV10Async() as service:
            total_categorias = len(self.categorias)
            categorias_processadas = 0
            
            for idx, (categoria, termos) in enumerate(self.categorias.items(), 1):
                await self.log(f"\n📌 Categoria {idx}/{total_categorias}: {categoria}")
                
                try:
                    async with self.semaphore:
                        posts_encontrados = await self.processar_categoria(
                            service, categoria, termos, familias, modelos_pendentes
                        )
                        categorias_processadas += 1
                        
                except Exception as e:
                    await self.log(f"❌ Falha crítica na categoria {categoria}: {e}", "ERROR")
                    continue
            
            # 4. Relatório final
            await self.gerar_relatorio_final(modelos_pendentes)
    
    async def gerar_relatorio_final(self, modelos_pendentes: List[Dict]):
        """Gera relatório detalhado da extração."""
        
        tempo_total = (datetime.datetime.now() - self.start_time).total_seconds()
        
        # Conta modelos que receberam pelo menos um post
        modelos_com_dados = set()
        for arquivo in DIRETORIO_BRUTO.glob("*.json"):
            if arquivo.stat().st_size > 100:  # Arquivo não vazio
                modelo_id = arquivo.stem
                modelos_com_dados.add(modelo_id)
        
        await self.log(f"\n{'='*70}")
        await self.log(f"📊 RELATÓRIO FINAL")
        await self.log(f"{'='*70}")
        await self.log(f"⏱️  Tempo total: {tempo_total:.1f}s ({tempo_total/60:.1f}min)")
        await self.log(f"📥 Posts baixados (brutos): {self.total_posts_baixados}")
        await self.log(f"\n📌 Modelos:")
        await self.log(f"   ├─ Pendentes no início: {len(modelos_pendentes)}")
        await self.log(f"   ├─ Com dados salvos: {len(modelos_com_dados)}")
        await self.log(f"   └─ Taxa de sucesso: {(len(modelos_com_dados)/len(modelos_pendentes)*100):.1f}%")
        
        # Salva logs
        if self.modelos_sem_resultados:
            df_vazios = pd.DataFrame(self.modelos_sem_resultados)
            df_vazios.to_csv(DIRETORIO_LOGS / f"modelos_sem_resultados_{self.session_id}.csv", index=False)
            await self.log(f"\n⚠️ {len(self.modelos_sem_resultados)} modelos sem resultados salvos em logs")
        
        await self.log(f"\n✅ Pipeline finalizado com sucesso!")
        await self.log(f"{'='*70}\n")


# =================================================================
# FUNÇÃO DE COMPARAÇÃO (PARA TESTES)
# =================================================================
async def comparar_abordagens():
    """
    Função opcional para comparar a eficiência entre abordagem antiga e nova.
    """
    print("\n📊 COMPARAÇÃO DE ABORDAGENS\n")
    
    # Abordagem antiga (estimativa)
    num_modelos = 500
    num_categorias = 7
    requests_antigo = num_modelos * num_categorias
    tempo_estimado_antigo = requests_antigo * 6  # 6 segundos por requisição
    
    # Abordagem nova
    requests_novo = num_categorias  # 1 por categoria
    tempo_estimado_novo = requests_novo * 30  # 30 segundos por requisição (mais dados)
    
    print(f"Abordagem Antiga (seu código original):")
    print(f"   - Requisições à API: {requests_antigo}")
    print(f"   - Tempo estimado: {tempo_estimado_antigo//60} minutos")
    print(f"   - Risco de Rate Limit: ALTO")
    
    print(f"\nAbordagem Nova (Pipeline Invertido):")
    print(f"   - Requisições à API: {requests_novo}")
    print(f"   - Tempo estimado: {tempo_estimado_novo//60} minutos")
    print(f"   - Risco de Rate Limit: BAIXO")
    
    print(f"\n✅ Redução de {((requests_antigo - requests_novo) / requests_antigo * 100):.1f}% nas requisições!")
    print(f"✅ Aceleração estimada: {requests_antigo / requests_novo:.1f}x\n")


# =================================================================
# MAIN
# =================================================================
# if __name__ == "__main__":
#     # Opcional: roda comparação primeiro
#     asyncio.run(comparar_abordagens())
    
#     # Executa pipeline invertido
#     pipeline = RedditExtractionPipelineInverted(
#         max_concurrency=6,  # Ajuste conforme sua quota da API
#         time_filter="all"   # Pode mudar para "year", "month", etc.
#     )
#     asyncio.run(pipeline.executar())
# No final do arquivo, temporariamente:
if __name__ == "__main__":
    # asyncio.run(comparar_abordagens())
    
    pipeline = RedditExtractionPipelineInverted(
        max_concurrency=2,  # Reduz para teste
        time_filter="month"  # Apenas último mês para teste rápido
    )
    
    # 🔥 Força apenas uma categoria para teste
    pipeline.categorias = {"thermal_failure": pipeline.categorias["thermal_failure"]}
    
    asyncio.run(pipeline.executar())