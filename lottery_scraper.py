"""Scraper multi-juego de loterías de EE.UU.

Extrae los resultados de Powerball (incluyendo Double Play), Mega Millions,
Lotto America y Cash4Life. Cada juego se extrae de forma independiente:
si uno falla, los demás se guardan igual.

Fuentes:
  - Powerball / Lotto America: sitio oficial (powerball.com / lottoamerica.com,
    comparten la misma estructura HTML) con respaldo en data.ny.gov.
  - Mega Millions: API oficial del sitio con respaldo en data.ny.gov.
  - Cash4Life: datos abiertos de data.ny.gov.
"""

import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import json
import sys
import time
import logging
import re
from config import *

try:
    from zoneinfo import ZoneInfo
    TZ_ET = ZoneInfo('America/New_York')
except Exception:
    TZ_ET = None

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)

MESES = {
    'January': 'Enero', 'February': 'Febrero', 'March': 'Marzo',
    'April': 'Abril', 'May': 'Mayo', 'June': 'Junio',
    'July': 'Julio', 'August': 'Agosto', 'September': 'Septiembre',
    'October': 'Octubre', 'November': 'Noviembre', 'December': 'Diciembre'
}

DIAS = {
    'Monday': 'Lunes', 'Tuesday': 'Martes', 'Wednesday': 'Miércoles',
    'Thursday': 'Jueves', 'Friday': 'Viernes', 'Saturday': 'Sábado',
    'Sunday': 'Domingo'
}


def ahora_et():
    """Hora actual en la zona horaria del Este de EE.UU. (donde se sortea)."""
    return datetime.now(TZ_ET) if TZ_ET else datetime.now()


class BaseScraper:
    """Lógica común a todos los juegos: fechas, montos, guardado e histórico."""

    def __init__(self, game_key, cfg):
        self.game_key = game_key
        self.cfg = cfg
        self.nombre = cfg['nombre']
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

    # ──────────────────────────────────────────────
    # Utilidades de fechas y montos
    # ──────────────────────────────────────────────
    def calcular_fecha_ultimo_sorteo(self):
        """Fecha esperada del último sorteo según los días de sorteo del juego."""
        hoy = ahora_et()
        dias_sorteo = self.cfg['dias_sorteo']

        if hoy.weekday() in dias_sorteo and hoy.hour >= 23:
            return hoy.strftime('%Y-%m-%d')

        for i in range(1, 8):
            fecha = hoy - timedelta(days=i)
            if fecha.weekday() in dias_sorteo:
                return fecha.strftime('%Y-%m-%d')

        return hoy.strftime('%Y-%m-%d')

    def calcular_proximo_sorteo(self, fecha_iso):
        """Próximo día de sorteo posterior a la fecha dada (YYYY-MM-DD)."""
        try:
            fecha = datetime.strptime(fecha_iso, '%Y-%m-%d')
            for i in range(1, 8):
                siguiente = fecha + timedelta(days=i)
                if siguiente.weekday() in self.cfg['dias_sorteo']:
                    return siguiente.strftime('%Y-%m-%d')
        except Exception as e:
            logging.warning(f"[{self.nombre}] No se pudo calcular próximo sorteo: {e}")
        return None

    def format_date_iso(self, date_str):
        """Convierte una fecha en texto a formato ISO (YYYY-MM-DD)."""
        try:
            if not date_str:
                return None
            date_str = str(date_str).strip()

            # Ya viene en ISO ("2026-07-15" o "2026-07-15T00:00:00.000")
            m = re.match(r'^(\d{4}-\d{2}-\d{2})', date_str)
            if m:
                return m.group(1)

            # Epoch de .NET: "/Date(1710475200000)/"
            m = re.search(r'/Date\((\d+)\)/', date_str)
            if m:
                return datetime.utcfromtimestamp(int(m.group(1)) / 1000).strftime('%Y-%m-%d')

            # Quitar día de la semana inicial ("Wed, ...")
            date_str_clean = re.sub(r'^[A-Za-z]+,\s*', '', date_str)

            month_abbr = {
                'Jan': 'January', 'Feb': 'February', 'Mar': 'March', 'Apr': 'April',
                'May': 'May', 'Jun': 'June', 'Jul': 'July', 'Aug': 'August',
                'Sep': 'September', 'Oct': 'October', 'Nov': 'November', 'Dec': 'December'
            }

            first_word = date_str_clean.split()[0] if date_str_clean else ''
            for abbr, full in month_abbr.items():
                if first_word.lower() == abbr.lower():
                    date_str_clean = full + date_str_clean[len(first_word):]
                    break

            for fmt in ['%B %d, %Y', '%m/%d/%Y', '%d-%m-%Y']:
                try:
                    return datetime.strptime(date_str_clean, fmt).strftime('%Y-%m-%d')
                except ValueError:
                    continue

            match = re.search(r'(\w+)\s+(\d+),\s+(\d{4})', date_str_clean)
            if match:
                month_str, day, year = match.groups()
                date_obj = datetime.strptime(f"{month_str} {day}, {year}", '%B %d, %Y')
                return date_obj.strftime('%Y-%m-%d')

            logging.warning(f"[{self.nombre}] No se pudo parsear la fecha: {date_str}")
            return None
        except Exception as e:
            logging.error(f"[{self.nombre}] Error al formatear fecha '{date_str}': {e}")
            return None

    def format_update_date(self):
        """Fecha de actualización en español (hora del Este)."""
        now = ahora_et()
        day_name = DIAS.get(now.strftime('%A'), now.strftime('%A'))
        month_name = MESES.get(now.strftime('%B'), now.strftime('%B'))
        return f"{day_name}, {now.day} de {month_name} de {now.year} - {now.strftime('%I:%M %p')} ET"

    def extract_prize_amount(self, text):
        """Extrae el monto del premio (maneja millones con decimales)."""
        try:
            if text is None:
                return None
            if isinstance(text, (int, float)):
                return int(text)
            text = str(text).strip()
            if not text:
                return None

            # "$218 Millones" / "$101.6 Millones" / "$218 Million"
            match_million = re.search(r'\$?\s*(\d+\.?\d*)\s*[Mm]ill(?:ones?|ion)', text, re.IGNORECASE)
            if match_million:
                return int(float(match_million.group(1)) * 1_000_000)

            # "$1.2 Billion" (mil millones en EE.UU.)
            match_billion = re.search(r'\$?\s*(\d+\.?\d*)\s*[Bb]ill(?:ones?|ion)', text, re.IGNORECASE)
            if match_billion:
                return int(float(match_billion.group(1)) * 1_000_000_000)

            # "$285,000,000"
            text_clean = text.replace('$', '').replace(',', '').strip()
            match_number = re.search(r'(\d+\.?\d*)', text_clean)
            if match_number:
                return int(float(match_number.group(1)))

            return None
        except Exception as e:
            logging.error(f"[{self.nombre}] Error extrayendo monto de '{text}': {e}")
            return None

    # ──────────────────────────────────────────────
    # Construcción del resultado
    # ──────────────────────────────────────────────
    def build_results(self, fecha, blancas, especial, multiplicador=None,
                      extra_sorteo=None, proximo=None):
        """Arma el diccionario de resultados con la estructura estándar."""
        blancas = blancas or []
        exito = len(blancas) == 5 and especial is not None and fecha is not None

        sorteo = {
            'fecha': fecha,
            'blancos': sorted(blancas),
            self.cfg['bola_especial']: especial,
        }
        if self.cfg.get('multiplicador'):
            sorteo[self.cfg['multiplicador']] = multiplicador
        if extra_sorteo:
            sorteo.update(extra_sorteo)

        proximo_sorteo = {'fecha': None, 'premio_estimado': None, 'premio_efectivo': None}
        if self.cfg.get('premio_descripcion'):
            proximo_sorteo['premio_descripcion'] = self.cfg['premio_descripcion']
        if proximo:
            proximo_sorteo.update({k: v for k, v in proximo.items() if v is not None})
        if not proximo_sorteo['fecha'] and fecha:
            proximo_sorteo['fecha'] = self.calcular_proximo_sorteo(fecha)

        return {
            'juego': self.game_key,
            'nombre': self.nombre,
            'sorteo': sorteo,
            'proximo_sorteo': proximo_sorteo,
            'fecha_actualizacion': self.format_update_date(),
            '_success': exito,
        }

    def build_error(self, error):
        return {
            'juego': self.game_key,
            'nombre': self.nombre,
            '_success': False,
            'error': str(error),
            'fecha_actualizacion': self.format_update_date(),
        }

    # ──────────────────────────────────────────────
    # Respaldo: datos abiertos de data.ny.gov (Socrata)
    # ──────────────────────────────────────────────
    def scrape_socrata(self):
        """Obtiene el último sorteo desde data.ny.gov."""
        url = self.cfg.get('socrata_url')
        if not url:
            raise RuntimeError('Este juego no tiene fuente Socrata configurada')

        logging.info(f"[{self.nombre}] Consultando respaldo data.ny.gov")
        response = requests.get(
            url,
            params={'$order': 'draw_date DESC', '$limit': 1},
            headers=self.headers,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        rows = response.json()
        if not rows:
            raise RuntimeError('data.ny.gov no devolvió filas')
        return self.parse_socrata_row(rows[0])

    def parse_socrata_row(self, row):
        """Convierte una fila de data.ny.gov al formato estándar."""
        formato = self.cfg['socrata_formato']
        fecha = self.format_date_iso(row.get('draw_date'))

        numeros = [int(n) for n in re.findall(r'\d+', row.get('winning_numbers', ''))]
        if formato['campo_especial']:
            blancas = numeros[:formato['bolas']]
            especial = row.get(formato['campo_especial'])
            especial = int(especial) if especial is not None else None
        else:
            # Los números incluyen la bola especial al final
            blancas = numeros[:formato['bolas'] - 1]
            especial = numeros[formato['bolas'] - 1] if len(numeros) >= formato['bolas'] else None

        multiplicador = None
        if formato.get('campo_multiplicador'):
            valor = row.get(formato['campo_multiplicador'])
            if valor is not None:
                try:
                    multiplicador = int(float(valor))
                except (TypeError, ValueError):
                    multiplicador = None

        return self.build_results(fecha, blancas, especial, multiplicador)

    # ──────────────────────────────────────────────
    # Ciclo de scraping
    # ──────────────────────────────────────────────
    def scrape(self):
        raise NotImplementedError

    def scrape_with_retry(self, max_attempts=MAX_RETRY_ATTEMPTS, delay=RETRY_DELAY_SECONDS):
        results = self.build_error('sin intentos')
        for attempt in range(1, max_attempts + 1):
            logging.info(f"[{self.nombre}] Intento {attempt} de {max_attempts}")
            try:
                results = self.scrape()
            except Exception as e:
                logging.error(f"[{self.nombre}] Scraping falló: {e}")
                results = self.build_error(e)
            if results.get('_success'):
                return results
            if attempt < max_attempts:
                logging.info(f"[{self.nombre}] Esperando {delay}s...")
                time.sleep(delay)
        logging.error(f"[{self.nombre}] Todos los intentos fallaron")
        return results

    # ──────────────────────────────────────────────
    # Guardado
    # ──────────────────────────────────────────────
    def save_results(self, results):
        """Guarda el resultado actual y lo agrega al histórico del juego."""
        try:
            results_to_save = {
                'juego': results['juego'],
                'nombre': results['nombre'],
                'sorteo': results['sorteo'],
                'proximo_sorteo': results['proximo_sorteo'],
                'fecha_actualizacion': results['fecha_actualizacion'],
            }

            with open(self.cfg['results_file'], 'w', encoding='utf-8') as f:
                json.dump(results_to_save, f, indent=2, ensure_ascii=False)
            logging.info(f"[{self.nombre}] Guardado en {self.cfg['results_file']}")

            try:
                with open(self.cfg['historic_file'], 'r', encoding='utf-8') as f:
                    historico = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                historico = []

            fecha_sorteo = results['sorteo']['fecha']
            ya_existe = any(r.get('sorteo', {}).get('fecha') == fecha_sorteo for r in historico)

            if not ya_existe:
                historico.insert(0, {
                    'sorteo': results['sorteo'],
                    'fecha_actualizacion': results['fecha_actualizacion'],
                })
                with open(self.cfg['historic_file'], 'w', encoding='utf-8') as f:
                    json.dump(historico, f, indent=2, ensure_ascii=False)
                logging.info(f"[{self.nombre}] Histórico: {len(historico)} sorteos")
            else:
                logging.info(f"[{self.nombre}] Sorteo {fecha_sorteo} ya existe en histórico")

            return True
        except Exception as e:
            logging.error(f"[{self.nombre}] Error al guardar: {e}")
            return False


class MuslSiteScraper(BaseScraper):
    """Scraper para los sitios de MUSL (powerball.com y lottoamerica.com),
    que comparten la misma estructura HTML."""

    def scrape(self):
        logging.info(f"[{self.nombre}] Iniciando scraping de {self.cfg['url']}")
        try:
            response = requests.get(self.cfg['url'], headers=self.headers, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            results = self.parse_html(response.content)
            if not results.get('_success') and self.cfg.get('socrata_url'):
                logging.warning(f"[{self.nombre}] Extracción incompleta del sitio, usando respaldo")
                return self.scrape_socrata()
            return results
        except Exception as e:
            if self.cfg.get('socrata_url'):
                logging.warning(f"[{self.nombre}] Sitio oficial falló ({e}), usando respaldo")
                return self.scrape_socrata()
            raise

    def _extraer_bolas(self, contenedor):
        """Devuelve (blancas, especial) dentro de un contenedor HTML.

        Las bolas blancas llevan la clase 'white-balls'. La bola especial es el
        primer elemento 'form-control' con solo dígitos que no sea blanca,
        priorizando las clases configuradas (evita confundirla con el
        multiplicador, cuyo texto es tipo '2X')."""
        blancas = []
        candidatos = []
        for c in contenedor.find_all('div', class_='form-control'):
            clases = c.get('class', [])
            texto = c.get_text(strip=True)
            if 'white-balls' in clases:
                num = re.sub(r'[^\d]', '', texto)
                if num.isdigit():
                    blancas.append(int(num))
            elif re.fullmatch(r'\d{1,3}', texto):
                candidatos.append((clases, int(texto)))

        especial = None
        hints = self.cfg.get('clases_bola_especial', [])
        for clases, num in candidatos:
            if any(hint in clase for hint in hints for clase in clases):
                especial = num
                break
        if especial is None and candidatos:
            especial = candidatos[0][1]
        return blancas, especial

    def parse_html(self, html):
        soup = BeautifulSoup(html, 'html.parser')

        # ── Sorteo actual (id="numbers") ──
        numbers_section = soup.find('div', class_='col', id='numbers')

        draw_date = None
        if numbers_section:
            date_el = numbers_section.find('h5', class_='card-title')
            if date_el:
                draw_date = self.format_date_iso(date_el.text.strip())
        if not draw_date:
            date_el = soup.find('h5', class_='card-title')
            if date_el:
                draw_date = self.format_date_iso(date_el.text.strip())
                logging.info(f"[{self.nombre}] Fecha (fallback): {draw_date}")

        # Bolas: primero dentro de la sección del sorteo; si no cuadra,
        # búsqueda en toda la página (comportamiento original)
        blancas, especial = [], None
        if numbers_section:
            blancas, especial = self._extraer_bolas(numbers_section)
        if len(blancas) != 5 or especial is None:
            blancas_pg, especial_pg = self._extraer_bolas(soup)
            if len(blancas_pg) == 5:
                blancas = blancas_pg
                especial = especial if especial is not None else especial_pg
        logging.info(f"[{self.nombre}] Blancas: {blancas} | Especial: {especial}")

        # Multiplicador (Power Play / All Star Bonus)
        multiplicador = None
        try:
            for pp in soup.find_all(string=re.compile(r'(Power\s*Play|All\s*Star\s*Bonus)', re.IGNORECASE)):
                src = pp if isinstance(pp, str) else pp.text
                m = re.search(r'(\d+)\s*x', src, re.IGNORECASE)
                if not m and getattr(pp, 'parent', None) is not None:
                    m = re.search(r'(\d+)\s*x', pp.parent.text, re.IGNORECASE)
                if m:
                    multiplicador = int(m.group(1))
                    break
        except Exception as e:
            logging.warning(f"[{self.nombre}] Error multiplicador: {e}")

        # ¿Ganó alguien el jackpot? (id="winners")
        jackpot_ganado = False
        ganador_estado = None
        try:
            winners_section = soup.find('div', class_='col', id='winners')
            if winners_section:
                texto = winners_section.get_text()
                if re.search(r'nadie|none|no\s+winner', texto, re.IGNORECASE):
                    jackpot_ganado = False
                else:
                    m = re.search(r'\b([A-Z]{2})\b', texto)
                    if m:
                        jackpot_ganado = True
                        ganador_estado = m.group(1)
                        logging.info(f"[{self.nombre}] Jackpot GANADO en: {ganador_estado}")
        except Exception as e:
            logging.warning(f"[{self.nombre}] Error al leer ganadores: {e}")

        # ── Próximo sorteo (id="next-drawing") ──
        proximo = {'fecha': None, 'premio_estimado': None, 'premio_efectivo': None}
        try:
            next_section = soup.find('div', class_='col', id='next-drawing')
            if next_section:
                next_date_el = next_section.find('h5', class_='card-title')
                if next_date_el:
                    proximo['fecha'] = self.format_date_iso(next_date_el.text.strip())

                jackpot_span = next_section.find('span', class_='game-jackpot-number')
                if jackpot_span:
                    proximo['premio_estimado'] = self.extract_prize_amount(jackpot_span.text.strip())

                cash_div = next_section.find('div', class_='cash-value')
                if cash_div:
                    for span in cash_div.find_all('span'):
                        t = span.text.strip()
                        if ('$' in t or re.search(r'\d', t)) and ':' not in t:
                            monto = self.extract_prize_amount(t)
                            if monto:
                                proximo['premio_efectivo'] = monto
                                break

                # Fallback: el cash value siempre es menor que el jackpot estimado
                if not proximo['premio_efectivo']:
                    todos = re.findall(r'\$?\s*(\d+\.?\d*)\s*[Mm]ill', next_section.get_text())
                    montos = [int(float(x) * 1_000_000) for x in todos]
                    if len(montos) >= 2:
                        proximo['premio_efectivo'] = min(montos)

                if (proximo['premio_efectivo'] and proximo['premio_estimado']
                        and proximo['premio_efectivo'] >= proximo['premio_estimado']):
                    logging.warning(f"[{self.nombre}] Cash value >= jackpot, descartando cash value")
                    proximo['premio_efectivo'] = None
        except Exception as e:
            logging.warning(f"[{self.nombre}] Error próximo sorteo: {e}")

        extra = self.extra_sorteo(soup, jackpot_ganado, ganador_estado)
        results = self.build_results(draw_date, blancas, especial, multiplicador,
                                     extra_sorteo=extra, proximo=proximo)

        if results['_success']:
            logging.info(f"[{self.nombre}] [OK] {sorted(blancas)} + {especial} | Próximo: {proximo['fecha']}")
        else:
            logging.warning(
                f"[{self.nombre}] [ADVERTENCIA] Incompleto — blancas:{len(blancas)}/5, "
                f"especial:{especial}, fecha:{draw_date}"
            )
        return results

    def extra_sorteo(self, soup, jackpot_ganado, ganador_estado):
        """Campos adicionales del sorteo; las subclases pueden ampliarlo."""
        return {'jackpot_ganado': jackpot_ganado, 'ganador_estado': ganador_estado}


class PowerballScraper(MuslSiteScraper):
    """Powerball: sitio oficial + extracción de Double Play."""

    def extra_sorteo(self, soup, jackpot_ganado, ganador_estado):
        extra = super().extra_sorteo(soup, jackpot_ganado, ganador_estado)
        extra['doble_jugada'] = self._extraer_doble_jugada(soup)
        return extra

    def _extraer_doble_jugada(self, soup):
        """Extrae los números del sorteo Double Play si aparecen en la página."""
        try:
            seccion = None
            for candidata in soup.find_all(id=re.compile(r'(double|dbl)', re.IGNORECASE)):
                if re.search(r'double\s*play', candidata.get_text(), re.IGNORECASE):
                    seccion = candidata
                    break
            if not seccion:
                marcador = soup.find(string=re.compile(r'Double\s*Play', re.IGNORECASE))
                if marcador and getattr(marcador, 'parent', None) is not None:
                    seccion = (marcador.find_parent('div', class_='card')
                               or marcador.find_parent('div', class_='col'))
            if not seccion:
                return None

            blancas, especial = self._extraer_bolas(seccion)
            if len(blancas) == 5 and especial is not None:
                logging.info(f"[{self.nombre}] Double Play: {sorted(blancas)} + {especial}")
                return {'blancos': sorted(blancas), 'powerball': especial}
        except Exception as e:
            logging.warning(f"[{self.nombre}] Error Double Play: {e}")
        return None


class MegaMillionsScraper(BaseScraper):
    """Mega Millions: API oficial del sitio, con respaldo en data.ny.gov."""

    def scrape(self):
        try:
            payload = self._fetch_api()
            results = self.parse_api(payload)
            if results.get('_success'):
                return results
            logging.warning(f"[{self.nombre}] Respuesta de API incompleta, usando respaldo")
        except Exception as e:
            logging.warning(f"[{self.nombre}] API oficial falló ({e}), usando respaldo")
        return self.scrape_socrata()

    def _fetch_api(self):
        url = self.cfg['api_url']
        logging.info(f"[{self.nombre}] Consultando API {url}")
        headers = {**self.headers, 'Content-Type': 'application/json'}
        try:
            response = requests.post(url, json={}, headers=headers, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
        except Exception:
            response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
        return response.json()

    def parse_api(self, payload):
        data = payload
        if isinstance(payload, dict) and 'd' in payload:
            data = payload['d']
            if isinstance(data, str):
                data = json.loads(data)

        drawing = data.get('Drawing') or data.get('CurrentDrawing') or data.get('DrawingData') or {}
        jackpot = data.get('Jackpot') or {}

        blancas = []
        for i in range(1, 6):
            valor = drawing.get(f'N{i}')
            try:
                blancas.append(int(valor))
            except (TypeError, ValueError):
                pass

        especial = drawing.get('MBall', drawing.get('MegaBall'))
        try:
            especial = int(especial)
        except (TypeError, ValueError):
            especial = None

        multiplicador = drawing.get('Megaplier')
        try:
            multiplicador = int(multiplicador)
        except (TypeError, ValueError):
            multiplicador = None

        fecha = self.format_date_iso(drawing.get('PlayDate') or drawing.get('DrawDate'))

        proximo = {
            'fecha': self.format_date_iso(
                data.get('NextDrawingDate') or jackpot.get('NextDrawingDate')
            ),
            'premio_estimado': self.extract_prize_amount(
                jackpot.get('NextPrizePool', jackpot.get('CurrentPrizePool'))
            ),
            'premio_efectivo': self.extract_prize_amount(
                jackpot.get('NextCashValue', jackpot.get('CurrentCashValue'))
            ),
        }

        return self.build_results(fecha, blancas, especial, multiplicador, proximo=proximo)


class SocrataScraper(BaseScraper):
    """Juegos que se obtienen directamente de data.ny.gov (ej. Cash4Life)."""

    def scrape(self):
        return self.scrape_socrata()


def crear_scraper(game_key, cfg):
    if game_key == 'powerball':
        return PowerballScraper(game_key, cfg)
    if game_key == 'megamillions':
        return MegaMillionsScraper(game_key, cfg)
    if cfg.get('url'):
        return MuslSiteScraper(game_key, cfg)
    return SocrataScraper(game_key, cfg)


def guardar_combinado(games):
    """Escribe un único JSON con el último resultado de todos los juegos."""
    combinado = {'juegos': {}, 'fecha_actualizacion': None}
    for game_key, cfg in games.items():
        try:
            with open(cfg['results_file'], 'r', encoding='utf-8') as f:
                combinado['juegos'][game_key] = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            continue
    if not combinado['juegos']:
        return
    fechas = [g.get('fecha_actualizacion') for g in combinado['juegos'].values()]
    combinado['fecha_actualizacion'] = next((f for f in fechas if f), None)
    with open(COMBINED_FILE, 'w', encoding='utf-8') as f:
        json.dump(combinado, f, indent=2, ensure_ascii=False)
    logging.info(f"Archivo combinado guardado en {COMBINED_FILE}")


def imprimir_resumen(resumen):
    for game_key, results in resumen.items():
        nombre = results.get('nombre', game_key)
        print("\n" + "=" * 60)
        print(f"  {nombre.upper()}")
        print("=" * 60)
        if not results.get('_success'):
            print("  ❌ No se pudieron obtener los resultados")
            if results.get('error'):
                print(f"  Detalle: {results['error']}")
            continue

        sorteo = results['sorteo']
        proximo = results['proximo_sorteo']
        cfg = GAMES[game_key]

        print(f"  Fecha       : {sorteo['fecha']}")
        print(f"  Blancos     : {' - '.join(map(str, sorteo['blancos']))}")
        print(f"  {cfg['bola_especial'].replace('_', ' ').title():<12}: {sorteo[cfg['bola_especial']]}")
        if cfg.get('multiplicador') and sorteo.get(cfg['multiplicador']):
            print(f"  Multiplicad.: {sorteo[cfg['multiplicador']]}x")
        if sorteo.get('doble_jugada'):
            dp = sorteo['doble_jugada']
            print(f"  Double Play : {' - '.join(map(str, dp['blancos']))} + {dp['powerball']}")
        if sorteo.get('jackpot_ganado'):
            print(f"  Jackpot     : ✅ GANADO en {sorteo.get('ganador_estado')}")

        print(f"  Próximo     : {proximo.get('fecha') or 'N/A'}")
        if proximo.get('premio_estimado'):
            print(f"  Est. Jackpot: ${proximo['premio_estimado']:,}")
        if proximo.get('premio_efectivo'):
            print(f"  Cash Value  : ${proximo['premio_efectivo']:,}")
        if proximo.get('premio_descripcion'):
            print(f"  Premio      : {proximo['premio_descripcion']}")


def main():
    logging.info("=" * 60)
    logging.info("LOTTERY SCRAPER MULTI-JUEGO - INICIANDO")
    logging.info("=" * 60)

    resumen = {}
    for game_key, cfg in GAMES.items():
        scraper = crear_scraper(game_key, cfg)
        results = scraper.scrape_with_retry()

        if results.get('_success'):
            # La fecha scrapeada es la fuente de verdad; solo se avisa si
            # parece atrasada respecto al calendario de sorteos.
            fecha_calculada = scraper.calcular_fecha_ultimo_sorteo()
            fecha_scrapeada = results['sorteo']['fecha']
            if fecha_scrapeada < fecha_calculada:
                logging.warning(
                    f"[{cfg['nombre']}] Posible desfase: scrapeada {fecha_scrapeada} "
                    f"vs esperada {fecha_calculada} (se conserva la scrapeada)"
                )
            scraper.save_results(results)
        resumen[game_key] = results

    guardar_combinado(GAMES)
    imprimir_resumen(resumen)

    exitosos = [k for k, r in resumen.items() if r.get('_success')]
    fallidos = [k for k, r in resumen.items() if not r.get('_success')]
    print("\n" + "=" * 60)
    print(f"  Juegos OK   : {', '.join(exitosos) or 'ninguno'}")
    if fallidos:
        print(f"  Fallidos    : {', '.join(fallidos)}")
    print("=" * 60)

    if not exitosos:
        logging.error("Ningún juego pudo extraerse")
        sys.exit(1)


if __name__ == '__main__':
    main()
