import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import json
import time
import logging
import re
from config import *

# Configurar logging para Windows
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)

class PowerballScraper:
    def __init__(self):
        self.url = POWERBALL_URL
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        self.meses = {
            'January': 'Enero', 'February': 'Febrero', 'March': 'Marzo',
            'April': 'Abril', 'May': 'Mayo', 'June': 'Junio',
            'July': 'Julio', 'August': 'Agosto', 'September': 'Septiembre',
            'October': 'Octubre', 'November': 'Noviembre', 'December': 'Diciembre'
        }
        
        self.dias = {
            'Monday': 'Lunes', 'Tuesday': 'Martes', 'Wednesday': 'Miércoles',
            'Thursday': 'Jueves', 'Friday': 'Viernes', 'Saturday': 'Sábado',
            'Sunday': 'Domingo'
        }
    
    def calcular_fecha_ultimo_sorteo(self):
        """Calcula la fecha del último sorteo según el día actual"""
        hoy = datetime.now()
        dia_semana = hoy.weekday()  # 0=Lunes, 2=Miércoles, 5=Sábado
        hora = hoy.hour
        dias_sorteo = [0, 2, 5]
        
        if dia_semana in dias_sorteo and hora >= 23:
            return hoy.strftime('%Y-%m-%d')
        
        for i in range(1, 8):
            fecha = hoy - timedelta(days=i)
            if fecha.weekday() in dias_sorteo:
                return fecha.strftime('%Y-%m-%d')
        
        return hoy.strftime('%Y-%m-%d')
    
    def leer_json_actual(self):
        """Lee el JSON actual si existe"""
        try:
            with open(RESULTS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            logging.info("No existe JSON anterior")
            return None
        except Exception as e:
            logging.error(f"Error leyendo JSON actual: {e}")
            return None
    
    def format_date_iso(self, date_str):
        """Convierte la fecha a formato ISO (YYYY-MM-DD)"""
        try:
            date_str_clean = re.sub(r'^[A-Za-z]+,\s*', '', date_str.strip())
            
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
                    date_obj = datetime.strptime(date_str_clean, fmt)
                    return date_obj.strftime('%Y-%m-%d')
                except ValueError:
                    continue
            
            match = re.search(r'(\w+)\s+(\d+),\s+(\d{4})', date_str_clean)
            if match:
                month_str, day, year = match.groups()
                date_obj = datetime.strptime(f"{month_str} {day}, {year}", '%B %d, %Y')
                return date_obj.strftime('%Y-%m-%d')
            
            logging.warning(f"No se pudo parsear la fecha: {date_str}")
            return None
        except Exception as e:
            logging.error(f"Error al formatear fecha '{date_str}': {e}")
            return None
    
    def format_update_date(self):
        """Genera la fecha de actualización en español"""
        now = datetime.now()
        day_name = self.dias.get(now.strftime('%A'), now.strftime('%A'))
        month_name = self.meses.get(now.strftime('%B'), now.strftime('%B'))
        return f"{day_name}, {now.day} de {month_name} de {now.year} - {now.strftime('%I:%M %p')} ET"
    
    def extract_prize_amount(self, text):
        """Extrae el monto del premio (maneja millones con decimales)"""
        try:
            if not text:
                return None
            text = text.strip()
            
            # "$218 Millones" / "$101.6 Millones" / "$218 Million"
            match_million = re.search(r'\$?\s*(\d+\.?\d*)\s*[Mm]ill(?:ones?|ion)', text, re.IGNORECASE)
            if match_million:
                return int(float(match_million.group(1)) * 1_000_000)
            
            # "$285,000,000"
            text_clean = text.replace('$', '').replace(',', '').strip()
            match_number = re.search(r'(\d+)', text_clean)
            if match_number:
                return int(match_number.group(1))
            
            return None
        except Exception as e:
            logging.error(f"Error extrayendo monto de '{text}': {e}")
            return None
    
    def scrape_results(self):
        """Extrae los resultados del Powerball con estructura separada sorteo/próximo"""
        try:
            logging.info(f"Iniciando scraping de {self.url}")
            response = requests.get(self.url, headers=self.headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # ══════════════════════════════════════════════
            # BLOQUE 1 — SORTEO ACTUAL  (id="numbers")
            # ══════════════════════════════════════════════
            numbers_section = soup.find('div', class_='col', id='numbers')
            
            # Fecha
            draw_date = None
            if numbers_section:
                date_el = numbers_section.find('h5', class_='card-title')
                if date_el:
                    draw_date = self.format_date_iso(date_el.text.strip())
                    logging.info(f"Fecha sorteo actual: {date_el.text.strip()} → {draw_date}")
            
            if not draw_date:
                date_el = soup.find('h5', class_='card-title')
                if date_el:
                    draw_date = self.format_date_iso(date_el.text.strip())
                    logging.info(f"Fecha (fallback): {draw_date}")
            
            # Números blancos
            white_balls = []
            ball_containers = soup.find_all('div', class_='form-control')
            for c in ball_containers:
                if 'white-balls' in c.get('class', []):
                    num = re.sub(r'[^\d]', '', c.text.strip())
                    if num.isdigit():
                        white_balls.append(int(num))
            logging.info(f"Blancos: {white_balls}")
            
            # Powerball rojo
            powerball = None
            for c in ball_containers:
                cls = c.get('class', [])
                if 'powerball' in cls and 'white-balls' not in cls:
                    num = re.sub(r'[^\d]', '', c.text.strip())
                    if num.isdigit():
                        powerball = int(num)
                        logging.info(f"Powerball: {powerball}")
                        break
            
            # Power Play
            power_play = None
            try:
                for pp in soup.find_all(string=re.compile(r'Power\s*Play', re.IGNORECASE)):
                    src = pp if isinstance(pp, str) else pp.text
                    m = re.search(r'(\d+)\s*x', src, re.IGNORECASE)
                    if not m and hasattr(pp, 'parent') and pp.parent:
                        m = re.search(r'(\d+)\s*x', pp.parent.text, re.IGNORECASE)
                    if m:
                        power_play = int(m.group(1))
                        logging.info(f"Power Play: {power_play}x")
                        break
            except Exception as e:
                logging.warning(f"Error Power Play: {e}")
            
            # ¿Ganó alguien el jackpot?  (id="winners")
            jackpot_ganado = False
            ganador_estado = None
            try:
                winners_section = soup.find('div', class_='col', id='winners')
                if winners_section:
                    texto = winners_section.get_text()
                    if re.search(r'nadie|none|no\s+winner', texto, re.IGNORECASE):
                        jackpot_ganado = False
                        logging.info("Jackpot: Nadie ganó")
                    else:
                        # Buscar estado de 2 letras mayúsculas como ganador
                        m = re.search(r'\b([A-Z]{2})\b', texto)
                        if m:
                            jackpot_ganado = True
                            ganador_estado = m.group(1)
                            logging.info(f"Jackpot GANADO en: {ganador_estado}")
            except Exception as e:
                logging.warning(f"Error al leer ganadores: {e}")
            
            # ══════════════════════════════════════════════
            # BLOQUE 2 — PRÓXIMO SORTEO  (id="next-drawing")
            # ══════════════════════════════════════════════
            proximo_fecha = None
            proximo_estimado = None
            proximo_efectivo = None
            
            try:
                next_section = soup.find('div', class_='col', id='next-drawing')
                if next_section:
                    # Fecha próximo sorteo
                    next_date_el = next_section.find('h5', class_='card-title')
                    if next_date_el:
                        proximo_fecha = self.format_date_iso(next_date_el.text.strip())
                        logging.info(f"Próximo sorteo: {proximo_fecha}")
                    
                    # Premio estimado (jackpot acumulado)
                    jackpot_span = next_section.find('span', class_='game-jackpot-number')
                    if jackpot_span:
                        proximo_estimado = self.extract_prize_amount(jackpot_span.text.strip())
                        logging.info(f"Próximo estimado: ${proximo_estimado:,}" if proximo_estimado else "Próximo estimado: sin dato")
                    
                    # Valor en efectivo
                    cash_div = next_section.find('div', class_='cash-value')
                    if cash_div:
                        for span in cash_div.find_all('span'):
                            t = span.text.strip()
                            if ('$' in t or re.search(r'\d', t)) and ':' not in t:
                                proximo_efectivo = self.extract_prize_amount(t)
                                if proximo_efectivo:
                                    logging.info(f"Próximo efectivo: ${proximo_efectivo:,}")
                                    break
                    
                    # Fallback: buscar TODOS los montos en millones y tomar el MENOR
                    # El cash value SIEMPRE es menor que el jackpot estimado
                    if not proximo_efectivo:
                        todos = re.findall(r'\$?\s*(\d+\.?\d*)\s*[Mm]ill', next_section.get_text())
                        montos = [int(float(x) * 1_000_000) for x in todos]
                        if len(montos) >= 2:
                            proximo_efectivo = min(montos)
                            logging.info(f"Próximo efectivo (fallback min): ${proximo_efectivo:,}")
                        elif len(montos) == 1:
                            logging.warning("Solo un monto encontrado, no se puede distinguir jackpot de cash value")
                    
                    # Sanity check: el efectivo SIEMPRE debe ser menor que el estimado
                    if proximo_efectivo and proximo_estimado and proximo_efectivo >= proximo_estimado:
                        logging.warning(f"⚠️ Cash value >= jackpot, descartando cash value")
                        proximo_efectivo = None
                    
            except Exception as e:
                logging.warning(f"Error próximo sorteo: {e}")
            
            # ══════════════════════════════════════════════
            # RESULTADO FINAL
            # ══════════════════════════════════════════════
            success = len(white_balls) == 5 and powerball is not None and draw_date is not None
            
            results = {
                'sorteo': {
                    'fecha': draw_date,
                    'blancos': sorted(white_balls),
                    'powerball': powerball,
                    'powerplay': power_play,
                    'jackpot_ganado': jackpot_ganado,
                    'ganador_estado': ganador_estado
                },
                'proximo_sorteo': {
                    'fecha': proximo_fecha,
                    'premio_estimado': proximo_estimado,
                    'premio_efectivo': proximo_efectivo
                },
                'fecha_actualizacion': self.format_update_date(),
                '_success': success
            }
            
            if success:
                logging.info(f"[OK] Completo: {sorted(white_balls)} PB:{powerball} | Próximo:{proximo_fecha} ${proximo_estimado}")
            else:
                logging.warning(f"[ADVERTENCIA] Incompleto — blancos:{len(white_balls)}/5, PB:{powerball}, fecha:{draw_date}")
            
            return results
            
        except Exception as e:
            logging.error(f"[ERROR] Scraping falló: {str(e)}", exc_info=True)
            return {
                '_success': False,
                'error': str(e),
                'fecha_actualizacion': self.format_update_date()
            }
    
    def scrape_with_retry(self, max_attempts=MAX_RETRY_ATTEMPTS, delay=RETRY_DELAY_SECONDS):
        """Intenta scrapear con reintentos"""
        for attempt in range(1, max_attempts + 1):
            logging.info(f"Intento {attempt} de {max_attempts}")
            results = self.scrape_results()
            if results.get('_success'):
                return results
            if attempt < max_attempts:
                logging.info(f"Esperando {delay}s...")
                time.sleep(delay)
        logging.error("[ERROR] Todos los intentos fallaron")
        return results
    
    def save_results(self, results):
        """Guarda resultados actuales e histórico"""
        try:
            results_to_save = {
                'sorteo': results['sorteo'],
                'proximo_sorteo': results['proximo_sorteo'],
                'fecha_actualizacion': results['fecha_actualizacion']
            }
            
            # 1. Archivo actual (se sobrescribe siempre)
            with open(RESULTS_FILE, 'w', encoding='utf-8') as f:
                json.dump(results_to_save, f, indent=2, ensure_ascii=False)
            logging.info(f"[OK] Guardado en {RESULTS_FILE}")
            
            # 2. Histórico — guarda solo el sorteo, sin proximo_sorteo
            try:
                with open(HISTORIC_FILE, 'r', encoding='utf-8') as f:
                    historico = json.load(f)
            except FileNotFoundError:
                historico = []
            
            fecha_sorteo = results['sorteo']['fecha']
            ya_existe = any(r.get('sorteo', {}).get('fecha') == fecha_sorteo for r in historico)
            
            if not ya_existe:
                historico.insert(0, {
                    'sorteo': results['sorteo'],
                    'fecha_actualizacion': results['fecha_actualizacion']
                })
                with open(HISTORIC_FILE, 'w', encoding='utf-8') as f:
                    json.dump(historico, f, indent=2, ensure_ascii=False)
                logging.info(f"[OK] Histórico: {len(historico)} sorteos")
            else:
                logging.info(f"[INFO] Sorteo {fecha_sorteo} ya existe en histórico")
            
            return True
        except Exception as e:
            logging.error(f"[ERROR] Error al guardar: {e}")
            return False


def main():
    logging.info("="*60)
    logging.info("POWERBALL SCRAPER - INICIANDO")
    logging.info("="*60)
    
    scraper = PowerballScraper()
    results = scraper.scrape_with_retry()
    
    if results.get('_success'):
        sorteo = results['sorteo']
        proximo = results['proximo_sorteo']
        
        # Validar fecha con doble seguro
        fecha_scrapeda = sorteo.get('fecha')
        fecha_calculada = scraper.calcular_fecha_ultimo_sorteo()
        
        if fecha_scrapeda:
            if fecha_calculada > fecha_scrapeda:
                logging.warning(f"⚠️ Fecha scrapeada ({fecha_scrapeda}) < calculada ({fecha_calculada})")
                sorteo['fecha'] = fecha_calculada
            else:
                logging.info(f"✓ Fecha correcta: {fecha_scrapeda}")
        else:
            sorteo['fecha'] = fecha_calculada
            logging.warning(f"⚠️ Usando fecha calculada: {fecha_calculada}")
        
        scraper.save_results(results)
        
        try:
            with open(HISTORIC_FILE, 'r', encoding='utf-8') as f:
                total_historico = len(json.load(f))
        except:
            total_historico = 0
        
        print("\n" + "="*60)
        print("  SORTEO ACTUAL")
        print("="*60)
        print(f"  Fecha       : {sorteo['fecha']}")
        print(f"  Blancos     : {' - '.join(map(str, sorteo['blancos']))}")
        print(f"  Powerball   : {sorteo['powerball']}")
        print(f"  Power Play  : {sorteo['powerplay']}x" if sorteo['powerplay'] else "  Power Play  : N/A")
        if sorteo['jackpot_ganado']:
            print(f"  Jackpot     : ✅ GANADO en {sorteo['ganador_estado']}")
        else:
            print(f"  Jackpot     : ❌ Nadie ganó — acumula para próximo sorteo")
        
        print("\n" + "-"*60)
        print("  PRÓXIMO SORTEO")
        print("-"*60)
        print(f"  Fecha       : {proximo['fecha'] or 'N/A'}")
        print(f"  Est. Jackpot: ${proximo['premio_estimado']:,}" if proximo['premio_estimado'] else "  Est. Jackpot: ⏳ Pendiente")
        print(f"  Cash Value  : ${proximo['premio_efectivo']:,}" if proximo['premio_efectivo'] else "  Cash Value  : ⏳ Pendiente")
        
        print("\n" + "-"*60)
        print(f"  Actualizado : {results['fecha_actualizacion']}")
        print(f"  Archivo     : {RESULTS_FILE}")
        print(f"  Histórico   : {total_historico} sorteos guardados")
        print("="*60)
    else:
        logging.error("No se pudieron obtener los resultados")
        print("\nERROR: No se pudieron obtener los resultados")
        if 'error' in results:
            print(f"Detalle: {results['error']}")


if __name__ == "__main__":
    main()

    