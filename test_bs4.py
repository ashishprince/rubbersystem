import urllib.request
import ssl
from bs4 import BeautifulSoup

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

req = urllib.request.Request(
    'https://rubberboard.gov.in/public', 
    headers={'User-Agent': 'Mozilla/5.0'}
)

try:
    with urllib.request.urlopen(req, context=ctx) as response:
        html = response.read().decode('utf-8')
        soup = BeautifulSoup(html, 'html.parser')
        
        # Look for the cell containing RSS4
        rows = soup.find_all('tr')
        for r in rows:
            text = r.get_text(separator=' | ', strip=True)
            if 'RSS' in text and '4' in text:
                print(f"Row: {text}")
                    
except Exception as e:
    print(f"Error: {e}")
