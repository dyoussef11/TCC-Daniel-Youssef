# Define here the models for your scraped items
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/items.html

import scrapy


# class ScrapyDellCommunityLinksItem(scrapy.Item):
#     # define the fields for your item here like:
#     # name = scrapy.Field()
#     pass


class ScrapyDellCommunityLinksItem(scrapy.Item):
    Titulo = scrapy.Field()          # Título da Discussão
    Link_da_Discussao = scrapy.Field() # Link da Discussão
    Modelo_Buscado = scrapy.Field()  # Modelo Buscado
    Categoria_Pesquisa = scrapy.Field()
 
