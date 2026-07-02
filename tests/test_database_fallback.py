import importlib
import os


def test_placeholder_mysql_url_falls_back_to_sqlite(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "mysql+pymysql://root:YOUR_MYSQL_PASSWORD@localhost:3306/zambia_fraud")

    import app.models.database as database_module
    importlib.reload(database_module)

    assert str(database_module.engine.url).startswith("sqlite")
