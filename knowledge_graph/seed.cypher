// Dealer AI Copilot 2.0 semantic knowledge graph.
// This graph contains DOMAIN SEMANTICS ONLY.
// It intentionally contains no benchmark answers and no transactional outcomes.

// ---------------------------------------------------------------------------
// Constraints
// ---------------------------------------------------------------------------
CREATE CONSTRAINT metric_name IF NOT EXISTS
FOR (n:Metric) REQUIRE n.name IS UNIQUE;

CREATE CONSTRAINT stage_name IF NOT EXISTS
FOR (n:FunnelStage) REQUIRE n.name IS UNIQUE;

CREATE CONSTRAINT semantic_name IF NOT EXISTS
FOR (n:TimeSemantic) REQUIRE n.name IS UNIQUE;

CREATE CONSTRAINT table_name IF NOT EXISTS
FOR (n:Table) REQUIRE n.name IS UNIQUE;

CREATE CONSTRAINT column_fq_name IF NOT EXISTS
FOR (n:Column) REQUIRE n.fq_name IS UNIQUE;

CREATE CONSTRAINT dimension_name IF NOT EXISTS
FOR (n:Dimension) REQUIRE n.name IS UNIQUE;

CREATE CONSTRAINT country_code IF NOT EXISTS
FOR (n:Country) REQUIRE n.code IS UNIQUE;

// ---------------------------------------------------------------------------
// Funnel
// ---------------------------------------------------------------------------
MERGE (lead:FunnelStage {name:'Lead'})
SET lead.order = 1,
    lead.entity_table = 'leads';

MERGE (application:FunnelStage {name:'Application'})
SET application.order = 2,
    application.entity_table = 'applications';

MERGE (approval:FunnelStage {name:'Approval'})
SET approval.order = 3,
    approval.entity_table = 'applications',
    approval.qualifier = "status = 'approved'";

MERGE (sale:FunnelStage {name:'Sale'})
SET sale.order = 4,
    sale.entity_table = 'sales';

MATCH (a:FunnelStage {name:'Lead'}), (b:FunnelStage {name:'Application'})
MERGE (a)-[:NEXT_STAGE]->(b);

MATCH (a:FunnelStage {name:'Application'}), (b:FunnelStage {name:'Approval'})
MERGE (a)-[:NEXT_STAGE]->(b);

MATCH (a:FunnelStage {name:'Approval'}), (b:FunnelStage {name:'Sale'})
MERGE (a)-[:NEXT_STAGE]->(b);

// ---------------------------------------------------------------------------
// Time semantics
// ---------------------------------------------------------------------------
MERGE (event:TimeSemantic {name:'event_period'})
SET event.description =
'Filter the date of the event being measured to the requested period.';

MERGE (cohort:TimeSemantic {name:'cohort'})
SET cohort.description =
'Select the starting population by its origin date, then follow linked downstream records by identifier. Late-2025 cohorts may mature through 2026-01-31.';

MERGE (alltime:TimeSemantic {name:'all_time'})
SET alltime.description =
'No additional time restriction is required.';

// ---------------------------------------------------------------------------
// Physical schema mappings
// ---------------------------------------------------------------------------
MERGE (:Table {name:'dealers'});
MERGE (:Table {name:'leads'});
MERGE (:Table {name:'applications'});
MERGE (:Table {name:'sales'});

MERGE (:Column {fq_name:'dealers.dealer_id', table:'dealers', column:'dealer_id'});
MERGE (:Column {fq_name:'dealers.dealer_name', table:'dealers', column:'dealer_name'});
MERGE (:Column {fq_name:'dealers.country', table:'dealers', column:'country'});

MERGE (:Column {fq_name:'leads.lead_id', table:'leads', column:'lead_id'});
MERGE (:Column {fq_name:'leads.dealer_id', table:'leads', column:'dealer_id'});
MERGE (:Column {fq_name:'leads.lead_date', table:'leads', column:'lead_date'});
MERGE (:Column {fq_name:'leads.lead_source', table:'leads', column:'lead_source'});

MERGE (:Column {fq_name:'applications.application_id', table:'applications', column:'application_id'});
MERGE (:Column {fq_name:'applications.lead_id', table:'applications', column:'lead_id'});
MERGE (:Column {fq_name:'applications.application_date', table:'applications', column:'application_date'});
MERGE (:Column {fq_name:'applications.application_channel', table:'applications', column:'application_channel'});
MERGE (:Column {fq_name:'applications.status', table:'applications', column:'status'});

MERGE (:Column {fq_name:'sales.sale_id', table:'sales', column:'sale_id'});
MERGE (:Column {fq_name:'sales.application_id', table:'sales', column:'application_id'});
MERGE (:Column {fq_name:'sales.lead_id', table:'sales', column:'lead_id'});
MERGE (:Column {fq_name:'sales.sale_date', table:'sales', column:'sale_date'});
MERGE (:Column {fq_name:'sales.sale_amount_usd', table:'sales', column:'sale_amount_usd'});
MERGE (:Column {fq_name:'sales.financing_bank', table:'sales', column:'financing_bank'});

// ---------------------------------------------------------------------------
// Metrics
// ---------------------------------------------------------------------------
MERGE (m:Metric {name:'lead_count'})
SET m.label='Leads',
    m.unit='count',
    m.definition='Count of lead records.',
    m.formula='COUNT(leads.lead_id)',
    m.default_time_semantic='event_period';

MERGE (m:Metric {name:'application_count'})
SET m.label='Applications',
    m.unit='count',
    m.definition='Count of application records.',
    m.formula='COUNT(applications.application_id)',
    m.default_time_semantic='event_period';

MERGE (m:Metric {name:'approved_application_count'})
SET m.label='Approved applications',
    m.unit='count',
    m.definition="Applications where status = 'approved'.",
    m.formula="COUNT(applications.application_id) FILTER (WHERE status = 'approved')",
    m.default_time_semantic='event_period';

MERGE (m:Metric {name:'sales_count'})
SET m.label='Sales',
    m.unit='count',
    m.definition='Count of sale records.',
    m.formula='COUNT(sales.sale_id)',
    m.default_time_semantic='event_period';

MERGE (m:Metric {name:'revenue'})
SET m.label='Sales revenue',
    m.unit='USD',
    m.definition='Sum of sale_amount_usd for the relevant sales.',
    m.formula='SUM(sales.sale_amount_usd)',
    m.default_time_semantic='event_period';

MERGE (m:Metric {name:'average_sale_value'})
SET m.label='Average sale value',
    m.unit='USD',
    m.definition='Mean sale_amount_usd for the relevant sales.',
    m.formula='AVG(sales.sale_amount_usd)',
    m.default_time_semantic='event_period';

MERGE (m:Metric {name:'application_approval_rate'})
SET m.label='Application approval percentage',
    m.unit='percent',
    m.definition='Approved applications divided by applications, multiplied by 100.',
    m.formula='approved_application_count / application_count * 100',
    m.default_time_semantic='event_period';

MERGE (m:Metric {name:'lead_to_application_rate'})
SET m.label='Lead-to-application percentage',
    m.unit='percent',
    m.definition='Applications linked to the selected lead cohort divided by cohort leads, multiplied by 100.',
    m.formula='linked_applications / cohort_leads * 100',
    m.default_time_semantic='cohort';

MERGE (m:Metric {name:'approved_to_sale_rate'})
SET m.label='Approved-to-sale percentage',
    m.unit='percent',
    m.definition='Sales linked to approved applications divided by approved applications, multiplied by 100.',
    m.formula='linked_sales / approved_applications * 100',
    m.default_time_semantic='cohort';

MERGE (m:Metric {name:'lead_to_sale_rate'})
SET m.label='Lead-to-sale percentage',
    m.unit='percent',
    m.definition='Sales linked to the selected lead cohort divided by cohort leads, multiplied by 100.',
    m.formula='linked_sales / cohort_leads * 100',
    m.default_time_semantic='cohort';

// Metric semantic relationships
MATCH (m:Metric), (s:TimeSemantic)
WHERE m.default_time_semantic = s.name
MERGE (m)-[:USES_TIME_SEMANTIC]->(s);

// Metric-column relationships
MATCH (m:Metric {name:'revenue'}), (c:Column {fq_name:'sales.sale_amount_usd'})
MERGE (m)-[:MAPS_TO]->(c);

MATCH (m:Metric {name:'average_sale_value'}), (c:Column {fq_name:'sales.sale_amount_usd'})
MERGE (m)-[:MAPS_TO]->(c);

MATCH (m:Metric {name:'lead_count'}), (c:Column {fq_name:'leads.lead_id'})
MERGE (m)-[:MAPS_TO]->(c);

MATCH (m:Metric {name:'application_count'}), (c:Column {fq_name:'applications.application_id'})
MERGE (m)-[:MAPS_TO]->(c);

MATCH (m:Metric {name:'sales_count'}), (c:Column {fq_name:'sales.sale_id'})
MERGE (m)-[:MAPS_TO]->(c);

// ---------------------------------------------------------------------------
// Dimensions
// ---------------------------------------------------------------------------
MERGE (d:Dimension {name:'country'})
SET d.description='Country dimension encoded with two-letter research codes.';

MERGE (d:Dimension {name:'dealer'})
SET d.description='Dealer entity identified by dealer_id and dealer_name.';

MERGE (d:Dimension {name:'lead_source'})
SET d.description='Lead acquisition source.';

MERGE (d:Dimension {name:'application_channel'})
SET d.description='Channel through which an application was submitted.';

MERGE (d:Dimension {name:'financing_bank'})
SET d.description='Synthetic financing-bank category attached to sales.';

MERGE (d:Dimension {name:'month'})
SET d.description='Calendar month derived from the relevant event/cohort date.';

MERGE (d:Dimension {name:'quarter'})
SET d.description='Calendar quarter derived from the relevant event/cohort date.';

// ---------------------------------------------------------------------------
// Country mappings
// ---------------------------------------------------------------------------
MERGE (:Country {code:'GH', name:'Ghana'});
MERGE (:Country {code:'NG', name:'Nigeria'});
MERGE (:Country {code:'KE', name:'Kenya'});
MERGE (:Country {code:'UG', name:'Uganda'});

// ---------------------------------------------------------------------------
// Relationship semantics
// ---------------------------------------------------------------------------
MATCH (l:Table {name:'leads'}), (a:Table {name:'applications'})
MERGE (l)-[:LINKED_BY {key:'lead_id', cardinality:'0_or_1_application_per_lead'}]->(a);

MATCH (a:Table {name:'applications'}), (s:Table {name:'sales'})
MERGE (a)-[:LINKED_BY {key:'application_id', cardinality:'0_or_1_sale_per_application'}]->(s);

MATCH (l:Table {name:'leads'}), (s:Table {name:'sales'})
MERGE (l)-[:LINKED_BY {key:'lead_id', cardinality:'0_or_1_sale_per_lead'}]->(s);
