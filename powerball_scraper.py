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
        
        # Mapeo de meses en inglés a español
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
        dia_semana = hoy.weekday()  # 0=Lunes, 1=Martes, ..., 5=Sábado, 6=Domingo
        hora = hoy.hour
        
        # Días de sorteo: Lunes(0), Miércoles(2), Sábado(5)
        dias_sorteo = [0, 2, 5]
        
        # Si es día de sorteo y ya pasaron las 23:00 (11 PM)
        if dia_semana in dias_sorteo and hora >= 23:
            return hoy.strftime('%Y-%m-%d')
        
        # Buscar el último día de sorteo hacia atrás
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
            # Limpiar el formato "Mon, Feb 2, 2026" eliminando el día de la semana
            date_str_clean = re.sub(r'^[A-Za-z]+,\s*', '', date_str.strip())
            
            # Mapeo de abreviaturas de meses a nombres completos
            month_abbr = {
                'Jan': 'January', 'Feb': 'February', 'Mar': 'March', 'Apr': 'April',
                'May': 'May', 'Jun': 'June', 'Jul': 'July', 'Aug': 'August',
                'Sep': 'September', 'Oct': 'October', 'Nov': 'November', 'Dec': 'December'
            }
            
            # Reemplazar abreviatura de mes por nombre completo
            for abbr, full in month_abbr.items():
                if date_str_clean.startswith(abbr):
                    date_str_clean = date_str_clean.replace(abbr, full, 1)
                    break
            
            # Intentar diferentes formatos de fecha
            for fmt in ['%B %d, %Y', '%m/%d/%Y', '%d-%m-%Y']:
                try:
                    date_obj = datetime.strptime(date_str_clean, fmt)
                    return date_obj.strftime('%Y-%m-%d')
                except ValueError:
                    continue
            
            # Si no funciona ningún formato, intentar extracción con regex
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
        
        # Obtener día de la semana y mes en español
        day_name = self.dias.get(now.strftime('%A'), now.strftime('%A'))
        month_name = self.meses.get(now.strftime('%B'), now.strftime('%B'))
        
        # Formato: "Sábado, 1 de Febrero de 2026 - 11:15 PM ET"
        formatted = f"{day_name}, {now.day} de {month_name} de {now.year} - {now.strftime('%I:%M %p')} ET"
        return formatted
    
    def extract_prize_amount(self, text):
        """Extrae el monto del premio (maneja millones y miles)"""
        try:
            if not text:
                return None
            
            # Limpiar texto básico
            text = text.strip()
            
            # Buscar patrón de millones (ej: "$80 Million" o "$36.2 Million")
            match_million = re.search(r'\$?\s*(\d+\.?\d*)\s*[Mm]illion', text, re.IGNORECASE)
            if match_million:
                amount = float(match_million.group(1)) * 1_000_000
                return int(amount)
            
            # Buscar patrón de número con comas (ej: "$285,000,000")
            text_clean = text.replace('$', '').replace(',', '').strip()
            match_number = re.search(r'(\d+)', text_clean)
            if match_number:
                return int(match_number.group(1))
            
            return None
        except Exception as e:
            logging.error(f"Error extrayendo monto del premio de '{text}': {e}")
            return None
    
    def scrape_results(self):
        """Extrae los resultados más recientes del Powerball"""
        try:
            logging.info(f"Iniciando scraping de {self.url}")
            response = requests.get(self.url, headers=self.headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extraer fecha - Buscar en la sección de Winners
            date_element = None
            # Primero buscar en la sección de ganadores
            winners_section = soup.find('div', class_='col', id='winners')
            if winners_section:
                date_element = winners_section.find('h5', class_='card-title')
            
            # Si no se encuentra, buscar en toda la página
            if not date_element:
                date_element = soup.find('h5', class_='card-title')
            
            draw_date_raw = date_element.text.strip() if date_element else None
            draw_date = self.format_date_iso(draw_date_raw) if draw_date_raw else None
            logging.info(f"Fecha encontrada: {draw_date_raw} -> {draw_date}")
            
            # Extraer números blancos - Buscar elementos con clase "white-balls item-powerball"
            white_balls = []
            
            # Buscar todos los divs que contengan números del powerball
            ball_containers = soup.find_all('div', class_='form-control')
            
            logging.info(f"Elementos form-control encontrados: {len(ball_containers)}")
            
            for container in ball_containers:
                # Solo los que tienen clase white-balls
                if 'white-balls' in container.get('class', []):
                    number_text = container.text.strip()
                    # Limpiar el texto y extraer solo números
                    number_clean = re.sub(r'[^\d]', '', number_text)
                    if number_clean.isdigit():
                        white_balls.append(int(number_clean))
            
            logging.info(f"Números blancos extraídos: {white_balls}")
            
            # Extraer Powerball (número rojo) - Buscar div con clase "powerball item-powerball"
            powerball = None
            
            for container in ball_containers:
                if 'powerball' in container.get('class', []) and 'white-balls' not in container.get('class', []):
                    number_text = container.text.strip()
                    number_clean = re.sub(r'[^\d]', '', number_text)
                    if number_clean.isdigit():
                        powerball = int(number_clean)
                        logging.info(f"Powerball extraído: {powerball}")
                        break
            
            if powerball is None:
                logging.warning("No se encontró elemento powerball")
            
            # Extraer Power Play - Buscar el texto "Power Play 2x" o similar
            power_play = None
            try:
                # Buscar todos los elementos de texto que contengan "Power Play"
                power_play_elements = soup.find_all(string=re.compile(r'Power\s*Play', re.IGNORECASE))
                
                logging.info(f"Elementos con 'Power Play' encontrados: {len(power_play_elements)}")
                
                for pp_elem in power_play_elements:
                    # Buscar el número seguido de 'x' en el mismo texto
                    match = re.search(r'(\d+)\s*x', pp_elem, re.IGNORECASE)
                    if match:
                        power_play = int(match.group(1))
                        logging.info(f"Power Play extraído del texto: {power_play}x")
                        break
                    
                    # Si no está en el mismo elemento, buscar en elementos cercanos
                    if not power_play and pp_elem.parent:
                        parent_text = pp_elem.parent.text
                        match = re.search(r'(\d+)\s*x', parent_text, re.IGNORECASE)
                        if match:
                            power_play = int(match.group(1))
                            logging.info(f"Power Play extraído del elemento padre: {power_play}x")
                            break
                
                if power_play is None:
                    logging.warning("No se pudo extraer Power Play")
            except Exception as e:
                logging.warning(f"Error al extraer Power Play: {e}")
            
            # Extraer Premio Estimado (Jackpot) - Buscar span con clase "game-jackpot-number"
            premio_estimado = None
            try:
                # Buscar el span que contiene el monto del jackpot
                jackpot_span = soup.find('span', class_='game-jackpot-number')
                
                if jackpot_span:
                    jackpot_text = jackpot_span.text.strip()
                    premio_estimado = self.extract_prize_amount(jackpot_text)
                    logging.info(f"Premio estimado extraído: ${premio_estimado:,}" if premio_estimado else "Premio estimado: No se pudo parsear")
                else:
                    # Intento alternativo: buscar texto que contenga "Estimated Jackpot"
                    jackpot_section = soup.find(string=re.compile(r'Estimated Jackpot', re.IGNORECASE))
                    if jackpot_section:
                        # Buscar el siguiente span con el número
                        parent = jackpot_section.parent
                        if parent:
                            next_span = parent.find_next('span', class_=re.compile(r'jackpot'))
                            if next_span:
                                premio_estimado = self.extract_prize_amount(next_span.text)
                    
                    if premio_estimado:
                        logging.info(f"Premio estimado (método alternativo): ${premio_estimado:,}")
                    else:
                        logging.warning("No se encontró elemento de premio estimado")
            except Exception as e:
                logging.warning(f"Error al extraer premio estimado: {e}")
            
            # Extraer Premio en Efectivo (Cash Value)
            premio_efectivo = None
            try:
                # Buscar el texto "CASH VALUE" y el siguiente elemento
                cash_labels = soup.find_all(string=re.compile(r'CASH\s*VALUE', re.IGNORECASE))
                
                for cash_label in cash_labels:
                    parent = cash_label.parent
                    if parent:
                        # Buscar el siguiente hermano que contenga el monto
                        next_elem = parent.find_next_sibling()
                        if next_elem:
                            cash_text = next_elem.text.strip()
                            premio_efectivo = self.extract_prize_amount(cash_text)
                            if premio_efectivo:
                                logging.info(f"Premio efectivo extraído: ${premio_efectivo:,}")
                                break
                        
                        # Si no hay hermano, buscar en el contenedor padre
                        if not premio_efectivo:
                            parent_container = parent.parent
                            if parent_container:
                                # Buscar todos los spans o divs que puedan contener el monto
                                possible_cash = parent_container.find_all(string=re.compile(r'\$.*Million|\$[\d,]+'))
                                for cash_candidate in possible_cash:
                                    if 'CASH' not in cash_candidate.upper() and 'VALUE' not in cash_candidate.upper():
                                        premio_efectivo = self.extract_prize_amount(cash_candidate)
                                        if premio_efectivo:
                                            logging.info(f"Premio efectivo extraído (método alternativo): ${premio_efectivo:,}")
                                            break
                                if premio_efectivo:
                                    break
                
                if premio_efectivo is None:
                    logging.warning("No se encontró elemento de premio efectivo")
            except Exception as e:
                logging.warning(f"Error al extraer premio efectivo: {e}")
            
            # Validar resultados
            success = (
                len(white_balls) == 5 and 
                powerball is not None and 
                draw_date is not None
            )
            
            # Crear estructura JSON según el formato requerido
            results = {
                'sorteo': {
                    'fecha': draw_date,
                    'blancos': sorted(white_balls),
                    'powerball': powerball,
                    'powerplay': power_play,
                    'premio_estimado': premio_estimado,
                    'premio_efectivo': premio_efectivo
                },
                'fecha_actualizacion': self.format_update_date(),
                '_success': success
            }
            
            if success:
                logging.info(f"[OK] Resultados completos: {sorted(white_balls)} + {powerball}")
            else:
                logging.warning(f"[ADVERTENCIA] Resultados incompletos - White balls: {len(white_balls)}/5, Powerball: {powerball}, Fecha: {draw_date}")
            
            return results
            
        except Exception as e:
            logging.error(f"[ERROR] Error en scraping: {str(e)}", exc_info=True)
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
            else:
                if attempt < max_attempts:
                    logging.info(f"Esperando {delay} segundos antes del próximo intento...")
                    time.sleep(delay)
        
        logging.error("[ERROR] Todos los intentos fallaron")
        return results
    
    def save_results(self, results):
        """Guarda los resultados en JSON (actuales e histórico)"""
        try:
            # Crear copia del resultado sin el campo '_success'
            results_to_save = {
                'sorteo': results['sorteo'],
                'fecha_actualizacion': results['fecha_actualizacion']
            }
            
            # 1. Guardar resultados actuales (se sobrescribe)
            with open(RESULTS_FILE, 'w', encoding='utf-8') as f:
                json.dump(results_to_save, f, indent=2, ensure_ascii=False)
            logging.info(f"[OK] Resultados actuales guardados en {RESULTS_FILE}")
            
            # 2. Agregar al histórico (solo si no existe esa fecha)
            try:
                # Intentar cargar histórico existente
                with open(HISTORIC_FILE, 'r', encoding='utf-8') as f:
                    historico = json.load(f)
            except FileNotFoundError:
                # Si no existe, crear array vacío
                historico = []
                logging.info(f"Creando nuevo archivo de histórico: {HISTORIC_FILE}")
            
            # Verificar si ya existe este sorteo en el histórico (por fecha)
            fecha_sorteo = results['sorteo']['fecha']
            ya_existe = any(r.get('sorteo', {}).get('fecha') == fecha_sorteo for r in historico)
            
            if not ya_existe:
                # Agregar al inicio del array (más reciente primero)
                historico.insert(0, results_to_save)
                
                # Guardar histórico actualizado
                with open(HISTORIC_FILE, 'w', encoding='utf-8') as f:
                    json.dump(historico, f, indent=2, ensure_ascii=False)
                
                logging.info(f"[OK] Resultado agregado al histórico: {HISTORIC_FILE} (Total: {len(historico)} sorteos)")
            else:
                logging.info(f"[INFO] Sorteo del {fecha_sorteo} ya existe en el histórico, no se agregó")
            
            return True
            
        except Exception as e:
            logging.error(f"[ERROR] Error al guardar: {e}")
            return False


def main():
    """Función principal"""
    logging.info("="*60)
    logging.info("POWERBALL SCRAPER - INICIANDO")
    logging.info("="*60)
    
    scraper = PowerballScraper()
    results = scraper.scrape_with_retry()
    
    if results.get('_success'):
        sorteo = results['sorteo']
        
        # ===== LEER JSON ACTUAL (solo para fecha) =====
        json_actual = scraper.leer_json_actual()
        fecha_anterior = None
        
        if json_actual and 'sorteo' in json_actual:
            fecha_anterior = json_actual['sorteo'].get('fecha')
        
        # ===== VALIDAR Y CORREGIR FECHA =====
        fecha_scrapeda = sorteo.get('fecha')
        
        if fecha_scrapeda and fecha_anterior:
            if fecha_scrapeda == fecha_anterior:
                # La fecha no cambió, calcular inteligentemente
                fecha_calculada = scraper.calcular_fecha_ultimo_sorteo()
                logging.info(f"📅 Fecha scrapeada sin cambios: {fecha_scrapeda}")
                logging.info(f"📅 Usando fecha calculada: {fecha_calculada}")
                sorteo['fecha'] = fecha_calculada
            else:
                logging.info(f"✓ Fecha actualizada: {fecha_anterior} → {fecha_scrapeda}")
        elif not fecha_scrapeda:
            # No se pudo scrapear fecha, calcular
            fecha_calculada = scraper.calcular_fecha_ultimo_sorteo()
            logging.warning(f"⚠️ No se pudo scrapear fecha, usando calculada: {fecha_calculada}")
            sorteo['fecha'] = fecha_calculada
        else:
            # Primera vez o no hay JSON anterior
            logging.info(f"✓ Fecha scrapeada: {fecha_scrapeda}")
        
        # ===== VALIDAR PREMIOS =====
        if sorteo['premio_estimado'] is None or sorteo['premio_efectivo'] is None:
            logging.warning("⚠️ Premios no disponibles aún en el sitio oficial")
            logging.info("📊 Se guardará como null - Frontend mostrará 'Se actualizará pronto'")
        else:
            logging.info("✓ Premios scrapeados correctamente")
        
        # ===== GUARDAR RESULTADOS =====
        scraper.save_results(results)
        
        # Contar histórico
        try:
            with open(HISTORIC_FILE, 'r', encoding='utf-8') as f:
                historico = json.load(f)
                total_historico = len(historico)
        except:
            total_historico = 0
        
        # ===== MOSTRAR RESUMEN =====
        print("\n" + "="*60)
        print("RESULTADOS DEL POWERBALL")
        print("="*60)
        print(f"Fecha: {sorteo['fecha']}")
        print(f"Números blancos: {' - '.join(map(str, sorteo['blancos']))}")
        print(f"Powerball: {sorteo['powerball']}")
        print(f"Power Play: {sorteo['powerplay']}x" if sorteo['powerplay'] else "Power Play: N/A")
        
        if sorteo['premio_estimado']:
            print(f"Premio Estimado: ${sorteo['premio_estimado']:,}")
        else:
            print("Premio Estimado: ⏳ Se actualizará pronto")
        
        if sorteo['premio_efectivo']:
            print(f"Premio Efectivo: ${sorteo['premio_efectivo']:,}")
        else:
            print("Premio Efectivo: ⏳ Se actualizará pronto")
        
        print(f"\nActualizado: {results['fecha_actualizacion']}")
        print("-"*60)
        print(f"📁 Archivo actual: {RESULTS_FILE}")
        print(f"📚 Histórico: {HISTORIC_FILE} ({total_historico} sorteos)")
        print("="*60)
        
        if sorteo['premio_estimado'] is None or sorteo['premio_efectivo'] is None:
            print("\n⚠️  NOTA: Los premios del próximo sorteo se actualizarán pronto")
            print("    El sitio oficial aún no ha publicado esta información.")
            print("="*60)
    else:
        logging.error("No se pudieron obtener los resultados")
        print("\n" + "="*60)
        print("ERROR: No se pudieron obtener los resultados")
        print("="*60)
        if 'error' in results:
            print(f"Detalle: {results['error']}")


if __name__ == "__main__":
    main()

    