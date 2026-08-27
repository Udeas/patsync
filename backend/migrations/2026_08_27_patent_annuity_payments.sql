-- Renewal ("annuity") payment records: one row per payment transaction,
-- one child row per renewal year that payment covers.
CREATE TABLE IF NOT EXISTS patent_annuity_payment (
  id SERIAL PRIMARY KEY,
  project_id INTEGER NOT NULL REFERENCES patent_project(id),
  payment_date DATE NOT NULL,
  total_fee INTEGER NOT NULL,
  created_date TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS patent_annuity_payment_year (
  id SERIAL PRIMARY KEY,
  payment_id INTEGER NOT NULL REFERENCES patent_annuity_payment(id),
  renewal_year INTEGER NOT NULL
);
