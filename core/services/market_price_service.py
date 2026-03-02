import re
import logging
import requests
from django.utils import timezone

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────

def get_market_price_for_dashboard():
    """
    Returns latest market price for the dashboard.
    Auto-fetches once per day on first call; otherwise returns cached DB value.
    Never raises — always returns a structured dict.
    """
    from core.models import MarketPrice

    latest = MarketPrice.objects.filter(is_active=True).first()

    # Auto-fetch only if no record exists OR last fetch was before today
    today = timezone.now().date()
    needs_fetch = (
        latest is None or
        latest.fetched_at.date() < today
    )

    if needs_fetch:
        result = _fetch_and_save(fetch_type='AUTO')
        if result['success']:
            return result
        # Fall back to last stored value if fetch failed
        if latest:
            return {
                'success': False,
                'price': latest.price_per_kg,
                'status': 'cached',
                'fetched_at': latest.fetched_at,
                'message': 'Live fetch failed. Showing last known price.',
            }
        return _no_price_response()

    return {
        'success': True,
        'price': latest.price_per_kg,
        'status': 'cached',
        'fetched_at': latest.fetched_at,
        'message': '',
    }


def manual_fetch():
    """
    Forces an immediate fresh fetch. Called from the manual AJAX endpoint.
    Returns structured dict.
    """
    result = _fetch_and_save(fetch_type='MANUAL')
    if result['success']:
        return result

    # Return last cached if available
    from core.models import MarketPrice
    latest = MarketPrice.objects.filter(is_active=True).first()
    if latest:
        return {
            'success': False,
            'price': latest.price_per_kg,
            'status': 'cached',
            'fetched_at': latest.fetched_at,
            'message': 'Live fetch failed. Showing last known price.',
        }
    return _no_price_response()


# ─────────────────────────────────────────────
# INTERNAL
# ─────────────────────────────────────────────

def _fetch_and_save(fetch_type='AUTO'):
    """
    Scrapes RSS4 price from Rubber Board India and saves to DB.
    Returns structured dict. Never raises.
    """
    try:
        price = _scrape_rubber_price()
        if price is None:
            logger.warning("MarketPriceService: Could not extract RSS4 price from source.")
            return {'success': False, 'price': None, 'status': 'failed',
                    'fetched_at': None, 'message': 'Could not parse price from source.'}

        from core.models import MarketPrice

        # Deactivate all previous records
        MarketPrice.objects.filter(is_active=True).update(is_active=False)

        # Save new active record
        record = MarketPrice.objects.create(
            price_per_kg=price,
            fetch_type=fetch_type,
            is_active=True,
        )

        logger.info(f"MarketPriceService: Saved RSS4 price ₹{price}/kg ({fetch_type})")
        return {
            'success': True,
            'price': price,
            'status': 'live',
            'fetched_at': record.fetched_at,
            'message': '',
        }

    except Exception as e:
        logger.error(f"MarketPriceService: Unexpected error — {e}")
        return {'success': False, 'price': None, 'status': 'failed',
                'fetched_at': None, 'message': str(e)}


def _scrape_rubber_price():
    """Scrape RSS4 price from Rubber Board India."""
    import urllib.request
    import ssl
    from bs4 import BeautifulSoup
    
    urls_to_try = [
        'https://rubberboard.gov.in/public',
        'https://www.rubberboard.org.in/rubberprices',
    ]
    
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    # Try multiple URLs for redundancy
    for url in urls_to_try:
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, context=ctx, timeout=15) as response:
                html = response.read().decode('utf-8')
                soup = BeautifulSoup(html, 'html.parser')

                # Look through table rows for RSS4
                rows = soup.find_all('tr')
                for row in rows:
                    cells = row.find_all('td')
                    if len(cells) >= 3:
                        # Typically: Grade, Kochi Price, Kottayam Price
                        row_text = row.get_text(separator=' ', strip=True).upper()
                        if 'RSS' in row_text and '4' in row_text:
                            # Prioritize finding the INR price (which is per 100kg, so it will be a large number)
                            for cell in cells:
                                cell_text = cell.get_text(strip=True).replace('₹', '').replace(',', '').replace('$', '').strip()
                                try:
                                    val = float(cell_text)
                                    # The INR price for 100kg is typically between 10,000 and 50,000
                                    if val > 1000:
                                        price_per_kg = val / 100.0
                                        # Sanity check: Rubber price should be roughly 100-500 INR/kg
                                        if 100 <= price_per_kg <= 500:
                                            return round(price_per_kg, 2)
                                except ValueError:
                                    continue
        except Exception as e:
            logger.warning(f"MarketPriceService: Failed fetching/parsing {url}: {e}")
            continue

    logger.error("MarketPriceService: Could not extract RSS4 price from sources using BS4.")
    return None


def _no_price_response():
    return {
        'success': False,
        'price': None,
        'status': 'unavailable',
        'fetched_at': None,
        'message': 'No market price data available yet.',
    }
