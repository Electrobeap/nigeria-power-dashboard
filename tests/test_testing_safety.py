"""Fail before destructive fixtures if a developer points pytest at a real database."""
import pytest

from tests.conftest import pytest_configure


@pytest.mark.parametrize("uri", [
    "postgresql+psycopg://npd_test:synthetic@production.example/npd_test",
    "postgresql+psycopg://npd_test:synthetic@localhost/production",
    "postgresql+psycopg://postgres:synthetic@localhost/npd_test",
    "postgresql+psycopg://npd_test:synthetic@localhost/npd_test?host=production.example",
    "sqlite:///production.sqlite",
    "not-a-database-url",
])
def test_non_disposable_test_database_is_rejected(monkeypatch, uri):
    monkeypatch.setenv("SUBSCRIPTION_TEST_DATABASE_URL", uri)
    with pytest.raises(pytest.UsageError, match="Tests destroy their database") as error:
        pytest_configure(None)
    assert "synthetic" not in str(error.value)


@pytest.mark.parametrize("uri", [
    "",
    "postgresql+psycopg://npd_test:synthetic@127.0.0.1:5432/npd_test",
    "postgresql+psycopg://npd_test:synthetic@localhost:5433/npd_test",
])
def test_explicit_local_disposable_database_is_allowed(monkeypatch, uri):
    monkeypatch.setenv("SUBSCRIPTION_TEST_DATABASE_URL", uri)
    pytest_configure(None)
