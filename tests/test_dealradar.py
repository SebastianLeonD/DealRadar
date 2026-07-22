from app import categorize, db


def test_categorize_tech():
    assert categorize.categorize("Samsung 55\" OLED TV + soundbar bundle $899") == "Tech"


def test_categorize_clothing():
    assert categorize.categorize("Levi's 501 jeans 40% off at Amazon") == "Clothing"


def test_categorize_gaming():
    assert categorize.categorize("PS5 DualSense controller $49") == "Gaming"


def test_categorize_unknown_falls_back_to_other():
    assert categorize.categorize("zzz completely unrelated thing") == "Other"


def test_db_upsert_dedupes(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    deal = {"title": "RTX 4070 $499", "url": "https://x.test/1", "source": "test",
            "category": "Tech", "posted_at": None}
    assert db.upsert_deals([deal]) == 1
    assert db.upsert_deals([deal]) == 0  # same URL -> ignored
    rows = db.list_deals()
    assert len(rows) == 1 and rows[0]["category"] == "Tech"


def test_db_filters(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.upsert_deals([
        {"title": "RTX 4070 $499", "url": "https://x.test/1", "source": "t", "category": "Tech"},
        {"title": "Nike hoodie $30", "url": "https://x.test/2", "source": "t", "category": "Clothing"},
    ])
    assert len(db.list_deals(category="Tech")) == 1
    assert len(db.list_deals(q="hoodie")) == 1
    counts = {c["category"]: c["n"] for c in db.category_counts()}
    assert counts == {"Tech": 1, "Clothing": 1}
