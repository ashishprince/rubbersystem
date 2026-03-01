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
    """
    Attempts to extract RSS4 price from Rubber Board India.
    Returns float or None on failure.
    """
    urls_to_try = [
        'https://rubberboard.gov.in/public',
        'https://www.rubberboard.org.in/rubberprices',
    ]

    headers = {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/120.0.0.0 Safari/537.36'
        )
    }

    for url in urls_to_try:
        try:
            response = requests.get(url, headers=headers, timeout=8)
            if response.status_code != 200:
                continue

            text = response.text

            # Pattern 1: look for RSS4 followed by a price like 170.50 or 170
            patterns = [
                r'RSS[\s\-]?4[\s\S]{0,100}?(\d{3,4}(?:\.\d{1,2})?)',
                r'RSS4[\s\S]{0,50}?₹?\s*(\d{3,4}(?:\.\d{1,2})?)',
                r'Ribbed\s+Smoked\s+Sheet[\s\S]{0,200}?(\d{3,4}(?:\.\d{1,2})?)',
            ]

            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    price = float(match.group(1))
                    # Sanity check: rubber price should be between 100-500 ₹/kg
                    if 100 <= price <= 500:
                        return price

        except requests.exceptions.Timeout:
            logger.warning(f"MarketPriceService: Timeout fetching {url}")
        except requests.exceptions.RequestException as e:
            logger.warning(f"MarketPriceService: Request error for {url}: {e}")
        except Exception as e:
            logger.warning(f"MarketPriceService: Parse error for {url}: {e}")

    return None


def _no_price_response():
    return {
        'success': False,
        'price': None,
        'status': 'unavailable',
        'fetched_at': None,
        'message': 'No market price data available yet.',
    }
