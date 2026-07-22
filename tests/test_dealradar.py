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


def test_extract_price_basic():
    assert categorize.extract_price("Levi's 501 Jeans $39.99 (was $70)") == 39.99


def test_extract_price_takes_first_amount():
    assert categorize.extract_price("Hollister shorts $ 15 reg. $40") == 15.0


def test_extract_price_with_commas():
    assert categorize.extract_price("LG C4 65\" OLED $1,299.99") == 1299.99


def test_extract_price_none():
    assert categorize.extract_price("50% off everything at ASOS") is None


def test_detect_store_from_title():
    assert categorize.detect_store("Hollister jeans BOGO 50% off") == "Hollister"
    assert categorize.detect_store("ASOS extra 20% off sale") == "ASOS"
    assert categorize.detect_store("Zara end-of-season event") == "Zara"


def test_detect_store_from_url():
    assert categorize.detect_store("Echo Dot $22", "https://www.amazon.com/dp/x") == "Amazon"


def test_detect_store_unknown():
    assert categorize.detect_store("Random local shop clearance") is None


def test_detect_mens_popular_stores():
    assert categorize.detect_store("PacSun: all shorts 2 for $40") == "PacSun"
    assert categorize.detect_store("Ralph Lauren polo sale 40% off") == "Ralph Lauren"
    assert categorize.detect_store("H&M members: extra 20% off") == "H&M"
    assert categorize.detect_store("American Eagle jeans $29.99") == "American Eagle"
    assert categorize.detect_store("Vans slip-ons $35", "https://www.vans.com/x") == "Vans"
    assert categorize.detect_store("New Balance 574 $59.99") == "New Balance"


def test_age_filter_and_order(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.upsert_deals([
        {"title": "fresh deal $10", "url": "https://x.test/f", "source": "t",
         "category": "Other", "posted_at": "2099-01-01T00:00:00Z"},
        {"title": "ancient deal $10", "url": "https://x.test/o", "source": "t",
         "category": "Other", "posted_at": "2001-01-01T00:00:00Z"},
    ])
    fresh_only = db.list_deals(max_age_hours=48)
    assert [d["title"] for d in fresh_only] == ["fresh deal $10"]
    newest_first = db.list_deals(order="new")
    assert newest_first[0]["title"] == "fresh deal $10"
    assert len(db.list_deals()) == 2  # no age filter -> everything


def test_price_and_store_filters(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.upsert_deals([
        {"title": "Levi's jeans $39.99", "url": "https://x.test/1", "source": "t",
         "category": "Clothing", "store": "Amazon", "price": 39.99},
        {"title": "ASOS jeans $25", "url": "https://x.test/2", "source": "t",
         "category": "Clothing", "store": "ASOS", "price": 25.0},
        {"title": "Hollister shorts, no price listed", "url": "https://x.test/3", "source": "t",
         "category": "Clothing", "store": "Hollister"},
    ])
    # "jeans under $30"
    under_30 = db.list_deals(item="jeans", max_price=30)
    assert [d["store"] for d in under_30] == ["ASOS"]
    # store filter
    assert len(db.list_deals(store="Hollister")) == 1
    # max_price excludes deals with no extracted price
    assert len(db.list_deals(max_price=1000)) == 2
    stores = {s["store"] for s in db.store_counts()}
    assert stores == {"Amazon", "ASOS", "Hollister"}


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
