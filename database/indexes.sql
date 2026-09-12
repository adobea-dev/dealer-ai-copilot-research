-- ================================================================
-- Dealer AI Copilot 2.0
-- PostgreSQL Indexes
-- ================================================================
--
-- These indexes support the kinds of filtering, joining, grouping,
-- ranking, and temporal analytics expected in the benchmark.
--
-- Primary keys and UNIQUE constraints already create indexes
-- automatically, so they are not duplicated here.
-- ================================================================


-- ----------------------------------------------------------------
-- DEALERS
-- ----------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_dealers_country
    ON dealers(country);

CREATE INDEX IF NOT EXISTS idx_dealers_city
    ON dealers(city);


-- ----------------------------------------------------------------
-- LEADS
-- ----------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_leads_dealer
    ON leads(dealer_id);

CREATE INDEX IF NOT EXISTS idx_leads_country
    ON leads(country);

CREATE INDEX IF NOT EXISTS idx_leads_date
    ON leads(lead_date);

CREATE INDEX IF NOT EXISTS idx_leads_dealer_date
    ON leads(dealer_id, lead_date);

CREATE INDEX IF NOT EXISTS idx_leads_country_date
    ON leads(country, lead_date);

CREATE INDEX IF NOT EXISTS idx_leads_source
    ON leads(lead_source);


-- ----------------------------------------------------------------
-- APPLICATIONS
-- ----------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_applications_dealer
    ON applications(dealer_id);

CREATE INDEX IF NOT EXISTS idx_applications_country
    ON applications(country);

CREATE INDEX IF NOT EXISTS idx_applications_date
    ON applications(application_date);

CREATE INDEX IF NOT EXISTS idx_applications_status
    ON applications(status);

CREATE INDEX IF NOT EXISTS idx_applications_dealer_date
    ON applications(dealer_id, application_date);

CREATE INDEX IF NOT EXISTS idx_applications_country_date
    ON applications(country, application_date);

CREATE INDEX IF NOT EXISTS idx_applications_dealer_status
    ON applications(dealer_id, status);


-- ----------------------------------------------------------------
-- SALES
-- ----------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_sales_dealer
    ON sales(dealer_id);

CREATE INDEX IF NOT EXISTS idx_sales_lead
    ON sales(lead_id);

CREATE INDEX IF NOT EXISTS idx_sales_country
    ON sales(country);

CREATE INDEX IF NOT EXISTS idx_sales_date
    ON sales(sale_date);

CREATE INDEX IF NOT EXISTS idx_sales_dealer_date
    ON sales(dealer_id, sale_date);

CREATE INDEX IF NOT EXISTS idx_sales_country_date
    ON sales(country, sale_date);

CREATE INDEX IF NOT EXISTS idx_sales_financing_bank
    ON sales(financing_bank);