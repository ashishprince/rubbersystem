import urllib.request
import re
import ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

req = urllib.request.Request(
    'https://rubberboard.gov.in/public', 
    headers={'User-Agent': 'Mozilla/5.0'}
)

try:
    with urllib.request.urlopen(req, context=ctx) as response:
        text = response.read().decode('utf-8')
        print(f"Content length: {len(text)}")
        
        # Test original patterns
        patterns = [
            r'RSS[\s\-]?4[\s\S]{0,100}?(\d{3,4}(?:\.\d{1,2})?)',
            r'RSS4[\s\S]{0,50}?₹?\s*(\d{3,4}(?:\.\d{1,2})?)',
            r'Ribbed\s+Smoked\s+Sheet[\s\S]{0,200}?(\d{3,4}(?:\.\d{1,2})?)',
        ]
        
        for p in patterns:
            match = re.search(p, text, re.IGNORECASE)
            print(f"Pattern '{p}' -> {match.group(1) if match else 'None'}")
            
        print("\nAll occurrences of RSS4 in text:")
        occurrences = re.findall(r'RSS[\s\-]?4.{0,300}', text, re.IGNORECASE)
        for occ in occurrences:
            print(repr(occ))
            
except Exception as e:
    print(f"Error: {e}")
