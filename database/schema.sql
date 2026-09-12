-- ================================================================
-- Dealer AI Copilot 2.0
-- PostgreSQL Experimental Database Schema
-- ================================================================
--
-- This schema contains ONLY information that may be exposed to the
-- experimental AI systems.
--
-- Research-only variables from:
--
--     data/research_truth/
--
-- must NEVER be loaded into this database.
--
-- We also deliberately avoid pre-computed analytics tables such as
-- dealer_activity_metrics.
--
-- Conversion rates, rankings, trends, revenue statistics, and other
-- analytics should be derived from the underlying event tables.
-- ================================================================


-- ----------------------------------------------------------------
-- OPTIONAL CLEAN RESET
-- ----------------------------------------------------------------
--
-- Tables are dropped in reverse dependency order.
--
-- This is useful during development when rebuilding the database from
-- the frozen CSV dataset.

DROP TABLE IF EXISTS sales CASCADE;
DROP TABLE IF EXISTS applications CASCADE;
DROP TABLE IF EXISTS leads CASCADE;
DROP TABLE IF EXISTS dealers CASCADE;


-- ================================================================
-- DEALERS
-- ================================================================

CREATE TABLE dealers (
    dealer_id UUID PRIMARY KEY,

    dealer_name VARCHAR(100) NOT NULL,

    -- Two-letter synthetic country code:
    -- GH, NG, KE, UG
    country CHAR(2) NOT NULL,

    city VARCHAR(100) NOT NULL,

    active BOOLEAN NOT NULL,

    CONSTRAINT chk_dealer_country
        CHECK (
            country IN (
                'GH',
                'NG',
                'KE',
                'UG'
            )
        )
);


-- ================================================================
-- LEADS
-- ================================================================
--
-- Each lead belongs to exactly one dealer.
--
-- New leads exist only during the primary analysis period:
--
--     2024-01-01 through 2025-12-31
-- ================================================================

CREATE TABLE leads (
    lead_id UUID PRIMARY KEY,

    dealer_id UUID NOT NULL,

    country CHAR(2) NOT NULL,

    lead_date DATE NOT NULL,

    lead_source VARCHAR(50) NOT NULL,

    CONSTRAINT fk_lead_dealer
        FOREIGN KEY (dealer_id)
        REFERENCES dealers(dealer_id)
        ON DELETE RESTRICT,

    CONSTRAINT chk_lead_country
        CHECK (
            country IN (
                'GH',
                'NG',
                'KE',
                'UG'
            )
        ),

    CONSTRAINT chk_lead_source
        CHECK (
            lead_source IN (
                'organic_web',
                'paid_search',
                'social',
                'referral',
                'marketplace'
            )
        ),

    CONSTRAINT chk_lead_analysis_window
        CHECK (
            lead_date >= DATE '2024-01-01'
            AND lead_date <= DATE '2025-12-31'
        )
);


-- ================================================================
-- APPLICATIONS
-- ================================================================
--
-- Every application originates from exactly one lead.
--
-- Under the current simulation design:
--
--     one lead -> zero or one application
--
-- Applications may occur during January 2026 because the simulation
-- includes a maturation buffer for late-December leads.
-- ================================================================

CREATE TABLE applications (
    application_id UUID PRIMARY KEY,

    lead_id UUID NOT NULL UNIQUE,

    dealer_id UUID NOT NULL,

    country CHAR(2) NOT NULL,

    application_date DATE NOT NULL,

    application_channel VARCHAR(50) NOT NULL,

    status VARCHAR(20) NOT NULL,

    CONSTRAINT fk_application_lead
        FOREIGN KEY (lead_id)
        REFERENCES leads(lead_id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_application_dealer
        FOREIGN KEY (dealer_id)
        REFERENCES dealers(dealer_id)
        ON DELETE RESTRICT,

    CONSTRAINT chk_application_country
        CHECK (
            country IN (
                'GH',
                'NG',
                'KE',
                'UG'
            )
        ),

    CONSTRAINT chk_application_channel
        CHECK (
            application_channel IN (
                'online',
                'dealer_branch',
                'bank_partner'
            )
        ),

    CONSTRAINT chk_application_status
        CHECK (
            status IN (
                'approved',
                'rejected'
            )
        ),

    CONSTRAINT chk_application_window
        CHECK (
            application_date >= DATE '2024-01-01'
            AND application_date <= DATE '2026-01-31'
        )
);


-- ================================================================
-- SALES
-- ================================================================
--
-- A sale may occur only after an approved application.
--
-- PostgreSQL foreign keys ensure that the referenced application,
-- lead, and dealer exist.
--
-- Whether the referenced application is actually approved is a
-- cross-table business rule and therefore will additionally be
-- checked during loading / validation.
--
-- Under the simulation design:
--
--     one application -> zero or one sale
-- ================================================================

CREATE TABLE sales (
    sale_id UUID PRIMARY KEY,

    application_id UUID NOT NULL UNIQUE,

    lead_id UUID NOT NULL,

    dealer_id UUID NOT NULL,

    country CHAR(2) NOT NULL,

    sale_date DATE NOT NULL,

    sale_amount_usd NUMERIC(12, 2) NOT NULL,

    financing_bank VARCHAR(50) NOT NULL,

    CONSTRAINT fk_sale_application
        FOREIGN KEY (application_id)
        REFERENCES applications(application_id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_sale_lead
        FOREIGN KEY (lead_id)
        REFERENCES leads(lead_id)
        ON DELETE RESTRICT,

    CONSTRAINT fk_sale_dealer
        FOREIGN KEY (dealer_id)
        REFERENCES dealers(dealer_id)
        ON DELETE RESTRICT,

    CONSTRAINT chk_sale_country
        CHECK (
            country IN (
                'GH',
                'NG',
                'KE',
                'UG'
            )
        ),

    CONSTRAINT chk_sale_amount
        CHECK (
            sale_amount_usd > 0
        ),

    CONSTRAINT chk_financing_bank
        CHECK (
            financing_bank IN (
                'Bank_A',
                'Bank_B',
                'Bank_C',
                'Bank_D'
            )
        ),

    CONSTRAINT chk_sale_window
        CHECK (
            sale_date >= DATE '2024-01-01'
            AND sale_date <= DATE '2026-01-31'
        )
);