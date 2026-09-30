-- Trademark project detail: manual "Under Hearing" display flag. Lets a user
-- flag the case as under hearing before the real Hearing Issued date is
-- known, without touching the dated status timeline. Purely a display
-- override - see _display_current_status in trademark_service.py.
ALTER TABLE tm_application_data ADD COLUMN IF NOT EXISTS is_under_hearing BOOLEAN NOT NULL DEFAULT FALSE;
