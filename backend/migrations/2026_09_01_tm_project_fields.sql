-- Trademark Create screen: applicant type, TM type, multi-class support, and
-- the applicant's own class description. project_code itself is no longer
-- client-supplied (system generates TM<4-digit> on create) so no column
-- change is needed for it - the existing unique text column is reused.
ALTER TABLE tm_application_data ADD COLUMN IF NOT EXISTS applicant_type TEXT;
ALTER TABLE tm_application_data ADD COLUMN IF NOT EXISTS tm_type TEXT;
ALTER TABLE tm_application_data ADD COLUMN IF NOT EXISTS is_multi_class BOOLEAN DEFAULT FALSE;
ALTER TABLE tm_application_data ADD COLUMN IF NOT EXISTS tm_selected_classes TEXT;
ALTER TABLE tm_application_data ADD COLUMN IF NOT EXISTS application_class_description TEXT;
