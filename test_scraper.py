"""Tests offline del scraper multi-juego (sin acceso a red).

Ejecutar con: python test_scraper.py
"""

import json
import os
import tempfile
import unittest

from config import GAMES
from lottery_scraper import (
    PowerballScraper,
    MegaMillionsScraper,
    MuslSiteScraper,
    SocrataScraper,
    crear_scraper,
)

# HTML con la estructura de powerball.com / lottoamerica.com
HTML_POWERBALL = """
<html><body>
<div class="col" id="numbers">
  <h5 class="card-title">Wed, Jul 15, 2026</h5>
  <div class="form-control col white-balls item-powerball">2</div>
  <div class="form-control col white-balls item-powerball">7</div>
  <div class="form-control col white-balls item-powerball">18</div>
  <div class="form-control col white-balls item-powerball">29</div>
  <div class="form-control col white-balls item-powerball">38</div>
  <div class="form-control col powerball item-powerball">16</div>
  <span class="multiplier">Power Play 2X</span>
</div>
<div class="col" id="winners">
  <p>Jackpot Winners: None</p>
</div>
<div class="col" id="dbl-numbers">
  <h5 class="card-title">Double Play</h5>
  <div class="form-control col white-balls">5</div>
  <div class="form-control col white-balls">11</div>
  <div class="form-control col white-balls">22</div>
  <div class="form-control col white-balls">33</div>
  <div class="form-control col white-balls">44</div>
  <div class="form-control col powerball">9</div>
</div>
<div class="col" id="next-drawing">
  <h5 class="card-title">Sat, Jul 18, 2026</h5>
  <span class="game-jackpot-number">$526 Million</span>
  <div class="cash-value"><span>Cash Value:</span> <span>$233.6 Million</span></div>
</div>
</body></html>
"""

HTML_LOTTO_AMERICA = """
<html><body>
<div class="col" id="numbers">
  <h5 class="card-title">Wed, Jul 15, 2026</h5>
  <div class="form-control col white-balls">3</div>
  <div class="form-control col white-balls">14</div>
  <div class="form-control col white-balls">25</div>
  <div class="form-control col white-balls">36</div>
  <div class="form-control col white-balls">47</div>
  <div class="form-control col star-ball">8</div>
  <span class="multiplier">All Star Bonus 3X</span>
</div>
<div class="col" id="next-drawing">
  <h5 class="card-title">Sat, Jul 18, 2026</h5>
  <span class="game-jackpot-number">$3.15 Million</span>
</div>
</body></html>
"""

MEGAMILLIONS_API_PAYLOAD = {
    "d": json.dumps({
        "Drawing": {
            "PlayDate": "2026-07-14T23:00:00",
            "N1": 10, "N2": 11, "N3": 26, "N4": 27, "N5": 34,
            "MBall": 7,
            "Megaplier": 3,
        },
        "Jackpot": {
            "NextPrizePool": 875000000,
            "NextCashValue": 413500000,
        },
        "NextDrawingDate": "2026-07-17T23:00:00",
    })
}

SOCRATA_POWERBALL_ROW = {
    "draw_date": "2026-07-15T00:00:00.000",
    "winning_numbers": "02 07 18 29 38 16",
    "multiplier": "2",
}

SOCRATA_MEGAMILLIONS_ROW = {
    "draw_date": "2026-07-14T00:00:00.000",
    "winning_numbers": "10 11 26 27 34",
    "mega_ball": "7",
    "multiplier": "3",
}

SOCRATA_CASH4LIFE_ROW = {
    "draw_date": "2026-07-17T00:00:00.000",
    "winning_numbers": "05 21 30 42 55",
    "cash_ball": "3",
}


class TestPowerball(unittest.TestCase):
    def setUp(self):
        self.scraper = PowerballScraper('powerball', GAMES['powerball'])

    def test_parse_html_completo(self):
        r = self.scraper.parse_html(HTML_POWERBALL)
        self.assertTrue(r['_success'])
        self.assertEqual(r['sorteo']['fecha'], '2026-07-15')
        self.assertEqual(r['sorteo']['blancos'], [2, 7, 18, 29, 38])
        self.assertEqual(r['sorteo']['powerball'], 16)
        self.assertEqual(r['sorteo']['powerplay'], 2)
        self.assertFalse(r['sorteo']['jackpot_ganado'])
        self.assertIsNone(r['sorteo']['ganador_estado'])

    def test_double_play(self):
        r = self.scraper.parse_html(HTML_POWERBALL)
        dp = r['sorteo']['doble_jugada']
        self.assertIsNotNone(dp)
        self.assertEqual(dp['blancos'], [5, 11, 22, 33, 44])
        self.assertEqual(dp['powerball'], 9)

    def test_proximo_sorteo(self):
        r = self.scraper.parse_html(HTML_POWERBALL)
        self.assertEqual(r['proximo_sorteo']['fecha'], '2026-07-18')
        self.assertEqual(r['proximo_sorteo']['premio_estimado'], 526000000)
        self.assertEqual(r['proximo_sorteo']['premio_efectivo'], 233600000)

    def test_double_play_no_contamina_sorteo_principal(self):
        # Aunque la página tiene 10 bolas blancas en total (5 + 5 Double Play),
        # el sorteo principal debe extraer solo las de la sección #numbers
        r = self.scraper.parse_html(HTML_POWERBALL)
        self.assertEqual(len(r['sorteo']['blancos']), 5)
        self.assertNotIn(44, r['sorteo']['blancos'])

    def test_socrata_fallback(self):
        r = self.scraper.parse_socrata_row(SOCRATA_POWERBALL_ROW)
        self.assertTrue(r['_success'])
        self.assertEqual(r['sorteo']['fecha'], '2026-07-15')
        self.assertEqual(r['sorteo']['blancos'], [2, 7, 18, 29, 38])
        self.assertEqual(r['sorteo']['powerball'], 16)
        self.assertEqual(r['sorteo']['powerplay'], 2)
        # Próximo sorteo calculado: el sábado siguiente al miércoles
        self.assertEqual(r['proximo_sorteo']['fecha'], '2026-07-18')


class TestLottoAmerica(unittest.TestCase):
    def test_parse_html(self):
        scraper = MuslSiteScraper('lottoamerica', GAMES['lottoamerica'])
        r = scraper.parse_html(HTML_LOTTO_AMERICA)
        self.assertTrue(r['_success'])
        self.assertEqual(r['sorteo']['blancos'], [3, 14, 25, 36, 47])
        self.assertEqual(r['sorteo']['star_ball'], 8)
        self.assertEqual(r['sorteo']['all_star_bonus'], 3)
        self.assertEqual(r['proximo_sorteo']['premio_estimado'], 3150000)


class TestMegaMillions(unittest.TestCase):
    def setUp(self):
        self.scraper = MegaMillionsScraper('megamillions', GAMES['megamillions'])

    def test_parse_api(self):
        r = self.scraper.parse_api(MEGAMILLIONS_API_PAYLOAD)
        self.assertTrue(r['_success'])
        self.assertEqual(r['sorteo']['fecha'], '2026-07-14')
        self.assertEqual(r['sorteo']['blancos'], [10, 11, 26, 27, 34])
        self.assertEqual(r['sorteo']['megaball'], 7)
        self.assertEqual(r['sorteo']['megaplier'], 3)
        self.assertEqual(r['proximo_sorteo']['fecha'], '2026-07-17')
        self.assertEqual(r['proximo_sorteo']['premio_estimado'], 875000000)
        self.assertEqual(r['proximo_sorteo']['premio_efectivo'], 413500000)

    def test_socrata_fallback(self):
        r = self.scraper.parse_socrata_row(SOCRATA_MEGAMILLIONS_ROW)
        self.assertTrue(r['_success'])
        self.assertEqual(r['sorteo']['blancos'], [10, 11, 26, 27, 34])
        self.assertEqual(r['sorteo']['megaball'], 7)
        # Martes 14 → próximo sorteo el viernes 17
        self.assertEqual(r['proximo_sorteo']['fecha'], '2026-07-17')


class TestCash4Life(unittest.TestCase):
    def test_parse_socrata(self):
        scraper = SocrataScraper('cash4life', GAMES['cash4life'])
        r = scraper.parse_socrata_row(SOCRATA_CASH4LIFE_ROW)
        self.assertTrue(r['_success'])
        self.assertEqual(r['sorteo']['fecha'], '2026-07-17')
        self.assertEqual(r['sorteo']['blancos'], [5, 21, 30, 42, 55])
        self.assertEqual(r['sorteo']['cash_ball'], 3)
        # Es diario: el próximo sorteo es el día siguiente
        self.assertEqual(r['proximo_sorteo']['fecha'], '2026-07-18')
        self.assertEqual(r['proximo_sorteo']['premio_descripcion'], '$1,000 al día de por vida')


class TestUtilidades(unittest.TestCase):
    def setUp(self):
        self.scraper = PowerballScraper('powerball', GAMES['powerball'])

    def test_extract_prize_amount(self):
        casos = {
            '$218 Millones': 218000000,
            '$101.6 Millones': 101600000,
            '$218 Million': 218000000,
            '$285,000,000': 285000000,
            '$1.2 Billion': 1200000000,
            875000000: 875000000,
            None: None,
            '': None,
        }
        for texto, esperado in casos.items():
            self.assertEqual(self.scraper.extract_prize_amount(texto), esperado, msg=str(texto))

    def test_format_date_iso(self):
        casos = {
            'Wed, Jul 15, 2026': '2026-07-15',
            'July 15, 2026': '2026-07-15',
            '07/15/2026': '2026-07-15',
            '2026-07-15T00:00:00.000': '2026-07-15',
            '2026-07-15': '2026-07-15',
        }
        for texto, esperado in casos.items():
            self.assertEqual(self.scraper.format_date_iso(texto), esperado, msg=texto)

    def test_crear_scraper(self):
        self.assertIsInstance(crear_scraper('powerball', GAMES['powerball']), PowerballScraper)
        self.assertIsInstance(crear_scraper('megamillions', GAMES['megamillions']), MegaMillionsScraper)
        self.assertIsInstance(crear_scraper('lottoamerica', GAMES['lottoamerica']), MuslSiteScraper)
        self.assertIsInstance(crear_scraper('cash4life', GAMES['cash4life']), SocrataScraper)


class TestGuardado(unittest.TestCase):
    def test_save_y_dedup_historico(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = dict(GAMES['powerball'])
            cfg['results_file'] = os.path.join(tmp, 'actual.json')
            cfg['historic_file'] = os.path.join(tmp, 'historico.json')
            scraper = PowerballScraper('powerball', cfg)

            r = scraper.parse_html(HTML_POWERBALL)
            self.assertTrue(scraper.save_results(r))
            # Guardar dos veces el mismo sorteo no debe duplicar el histórico
            self.assertTrue(scraper.save_results(r))

            with open(cfg['historic_file'], encoding='utf-8') as f:
                historico = json.load(f)
            self.assertEqual(len(historico), 1)
            self.assertEqual(historico[0]['sorteo']['fecha'], '2026-07-15')

            with open(cfg['results_file'], encoding='utf-8') as f:
                actual = json.load(f)
            self.assertEqual(actual['juego'], 'powerball')
            self.assertNotIn('_success', actual)


if __name__ == '__main__':
    unittest.main(verbosity=2)
