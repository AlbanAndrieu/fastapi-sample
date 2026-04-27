import requests
import os
from bs4 import BeautifulSoup

DOWNLOAD_URL = os.environ.get("DOWNLOAD_URL", "https://example.com/resources/")


html = requests.get(DOWNLOAD_URL, timeout=1).text
soup = BeautifulSoup(html, "html.parser")
for link in soup.find_all("a", href=True):
    if link["href"].endswith(".pdf"):
        file_url = DOWNLOAD_URL + link["href"]
        file_data = requests.get(file_url, timeout=1).content
        open(link["href"], "wb").write(file_data)
