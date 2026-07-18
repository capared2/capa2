# 🎱 Lottery Scraper Multi-Juego

Scraper automatizado para obtener los resultados de las principales loterías de EE.UU.:

| Juego | Fuente principal | Fuente de respaldo | Sorteos |
|---|---|---|---|
| **Powerball** (+ Double Play) | powerball.com | data.ny.gov | Lun, Mié, Sáb |
| **Mega Millions** | API de megamillions.com | data.ny.gov | Mar, Vie |
| **Lotto America** | lottoamerica.com | — | Lun, Mié, Sáb |
| **Cash4Life** | data.ny.gov | — | Diario |

Cada juego se extrae de forma independiente: si una fuente falla, se usa el
respaldo, y si un juego falla por completo, los demás se guardan igual.

## Instalación

1. Clonar el repositorio
2. Crear entorno virtual: `python -m venv venv`
3. Activar entorno: `source venv/bin/activate` (Linux/Mac) o `venv\Scripts\activate` (Windows)
4. Instalar dependencias: `pip install -r requirements.txt`

## Uso
```bash
python lottery_scraper.py
```

(`python powerball_scraper.py` sigue funcionando por compatibilidad y ejecuta todos los juegos.)

## Tests (sin red)
```bash
python test_scraper.py
```

## Archivos de resultados

| Archivo | Contenido |
|---|---|
| `resultados_actuales.json` | Último sorteo de Powerball (formato original) |
| `historico_resultados.json` | Histórico de Powerball |
| `resultados_megamillions.json` / `historico_megamillions.json` | Mega Millions |
| `resultados_lottoamerica.json` / `historico_lottoamerica.json` | Lotto America |
| `resultados_cash4life.json` / `historico_cash4life.json` | Cash4Life |
| `resultados_todos.json` | Último resultado de todos los juegos en un solo archivo |

Estructura por juego:
```json
{
  "juego": "powerball",
  "nombre": "Powerball",
  "sorteo": {
    "fecha": "2026-07-15",
    "blancos": [2, 7, 18, 29, 38],
    "powerball": 16,
    "powerplay": 2,
    "jackpot_ganado": false,
    "ganador_estado": null,
    "doble_jugada": {"blancos": [5, 11, 22, 33, 44], "powerball": 9}
  },
  "proximo_sorteo": {
    "fecha": "2026-07-18",
    "premio_estimado": 526000000,
    "premio_efectivo": 233600000
  },
  "fecha_actualizacion": "Sábado, 18 de Julio de 2026 - 01:00 PM ET"
}
```
La bola especial y el multiplicador cambian de nombre según el juego:
`powerball`/`powerplay`, `megaball`/`megaplier`, `star_ball`/`all_star_bonus`,
`cash_ball`.

## Configuración

Los juegos, URLs, archivos de salida y días de sorteo se definen en `config.py`
(diccionario `GAMES`). Para desactivar un juego basta con quitarlo de ahí.

## Automatización

El workflow de GitHub Actions (`.github/workflows/scraper.yml`) corre a diario
a las 05:00 UTC (después de todos los sorteos) y también se puede lanzar
manualmente. Hace commit de los JSON solo cuando hay cambios.

Para ejecutarlo con crontab en un servidor propio:
```bash
# Todos los días a las 00:10 ET (después de los sorteos)
10 0 * * * cd /ruta/al/proyecto && ./venv/bin/python lottery_scraper.py
```
