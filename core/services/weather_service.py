import requests
from django.conf import settings
from django.core.cache import cache
import logging

logger = logging.getLogger(__name__)

def get_weather_for_coordinates(lat, lng):
    """
    Fetches real-time weather data for given coordinates, utilizing Django's cache
    to prevent excessive API calls. Caches the result for 30 minutes.
    """
    if not lat or not lng:
        return _get_default_weather_data("Coordinates unavailable")

    # Create a unique cache key for these coordinates (rounding to ~1km precision to maximize cache hits)
    cache_key = f"weather_{round(float(lat), 3)}_{round(float(lng), 3)}"
    
    # Return cached data if available
    cached_data = cache.get(cache_key)
    if cached_data:
        return cached_data

    api_key = getattr(settings, 'WEATHER_API_KEY', None)
    if not api_key or api_key == 'demo_key_provide_one_in_env':
        logger.warning("WEATHER_API_KEY is not set or is using the default demo key.")
        return _get_default_weather_data("API Key not configured")

    try:
        # OpenWeatherMap Current Weather Data API
        url = "https://api.openweathermap.org/data/2.5/weather"
        params = {
            'lat': lat,
            'lon': lng,
            'appid': api_key,
            'units': 'metric' # Returns temperature in Celsius
        }
        
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()

        temperature = data.get('main', {}).get('temp', 0)
        humidity = data.get('main', {}).get('humidity', 0)
        condition = data.get('weather', [{}])[0].get('main', 'Unknown')
        
        # OpenWeatherMap returns rain/snow volume in the last 1 hour, or sometimes pop in forecast.
        # For current weather, we infer rain probability based on condition and historical metrics.
        # If 'rain' key exists, it is raining. We synthesize a probability for the UI.
        rain_probability = 0
        if 'Rain' in condition or 'Drizzle' in condition:
            rain_probability = 100
        elif 'Clouds' in condition and data.get('clouds', {}).get('all', 0) > 80:
            rain_probability = 60 # High cloud cover inference
        
        weather_data = {
            "temperature": round(temperature, 1),
            "rain_probability": rain_probability,
            "condition": condition,
            "humidity": humidity,
            "alert_level": _calculate_alert_level(temperature, humidity, condition, rain_probability),
            "alert_message": _generate_alert_message(temperature, humidity, condition, rain_probability)
        }

        # Cache the result for 30 minutes (1800 seconds)
        cache.set(cache_key, weather_data, 1800)
        
        return weather_data

    except requests.exceptions.RequestException as e:
        logger.error(f"Weather API request failed: {e}")
        return _get_default_weather_data("API Request Failed")
    except Exception as e:
        logger.error(f"Unexpected error fetching weather: {e}")
        return _get_default_weather_data("Weather parsing error")


def _calculate_alert_level(temperature, humidity, condition, rain_probability):
    """Business Intelligence: Determine operational alert level based on weather."""
    if 'Storm' in condition or 'Thunder' in condition:
        return 'danger'
    if temperature > 38:
        return 'danger'
    
    if rain_probability > 60:
        return 'caution'
    if temperature > 35:
        return 'caution'
    if humidity > 90:
        return 'caution'
        
    return 'normal'

def _generate_alert_message(temperature, humidity, condition, rain_probability):
    """Generate human-readable alert messages based on thresholds."""
    if 'Storm' in condition or 'Thunder' in condition:
        return "Thunderstorm warning. Field activity not advised."
    if temperature > 38:
        return "Extreme heat danger. Suspend field operations."
    
    messages = []
    if rain_probability > 60:
        messages.append("High rainfall probability. Consider postponing tapping.")
    if temperature > 35:
        messages.append("High heat. Ensure adequate hydration.")
    if humidity > 90:
        messages.append("High humidity may affect drying times.")
        
    if messages:
        # Join multiple caution messages if applicable, or just return the first
        return " ".join(messages)
        
    return "Weather optimal for field operations."

def _get_default_weather_data(error_msg="Unavailable"):
    """Fallback when API fails or is unconfigured."""
    return {
        "temperature": "--",
        "rain_probability": "--",
        "condition": "Unknown",
        "humidity": "--",
        "alert_level": "normal",
        "alert_message": f"Weather data unavailable ({error_msg})."
    }
