from datetime import date



import pytest



from app.patents.patent_status_catalog import (

    STATUS_ID_ABANDONED,

    STATUS_ID_APPLICATION_FILED,

    STATUS_ID_FER_ISSUED,

    STATUS_ID_FER_RESPONSE_SUBMITTED,

    STATUS_ID_GRANTED,

    STATUS_ID_NON_PROVISIONAL_APPLICATION,

    STATUS_ID_PUBLICATION,

    STATUS_ID_REFUSED,

    STATUS_ID_REQUEST_FOR_EXAMINATION,

)

from app.patents.workflow import (

    derive_current_status,

    enabled_status_ids,

    validate_timeline_updates,

)





def test_op_requires_non_provisional_step():

    filled = {STATUS_ID_APPLICATION_FILED: date(2026, 1, 1)}

    enabled = enabled_status_ids(filled, requires_non_provisional=True)

    assert STATUS_ID_NON_PROVISIONAL_APPLICATION in enabled

    assert STATUS_ID_FER_ISSUED not in enabled





def test_op_blocks_fer_until_non_prov():

    filled = {STATUS_ID_APPLICATION_FILED: date(2026, 1, 1)}

    enabled = enabled_status_ids(filled, requires_non_provisional=True)

    assert STATUS_ID_GRANTED not in enabled

    assert STATUS_ID_PUBLICATION not in enabled





def test_onp_skips_non_provisional_step():

    filled = {STATUS_ID_APPLICATION_FILED: date(2026, 1, 1)}

    enabled = enabled_status_ids(filled, requires_non_provisional=False)

    assert STATUS_ID_NON_PROVISIONAL_APPLICATION not in enabled

    assert STATUS_ID_PUBLICATION in enabled

    assert STATUS_ID_GRANTED in enabled





def test_cannot_set_fer_response_before_fer():

    with pytest.raises(ValueError):

        validate_timeline_updates(

            [

                (STATUS_ID_APPLICATION_FILED, date(2026, 1, 1)),

                (STATUS_ID_FER_RESPONSE_SUBMITTED, date(2026, 2, 1)),

            ],

            requires_non_provisional=False,

        )





def test_fer_requires_rfe():

    with pytest.raises(ValueError, match="Request for Examination"):

        validate_timeline_updates(

            [

                (STATUS_ID_APPLICATION_FILED, date(2026, 1, 1)),

                (STATUS_ID_FER_ISSUED, date(2026, 2, 1)),

            ],

            requires_non_provisional=False,

        )


def test_rfe_must_be_on_or_before_fer_issued():
    with pytest.raises(ValueError, match="FER Issued"):
        validate_timeline_updates(
            [
                (STATUS_ID_APPLICATION_FILED, date(2026, 5, 29)),
                (STATUS_ID_FER_ISSUED, date(2026, 8, 4)),
                (STATUS_ID_REQUEST_FOR_EXAMINATION, date(2026, 8, 11)),
            ],
            requires_non_provisional=False,
            in_application_date=date(2026, 5, 29),
        )


def test_rfe_before_fer_issued_is_valid():
    validate_timeline_updates(
        [
            (STATUS_ID_APPLICATION_FILED, date(2026, 5, 29)),
            (STATUS_ID_REQUEST_FOR_EXAMINATION, date(2026, 6, 1)),
            (STATUS_ID_FER_ISSUED, date(2026, 8, 4)),
        ],
        requires_non_provisional=False,
        in_application_date=date(2026, 5, 29),
    )


def test_granted_without_examination_path_ok():

    validate_timeline_updates(

        [

            (STATUS_ID_APPLICATION_FILED, date(2026, 1, 1)),

            (STATUS_ID_GRANTED, date(2026, 3, 1)),

        ],

        requires_non_provisional=False,

    )





def test_refused_without_fer_ok():

    validate_timeline_updates(

        [

            (STATUS_ID_APPLICATION_FILED, date(2026, 1, 1)),

            (STATUS_ID_REFUSED, date(2026, 3, 1)),

        ],

        requires_non_provisional=False,

    )





def test_nominal_path_is_valid():

    validate_timeline_updates(

        [

            (STATUS_ID_APPLICATION_FILED, date(2026, 1, 1)),

            (STATUS_ID_REQUEST_FOR_EXAMINATION, date(2026, 1, 15)),

            (STATUS_ID_PUBLICATION, date(2026, 2, 1)),

            (STATUS_ID_FER_ISSUED, date(2026, 3, 1)),

            (STATUS_ID_FER_RESPONSE_SUBMITTED, date(2026, 4, 1)),

            (STATUS_ID_GRANTED, date(2026, 5, 1)),

        ],

        requires_non_provisional=False,

        in_application_date=date(2026, 1, 1),

    )





def test_abandoned_after_filed_ok():

    validate_timeline_updates(

        [

            (STATUS_ID_APPLICATION_FILED, date(2026, 1, 1)),

            (STATUS_ID_ABANDONED, date(2026, 2, 1)),

        ],

        requires_non_provisional=False,

    )





def test_rfe_can_be_before_publication():

    validate_timeline_updates(

        [

            (STATUS_ID_APPLICATION_FILED, date(2026, 1, 1)),

            (STATUS_ID_REQUEST_FOR_EXAMINATION, date(2026, 2, 1)),

            (STATUS_ID_PUBLICATION, date(2026, 6, 1)),

        ],

        requires_non_provisional=False,

        in_application_date=date(2026, 1, 1),

    )





def test_rfe_must_be_on_or_after_in_filing():

    with pytest.raises(ValueError, match="IN application filing date"):

        validate_timeline_updates(

            [

                (STATUS_ID_APPLICATION_FILED, date(2026, 1, 1)),

                (STATUS_ID_REQUEST_FOR_EXAMINATION, date(2025, 12, 1)),

            ],

            requires_non_provisional=False,

            in_application_date=date(2026, 1, 1),

        )





def test_rfe_within_31_months_of_earlier_convention_or_in():

    validate_timeline_updates(

        [

            (STATUS_ID_APPLICATION_FILED, date(2026, 1, 1)),

            (STATUS_ID_REQUEST_FOR_EXAMINATION, date(2026, 12, 1)),

        ],

        requires_non_provisional=False,

        in_application_date=date(2026, 1, 1),

        priority_dates=[date(2024, 6, 1)],

    )



    with pytest.raises(ValueError, match="31 months"):

        validate_timeline_updates(

            [

                (STATUS_ID_APPLICATION_FILED, date(2026, 1, 1)),

                (STATUS_ID_REQUEST_FOR_EXAMINATION, date(2027, 2, 1)),

            ],

            requires_non_provisional=False,

            in_application_date=date(2026, 1, 1),

            priority_dates=[date(2024, 6, 1)],

        )





def test_current_status_rfe_over_publication():

    filled = {

        STATUS_ID_APPLICATION_FILED: date(2026, 1, 1),

        STATUS_ID_REQUEST_FOR_EXAMINATION: date(2026, 2, 1),

        STATUS_ID_PUBLICATION: date(2026, 6, 1),

    }

    current = derive_current_status(filled)

    assert current is not None

    assert current[0] == STATUS_ID_REQUEST_FOR_EXAMINATION

    assert current[1] == date(2026, 2, 1)


