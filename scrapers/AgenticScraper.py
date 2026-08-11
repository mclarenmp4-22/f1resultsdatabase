from ollama import chat
from duckduckgo_search import DDGS
from curl_cffi import requests
import time
import random
from bs4 import BeautifulSoup

SEARCH_MODEL = ""
CONTENT_MODEL = ""
INTEGRATION_MODEL = ""

class AgenticScraper:
    def __init__(self, search_model=SEARCH_MODEL, content_model=CONTENT_MODEL, integration_model=INTEGRATION_MODEL):
        self.search_model = search_model
        self.content_model = content_model
        self.integration_model = integration_model

    def search(query):
        """Searches for a query using the official DuckDuckGo search API"""
        with DDGS() as ddgs:
            results = ddgs.text(query)
            return [result for result in results]
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }
    def open_url(url, retries=3):
        """Opens a URL and returns the BeautifulSoup object of the page content. Retries on failure."""
        url = "https://" + url.replace("https://", "").replace("//", "/")
        last_exception = None

        for attempt in range(retries):
            try:
                response = requests.get(
                    url,
                    headers=headers,
                    impersonate="chrome",
                    timeout=30
                )
                if (
                    response.status_code == 302
                    and response.headers.get("location")
                    == "https://www.statsf1.com/errors/GenericErrorPage.htm"
                ):
                    raise Exception(
                        "You have been IP blocked by statsf1.com. Please wait and try again later."
                    )
                response.raise_for_status()
                if "statsf1.com" in url:
                    time.sleep(random.uniform(4, 15))
                global soup
                soup = BeautifulSoup(response.content, "html.parser")
                for element in soup(["script", "style", "nav", "footer", "header"]):
                    element.extract()
                text = soup.get_text(separator=" ", strip=True)          
                return (url, text)
            except Exception as e:
                last_exception = e
                print(f"Attempt {attempt + 1} failed for URL {url}: {e}")

                if attempt < retries - 1:
                    time.sleep(
                        random.expovariate(1 / (5 * (2 ** attempt)))
                    )
        if isinstance(last_exception, (requests.exceptions.Timeout, TimeoutError)):
            print("Timed out after all retries. Sleeping for 5 minutes...")
            time.sleep(300)
        raise RuntimeError(
            f"Failed to open URL {url} after {retries} attempts."
        ) from last_exception    
    def scrape_for_session(self, session):
        reliable_sources = ["https://en.wikipedia.org/wiki/", "https://www.statsf1.com/en/", "https://grandprix.com", "https://www.formula1.com", "https://www.motorsport.com"
                            , "https://www.motorsportmagazine.com/"]
        overall_scraped_content=[]
        

        
