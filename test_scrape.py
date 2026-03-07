import requests
import re
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def test_scrape():
    urls_to_try = [
        'https://rubberboard.gov.in/public',
        'https://www.rubberboard.org.in/rubberprices',
    ]

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    for url in urls_to_try:
        try:
            print(f"Trying {url}...")
            response = requests.get(url, headers=headers, timeout=15, verify=False)
            print(f"Status: {response.status_code}")
            if response.status_code != 200:
                continue

            text = response.text
            print(f"Got {len(text)} bytes. Sample:")
            # Find RSS4 occurrences
            occurrences = re.findall(r'.{0,30}RSS[\s\-]?4.{0,30}', text, re.IGNORECASE)
            print(f"Found {len(occurrences)} occurrences of RSS4")
            for occ in occurrences:
                print("...", occ, "...")

        except Exception as e:
            print(f"Error: {e}")

if __name__ == '__main__':
    test_scrape()
