import os
import tempfile

from cryptography.fernet import Fernet

# El entorno debe existir antes de importar la app.
_tmp = tempfile.mkdtemp(prefix="cc-test-")
os.environ.update(
    {
        "DATABASE_URL": f"sqlite:///{_tmp}/test.db",
        "DATA_DIR": _tmp,
        "SESSION_SECRET": "test-secret",
        "TOKEN_ENCRYPTION_KEY": Fernet.generate_key().decode(),
        "GOOGLE_CLIENT_ID": "test-client-id.apps.googleusercontent.com",
        "GOOGLE_CLIENT_SECRET": "test-client-secret",
        "OAUTH_REDIRECT_URI": "http://localhost:5173/api/auth/callback",
        "FRONTEND_URL": "http://localhost:5173",
    }
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import models  # noqa: E402,F401
from app.db.session import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def _db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    return TestClient(app, follow_redirects=False)


class FakeRequest:
    def __init__(self, response):
        self._response = response

    def execute(self):
        return self._response


class FakeCollection:
    """Imita un recurso de googleapiclient: .list(**kw) devuelve páginas por pageToken."""

    def __init__(self, pages_by_parent: dict, children: dict | None = None):
        self.pages_by_parent = pages_by_parent
        self.children = children or {}
        self.calls: list[dict] = []

    def list(self, **kwargs):
        self.calls.append(kwargs)
        parent = kwargs.get("courseWorkId") or kwargs.get("courseId") or "me"
        pages = self.pages_by_parent.get(parent, [{}])
        idx = int(kwargs.get("pageToken") or 0)
        page = dict(pages[idx])
        if idx + 1 < len(pages):
            page["nextPageToken"] = str(idx + 1)
        return FakeRequest(page)

    def __getattr__(self, name):
        if name in self.children:
            return lambda: self.children[name]
        raise AttributeError(name)


class FakeClassroomService:
    def __init__(self, courses=None, coursework=None, students=None, submissions=None):
        self.submissions = FakeCollection(submissions or {})
        self.coursework = FakeCollection(
            coursework or {}, {"studentSubmissions": self.submissions}
        )
        self.students = FakeCollection(students or {})
        self.courses_col = FakeCollection(
            courses or {}, {"courseWork": self.coursework, "students": self.students}
        )

    def courses(self):
        return self.courses_col
