"""Email template definitions for s3_create_email_drafts.py.

Available placeholders:
- {application_no} : USPTO application serial number from sheet
- {docket_no} : internal matter or docket identifier
- {event_date} : USPTO document issue or mailroom date
- {title} : application title text
- {filing_date} : original application filing date text
- {particulars} : spreadsheet particulars/notes for the row
- {doc_code} : normalized document code from the row
- {issue_fee_deadline} : computed NOA due date (event date + 3 months)
- {ctfr_due_date} : computed office action due date (event date + 3 months)
- {ctfr_extension_due_date} : computed extension due date (event date + 6 months)
- {ntc_miss_prt_due_date} : computed missing parts due date (event date + 2 months)
- {rip_matter_id} : reserved for future templates
- {notice_issued_on} : reserved for future templates
- {allowed_claims} : reserved for future templates
- {issue_fee_amount} : reserved for NOA fee field (currently static in template body)
- {required_response_time} : reserved for reusable response timing line
- {attachments_html} : reserved for reusable attachment list html
- {salutation} : reserved for reusable greeting line
"""

DOC_CODE_TEMPLATES = {
    "NOA": {
        "subject": "Notice of Allowance and Fees Due - App {application_no}",
        "body": (
            "<div style='font-family: Arial, sans-serif; font-size: 14px; line-height: 1.6; color: #222;'>"
            "<p style='margin: 0 0 10px 0;'><strong>Title:</strong> <br>"
            "<strong>Application No:</strong> {application_no}<br>"
            "<strong>Filing Date:</strong> <br>"
            "<strong>RIP Matter ID:</strong> {docket_no}</p>"
            "<p style='margin: 16px 0 12px 0;'>Dear Sir/Madam,</p>"
            "<p style='margin: 0 0 14px 0;'>"
            "We are pleased to inform you that the <strong>U.S. Patent and Trademark Office</strong> has issued a "
            "<strong>Notice of Allowance and Fees Due</strong> for the above-referenced application."
            "</p>"
            "<p style='margin: 0 0 8px 0;'><strong>Key Details:</strong></p>"
            "<ul style='margin: 0 0 14px 20px; padding-left: 12px;'>"
            "<li><strong>Notice Issued On:</strong> {event_date}</li>"
            "<li><strong>Issue Fee Amount:</strong> $480.00</li>"
            "<li><strong>Issue Fee Deadline:</strong> {issue_fee_deadline}</li>"
            "<li><strong>Required Response Time:</strong> Written instructions and payment method must be received at least 14 days prior to the deadline.</li>"
            "</ul>"
            "<p style='margin: 0 0 8px 0;'><strong>Attachments:</strong></p>"
            "<ul style='margin: 0 0 14px 20px; padding-left: 12px;'>"
            "<li>Notice of Allowance and Fees Due</li>"
            "<li>Copy of allowed claims</li>"
            "</ul>"
            "<p style='margin: 0 0 14px 0;'>"
            "Please confirm if you wish to proceed with payment of the issue fee and provide your payment instructions accordingly."
            "</p>"
            "<p style='margin: 0 0 14px 0;'><strong>Important:</strong><br>"
            "If we do not receive your instructions and payment method at least 14 days before the deadline, "
            "we will not be responsible for any delay or abandonment of the application."
            "</p>"
            "<p style='margin: 0 0 14px 0;'>"
            "As always, please do not hesitate to contact me should you have any questions or concerns."
            "</p>"
            "<p style='margin: 0;'>All the best,<br>Rahul Maurya<br>Patent Ventures LLC</p>"
            "</div>"
        ),
    },
    "CTFR": {
        "subject": "Final Office Action - App {application_no}",
        "body": (
            "<div style='font-family: Arial, sans-serif; font-size: 14px; line-height: 1.6; color: #222;'>"
            "<p style='margin: 0 0 16px 0;'>"
            "<strong>In re:</strong> <span style='margin-left: 8px;'>U.S. Utility Patent Application Serial No.: {application_no}</span><br>"
            "<strong>Title:</strong> <span style='margin-left: 8px;'>{title}</span><br>"
            "<strong>Filing Date:</strong> <span style='margin-left: 8px;'>{filing_date}</span><br>"
            "<strong>Your Matter ID.:</strong> <span style='margin-left: 8px;'>{docket_no}</span>"
            "</p>"
            "<p style='margin: 16px 0 12px 0;'>Dear Sir/Madam,</p>"
            "<p style='margin: 0 0 14px 0;'>"
            "Attached please find the following document issued by the U.S. Patent and Trademark Office on "
            "{event_date} for the above-captioned application:"
            "</p>"
            "<ul style='margin: 0 0 14px 20px; padding-left: 12px;'>"
            "<li><strong>FINAL OFFICE ACTION</strong></li>"
            "</ul>"
            "<p style='margin: 0 0 6px 0;'><strong>Due Date (3 months):</strong> {ctfr_due_date}</p>"
            "<p style='margin: 0 0 14px 0;'><strong>Due Date with 3 month Extension:</strong> {ctfr_extension_due_date}</p>"
            "<p style='margin: 0 0 14px 0;'>"
            "Please advise how you wish to proceed with the response before the due date."
            "</p>"
            "<p style='margin: 0 0 14px 0;'><strong>Important Note:</strong> "
            "Kindly send your instructions in a timely manner; <strong>at least 14 days before the due date.</strong> "
            "If instructions are not received well in advance, we will not be held responsible for any resulting abandonment of the application."
            "</p>"
            "<p style='margin: 0 0 14px 0;'>"
            "As always, please do not hesitate to contact us should you have any questions or concerns."
            "</p>"
            "<p style='margin: 0;'>All the best,<br>Rahul Maurya<br>Patent Ventures LLC</p>"
            "</div>"
        ),
    },
    "CTNF": {
        "subject": "Final Office Action - App {application_no}",
        "body": (
            "<div style='font-family: Arial, sans-serif; font-size: 14px; line-height: 1.6; color: #222;'>"
            "<p style='margin: 0 0 16px 0;'>"
            "<strong>In re:</strong> <span style='margin-left: 8px;'>U.S. Utility Patent Application Serial No.: {application_no}</span><br>"
            "<strong>Title:</strong> <span style='margin-left: 8px;'>{title}</span><br>"
            "<strong>Filing Date:</strong> <span style='margin-left: 8px;'>{filing_date}</span><br>"
            "<strong>Your Matter ID.:</strong> <span style='margin-left: 8px;'>{docket_no}</span>"
            "</p>"
            "<p style='margin: 16px 0 12px 0;'>Dear Sir/Madam,</p>"
            "<p style='margin: 0 0 14px 0;'>"
            "Attached please find the following document issued by the U.S. Patent and Trademark Office on "
            "{event_date} for the above-captioned application:"
            "</p>"
            "<ul style='margin: 0 0 14px 20px; padding-left: 12px;'>"
            "<li><strong>NON-FINAL OFFICE ACTION</strong></li>"
            "</ul>"
            "<p style='margin: 0 0 6px 0;'><strong>Due Date (3 months):</strong> {ctfr_due_date}</p>"
            "<p style='margin: 0 0 14px 0;'><strong>Due Date with 3 month Extension:</strong> {ctfr_extension_due_date}</p>"
            "<p style='margin: 0 0 14px 0;'>"
            "Please advise how you wish to proceed with the response before the due date."
            "</p>"
            "<p style='margin: 0 0 14px 0;'><strong>Important Note:</strong> "
            "Kindly send your instructions in a timely manner; <strong>at least 14 days before the due date.</strong> "
            "If instructions are not received well in advance, we will not be held responsible for any resulting abandonment of the application."
            "</p>"
            "<p style='margin: 0 0 14px 0;'>"
            "As always, please do not hesitate to contact us should you have any questions or concerns."
            "</p>"
            "<p style='margin: 0;'>All the best,<br>Rahul Maurya<br>Patent Ventures LLC</p>"
            "</div>"
        ),
    },
    "NTC.MISS.PRT": {
        "subject": "Notice to Submit Missing Parts - App {application_no}",
        "body": (
            "<div style='font-family: Arial, sans-serif; font-size: 14px; line-height: 1.6; color: #222;'>"
            "<p style='margin: 0 0 16px 0;'><strong><em>NOTICE TO SUBMIT MISSING PARTS due {ntc_miss_prt_due_date}</em></strong></p>"
            "<p style='margin: 0 0 16px 0;'>"
            "<strong>In re:</strong> <span style='margin-left: 8px;'>U.S. Patent Application Serial No.: {application_no}</span><br>"
            "<strong>Title:</strong> <span style='margin-left: 8px;'>{title}</span><br>"
            "<strong>Filing Date:</strong> <span style='margin-left: 8px;'>{filing_date}</span><br>"
            "<strong>Our File No.:</strong> <span style='margin-left: 8px;'>{docket_no}</span>"
            "</p>"
            "<p style='margin: 16px 0 12px 0;'>Dear Sir/Madam,</p>"
            "<p style='margin: 0 0 14px 0;'>"
            "Attached please find the <strong>Notice to Submit Missing Parts</strong> issued by the U.S. Patent and Trademark Office for the above-referenced application."
            "</p>"
            "<p style='margin: 0 0 8px 0;'>This notice requires submission of the following:</p>"
            "<ul style='margin: 0 0 14px 20px; padding-left: 12px;'>"
            "<li><strong>USPTO filing fees of USD</strong></li>"
            "</ul>"
            "<p style='margin: 0 0 10px 0;'><strong>DUE DATE:</strong></p>"
            "<p style='margin: 0 0 14px 0;'>"
            "Please advise how you wish to proceed with the required submissions on or before {ntc_miss_prt_due_date}"
            "</p>"
            "<p style='margin: 0 0 14px 0;'><strong>Important Note:</strong> "
            "Kindly send your instructions <strong>at least 14 days before the deadline.</strong> "
            "If instructions are not received in time, we will not be held responsible for any resulting abandonment of the application."
            "</p>"
            "<p style='margin: 0 0 14px 0;'>"
            "As always, please do not hesitate to contact me should you have any questions or concerns."
            "</p>"
            "<p style='margin: 0;'>All the best,<br>Rahul Maurya<br>Patent Ventures LLC</p>"
            "</div>"
        ),
    },
}
