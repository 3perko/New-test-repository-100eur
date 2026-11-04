import os
import tempfile

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://app:app@localhost:5432/naklady_test")
os.environ["STORAGE_DIR"] = tempfile.mkdtemp(prefix="naklady-test-")
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["ADMIN_EMAIL"] = ""
os.environ["SECRET_KEY"] = "test-secret-key-test-secret-key-123456"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Company, Project, User  # noqa: E402
from app.security import hash_password  # noqa: E402


@pytest.fixture()
def db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    s = SessionLocal()
    yield s
    s.close()


@pytest.fixture()
def setup(db):
    c1 = Company(name="Alfa s.r.o.", ico="11111111", vat_payer=True)
    c2 = Company(name="Beta s.r.o.", ico="22222222", vat_payer=False)
    db.add_all([c1, c2])
    db.flush()
    db.add_all([Project(company_id=c1.id, name="Réžia", is_overhead=True),
                Project(company_id=c2.id, name="Réžia", is_overhead=True)])
    db.add(User(email="admin@test.sk", name="Admin", role="admin", password_hash=hash_password("heslo1234")))
    db.commit()
    return {"c1": c1.id, "c2": c2.id}


def make_client(email="admin@test.sk", password="heslo1234", company_id=None) -> TestClient:
    c = TestClient(app)
    c.headers["X-Requested-With"] = "app"
    r = c.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    if company_id:
        c.headers["X-Company-Id"] = str(company_id)
    return c


@pytest.fixture()
def admin(setup):
    return make_client(company_id=setup["c1"])


def create(client, entity, data, status=200):
    r = client.post(f"/api/data/{entity}", json=data)
    assert r.status_code == status, r.text
    return r.json()
