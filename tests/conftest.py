from datetime import date

import pytest

from mitra.agent import Assistant
from mitra.kb import KnowledgeBase
from mitra.seed import CitizenStore

TODAY = date(2026, 11, 21)  # the "current" date in the knowledge base's world


@pytest.fixture(scope="session")
def kb() -> KnowledgeBase:
    return KnowledgeBase.load()


@pytest.fixture(scope="session")
def citizens() -> CitizenStore:
    store = CitizenStore.load()
    if not len(store):
        pytest.skip("seed citizens not found")
    return store


@pytest.fixture(scope="session")
def assistant(kb, citizens) -> Assistant:
    return Assistant(kb, citizens)
