"""Sondeo de cobertura de juegos (diagnóstico, no scrapea resultados).

Recorre powerball.com y los sitios/páginas candidatas de cada juego del menú
"Juegos" (Powerball, Lotto America, 2by2, Double Play, Jackpot USA,
Millionaire For Life) e imprime la estructura relevante de cada página:
enlaces del menú, secciones de resultados y clases de las bolas. Sirve para
decidir cómo extender el scraper. Se ejecuta desde GitHub Actions
(workflow probe.yml) porque el entorno local no tiene salida a internet.
"""

import re
import requests
from bs4 import BeautifulSoup

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}
TIMEOUT = 20

URLS = [
    'https://www.powerball.com/',
    'https://www.lottoamerica.com/',
    # Candidatas para los juegos del menú de powerball.com
    'https://www.powerball.com/2by2',
    'https://www.powerball.com/jackpot-usa',
    'https://www.powerball.com/millionaire-for-life',
    'https://www.powerball.com/double-play',
]

KEYWORDS = re.compile(r'(2by2|2-by-2|jackpot[\s-]*usa|millionaire|double[\s-]*play|lotto[\s-]*america)', re.I)


def resumen(url):
    print('\n' + '=' * 70)
    print(f'URL: {url}')
    print('=' * 70)
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
    except Exception as e:
        print(f'  ERROR de red: {e}')
        return

    print(f'  HTTP {r.status_code} | URL final: {r.url} | {len(r.content)} bytes')
    if r.status_code != 200:
        return

    soup = BeautifulSoup(r.content, 'html.parser')
    title = soup.find('title')
    print(f'  <title>: {title.get_text(strip=True) if title else "(sin título)"}')

    # Enlaces internos que suenan a juegos (para descubrir las URLs reales del menú)
    vistos = set()
    for a in soup.find_all('a', href=True):
        href = a['href']
        texto = a.get_text(strip=True)[:40]
        if KEYWORDS.search(href) or KEYWORDS.search(texto or ''):
            clave = (href, texto)
            if clave not in vistos:
                vistos.add(clave)
                print(f'  LINK juego: {href!r}  texto={texto!r}')

    # Secciones típicas de resultados en sitios MUSL
    for sec_id in ['numbers', 'next-drawing', 'winners']:
        el = soup.find(id=sec_id)
        print(f'  id="{sec_id}": {"SÍ" if el else "no"}')

    # Clases que contengan "ball" y elementos form-control (estructura de bolas)
    clases_ball = {}
    for el in soup.find_all(class_=re.compile(r'ball', re.I)):
        for c in el.get('class', []):
            if 'ball' in c.lower():
                clases_ball[c] = clases_ball.get(c, 0) + 1
    print(f'  clases con "ball": {clases_ball or "ninguna"}')

    fc = soup.find_all('div', class_='form-control')
    print(f'  div.form-control: {len(fc)}')
    for el in fc[:12]:
        print(f'    - clases={el.get("class")} texto={el.get_text(strip=True)[:15]!r}')

    # Fechas de tarjetas (card-title) y encabezados de secciones de juego
    for h5 in soup.find_all('h5', class_='card-title')[:6]:
        print(f'  h5.card-title: {h5.get_text(strip=True)[:60]!r}')
    for h2 in soup.find_all(['h1', 'h2'])[:8]:
        t = h2.get_text(strip=True)[:60]
        if t:
            print(f'  {h2.name}: {t!r}')


def main():
    for url in URLS:
        resumen(url)
    print('\nSondeo terminado.')


if __name__ == '__main__':
    main()
