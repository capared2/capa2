# 🎱 Powerball Scraper

Scraper automatizado para obtener resultados del Powerball.

## Instalación

1. Clonar el repositorio
2. Crear entorno virtual: `python -m venv venv`
3. Activar entorno: `source venv/bin/activate` (Linux/Mac) o `venv\Scripts\activate` (Windows)
4. Instalar dependencias: `pip install -r requirements.txt`

## Uso
```bash
python powerball_scraper.py
```

## Configuración Crontab
```bash
# Ejecutar Lunes, Miércoles y Sábados a las 9:10 PM
10 21 * * 1,3,6 /ruta/al/proyecto/run_scraper.sh
```

## Resultados

Los resultados se guardan en `powerball_results.json`