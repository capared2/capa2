"""Compatibilidad: el scraper ahora es multi-juego y vive en lottery_scraper.py.

Este archivo se mantiene para no romper crons o scripts que ejecutaban
`python powerball_scraper.py`. Ejecuta todos los juegos configurados.
"""

from lottery_scraper import main

if __name__ == '__main__':
    main()
