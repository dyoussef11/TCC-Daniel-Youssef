from scrapy import signals
import time
import random
import undetected_chromedriver as uc
from scrapy.http import HtmlResponse
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from urllib.parse import quote 

class UcDellMiddleware:
    def __init__(self):
        self.driver = None
        self.cookie_popup_fechado = False

    @classmethod
    def from_crawler(cls, crawler):
        middleware = cls()
        crawler.signals.connect(middleware.spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(middleware.spider_closed, signal=signals.spider_closed)
        return middleware

    def spider_opened(self, spider):
        options = uc.ChromeOptions()
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        
        # Comente a linha abaixo se quiser ver o navegador trabalhando (útil para debug)
        # options.add_argument("--blink-settings=imagesEnabled=false") 

        spider.logger.info(">>> TENTANDO INICIAR DRIVER (Modo Automático)...")

        try:
            # CONFIGURAÇÃO CRÍTICA PARA WINDOWS
            # version_main=None: Deixa o UC descobrir a versão sozinho
            # use_subprocess=True: Evita que o processo fique "preso" e dê timeout
            self.driver = uc.Chrome(
                options=options, 
                headless=False, 
                version_main=None, 
                use_subprocess=True
            )
            self.wait = WebDriverWait(self.driver, 20)
            spider.logger.info(">>> SUCESSO: Navegador Aberto! <<<")
            
        except Exception as e:
            spider.logger.error(f"!!! ERRO CRÍTICO AO ABRIR O CHROME: {e}")
            spider.logger.error("DICA: Se você usa Chrome Canary/Dev (v143+), desinstale e instale o Chrome Estável.")
            # Encerra o spider forçadamente para não gerar erros de 'NoneType' depois
            raise e

    def spider_closed(self, spider):
        if self.driver:
            try:
                spider.logger.info("Fechando navegador...")
                self.driver.quit()
            except:
                pass

    def process_request(self, request, spider):
        if not request.meta.get('use_selenium'):
            return None

        # Verificação de segurança: Se o driver não abriu, não tenta navegar
        if not self.driver:
            spider.logger.error("O Driver não existe. Cancelando request.")
            return None

        action = request.meta.get('action')
        modelo = request.meta.get('modelo')

        if not modelo:
            return None
        
        modelo_str = str(modelo) 

        # --- ABERTURA INICIAL ---
        if action == 'init_search':
            spider.logger.info(f"Busca Direta: {modelo_str}")
            
            modelo_limpo = modelo_str.replace('"', '').strip()
            termo_codificado = quote(f'"{modelo_limpo}"') 
            
            # URL com ID fixo da categoria, mas o nome pegaremos dinamicamente depois
            url_direta = (
                f"https://www.dell.com/community/pt/conversations/search"
                f"?q={termo_codificado}"
                f"&conversationType=POST"
                f"&categoryIds=647a1e3eabcdf40a31989978"
                f"&page=1"
            )

            try:
                self.driver.get(url_direta)
            except Exception as e:
                spider.logger.error(f"Erro ao carregar URL: {e}")
                return None

            # Fecha Popup de Cookies (uma vez por sessão)
            if not self.cookie_popup_fechado:
                try:
                    cookie_btn = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))
                    )
                    cookie_btn.click()
                    self.cookie_popup_fechado = True
                except:
                    pass # As vezes não aparece ou já foi aceito

            # Wait Inteligente (Espera resultados ou aviso de "sem resultados")
            try:
                self.wait.until(EC.any_of(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "section.conversation-card")),
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".search-no-results")),
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".nodata-container"))
                ))
            except Exception:
                spider.logger.warning(f"Timeout esperando elementos na página para: {modelo_str}")

        # --- PAGINAÇÃO ---
        elif action == 'next_page':
            spider.logger.info(f"Paginação: {modelo_str}")
            try:
                # Scroll para garantir que o botão esteja visível
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1)
                
                next_btn = self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'li[title="Próximo"]')))
                self.driver.execute_script("arguments[0].click();", next_btn)
                time.sleep(random.uniform(3, 5)) # Delay humano
            except Exception:
                spider.logger.info("Fim da paginação (botão não encontrado ou erro).")

        return HtmlResponse(
            url=self.driver.current_url,
            body=self.driver.page_source,
            encoding='utf-8',
            request=request
        )