"""Single vs multi class application consistency: tm_class <-> is_multi_class <-> tm_selected_classes."""

from datetime import date

import pytest
from pydantic import ValidationError
from sqlmodel import Session, SQLModel, create_engine

from app.models.trademark import TmStatus
from app.schemas.trademark import TmApplicationCreate, TmApplicationUpdate, TmClassDescriptionEntry
from app.services.trademark_service import create_tm_application, update_tm_application
from app.tm_status_catalog import STATUS_ID_TM_APPLICATION_FILED


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    session.add(TmStatus(id=STATUS_ID_TM_APPLICATION_FILED, status="Application filed"))
    session.commit()
    return session


def _base_kwargs(**overrides):
    kwargs = dict(
        application_number="1234567",
        application_date=date(2025, 1, 10),
        applicant_name="Client",
        applicant_type="Individual",
        tm_name="Mark",
        tm_type="Wordmark",
        tm_class="5",
        applicant_address="Address",
    )
    kwargs.update(overrides)
    return kwargs


def test_single_class_application_stores_the_chosen_class() -> None:
    with _make_session() as session:
        created = create_tm_application(session, TmApplicationCreate(**_base_kwargs(tm_class="12")))
        assert created.tm_class == "12"
        assert created.is_multi_class is False
        assert created.tm_selected_classes == []


def test_multi_class_application_stores_main_class_99_and_selected_classes() -> None:
    with _make_session() as session:
        created = create_tm_application(
            session,
            TmApplicationCreate(
                **_base_kwargs(
                    tm_class="99",
                    is_multi_class=True,
                    tm_selected_classes=["9", "35", "42"],
                )
            ),
        )
        assert created.tm_class == "99"
        assert created.is_multi_class is True
        assert created.tm_selected_classes == ["9", "35", "42"]


def test_single_class_application_rejects_class_99() -> None:
    with pytest.raises(ValidationError):
        TmApplicationCreate(**_base_kwargs(tm_class="99"))


def test_single_class_application_rejects_selected_classes_list() -> None:
    with pytest.raises(ValidationError):
        TmApplicationCreate(**_base_kwargs(tm_class="12", tm_selected_classes=["9"]))


def test_multi_class_application_requires_at_least_one_selected_class() -> None:
    with pytest.raises(ValidationError):
        TmApplicationCreate(**_base_kwargs(tm_class="99", is_multi_class=True, tm_selected_classes=[]))


def test_multi_class_application_requires_tm_class_99() -> None:
    with pytest.raises(ValidationError):
        TmApplicationCreate(
            **_base_kwargs(tm_class="12", is_multi_class=True, tm_selected_classes=["9"])
        )


def test_update_switching_to_multi_class_validates_merged_state() -> None:
    with _make_session() as session:
        created = create_tm_application(session, TmApplicationCreate(**_base_kwargs(tm_class="12")))

        with pytest.raises(ValueError, match="tm_class must be '99'"):
            update_tm_application(session, created.id, TmApplicationUpdate(is_multi_class=True))

        updated = update_tm_application(
            session,
            created.id,
            TmApplicationUpdate(is_multi_class=True, tm_class="99", tm_selected_classes=["1", "2"]),
        )
        assert updated is not None
        assert updated.tm_class == "99"
        assert updated.is_multi_class is True
        assert updated.tm_selected_classes == ["1", "2"]


def test_update_switching_back_to_single_class_requires_specific_class() -> None:
    with _make_session() as session:
        created = create_tm_application(
            session,
            TmApplicationCreate(
                **_base_kwargs(tm_class="99", is_multi_class=True, tm_selected_classes=["9"])
            ),
        )

        with pytest.raises(ValueError, match="specific class"):
            update_tm_application(session, created.id, TmApplicationUpdate(is_multi_class=False))

        updated = update_tm_application(
            session,
            created.id,
            TmApplicationUpdate(is_multi_class=False, tm_class="9", tm_selected_classes=[]),
        )
        assert updated is not None
        assert updated.tm_class == "9"
        assert updated.is_multi_class is False
        assert updated.tm_selected_classes == []


def test_single_class_application_stores_one_class_description() -> None:
    with _make_session() as session:
        created = create_tm_application(
            session,
            TmApplicationCreate(
                **_base_kwargs(
                    tm_class="12",
                    application_class_descriptions=[
                        TmClassDescriptionEntry(class_no="12", description="Vehicles and parts")
                    ],
                )
            ),
        )
        assert created.application_class_descriptions == [
            TmClassDescriptionEntry(class_no="12", description="Vehicles and parts")
        ]


def test_multi_class_application_stores_one_description_per_class() -> None:
    with _make_session() as session:
        created = create_tm_application(
            session,
            TmApplicationCreate(
                **_base_kwargs(
                    tm_class="99",
                    is_multi_class=True,
                    tm_selected_classes=["9", "35"],
                    application_class_descriptions=[
                        TmClassDescriptionEntry(class_no="9", description="Software"),
                        TmClassDescriptionEntry(class_no="35", description="Advertising"),
                    ],
                )
            ),
        )
        assert created.application_class_descriptions == [
            TmClassDescriptionEntry(class_no="9", description="Software"),
            TmClassDescriptionEntry(class_no="35", description="Advertising"),
        ]


def test_class_description_must_belong_to_a_selected_class() -> None:
    with pytest.raises(ValidationError):
        TmApplicationCreate(
            **_base_kwargs(
                tm_class="12",
                application_class_descriptions=[
                    TmClassDescriptionEntry(class_no="9", description="Wrong class")
                ],
            )
        )


def test_update_replaces_class_descriptions() -> None:
    with _make_session() as session:
        created = create_tm_application(
            session,
            TmApplicationCreate(
                **_base_kwargs(
                    tm_class="12",
                    application_class_descriptions=[
                        TmClassDescriptionEntry(class_no="12", description="Old text")
                    ],
                )
            ),
        )
        updated = update_tm_application(
            session,
            created.id,
            TmApplicationUpdate(
                application_class_descriptions=[
                    TmClassDescriptionEntry(class_no="12", description="New text")
                ]
            ),
        )
        assert updated is not None
        assert updated.application_class_descriptions == [
            TmClassDescriptionEntry(class_no="12", description="New text")
        ]
