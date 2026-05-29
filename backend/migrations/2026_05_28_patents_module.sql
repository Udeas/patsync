-- Isolated patents module schema
CREATE TABLE IF NOT EXISTS patent_client (
  id INTEGER PRIMARY KEY,
  client_code VARCHAR(4) NOT NULL UNIQUE,
  name VARCHAR NOT NULL,
  address TEXT,
  email VARCHAR,
  key_contacts TEXT,
  docketing_email VARCHAR
);

CREATE TABLE IF NOT EXISTS patent_agent (
  id INTEGER PRIMARY KEY,
  name VARCHAR NOT NULL,
  agent_code VARCHAR NOT NULL UNIQUE,
  address TEXT,
  mobile_1 VARCHAR NOT NULL,
  mobile_2 VARCHAR,
  email_1 VARCHAR NOT NULL,
  email_2 VARCHAR
);

CREATE TABLE IF NOT EXISTS patent_project (
  id INTEGER PRIMARY KEY,
  docket_no VARCHAR NOT NULL UNIQUE,
  project_mode VARCHAR NOT NULL,
  project_stage VARCHAR NOT NULL,
  in_application_no VARCHAR UNIQUE,
  in_application_date DATE,
  applicant_name VARCHAR NOT NULL,
  applicant_country VARCHAR(2),
  applicant_address TEXT,
  application_title VARCHAR,
  attorney_id INTEGER REFERENCES patent_agent(id),
  client_id INTEGER REFERENCES patent_client(id),
  client_docket_no VARCHAR,
  created_date TIMESTAMP,
  modified_date TIMESTAMP
);

CREATE TABLE IF NOT EXISTS patent_inventor (
  id INTEGER PRIMARY KEY,
  project_id INTEGER NOT NULL REFERENCES patent_project(id),
  name VARCHAR NOT NULL,
  nationality VARCHAR(2),
  address TEXT
);

CREATE TABLE IF NOT EXISTS patent_priority (
  id INTEGER PRIMARY KEY,
  project_id INTEGER NOT NULL REFERENCES patent_project(id),
  priority_application_no VARCHAR NOT NULL,
  priority_application_date DATE NOT NULL,
  country VARCHAR(2) NOT NULL,
  title VARCHAR NOT NULL
);

CREATE TABLE IF NOT EXISTS patent_status_event (
  id INTEGER PRIMARY KEY,
  project_id INTEGER NOT NULL REFERENCES patent_project(id),
  status_id INTEGER NOT NULL,
  status_date DATE NOT NULL
);
