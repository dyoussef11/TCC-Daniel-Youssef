import sys
import scrapy
import csv 
from pathlib import Path

# Configuração de Caminhos
caminho_script = Path(__file__).resolve().parent
caminho_raiz_projeto = caminho_script.parent.parent.parent.parent
sys.path.append(str(caminho_raiz_projeto))

# Ajuste esses caminhos conforme sua necessidade real
DIRETORIO_DADOS_WEBSCRAPPING = caminho_raiz_projeto / "1- WebScrapping - Links Apenas" / "data"

class DellSpider(scrapy.Spider):
    name = "dell_postagens.py"
    allowed_domains = ["dell.com"]
    base_url = "https://www.dell.com/community/pt/categories/comunidade-da-dell"

    custom_settings = {
        'FEEDS': {
            str(DIRETORIO_DADOS_WEBSCRAPPING / 'links_discussoes_Dell_Brasil_UNICO_MODELO.csv'): {
                'format': 'csv',
                'fields': ['Titulo', 'Link_da_Discussao', 'Modelo_Buscado', 'Categoria_Pesquisa'],
                'overwrite': True
            }
        }
    }

    def start_requests(self):
        # LISTA MANUAL PARA TESTE
        modelos_a_buscar = ['"Dell G7 15 7588"']
        
        # SE QUISER USAR O CSV DEPOIS, DESCOMENTE:
        # try:
        #     caminho_entrada = ... (seu caminho)
        #     with open(caminho_entrada, 'r', encoding='utf-8') as f:
        #         reader = csv.DictReader(f)
        #         for row in reader:
        #             if 'DELL' in row.get('Marca', '').upper(): 
        #                  modelos_a_buscar.append(row.get('Modelo', ''))
        # except Exception as e:
        #     self.logger.error(f"Erro CSV: {e}")

        self.logger.info(f"Iniciando busca para {len(modelos_a_buscar)} modelos.")
        
        for modelo in modelos_a_buscar:
             yield scrapy.Request(
                url=self.base_url,
                callback=self.parse,
                dont_filter=True,
                meta={
                    'use_selenium': True,
                    'action': 'init_search',
                    'modelo': modelo, 
                    'download_timeout': 120 # Aumentado para dar margem ao Selenium
                }
            )

    def parse(self, response):
        modelo_atual = response.meta['modelo']

        # --- LÓGICA DE CAPTURA DA CATEGORIA (DO HTML) ---
        categoria_detectada = response.css('div.checkbox[aria-checked="true"]').get()
        
        if not categoria_detectada:
            categoria_detectada = "Não Identificada/Geral"
        else:
            categoria_detectada = categoria_detectada.strip()
        # ------------------------------------------------

        elements = response.css("section.conversation-card .conversation-card__details a[title]")
        
        if not elements:
            self.logger.info(f"Sem resultados visíveis para {modelo_atual}")
            # Não damos return aqui porque as vezes queremos ver se tem paginação mesmo sem cards (raro, mas possivel)
        
        for element in elements:
            item = {} 
            item['Titulo'] = element.attrib.get('title')
            item['Link_da_Discussao'] = element.attrib.get('href')
            item['Modelo_Buscado'] = modelo_atual
            item['Categoria_Pesquisa'] = categoria_detectada
            yield item

        # Paginação
        next_page_ativo = response.css('li[title="Próximo"]:not(.pagination-disabled)')
        
        if next_page_ativo:
            self.logger.info(f"Indo para próxima página de: {modelo_atual}")
            yield scrapy.Request(
                url=response.url, # A URL não muda no Selenium, mas o Scrapy precisa de uma para o request
                callback=self.parse,
                dont_filter=True,
                meta={
                    'use_selenium': True,
                    'action': 'next_page',
                    'modelo': modelo_atual,
                }
            )