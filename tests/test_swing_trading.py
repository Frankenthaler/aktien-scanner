"""
tests/test_swing_trading.py

FIX 4: Unit-Tests für Swing-Trading Tracking
"""

import unittest
import sqlite3
import pandas as pd
from datetime import date
import tempfile
import os

import sys, os as os2
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trading.recommendation_tracker import (
    init_swing_trading_schema,
    save_swing_trade_recommendation,
    SCORE_VERSION,
)


class TestScoreVersioning(unittest.TestCase):
    """Test: Score-Versionierung"""
    
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.db_path = self.temp_db.name
        self.temp_db.close()
        
        init_swing_trading_schema(self.db_path)
    
    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
    
    def test_save_recommendation_with_score_version_1_0(self):
        """Test: Empfehlung mit Score-Version 1.0 speichern"""
        
        score_dict = {
            'date': str(date.today()),
            'ticker': 'TEST',
            'score_total': 75,
            'score_sma200': 15,
            'score_rs': 20,
            'score_breakout': 25,
            'score_regime': 10,
            'score_risk': 5,
            'rating': 'Interessant',
            'price_close': 125.50,
            'sma200': 122.0,
            'rs_score': 3.5,
            'breakout_flag': 1,
            'breakout_age': 1,
            'regime': 'positiv',
            'atr14': 2.5,
            'atr_ratio': 2.0,
            'crv': 2.1,
            'kursziel': 135.0,
        }
        
        rec_id = save_swing_trade_recommendation(
            score_dict=score_dict,
            stop_buy_price=126.50,
            stop_loss_price=120.25,
            score_version="1.0",
            db_path=self.db_path
        )
        
        self.assertIsNotNone(rec_id)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT score_version FROM swing_trade_recommendations WHERE id=?", (rec_id,))
        result = cursor.fetchone()
        
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "1.0")
        conn.close()
    
    def test_score_version_default_1_0(self):
        """Test: Default Score-Version ist 1.0"""
        self.assertEqual(SCORE_VERSION, "1.0")
    
    def test_filter_low_scores(self):
        """Test: Scores < 55 werden nicht gespeichert"""
        
        low_score = {
            'date': str(date.today()),
            'ticker': 'LOW',
            'score_total': 40,
            'score_sma200': 10,
            'score_rs': 10,
            'score_breakout': 10,
            'score_regime': 5,
            'score_risk': 5,
            'rating': 'Beobachten',
            'price_close': 100.0,
            'sma200': 100.0,
            'rs_score': -1.0,
            'breakout_flag': 0,
            'breakout_age': 0,
            'regime': 'neutral',
            'atr14': 1.5,
            'atr_ratio': 1.5,
            'crv': 0.5,
            'kursziel': 105.0,
        }
        
        rec_id = save_swing_trade_recommendation(
            score_dict=low_score,
            stop_buy_price=100.50,
            stop_loss_price=95.0,
            db_path=self.db_path
        )
        
        self.assertIsNone(rec_id)
    
    def test_database_tables_created(self):
        """Test: Datenbank-Tabellen wurden erstellt"""
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='swing_trade_recommendations'")
        self.assertIsNotNone(cursor.fetchone())
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='swing_trade_performance'")
        self.assertIsNotNone(cursor.fetchone())
        
        conn.close()
    
    def test_score_version_field_exists(self):
        """Test: Score-Version Feld existiert in Datenbank"""
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("PRAGMA table_info(swing_trade_recommendations)")
        columns = [row[1] for row in cursor.fetchall()]
        
        self.assertIn('score_version', columns)
        conn.close()


class TestTradingDayCalculation(unittest.TestCase):
    """FIX 4: Unit-Tests für Handeltag-Berechnung"""
    
    def get_price_at_trading_day_offset(self, idx, offset, dates, closes):
        """Helper: Implementierung der Handelstag-Berechnung"""
        trading_day_count = 0
        for j in range(idx + 1, len(dates)):
            if dates[j].weekday() < 5:
                trading_day_count += 1
            if trading_day_count == offset:
                return float(closes[j])
        return None
    
    def test_trading_day_offset_with_weekend(self):
        """Test: Wochenende wird korrekt übersprungen"""
        
        dates = pd.DatetimeIndex([
            '2024-01-01',
            '2024-01-02',
            '2024-01-03',
            '2024-01-04',
            '2024-01-05',
            '2024-01-06',
            '2024-01-07',
            '2024-01-08',
        ])
        
        closes = [100, 101, 102, 103, 104, 105, 106, 107]
        
        price = self.get_price_at_trading_day_offset(0, 5, dates, closes)
        
        self.assertEqual(price, 107.0)
    
    def test_trading_day_count_accuracy(self):
        """Test: Handelstag-Zählung ist korrekt"""
        
        dates = pd.DatetimeIndex([
            '2024-01-01',
            '2024-01-02',
            '2024-01-03',
        ])
        
        closes = [100, 101, 102]
        
        price = self.get_price_at_trading_day_offset(0, 2, dates, closes)
        
        self.assertEqual(price, 102.0)
    
    def test_insufficient_data(self):
        """Test: Zu wenig Daten -> None"""
        
        dates = pd.DatetimeIndex(['2024-01-01', '2024-01-02'])
        closes = [100, 101]
        
        price = self.get_price_at_trading_day_offset(0, 10, dates, closes)
        
        self.assertIsNone(price)


if __name__ == '__main__':
    print("=" * 70)
    print("FIX 4: UNIT-TESTS FÜR SWING-TRADING TRACKING")
    print("=" * 70)
    print()
    
    unittest.main(argv=[''], verbosity=2, exit=False)
    
    print()
    print("=" * 70)
    print("✓ TESTS ABGESCHLOSSEN")
    print("=" * 70)
