"""Extension checks E1 to E12: resource-specific duration and cancellation notice.

Seeded policies: Meeting room (id 5) allows 2 hours per occurrence and needs
24 hours notice to cancel; Projector (id 6) allows 8 hours and needs 1 hour.
The original resources (ids 1 to 4) keep the core rules: 8 hours, no extra
notice. Time moves only by rebuilding the app on the same SQLite file with a
later fixed clock. Rejections compare the full stored state before and after.
"""

import sqlite3
from collections.abc import Callable, Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from booking.database import initialize, make_engine
from booking.main import create_app
from booking.models import Resource

NOW = datetime(2030, 1, 15, 9)  # Tuesday
ALEX = {"X-User-ID": "1"}
SAM = {"X-User-ID": "2"}
MEETING_ROOM = 5
PROJECTOR = 6

Client = Callable[[datetime], TestClient]


@pytest.fixture
def database(tmp_path: Path) -> Path:
    path = tmp_path / "booking.sqlite3"
    initialize(path)
    return path


@pytest.fixture
def client_at(database: Path) -> Iterator[Client]:
    clients: list[TestClient] = []

    def open_client(now: datetime) -> TestClient:
        client = TestClient(create_app(database, clock=lambda: now))
        client.__enter__()
        clients.append(client)
        return client

    yield open_client
    for client in clients:
        client.__exit__(None, None, None)


def stored_state(database: Path) -> dict[str, list[tuple[Any, ...]]]:
    connection = sqlite3.connect(database)
    try:
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
            )
        ]
        return {
            table: sorted(
                connection.execute(f'SELECT * FROM "{table}"').fetchall(), key=repr
            )
            for table in tables
        }
    finally:
        connection.close()


def book(client: TestClient, resource_id: int, start: str, end: str) -> dict[str, Any]:
    response = client.post(
        "/bookings",
        headers=ALEX,
        json={"resource_id": resource_id, "start": start, "end": end},
    )
    assert response.status_code == 201, response.json()
    booking: dict[str, Any] = response.json()
    return booking


def create_series(
    client: TestClient, resource_id: int, start: str, end: str, count: int
) -> dict[str, Any]:
    response = client.post(
        "/series",
        headers=ALEX,
        json={"resource_id": resource_id, "start": start, "end": end, "count": count},
    )
    assert response.status_code == 201, response.json()
    series: dict[str, Any] = response.json()
    return series


def flags(series: dict[str, Any]) -> list[bool]:
    return [o["cancelled"] for o in series["occurrences"]]


# E1: Meeting room allows exactly 2 hours per booking, not a second more.
def test_meeting_room_duration_boundary(client_at: Client, database: Path) -> None:
    client = client_at(NOW)
    book(client, MEETING_ROOM, "2030-01-16T10:00:00", "2030-01-16T12:00:00")
    before = stored_state(database)
    response = client.post(
        "/bookings",
        headers=ALEX,
        json={
            "resource_id": MEETING_ROOM,
            "start": "2030-01-17T10:00:00",
            "end": "2030-01-17T12:00:01",
        },
    )
    assert response.status_code == 422
    assert response.json() == {"detail": "Duration must be at most two hours"}
    assert stored_state(database) == before


# E2: The per-resource limit applies to every week of a series; all-or-nothing.
def test_meeting_room_series_over_limit_saves_nothing(
    client_at: Client, database: Path
) -> None:
    client = client_at(NOW)
    before = stored_state(database)
    response = client.post(
        "/series",
        headers=ALEX,
        json={
            "resource_id": MEETING_ROOM,
            "start": "2030-01-16T10:00:00",
            "end": "2030-01-16T12:00:01",
            "count": 3,
        },
    )
    assert response.status_code == 422
    assert stored_state(database) == before
    series = create_series(
        client, MEETING_ROOM, "2030-01-16T10:00:00", "2030-01-16T12:00:00", 3
    )
    assert len(series["occurrences"]) == 3


# E3: Projector allows exactly 8 hours, overnight included.
def test_projector_duration_boundary(client_at: Client) -> None:
    client = client_at(NOW)
    book(client, PROJECTOR, "2030-01-16T22:00:00", "2030-01-17T06:00:00")
    response = client.post(
        "/bookings",
        headers=ALEX,
        json={
            "resource_id": PROJECTOR,
            "start": "2030-01-18T22:00:00",
            "end": "2030-01-19T06:00:01",
        },
    )
    assert response.status_code == 422
    assert response.json() == {"detail": "Duration must be at most eight hours"}


# E4: Original resources keep the core 8-hour rule and its message.
@pytest.mark.parametrize("resource_id", [1, 2, 3, 4])
def test_original_resources_keep_core_duration(
    client_at: Client, resource_id: int
) -> None:
    client = client_at(NOW)
    book(client, resource_id, "2030-01-16T09:00:00", "2030-01-16T17:00:00")
    response = client.post(
        "/bookings",
        headers=ALEX,
        json={
            "resource_id": resource_id,
            "start": "2030-01-17T09:00:00",
            "end": "2030-01-17T17:00:01",
        },
    )
    assert response.status_code == 422
    assert response.json() == {"detail": "Duration must be at most eight hours"}


# E5: Meeting room cancellation at exactly 24 hours notice works; a second
# less is refused and the booking stays active.
def test_meeting_room_cancel_at_notice_boundary(client_at: Client) -> None:
    booking = book(
        client_at(NOW), MEETING_ROOM, "2030-01-17T10:00:00", "2030-01-17T11:00:00"
    )
    too_late = client_at(datetime(2030, 1, 16, 10, 0, 1))
    refused = too_late.post(f"/bookings/{booking['id']}/cancel", headers=ALEX)
    assert refused.status_code == 409
    assert refused.json() == {
        "detail": (
            "Cancellation needs at least twenty-four hours notice for this resource"
        )
    }
    assert too_late.get(f"/bookings/{booking['id']}").json()["cancelled"] is False

    exactly = client_at(datetime(2030, 1, 16, 10))
    allowed = exactly.post(f"/bookings/{booking['id']}/cancel", headers=ALEX)
    assert allowed.status_code == 200
    assert allowed.json()["cancelled"] is True


# E6: Projector needs 1 hour notice, boundary inclusive.
def test_projector_cancel_at_notice_boundary(client_at: Client) -> None:
    first = book(
        client_at(NOW), PROJECTOR, "2030-01-16T12:00:00", "2030-01-16T13:00:00"
    )
    second = book(
        client_at(NOW), PROJECTOR, "2030-01-17T12:00:00", "2030-01-17T13:00:00"
    )
    late = client_at(datetime(2030, 1, 16, 11, 0, 1))
    assert late.post(f"/bookings/{first['id']}/cancel", headers=ALEX).status_code == (
        409
    )
    exactly = client_at(datetime(2030, 1, 17, 11))
    response = exactly.post(f"/bookings/{second['id']}/cancel", headers=ALEX)
    assert response.status_code == 200


# E7 and E8: the requirements' example. A Meeting room series has two dates
# left: the next is 12 hours away, the other next week. Cancelling the series
# changes nothing; the later date can still be cancelled on its own.
def test_series_cancel_refused_if_any_week_lacks_notice(
    client_at: Client, database: Path
) -> None:
    series = create_series(
        client_at(NOW), MEETING_ROOM, "2030-01-16T10:00:00", "2030-01-16T11:00:00", 3
    )
    later = client_at(datetime(2030, 1, 22, 22))  # week 1 past, week 2 in 12h
    before = stored_state(database)
    refused = later.post(f"/series/{series['id']}/cancel", headers=ALEX)
    assert refused.status_code == 409
    assert stored_state(database) == before
    assert flags(later.get(f"/series/{series['id']}").json()) == [False] * 3

    third = series["occurrences"][2]
    single = later.post(f"/bookings/{third['id']}/cancel", headers=ALEX)
    assert single.status_code == 200
    assert flags(later.get(f"/series/{series['id']}").json()) == [False, False, True]


# E9: With enough notice for every affected week, all of them are cancelled;
# past and ongoing weeks are preserved.
def test_series_cancel_with_enough_notice(client_at: Client) -> None:
    series = create_series(
        client_at(NOW), PROJECTOR, "2030-01-15T10:00:00", "2030-01-15T11:00:00", 4
    )
    later = client_at(datetime(2030, 1, 22, 10, 30))  # week 1 past, week 2 ongoing
    response = later.post(f"/series/{series['id']}/cancel", headers=ALEX)
    assert response.status_code == 200
    assert flags(response.json()) == [False, False, True, True]


def test_meeting_room_series_cancel_with_enough_notice(client_at: Client) -> None:
    series = create_series(
        client_at(NOW), MEETING_ROOM, "2030-01-16T10:00:00", "2030-01-16T11:00:00", 3
    )
    response = client_at(NOW).post(f"/series/{series['id']}/cancel", headers=ALEX)
    assert response.status_code == 200
    assert flags(response.json()) == [True, True, True]


# E10: Repeating a successful cancellation is harmless, even once notice would
# no longer be met.
def test_repeat_cancellations_stay_harmless(client_at: Client) -> None:
    client = client_at(NOW)
    series = create_series(
        client, MEETING_ROOM, "2030-01-16T10:00:00", "2030-01-16T11:00:00", 2
    )
    single = book(client, MEETING_ROOM, "2030-01-17T14:00:00", "2030-01-17T15:00:00")
    first = client.post(f"/series/{series['id']}/cancel", headers=ALEX)
    assert first.status_code == 200
    assert client.post(
        f"/bookings/{single['id']}/cancel", headers=ALEX
    ).status_code == (200)

    late = client_at(datetime(2030, 1, 16, 9, 30))
    repeat = late.post(f"/series/{series['id']}/cancel", headers=ALEX)
    assert repeat.status_code == 200
    assert repeat.json() == first.json()
    single_repeat = late.post(f"/bookings/{single['id']}/cancel", headers=ALEX)
    assert single_repeat.status_code == 200
    assert single_repeat.json()["cancelled"] is True


# E11: Core cancellation rules still come first: ownership (403), then
# "already started" (409), before the notice rule.
def test_core_cancel_checks_run_before_notice(client_at: Client) -> None:
    booking = book(
        client_at(NOW), MEETING_ROOM, "2030-01-16T10:00:00", "2030-01-16T11:00:00"
    )
    late = client_at(datetime(2030, 1, 16, 9))
    assert late.post(f"/bookings/{booking['id']}/cancel", headers=SAM).status_code == (
        403
    )
    started = client_at(datetime(2030, 1, 16, 10))
    response = started.post(f"/bookings/{booking['id']}/cancel", headers=ALEX)
    assert response.status_code == 409
    assert response.json() == {"detail": "Booking has already started"}


def test_original_resources_cancel_until_start(client_at: Client) -> None:
    booking = book(client_at(NOW), 1, "2030-01-16T10:00:00", "2030-01-16T11:00:00")
    just_before = client_at(datetime(2030, 1, 16, 9, 59, 59))
    response = just_before.post(f"/bookings/{booking['id']}/cancel", headers=ALEX)
    assert response.status_code == 200


# E12: Seed data stores the policies; GET /resources keeps its core shape.
def test_seeded_policies(database: Path, client_at: Client) -> None:
    initialize(database)  # repeat init must not change anything
    engine = make_engine(database)
    try:
        with Session(engine) as session:
            policies = {
                r.id: (r.name, r.max_duration_minutes, r.min_cancel_notice_minutes)
                for r in [session.get(Resource, i) for i in range(1, 7)]
                if r is not None
            }
    finally:
        engine.dispose()
    assert policies == {
        1: ("Study room A", 480, 0),
        2: ("Study room B", 480, 0),
        3: ("Camera 01", 480, 0),
        4: ("Camera 02", 480, 0),
        5: ("Meeting room", 120, 1440),
        6: ("Projector", 480, 60),
    }
    resources = client_at(NOW).get("/resources").json()
    assert all(set(r) == {"id", "name", "kind"} for r in resources)
