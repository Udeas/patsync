-- Which docket types (patent/trademark/design) a client is eligible for.
-- Controls whether the client shows up in each docket type's client picker.
-- Existing clients default to all three so nothing currently wired up breaks.
ALTER TABLE patent_client ADD COLUMN IF NOT EXISTS client_types TEXT DEFAULT '["patent","trademark","design"]';
