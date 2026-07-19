# Configuración del Lottery Scraper (multi-juego)

# Archivo de log
LOG_FILE = 'lottery_scraper.log'

# Configuración de reintentos (por juego)
MAX_RETRY_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 10

# Timeout de peticiones HTTP (segundos)
REQUEST_TIMEOUT = 15

# Archivo combinado con el último resultado de todos los juegos
COMBINED_FILE = 'resultados_todos.json'

# Juegos a extraer.
# 'dias_sorteo': 0=Lunes, 1=Martes, ... 6=Domingo
# 'socrata_url': API de datos abiertos del estado de NY (data.ny.gov),
#                se usa como fuente de respaldo cuando el sitio oficial falla.
GAMES = {
    'powerball': {
        'nombre': 'Powerball',
        'url': 'https://www.powerball.com/',
        # Página dedicada del Double Play (más confiable que buscarlo en la portada)
        'double_play_url': 'https://www.powerball.com/double-play',
        'socrata_url': 'https://data.ny.gov/resource/d6yy-54nr.json',
        'results_file': 'resultados_actuales.json',
        'historic_file': 'historico_resultados.json',
        'dias_sorteo': [0, 2, 5],           # Lunes, Miércoles, Sábado
        'bola_especial': 'powerball',
        'multiplicador': 'powerplay',
        'clases_bola_especial': ['powerball'],
        # En data.ny.gov los 6 números vienen juntos: los 5 blancos + powerball
        'socrata_formato': {'bolas': 6, 'campo_especial': None, 'campo_multiplicador': 'multiplier'},
    },
    'megamillions': {
        'nombre': 'Mega Millions',
        'api_url': 'https://www.megamillions.com/cmspages/utilservice.asmx/GetLatestDrawData',
        'socrata_url': 'https://data.ny.gov/resource/5xaw-6ayf.json',
        'results_file': 'resultados_megamillions.json',
        'historic_file': 'historico_megamillions.json',
        'dias_sorteo': [1, 4],              # Martes, Viernes
        'bola_especial': 'megaball',
        'multiplicador': 'megaplier',
        'socrata_formato': {'bolas': 5, 'campo_especial': 'mega_ball', 'campo_multiplicador': 'multiplier'},
    },
    'lottoamerica': {
        'nombre': 'Lotto America',
        # La página hermana en powerball.com comparte la estructura HTML
        # estándar de MUSL; lottoamerica.com usa un HTML distinto que el
        # parser no entiende (verificado con probe_juegos.py).
        'url': 'https://www.powerball.com/lotto-america',
        'results_file': 'resultados_lottoamerica.json',
        'historic_file': 'historico_lottoamerica.json',
        'dias_sorteo': [0, 2, 5],           # Lunes, Miércoles, Sábado
        'bola_especial': 'star_ball',
        'multiplicador': 'all_star_bonus',
        'clases_bola_especial': ['star', 'bonus'],
    },
    '2by2': {
        'nombre': '2by2',
        'url': 'https://www.powerball.com/2by2',
        'results_file': 'resultados_2by2.json',
        'historic_file': 'historico_2by2.json',
        'dias_sorteo': [0, 1, 2, 3, 4, 5, 6],  # Diario
        # Formato distinto: 2 bolas rojas + 2 blancas, sin bola especial
        'num_blancos': 2,
        'num_rojas': 2,
        'bola_especial': None,
        'multiplicador': None,
        'premio_descripcion': 'Premio mayor: $22,000',
    },
    'cash4life': {
        'nombre': 'Cash4Life',
        'socrata_url': 'https://data.ny.gov/resource/kwxv-fwze.json',
        'results_file': 'resultados_cash4life.json',
        'historic_file': 'historico_cash4life.json',
        'dias_sorteo': [0, 1, 2, 3, 4, 5, 6],  # Diario
        'bola_especial': 'cash_ball',
        'multiplicador': None,
        'premio_descripcion': '$1,000 al día de por vida',
        'socrata_formato': {'bolas': 5, 'campo_especial': 'cash_ball', 'campo_multiplicador': None},
    },
}

# --- Compatibilidad con la versión anterior (solo Powerball) ---
POWERBALL_URL = GAMES['powerball']['url']
RESULTS_FILE = GAMES['powerball']['results_file']
HISTORIC_FILE = GAMES['powerball']['historic_file']
