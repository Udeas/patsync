from __future__ import annotations



import calendar

from datetime import date

from typing import Mapping, Sequence



from .patent_status_catalog import (

    ALL_STATUS_IDS,

    STATUS_ID_ABANDONED,

    STATUS_ID_APPLICATION_FILED,

    STATUS_ID_FER_ISSUED,

    STATUS_ID_FER_RESPONSE_SUBMITTED,

    STATUS_ID_GRANTED,

    STATUS_ID_HEARING,

    STATUS_ID_NON_PROVISIONAL_APPLICATION,

    STATUS_ID_PUBLICATION,

    STATUS_ID_REFUSED,

    STATUS_ID_REQUEST_FOR_EXAMINATION,

    TERMINAL_STATUS_IDS,

    status_label,

)



# Re-export catalog constants for existing imports

STATUS_ID_FIRST_EXAMINATION_REPORT = STATUS_ID_FER_RESPONSE_SUBMITTED

STATUS_ID_UNDER_HEARING = STATUS_ID_HEARING



CURRENT_STATUS_PRECEDENCE: list[int] = [

    STATUS_ID_GRANTED,

    STATUS_ID_REFUSED,

    STATUS_ID_ABANDONED,

    STATUS_ID_HEARING,

    STATUS_ID_FER_RESPONSE_SUBMITTED,

    STATUS_ID_FER_ISSUED,

    STATUS_ID_REQUEST_FOR_EXAMINATION,

    STATUS_ID_PUBLICATION,

    STATUS_ID_NON_PROVISIONAL_APPLICATION,

    STATUS_ID_APPLICATION_FILED,

]



# Chronological ordering for milestones in this list (optional ms excluded).

_SEQUENCE_ORDER = [

    STATUS_ID_APPLICATION_FILED,

    STATUS_ID_NON_PROVISIONAL_APPLICATION,

    STATUS_ID_FER_ISSUED,

    STATUS_ID_FER_RESPONSE_SUBMITTED,

    STATUS_ID_HEARING,

    STATUS_ID_REFUSED,

    STATUS_ID_GRANTED,

]





def _add_months(value: date, months: int) -> date:

    month = value.month + months

    year = value.year + (month - 1) // 12

    month = (month - 1) % 12 + 1

    day = min(value.day, calendar.monthrange(year, month)[1])

    return date(year, month, day)


def compute_rfe_deadline(
    in_application_date: date,
    priority_dates: Sequence[date] = (),
) -> date:
    anchor = in_application_date
    if priority_dates:
        anchor = min(in_application_date, min(priority_dates))
    return _add_months(anchor, 31)


def _validate_request_for_examination(

    rfe_date: date,

    in_application_date: date,

    priority_dates: Sequence[date],

) -> None:

    if rfe_date < in_application_date:

        raise ValueError("Request for Examination date must be on or after IN application filing date")



    deadline = compute_rfe_deadline(in_application_date, priority_dates)

    if rfe_date > deadline:

        raise ValueError(

            "Request for Examination date must be within 31 months of the earlier of "

            "convention filing date or IN application filing date"

        )





def derive_current_status(filled: Mapping[int, date]) -> tuple[int, date] | None:

    """Highest workflow stage among filled milestones (not latest calendar date)."""

    for status_id in CURRENT_STATUS_PRECEDENCE:

        if status_id in filled:

            return status_id, filled[status_id]

    return None





def enabled_status_ids(filled: Mapping[int, date], requires_non_provisional: bool) -> set[int]:

    enabled = set(filled.keys())



    if not filled:

        return {STATUS_ID_APPLICATION_FILED}



    if STATUS_ID_ABANDONED in filled:

        return enabled



    if any(status_id in TERMINAL_STATUS_IDS for status_id in filled):

        return enabled



    enabled.add(STATUS_ID_ABANDONED)



    if STATUS_ID_APPLICATION_FILED not in filled:

        enabled.add(STATUS_ID_APPLICATION_FILED)

        return enabled



    if requires_non_provisional and STATUS_ID_NON_PROVISIONAL_APPLICATION not in filled:

        enabled.add(STATUS_ID_NON_PROVISIONAL_APPLICATION)

        return enabled



    enabled.update(

        {

            STATUS_ID_PUBLICATION,

            STATUS_ID_REQUEST_FOR_EXAMINATION,

            STATUS_ID_REFUSED,

            STATUS_ID_GRANTED,

        }

    )



    if STATUS_ID_REQUEST_FOR_EXAMINATION not in filled:

        return enabled



    enabled.add(STATUS_ID_FER_ISSUED)

    if STATUS_ID_FER_ISSUED not in filled:

        return enabled



    enabled.add(STATUS_ID_FER_RESPONSE_SUBMITTED)

    if STATUS_ID_FER_RESPONSE_SUBMITTED not in filled:

        return enabled



    enabled.add(STATUS_ID_HEARING)

    return enabled





def validate_timeline_updates(

    updates: Sequence[tuple[int, date]],

    requires_non_provisional: bool,

    in_application_date: date | None = None,

    priority_dates: Sequence[date] | None = None,

) -> None:

    filled: dict[int, date] = {}

    for status_id, status_date in updates:

        if status_id not in ALL_STATUS_IDS:

            raise ValueError(f"Invalid status id: {status_id}")

        filled[status_id] = status_date



    if not filled:

        return



    if STATUS_ID_APPLICATION_FILED not in filled:

        raise ValueError("Application Filed must be set first")



    if STATUS_ID_ABANDONED in filled:

        if len(filled) > 1 and STATUS_ID_APPLICATION_FILED not in filled:

            raise ValueError("Abandoned requires Application Filed")

        return



    if requires_non_provisional and STATUS_ID_NON_PROVISIONAL_APPLICATION not in filled:

        later = [

            sid

            for sid in filled

            if sid

            not in (

                STATUS_ID_APPLICATION_FILED,

                STATUS_ID_NON_PROVISIONAL_APPLICATION,

            )

        ]

        if later:

            raise ValueError("Non-Provisional application must be set before later milestones")



    if STATUS_ID_PUBLICATION in filled:

        if requires_non_provisional and STATUS_ID_NON_PROVISIONAL_APPLICATION not in filled:

            raise ValueError("Publication requires Non-Provisional application first")

        if not requires_non_provisional and STATUS_ID_APPLICATION_FILED not in filled:

            raise ValueError("Publication requires Application Filed first")



    filing_date = in_application_date or filled.get(STATUS_ID_APPLICATION_FILED)

    if STATUS_ID_REQUEST_FOR_EXAMINATION in filled:

        if not filing_date:

            raise ValueError("IN application filing date is required before Request for Examination")

        _validate_request_for_examination(

            filled[STATUS_ID_REQUEST_FOR_EXAMINATION],

            filing_date,

            priority_dates or (),

        )



    if STATUS_ID_FER_ISSUED in filled and STATUS_ID_REQUEST_FOR_EXAMINATION not in filled:

        raise ValueError("FER Issued requires Request for Examination date")

    if STATUS_ID_REQUEST_FOR_EXAMINATION in filled and STATUS_ID_FER_ISSUED in filled:
        if filled[STATUS_ID_REQUEST_FOR_EXAMINATION] > filled[STATUS_ID_FER_ISSUED]:
            raise ValueError(
                "Request for Examination date must be on or before FER Issued date"
            )

    order = list(_SEQUENCE_ORDER)

    if not requires_non_provisional:

        order = [sid for sid in order if sid != STATUS_ID_NON_PROVISIONAL_APPLICATION]



    present = [sid for sid in order if sid in filled]

    for idx, status_id in enumerate(present):

        if idx == 0:

            continue

        prev = present[idx - 1]

        if filled[status_id] < filled[prev]:

            raise ValueError(

                f"{status_label(status_id)} date must be on or after {status_label(prev)}"

            )



    if STATUS_ID_FER_RESPONSE_SUBMITTED in filled and STATUS_ID_FER_ISSUED not in filled:

        raise ValueError("FER Response submitted requires FER Issued date")



    if STATUS_ID_HEARING in filled and STATUS_ID_FER_RESPONSE_SUBMITTED not in filled:

        raise ValueError("Hearing requires FER Response submitted date")



    terminals = {STATUS_ID_REFUSED, STATUS_ID_GRANTED}

    if len(terminals.intersection(filled.keys())) > 1:

        raise ValueError("Granted and Refused cannot both be set")


