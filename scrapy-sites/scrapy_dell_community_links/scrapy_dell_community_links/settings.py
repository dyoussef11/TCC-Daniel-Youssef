# Scrapy settings for scrapy_dell_community_links project
#
# For simplicity, this file contains only settings considered important or
# commonly used. You can find more settings consulting the documentation:
#
#     https://docs.scrapy.org/en/latest/topics/settings.html
#     https://docs.scrapy.org/en/latest/topics/downloader-middleware.html
#     https://docs.scrapy.org/en/latest/topics/spider-middleware.html

BOT_NAME = "scrapy_dell_community_links"

SPIDER_MODULES = ["scrapy_dell_community_links.spiders"]
NEWSPIDER_MODULE = "scrapy_dell_community_links.spiders"

# BOT_NAME = 'dell_scraper'

# SPIDER_MODULES = ['dell_scraper.spiders']
# NEWSPIDER_MODULE = 'dell_scraper.spiders'

ADDONS = {}


# Crawl responsibly by identifying yourself (and your website) on the user-agent
#USER_AGENT = "scrapy_dell_community_links (+http://www.yourdomain.com)"

# Obey robots.txt rules
ROBOTSTXT_OBEY = True

# Mantenha 1 request concorrente (limitado pelo navegador único)
CONCURRENT_REQUESTS = 1

# O Scrapy vai esperar esse tempo ENTRE requests.
# Isso imita um humano lendo os resultados antes de buscar o próximo modelo.
# 2 a 4 segundos é seguro e eficiente.
DOWNLOAD_DELAY = 3 
RANDOMIZE_DOWNLOAD_DELAY = True # Varia entre 0.5x e 1.5x do delay (ex: 1.5s a 4.5s)

# Headers (User-Agent)
# O UC já cuida disso, mas é bom garantir que o Scrapy não envie headers conflitantes
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

# --- ATIVAR O MIDDLEWARE ---
DOWNLOADER_MIDDLEWARES = {
#    'dell_scraper.middlewares.UcDellMiddleware': 543,
   'scrapy_dell_community_links.middlewares.UcDellMiddleware': 543,
   # Desabilita middlewares padrão que podem conflitar ou são desnecessários
   'scrapy.downloadermiddlewares.useragent.UserAgentMiddleware': None,
}

# Logs
LOG_LEVEL = 'INFO'

# Ignorar robots.txt (já que estamos simulando user real)
ROBOTSTXT_OBEY = False

# Set settings whose default value is deprecated to a future-proof value
FEED_EXPORT_ENCODING = "utf-8"
