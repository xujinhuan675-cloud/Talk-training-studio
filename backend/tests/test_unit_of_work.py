from __future__ import annotations

import pytest

from infrastructure.unit_of_work import SQLAlchemyUnitOfWork


class FakeTransaction:
    def __init__(self) -> None:
        self.is_active = True
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1
        self.is_active = False


class FakeSession:
    def __init__(self) -> None:
        self.transaction = FakeTransaction()
        self.begin_calls = 0
        self.commit_calls = 0
        self.rollback_calls = 0
        self.close_calls = 0

    async def begin(self) -> FakeTransaction:
        self.begin_calls += 1
        self.transaction.is_active = True
        return self.transaction

    def in_transaction(self) -> bool:
        return self.transaction.is_active

    async def commit(self) -> None:
        self.commit_calls += 1
        self.transaction.is_active = False

    async def rollback(self) -> None:
        self.rollback_calls += 1
        self.transaction.is_active = False

    async def close(self) -> None:
        self.close_calls += 1


def session_factory_for(session: FakeSession):
    def _factory() -> FakeSession:
        return session

    return _factory


@pytest.mark.asyncio
async def test_unit_of_work_registers_repositories_and_auto_commits() -> None:
    session = FakeSession()
    uow = SQLAlchemyUnitOfWork(session_factory=session_factory_for(session))

    async with uow as active:
        assert active is uow
        assert session.begin_calls == 1
        assert uow.file_asset_repository is uow.get_repository("file_asset_repository")
        assert uow.chat_room_repository is uow.get_repository("chat_room_repository")
        assert uow.training_session_repository is uow.get_repository(
            "training_session_repository"
        )

    assert session.commit_calls == 1
    assert session.rollback_calls == 0
    assert session.close_calls == 1
    assert uow.session is None
    assert uow.file_asset_repository is None
    assert uow.get_repository("file_asset_repository") is None


@pytest.mark.asyncio
async def test_unit_of_work_rolls_back_and_cleans_up_on_exception() -> None:
    session = FakeSession()
    uow = SQLAlchemyUnitOfWork(session_factory=session_factory_for(session))

    with pytest.raises(RuntimeError, match="boom"):
        async with uow:
            raise RuntimeError("boom")

    assert session.commit_calls == 0
    assert session.rollback_calls == 1
    assert session.close_calls == 1
    assert uow.session is None
    assert uow.get_repository("chat_room_repository") is None


@pytest.mark.asyncio
async def test_unit_of_work_readonly_does_not_begin_or_commit_transaction() -> None:
    session = FakeSession()
    uow = SQLAlchemyUnitOfWork(
        session_factory=session_factory_for(session),
        readonly=True,
    )

    async with uow:
        assert session.begin_calls == 0
        assert uow.stakeholder_persona_repository is uow.get_repository(
            "stakeholder_persona_repository"
        )

    assert session.commit_calls == 0
    assert session.rollback_calls == 0
    assert session.close_calls == 1
    assert uow.get_repository("stakeholder_persona_repository") is None


@pytest.mark.asyncio
async def test_unit_of_work_keeps_external_session_open_after_cleanup() -> None:
    session = FakeSession()
    uow = SQLAlchemyUnitOfWork(session=session)

    async with uow:
        assert uow.session is session
        assert session.begin_calls == 1

    assert session.commit_calls == 1
    assert session.close_calls == 0
    assert uow.session is session
    assert uow.defense_session_repository is None
    assert uow.get_repository("defense_session_repository") is None


@pytest.mark.asyncio
async def test_explicit_commit_prevents_second_auto_commit() -> None:
    session = FakeSession()
    uow = SQLAlchemyUnitOfWork(session_factory=session_factory_for(session))

    async with uow:
        await uow.commit()

    assert session.commit_calls == 1
    assert session.rollback_calls == 0
    assert session.close_calls == 1
