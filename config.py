# Configuración del Powerball Scraper

# URL del sitio web de Powerball (página principal donde aparecen los resultados)
POWERBALL_URL = 'https://www.powerball.com/'

# Archivo para resultados actuales (se sobrescribe cada vez)
RESULTS_FILE = 'resultados_actuales.json'

# Archivo para histórico de resultados (se va agregando)
HISTORIC_FILE = 'historico_resultados.json'

# Archivo de log
LOG_FILE = 'powerball_scraper.log'

# Configuración de reintentos
MAX_RETRY_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 5