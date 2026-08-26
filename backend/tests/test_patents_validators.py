from datetime import date



import pytest



from app.patents.schemas import (

    PatentInternationalInput,

    PatentPriorityInput,

    PatentProjectCreate,

)

from app.patents.validators import (

    ApplicationDetermination,

    parse_in_application_number,

    validate_create_project_filing_windows,

    validate_divisional_parent_application,

    validate_in_application_date_for_draft,

    validate_in_within_months_of_anchor,

    validate_pct_international_number,

    validate_priority_date_within_window,

)





def test_parse_in_application_number_extracts_jurisdiction_and_type():

    parsed = parse_in_application_number("202412123456")

    assert parsed == ApplicationDetermination(

        raw_number="202412123456",

        filing_year=2024,

        jurisdiction_code="1",

        jurisdiction_name="Delhi",

        type_code="2",

        type_name="Ordinary Divisional",

        serial_number="123456",

        bucket="1_2_3",

    )





@pytest.mark.parametrize("value", ["2024A2123456", "20241212345", "2024121234567"])

def test_parse_in_application_number_rejects_invalid_format(value: str):

    with pytest.raises(ValueError):

        parse_in_application_number(value)





def test_validate_pct_number_accepts_expected_shape():

    validate_pct_international_number("PCT/US2024/123456")





def test_validate_pct_number_rejects_invalid_shape():

    with pytest.raises(ValueError):

        validate_pct_international_number("PCT/USA2024/12345")





def test_validate_priority_window_rejects_beyond_twelve_calendar_months():

    in_date = date(2026, 6, 1)

    with pytest.raises(ValueError, match="IN application date must be within 12 months"):

        validate_priority_date_within_window(date(2025, 4, 30), in_date)





def test_validate_in_within_months_accepts_twelfth_calendar_month():

    validate_in_within_months_of_anchor(

        in_application_date=date(2026, 4, 30),

        anchor_date=date(2025, 4, 30),

        months=12,

        anchor_label="priority application date",

    )





def test_convention_create_requires_priority_rows():

    with pytest.raises(ValueError, match="conventional priority"):

        validate_create_project_filing_windows(

            PatentProjectCreate(

                project_mode="final",

                application_type="Convention",

                docket_no="C-1",

                in_application_date=date(2026, 6, 1),

                applicant_name="Test",

                priorities=[],

            )

        )





def test_convention_create_validates_twelve_month_window():

    validate_create_project_filing_windows(

        PatentProjectCreate(

            project_mode="final",

            application_type="Convention",

            docket_no="C-2",

            in_application_date=date(2026, 6, 1),

            applicant_name="Test",

            priorities=[

                PatentPriorityInput(

                    priority_application_no="US123",

                    priority_application_date=date(2025, 8, 1),

                    country="US",

                    title="Priority",

                )

            ],

        )

    )





def test_pct_wipo_off_requires_convention_and_intl_rows():

    with pytest.raises(ValueError, match="conventional priority"):

        validate_create_project_filing_windows(

            PatentProjectCreate(

                project_mode="final",

                application_type="PCT National Phase Entry",

                docket_no="P-1",

                in_application_date=date(2026, 6, 1),

                applicant_name="Test",

                pct_wipo_filed_only=False,

                priorities=[],

                international_applications=[

                    PatentInternationalInput(

                        international_application_no="PCT/US2024/123456",

                        international_application_date=date(2025, 1, 1),

                    )

                ],

            )

        )





def test_pct_wipo_off_validates_in_against_intl_not_priority():

    validate_create_project_filing_windows(

        PatentProjectCreate(

            project_mode="final",

            application_type="PCT National Phase Entry",

            docket_no="P-2",

            in_application_date=date(2026, 2, 1),

            applicant_name="Test",

            pct_wipo_filed_only=False,

            priorities=[

                PatentPriorityInput(

                    priority_application_no="US123",

                    priority_application_date=date(2020, 1, 1),

                    country="US",

                    title="Old priority",

                )

            ],

            international_applications=[

                PatentInternationalInput(

                    international_application_no="PCT/US2024/123456",

                    international_application_date=date(2025, 8, 1),

                )

            ],

        )

    )





def test_pct_wipo_on_rejects_convention_priorities():

    with pytest.raises(ValueError, match="WIPO"):

        validate_create_project_filing_windows(

            PatentProjectCreate(

                project_mode="final",

                application_type="PCT National Phase Entry",

                docket_no="P-3",

                in_application_date=date(2026, 6, 1),

                applicant_name="Test",

                pct_wipo_filed_only=True,

                priorities=[

                    PatentPriorityInput(

                        priority_application_no="US123",

                        priority_application_date=date(2025, 8, 1),

                        country="US",

                        title="Priority",

                    )

                ],

                international_applications=[

                    PatentInternationalInput(

                        international_application_no="PCT/US2024/123456",

                        international_application_date=date(2025, 8, 1),

                    )

                ],

            )

        )





def test_pct_wipo_on_validates_in_against_intl_only():

    validate_create_project_filing_windows(

        PatentProjectCreate(

            project_mode="final",

            application_type="PCT National Phase Entry",

            docket_no="P-4",

            in_application_date=date(2026, 6, 1),

            applicant_name="Test",

            pct_wipo_filed_only=True,

            priorities=[],

            international_applications=[

                PatentInternationalInput(

                    international_application_no="PCT/US2024/123456",

                    international_application_date=date(2025, 8, 1),

                )

            ],

        )

    )





def test_pct_rejects_in_beyond_thirty_one_calendar_months():

    with pytest.raises(ValueError, match="31 months"):

        validate_create_project_filing_windows(

            PatentProjectCreate(

                project_mode="final",

                application_type="PCT National Phase Entry",

                docket_no="P-5",

                in_application_date=date(2027, 2, 1),

                applicant_name="Test",

                pct_wipo_filed_only=True,

                international_applications=[

                    PatentInternationalInput(

                        international_application_no="PCT/US2024/123456",

                        international_application_date=date(2024, 6, 1),

                    )

                ],

            )

        )





def test_draft_skips_filing_window_validation():

    validate_create_project_filing_windows(

        PatentProjectCreate(

            project_mode="draft",

            application_type="Convention",

            docket_no="D-1",

            applicant_name="Test",

            priorities=[],

        )

    )





def test_validate_in_application_date_draft_requires_current_date():

    with pytest.raises(ValueError):

        validate_in_application_date_for_draft(

            in_application_date=date(2026, 5, 1),

            current_date=date(2026, 5, 2),

        )


@pytest.mark.parametrize(
    "application_type",
    ["Ordinary Divisional", "Convention divisional", "PCT National Phase Entry - Divisional"],
)
def test_divisional_types_skip_filing_window_and_priority_requirement(application_type: str):
    # No priority rows, no international rows, IN date far outside any window -
    # would raise for non-divisional Convention/PCT types, but must pass here.
    validate_create_project_filing_windows(
        PatentProjectCreate(
            project_mode="final",
            application_type=application_type,
            docket_no="DIV-1",
            in_application_date=date(2026, 6, 1),
            applicant_name="Test",
            priorities=[],
            international_applications=[],
        )
    )


def test_non_divisional_types_still_enforce_filing_window():
    with pytest.raises(ValueError, match="conventional priority"):
        validate_create_project_filing_windows(
            PatentProjectCreate(
                project_mode="final",
                application_type="Convention",
                docket_no="NONDIV-1",
                in_application_date=date(2026, 6, 1),
                applicant_name="Test",
                priorities=[],
            )
        )


@pytest.mark.parametrize(
    "application_type",
    ["Ordinary Divisional", "Convention divisional", "PCT National Phase Entry - Divisional"],
)
def test_divisional_final_docket_requires_parent_application_data(application_type: str):
    with pytest.raises(ValueError, match="Parent application"):
        validate_divisional_parent_application(
            PatentProjectCreate(
                project_mode="final",
                application_type=application_type,
                docket_no="DIV-2",
                applicant_name="Test",
                parent_application_no=None,
                parent_application_date=None,
            )
        )


def test_divisional_final_docket_accepts_when_parent_application_data_present():
    validate_divisional_parent_application(
        PatentProjectCreate(
            project_mode="final",
            application_type="Ordinary Divisional",
            docket_no="DIV-3",
            applicant_name="Test",
            parent_application_no="202312000001",
            parent_application_date=date(2023, 1, 1),
        )
    )


def test_divisional_draft_docket_does_not_require_parent_application_data():
    validate_divisional_parent_application(
        PatentProjectCreate(
            project_mode="draft",
            application_type="Ordinary Divisional",
            docket_no="DIV-4",
            applicant_name="Test",
        )
    )


def test_non_divisional_final_docket_not_subject_to_parent_application_requirement():
    validate_divisional_parent_application(
        PatentProjectCreate(
            project_mode="final",
            application_type="Convention",
            docket_no="NONDIV-2",
            applicant_name="Test",
        )
    )


