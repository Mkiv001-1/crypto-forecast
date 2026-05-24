"""Tests for MetaLabelStage (shadow mode)."""

import sqlite3
from unittest.mock import MagicMock, patch

from scripts.core.meta_label.stage import MetaLabelStage
from scripts.core.pipeline.base import PipelineContext


def _minimal_db(tmp_path):
    db_file = tmp_path / "test.db"
    con = sqlite3.connect(db_file)
    con.executescript(
        """
        CREATE TABLE config (key TEXT PRIMARY KEY, value TEXT, description TEXT);
        CREATE TABLE settings (ticker TEXT PRIMARY KEY, active INTEGER, sector TEXT);
        CREATE TABLE consensus (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT, ticker TEXT, signal TEXT, confidence REAL,
            order_state TEXT, meta_score REAL, meta_decision TEXT,
            meta_model_version TEXT, meta_features_json TEXT
        );
        INSERT INTO config VALUES ('META_LABEL_ENABLED', 'true', '');
        INSERT INTO config VALUES ('META_LABEL_ENFORCE', 'false', '');
        INSERT INTO config VALUES ('META_LABEL_THRESHOLD', '0.9', '');
        INSERT INTO config VALUES ('META_MODEL_PATH', '', '');
        INSERT INTO settings VALUES ('BTCUSDT', 1, 'L1');
        INSERT INTO consensus (date, ticker, signal, confidence, order_state)
        VALUES ('2026-01-01', 'BTCUSDT', 'LONG', 80, 'PENDING_ORDER');
        """
    )
    con.commit()
    con.close()

    db = MagicMock()
    db.db_file = str(db_file)
    db.get_last_consensus_id = MagicMock(return_value=1)
    db.get_config_value = lambda key, default="": {
        "META_LABEL_ENABLED": "true",
        "META_LABEL_ENFORCE": "false",
        "META_LABEL_THRESHOLD": "0.9",
        "META_MODEL_PATH": "",
        "META_MODEL_VERSION": "test",
    }.get(key, default)

    def _connect():
        c = sqlite3.connect(str(db_file))
        c.row_factory = sqlite3.Row
        return c

    db._connect = _connect
    db.consensus_repo = MagicMock()
    return db


def test_meta_stage_shadow_writes_score(tmp_path):
    db = _minimal_db(tmp_path)
    ctx = PipelineContext(
        ticker="BTCUSDT",
        db_manager=db,
        run_id=1,
    )
    ctx.consensus = {"signal": "LONG", "confidence": 80.0, "horizon_hours": 24}
    ctx.has_consensus = True
    ctx.indicators = {"price": 100.0, "rsi14": 50, "adx14": 20, "atr14": 1}
    ctx.price_data = [{"open": 99, "high": 101, "low": 98, "close": 100, "volume": 1}]

    with patch("scripts.core.meta_label.stage.fetch_ticker_snapshot", return_value=None):
        MetaLabelStage().run(ctx)

    assert ctx.meta_score is not None
    assert ctx.meta_decision in ("PASS", "REJECT")
    assert ctx.meta_order_blocked is False

    con = sqlite3.connect(db.db_file)
    row = con.execute("SELECT meta_score, meta_decision FROM consensus WHERE id=1").fetchone()
    con.close()
    assert row[0] is not None
    assert row[1] in ("PASS", "REJECT")
