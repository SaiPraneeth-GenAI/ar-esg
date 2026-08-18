/** Static connector marketplace catalog -- no live integrations exist yet
 * (see the "no real credentials/API calls/OAuth" rule in the coming-soon
 * page). This file is the single source of truth for the grid, the
 * detail pages, and the coming-soon pages; every one of those reads from
 * here rather than hard-coding connector facts in multiple places. */

export type CategoryGroupId =
  | 'erp'
  | 'api'
  | 'iot'
  | 'database'
  | 'files'
  | 'documents'
  | 'utilities'
  | 'hr'
  | 'supply-chain'
  | 'esg';

export interface CategoryGroup {
  id: CategoryGroupId;
  label: string;
  blurb: string;
  prominent?: boolean;
}

export interface FilterPill {
  label: string;
  groups: CategoryGroupId[] | 'all';
}

export interface MappingExample {
  source: string;
  target: string;
}

export interface ConnectorDetail {
  overview: string;
  connects: string[];
  supportedData: string[];
  protocols: string[];
  authentication: string[];
  syncModes: string[];
  exampleData: string;
  exampleMapping: MappingExample[];
  dataFlow: string;
  useCases: string[];
}

export interface Connector {
  id: string;
  name: string;
  categoryGroup: CategoryGroupId;
  description: string;
  badges: string[];
  featured?: boolean;
  featuredTag?: string;
  detail: ConnectorDetail;
}

export const CATEGORY_GROUPS: CategoryGroup[] = [
  { id: 'erp', label: 'ERP & Enterprise', blurb: 'Finance, procurement, and operational systems of record.' },
  { id: 'api', label: 'APIs & Web Services', blurb: 'Programmatic, general-purpose connectivity.' },
  { id: 'iot', label: 'IoT & Industrial', blurb: 'Real-time telemetry straight from the plant floor.', prominent: true },
  { id: 'database', label: 'Databases', blurb: 'Direct connectivity to structured data infrastructure.' },
  { id: 'files', label: 'Files & Cloud', blurb: 'Spreadsheets, drops, and cloud object storage.' },
  { id: 'documents', label: 'Documents & Evidence', blurb: 'Unstructured evidence, read with AI extraction.' },
  { id: 'utilities', label: 'Energy & Utilities', blurb: 'Metered consumption at the source.' },
  { id: 'hr', label: 'Workforce', blurb: 'People, safety, and workforce systems.' },
  { id: 'supply-chain', label: 'Supply Chain', blurb: 'Upstream and downstream operational data.' },
  { id: 'esg', label: 'ESG Platforms', blurb: 'Interoperate with the ESG tools you already run.' }
];

export const FILTER_PILLS: FilterPill[] = [
  { label: 'All', groups: 'all' },
  { label: 'ERP', groups: ['erp'] },
  { label: 'API', groups: ['api'] },
  { label: 'IoT', groups: ['iot'] },
  { label: 'Industrial', groups: ['iot'] },
  { label: 'Database', groups: ['database'] },
  { label: 'Files', groups: ['files'] },
  { label: 'Documents', groups: ['documents'] },
  { label: 'Utilities', groups: ['utilities'] },
  { label: 'HR', groups: ['hr'] },
  { label: 'Supply Chain', groups: ['supply-chain'] },
  { label: 'ESG', groups: ['esg'] }
];

/** Sensible, category-appropriate detail content for every connector that
 * doesn't need a fully custom write-up -- the four Featured connectors
 * override every field below with hero-quality specifics instead. */
function defaultDetail(group: CategoryGroupId, name: string): ConnectorDetail {
  const templates: Record<CategoryGroupId, ConnectorDetail> = {
    erp: {
      overview: `${name} holds the transactional system-of-record data ESG reporting ultimately depends on -- energy and fuel purchases, production volumes, waste disposal costs, and the cost-center hierarchy that determines which site a figure belongs to.`,
      connects: ['General ledger & cost centers', 'Procurement & purchase orders', 'Production & material movements', 'Plant/site master data'],
      supportedData: ['Fuel and utility purchase line items', 'Production volume by material and plant', 'Waste disposal transactions', 'Site and cost-center hierarchy'],
      protocols: ['OData v4', 'REST', 'RFC/BAPI (SAP systems)'],
      authentication: ['OAuth 2.0 client credentials', 'SAML SSO', 'Service account with scoped read access'],
      syncModes: ['Scheduled batch (daily/monthly close-aligned)', 'On-demand pull'],
      exampleData: `{"plant": "ARE&M", "material": "Diesel", "quantity": 450, "unit": "L", "posting_date": "2026-08-14"}`,
      exampleMapping: [
        { source: 'MENGE (quantity)', target: 'Diesel Consumed — value' },
        { source: 'MEINS (unit)', target: 'Diesel Consumed — unit' },
        { source: 'WERKS (plant)', target: 'Location' }
      ],
      dataFlow: `${name} → Enviqo connector framework → validation & unit normalization → Draft entries, mapped to the matching data point → your existing Submit/Approve workflow.`,
      useCases: [`Auto-populate monthly fuel and electricity purchase volumes from ${name} instead of manual entry`, 'Cross-check submitted production volumes against the ERP system of record']
    },
    api: {
      overview: `${name} is the general-purpose path for pulling data out of any system that exposes one -- a billing platform, a metering vendor's own portal, or an internal tool that doesn't have a dedicated connector yet.`,
      connects: ['Any system exposing this protocol', 'Internal or third-party services', 'Vendor billing/metering portals'],
      supportedData: ['Whatever the source API returns -- shaped by field mapping at setup'],
      protocols: [name],
      authentication: ['API key', 'OAuth 2.0', 'Bearer token', 'Basic auth (legacy systems)'],
      syncModes: ['Scheduled poll', 'Event-driven (where the source supports it)'],
      exampleData: `{"meter_id": "MTR-014", "reading_kwh": 18000, "period": "2026-08"}`,
      exampleMapping: [
        { source: 'reading_kwh', target: 'Grid Electricity Consumed — value' },
        { source: 'period', target: 'Reporting period' }
      ],
      dataFlow: `${name} response → connector framework field mapping → validation → Draft entries → your existing Submit/Approve workflow.`,
      useCases: ['Connect a vendor billing API directly instead of downloading and re-uploading exports', 'Feed a custom internal tool into Enviqo without a bespoke connector']
    },
    iot: {
      overview: `${name} carries live telemetry straight from meters, sensors, and control systems on the plant floor -- the highest-frequency, most granular data source Enviqo can ingest, built for continuous monitoring rather than a monthly snapshot.`,
      connects: ['Smart meters & sub-meters', 'PLCs and control systems', 'Sensor networks', 'Building management systems'],
      supportedData: ['Electricity, water, and fuel consumption at meter-level granularity', 'Equipment run-state and utilization', 'Environmental sensor readings'],
      protocols: [name, 'TLS-encrypted transport'],
      authentication: ['Device certificates (mTLS)', 'Pre-shared credentials', 'Broker-level ACLs'],
      syncModes: ['Streaming / real-time', 'Store-and-forward on connectivity loss'],
      exampleData: `{"topic": "plant/aream/meter-14", "value": 42.8, "unit": "kWh", "ts": "2026-08-14T09:30:00Z"}`,
      exampleMapping: [
        { source: 'value (kWh, interval)', target: 'Grid Electricity Consumed — value, rolled up to monthly' },
        { source: 'ts', target: 'Reporting period (aggregated)' }
      ],
      dataFlow: `${name} device/broker → Enviqo edge ingestion → interval aggregation to monthly totals → validation → Draft entries → your existing Submit/Approve workflow.`,
      useCases: ['Replace manual meter readings with continuous, auditable telemetry', 'Catch consumption anomalies the same day instead of at month-end']
    },
    database: {
      overview: `${name} connects directly to a data warehouse or operational database your team already maintains -- for tenants that centralize sustainability-relevant figures in their own data infrastructure rather than a single source system.`,
      connects: ['Custom data warehouses', 'Operational reporting databases', 'BI/analytics layers'],
      supportedData: ['Any query result set -- shaped by the SQL/view defined at setup'],
      protocols: ['JDBC', 'ODBC', 'Native driver'],
      authentication: ['Database user credentials (read-only role recommended)', 'IAM-based auth (cloud-hosted instances)'],
      syncModes: ['Scheduled query (daily/monthly)', 'Incremental pull via a watermark column'],
      exampleData: `SELECT plant, metric, value, period FROM esg_staging WHERE period = '2026-08-01'`,
      exampleMapping: [
        { source: 'metric = \'diesel_l\'', target: 'Diesel Consumed — value' },
        { source: 'plant', target: 'Location' }
      ],
      dataFlow: `${name} query result → connector framework field mapping → validation → Draft entries → your existing Submit/Approve workflow.`,
      useCases: ['Pull from an existing internal ESG staging table instead of re-keying it', 'Keep a single warehouse as the source of truth across multiple reporting tools']
    },
    files: {
      overview: `${name} covers the file-based path -- for teams that already track sustainability data in spreadsheets or drop exports into cloud storage, without needing a live system connection.`,
      connects: ['Shared drives and cloud storage', 'Scheduled file exports from other systems', 'Manually maintained trackers'],
      supportedData: ['Whatever columns the file contains -- mapped once, then reused automatically'],
      protocols: [name.includes('SFTP') ? 'SFTP' : 'HTTPS'],
      authentication: ['Storage account credentials / access keys', 'SFTP key pair'],
      syncModes: ['Scheduled folder watch', 'Manual upload (existing Bulk Upload wizard)'],
      exampleData: `category,data_point,value,unit,year,month\nWater,Ground Water Withdrawal,819,KL,2026,8`,
      exampleMapping: [
        { source: 'data_point column', target: 'Matched to the corresponding field' },
        { source: 'year + month columns', target: 'Reporting period' }
      ],
      dataFlow: `${name} → the same column-mapping engine behind Bulk Upload today → validation → Draft entries → your existing Submit/Approve workflow.`,
      useCases: ['Auto-pick up a recurring monthly export dropped into a folder', 'Keep an existing spreadsheet-based process, just remove the manual re-upload step']
    },
    documents: {
      overview: `${name} reads unstructured evidence -- PDFs, scanned bills, lab reports -- and extracts the figures using the same AI extraction guardrails already used for peer BRSR report reading: only figures the document actually contains, never invented.`,
      connects: ['Utility bills and invoices', 'Third-party lab and audit reports', 'Emailed attachments'],
      supportedData: ['Consumption/quantity figures named in the document', 'Billing period', 'Vendor and account identifiers, for evidence trails'],
      protocols: ['Document upload', 'Email ingestion (where configured)'],
      authentication: ['Tenant-scoped upload, same auth as the rest of Enviqo'],
      syncModes: ['On upload', 'Scheduled inbox poll (email ingestion)'],
      exampleData: `"Billing period: Aug 2026 — Electricity consumed: 18,000 kWh"`,
      exampleMapping: [
        { source: 'Extracted "18,000 kWh"', target: 'Grid Electricity Consumed — value, pending review' },
        { source: 'Billing period', target: 'Reporting period' }
      ],
      dataFlow: `${name} → AI extraction (guardrailed, source-quoted) → reviewer confirms the read → Draft entries → your existing Submit/Approve workflow.`,
      useCases: ['Turn a stack of utility bills into entries without manual re-typing', 'Keep the original document attached as the audit evidence for every extracted figure']
    },
    utilities: {
      overview: `${name} represents the metered-utility path -- typically reached via the IoT/meter connectors above or a utility provider's own billing API/portal, grouped here by the resource it measures rather than the transport.`,
      connects: ['Utility provider billing systems', 'Site-level sub-meters', 'Renewable/PPA generation meters'],
      supportedData: [`${name} consumption or generation volumes, at whatever granularity the source provides`],
      protocols: ['Provider-specific API or portal export', 'Meter telemetry (see IoT & Industrial)'],
      authentication: ['Utility portal credentials', 'Provider-issued API key'],
      syncModes: ['Scheduled (billing-cycle aligned)', 'Real-time, where sub-metered'],
      exampleData: `{"resource": "${name.toLowerCase()}", "value": 18000, "unit": "kWh", "period": "2026-08"}`,
      exampleMapping: [{ source: 'value', target: `${name} — value` }],
      dataFlow: `Provider system → connector framework → validation → Draft entries → your existing Submit/Approve workflow.`,
      useCases: [`Auto-populate monthly ${name.toLowerCase()} figures instead of re-keying from a bill`, 'Reconcile billed volumes against sub-metered readings']
    },
    hr: {
      overview: `${name} supplies the workforce-linked figures behind the Safety & Trends metrics -- headcount, training completion, and incident data that today are entered manually each month.`,
      connects: ['Core HR / HRMS records', 'Safety incident tracking', 'Training and certification records'],
      supportedData: ['Headcount and site assignment', 'Training completion rates', 'Safety incident counts and classifications'],
      protocols: ['REST API', 'Scheduled export'],
      authentication: ['OAuth 2.0', 'Service account credentials'],
      syncModes: ['Scheduled batch (monthly)', 'On-demand pull'],
      exampleData: `{"metric": "defensive_driving_training_pct", "value": 81.2, "period": "2026-08"}`,
      exampleMapping: [{ source: 'value', target: 'Defensive Driving Training — value' }],
      dataFlow: `${name} → connector framework field mapping → validation → Draft entries → your existing Submit/Approve workflow.`,
      useCases: ['Auto-populate monthly safety and training metrics instead of manual entry', 'Keep one workforce system as the source of truth across HR and ESG reporting']
    },
    'supply-chain': {
      overview: `${name} extends ESG data collection upstream and downstream -- purchased-goods volumes, logistics fuel/distance, and warehouse energy use that feed Scope 3-adjacent reporting as that scope is built out.`,
      connects: ['Purchase orders and supplier records', 'Logistics and freight systems', 'Warehouse management systems'],
      supportedData: ['Purchased quantity and material type', 'Freight distance and mode', 'Warehouse energy and space utilization'],
      protocols: ['REST API', 'EDI (where the supplier system requires it)'],
      authentication: ['OAuth 2.0', 'Partner-issued API credentials'],
      syncModes: ['Scheduled batch', 'Event-driven on shipment/PO status change'],
      exampleData: `{"po_number": "PO-88213", "material": "Lead", "quantity_mt": 12.4, "period": "2026-08"}`,
      exampleMapping: [{ source: 'quantity_mt', target: 'Matched to the corresponding purchased-material data point' }],
      dataFlow: `${name} → connector framework field mapping → validation → Draft entries → your existing Submit/Approve workflow.`,
      useCases: ['Track purchased-material volumes as a foundation for Scope 3 reporting', 'Bring logistics fuel/distance data in without a manual export']
    },
    esg: {
      overview: `${name} lets Enviqo interoperate with an ESG platform you already run elsewhere -- exporting calculated figures out, or importing figures already validated there, instead of maintaining the same numbers twice.`,
      connects: [`${name} data model`, 'Shared calculation/audit metadata'],
      supportedData: ['Calculated emissions and intensity figures', 'Target and performance records', 'Audit trail metadata'],
      protocols: ['REST API', `${name} export format`],
      authentication: ['OAuth 2.0', 'Platform-issued API key'],
      syncModes: ['Scheduled export/import', 'On-demand'],
      exampleData: `{"metric": "scope1_2_tco2e", "value": 20.06, "period": "2026-08"}`,
      exampleMapping: [{ source: 'scope1_2_tco2e', target: 'Scope 1+2 (location-based) — mapped 1:1' }],
      dataFlow: `Enviqo calculation snapshots ↔ ${name} via its own API/export format, kept in sync on a schedule you control.`,
      useCases: [`Avoid maintaining the same figures in both Enviqo and ${name}`, 'Use Enviqo as the calculation engine while continuing to report out of an existing platform']
    }
  };
  return templates[group];
}

function d(group: CategoryGroupId, name: string, overrides?: Partial<ConnectorDetail>): ConnectorDetail {
  return { ...defaultDetail(group, name), ...(overrides ?? {}) };
}

export const CONNECTORS: Connector[] = [
  // -- Featured ------------------------------------------------------
  {
    id: 'sap-s4hana',
    name: 'SAP S/4HANA',
    categoryGroup: 'erp',
    description: 'Connect finance, supply chain, and operational data straight from your S/4HANA system of record.',
    badges: ['ERP', 'API', 'Batch'],
    featured: true,
    featuredTag: 'Enterprise ERP',
    detail: {
      overview:
        'SAP S/4HANA typically holds the transactional backbone most ESG figures trace back to -- fuel and utility purchases, production volumes by plant, waste disposal costs, and the cost-center/plant hierarchy that determines site attribution. A direct connection removes the re-keying step between SAP and Enviqo entirely.',
      connects: ['General ledger & cost centers', 'Materials management (purchasing)', 'Production planning', 'Plant & cost-center master data'],
      supportedData: [
        'Fuel, diesel, and utility purchase line items (MM)',
        'Production volume by material and plant (PP)',
        'Waste disposal transactions and cost postings (FI/CO)',
        'Plant, cost-center, and profit-center hierarchy'
      ],
      protocols: ['OData v4', 'REST (via SAP API Business Hub)', 'RFC/BAPI for legacy modules'],
      authentication: ['OAuth 2.0 client credentials', 'SAML SSO passthrough', 'Dedicated read-only service account'],
      syncModes: ['Scheduled batch, aligned to your monthly close', 'On-demand pull for a specific period'],
      exampleData: '{"plant": "ARE&M", "material": "Diesel", "quantity": 450, "unit": "L", "posting_date": "2026-08-14"}',
      exampleMapping: [
        { source: 'MENGE (quantity)', target: 'Diesel Consumed — value' },
        { source: 'MEINS (unit of measure)', target: 'Diesel Consumed — unit, converted if needed' },
        { source: 'WERKS (plant code)', target: 'Location' }
      ],
      dataFlow:
        'S/4HANA OData service → Enviqo connector framework → unit normalization & validation → Draft entries, matched to the corresponding data point → your existing Submit → Approve workflow, unchanged.',
      useCases: [
        'Auto-populate monthly fuel and electricity purchase volumes directly from SAP instead of manual entry',
        'Cross-check what a Manager submitted against the ERP system of record before approval',
        'Keep plant/cost-center attribution consistent between SAP and Enviqo automatically'
      ]
    }
  },
  {
    id: 'mqtt',
    name: 'MQTT',
    categoryGroup: 'iot',
    description: 'Real-time telemetry from meters, sensors, and control systems across the plant floor.',
    badges: ['Industrial', 'Real-time', 'API'],
    featured: true,
    featuredTag: 'Real-time Industrial IoT',
    detail: {
      overview:
        'MQTT is the lightweight publish/subscribe protocol most industrial meters and sensor networks already speak. Enviqo subscribes to the topics you designate and aggregates the stream into the monthly figures your data points expect -- the highest-frequency, most granular ingestion path available.',
      connects: ['Smart electricity and water sub-meters', 'PLC and SCADA telemetry bridges', 'Third-party sensor gateways'],
      supportedData: [
        'Electricity, water, and fuel consumption at meter-level, interval granularity',
        'Equipment run-state and duty-cycle telemetry',
        'Environmental sensor readings (temperature, flow, pressure)'
      ],
      protocols: ['MQTT v3.1.1 / v5', 'TLS-encrypted transport (MQTTS)'],
      authentication: ['Per-device X.509 certificates (mTLS)', 'Broker username/password with topic-level ACLs'],
      syncModes: ['Streaming / real-time', 'Store-and-forward buffering on connectivity loss'],
      exampleData: '{"topic": "plant/aream/meter-14", "value": 42.8, "unit": "kWh", "ts": "2026-08-14T09:30:00Z"}',
      exampleMapping: [
        { source: 'value (kWh, 15-min interval)', target: 'Grid Electricity Consumed — value, rolled up to a monthly total' },
        { source: 'ts (timestamp)', target: 'Reporting period, aggregated automatically' }
      ],
      dataFlow:
        'Meter/sensor → MQTT broker → Enviqo edge subscriber → interval aggregation to monthly totals → validation → Draft entries → your existing Submit → Approve workflow.',
      useCases: [
        'Replace manual monthly meter readings with continuous, timestamped telemetry',
        'Catch a consumption anomaly the same day it happens instead of discovering it at month-end reconciliation',
        'Build toward real-time (not just monthly) sustainability dashboards'
      ]
    }
  },
  {
    id: 'rest-api',
    name: 'REST API',
    categoryGroup: 'api',
    description: 'Universal, protocol-standard connectivity to any system that exposes a REST endpoint.',
    badges: ['API', 'Real-time', 'Batch'],
    featured: true,
    featuredTag: 'Universal API Connectivity',
    detail: {
      overview:
        'The REST connector is the general-purpose path -- for a billing platform, a metering vendor portal, or any internal tool that exposes an HTTP API but has no dedicated connector yet. One field-mapping configuration is all a new source needs.',
      connects: ['Any system exposing a REST/JSON API', 'Vendor billing and metering portals', 'Internal tools and microservices'],
      supportedData: ['Whatever the source endpoint returns -- shaped entirely by the field mapping set up at connection time'],
      protocols: ['REST over HTTPS', 'JSON / XML response parsing'],
      authentication: ['API key (header or query param)', 'OAuth 2.0 (authorization code or client credentials)', 'Bearer token', 'Basic auth for legacy systems'],
      syncModes: ['Scheduled poll (interval configurable)', 'Event-driven, where the source supports webhooks'],
      exampleData: '{"meter_id": "MTR-014", "reading_kwh": 18000, "period": "2026-08"}',
      exampleMapping: [
        { source: 'reading_kwh', target: 'Grid Electricity Consumed — value' },
        { source: 'period', target: 'Reporting period' }
      ],
      dataFlow:
        'Source API response → connector framework field mapping (configured once per source) → validation → Draft entries → your existing Submit → Approve workflow.',
      useCases: [
        'Connect a utility provider\'s billing API directly instead of downloading and re-uploading monthly exports',
        'Feed a bespoke internal tracking tool into Enviqo without waiting on a dedicated connector',
        'Standardize every future integration on one well-understood protocol'
      ]
    }
  },
  {
    id: 'pdf-documents',
    name: 'PDF Documents',
    categoryGroup: 'documents',
    description: 'AI-extracted figures from utility bills, invoices, and lab reports -- with the source always attached.',
    badges: ['AI Extraction', 'Documents'],
    featured: true,
    featuredTag: 'AI Evidence Extraction',
    detail: {
      overview:
        'The same guardrailed AI extraction already used to read peer BRSR reports applies here: a PDF is read for the figures it actually contains -- never invented, never guessed -- and a reviewer confirms the read before anything becomes an entry. The original document stays attached as the audit trail.',
      connects: ['Utility and energy bills', 'Third-party invoices', 'Laboratory and audit reports', 'Emailed attachments (where inbox ingestion is configured)'],
      supportedData: ['Consumption/quantity figures explicitly stated in the document', 'Billing period', 'Vendor, account, and meter identifiers, for evidence trails'],
      protocols: ['Direct upload', 'Scheduled email-inbox ingestion'],
      authentication: ['Tenant-scoped upload, same auth as the rest of Enviqo'],
      syncModes: ['On upload', 'Scheduled inbox poll'],
      exampleData: '"Billing period: Aug 2026 — Electricity consumed: 18,000 kWh"',
      exampleMapping: [
        { source: 'Extracted "18,000 kWh"', target: 'Grid Electricity Consumed — value, pending reviewer confirmation' },
        { source: 'Billing period', target: 'Reporting period' }
      ],
      dataFlow:
        'PDF upload → AI extraction (guardrailed, every figure traceable to its source line) → reviewer confirms the read → Draft entries → your existing Submit → Approve workflow.',
      useCases: [
        'Turn a folder of monthly utility bills into entries without manual re-typing',
        'Keep the original bill attached as evidence behind every extracted figure, satisfying audit requirements',
        'Extract from third-party lab reports for effluent/emissions data that only exists on paper today'
      ]
    }
  },

  // -- ERP & Enterprise ------------------------------------------------
  {
    id: 'sap-ecc',
    name: 'SAP ECC',
    categoryGroup: 'erp',
    description: 'Legacy SAP ECC 6.0 systems -- the same financial and operational data, via RFC/BAPI.',
    badges: ['ERP', 'Batch'],
    detail: d('erp', 'SAP ECC')
  },
  {
    id: 'oracle-erp',
    name: 'Oracle ERP Cloud',
    categoryGroup: 'erp',
    description: 'Financials, procurement, and supply chain data from Oracle Fusion Cloud ERP.',
    badges: ['ERP', 'API', 'Batch'],
    detail: d('erp', 'Oracle ERP Cloud')
  },
  {
    id: 'dynamics-365',
    name: 'Microsoft Dynamics 365',
    categoryGroup: 'erp',
    description: 'Finance and operations data from Dynamics 365, including cost-center and plant hierarchy.',
    badges: ['ERP', 'API'],
    detail: d('erp', 'Microsoft Dynamics 365')
  },

  // -- APIs & Web Services ------------------------------------------------
  {
    id: 'soap-api',
    name: 'SOAP API',
    categoryGroup: 'api',
    description: 'Structured XML-based connectivity for older enterprise and utility-provider systems.',
    badges: ['API', 'Batch'],
    detail: d('api', 'SOAP API', { protocols: ['SOAP over HTTPS', 'WSDL-defined contracts'] })
  },
  {
    id: 'odata',
    name: 'OData',
    categoryGroup: 'api',
    description: 'Query-friendly, standardized REST convention used widely across SAP and Microsoft systems.',
    badges: ['API', 'Real-time'],
    detail: d('api', 'OData', { protocols: ['OData v4'] })
  },
  {
    id: 'webhooks',
    name: 'Webhooks',
    categoryGroup: 'api',
    description: 'Push-based updates -- a source system notifies Enviqo the moment new data is ready.',
    badges: ['API', 'Real-time'],
    detail: d('api', 'Webhooks', { syncModes: ['Event-driven push, no polling needed'] })
  },

  // -- IoT & Industrial ------------------------------------------------
  {
    id: 'opc-ua',
    name: 'OPC-UA',
    categoryGroup: 'iot',
    description: 'The industrial-automation standard for secure, structured data exchange with control systems.',
    badges: ['Industrial', 'Real-time'],
    detail: d('iot', 'OPC-UA', { protocols: ['OPC Unified Architecture', 'TLS-secured transport'] })
  },
  {
    id: 'modbus',
    name: 'Modbus',
    categoryGroup: 'iot',
    description: 'The long-standing serial/TCP protocol still running most legacy industrial equipment.',
    badges: ['Industrial', 'Real-time'],
    detail: d('iot', 'Modbus', { protocols: ['Modbus TCP', 'Modbus RTU (via gateway)'] })
  },
  {
    id: 'scada',
    name: 'SCADA',
    categoryGroup: 'iot',
    description: 'Plant-wide supervisory control and data acquisition systems, read directly.',
    badges: ['Industrial', 'Real-time', 'Batch'],
    detail: d('iot', 'SCADA')
  },
  {
    id: 'bms',
    name: 'BMS',
    categoryGroup: 'iot',
    description: 'Building management systems -- HVAC, lighting, and facility-level energy telemetry.',
    badges: ['Industrial', 'Real-time'],
    detail: d('iot', 'BMS (Building Management System)')
  },
  {
    id: 'smart-meters',
    name: 'Smart Energy Meters',
    categoryGroup: 'iot',
    description: 'Direct telemetry from smart electricity, water, and gas meters at the site.',
    badges: ['Industrial', 'Real-time', 'API'],
    detail: d('iot', 'Smart Energy Meters')
  },

  // -- Databases ------------------------------------------------
  {
    id: 'postgresql',
    name: 'PostgreSQL',
    categoryGroup: 'database',
    description: 'Direct connectivity to a PostgreSQL database or data warehouse you already maintain.',
    badges: ['Database', 'Batch'],
    detail: d('database', 'PostgreSQL')
  },
  {
    id: 'mysql',
    name: 'MySQL',
    categoryGroup: 'database',
    description: 'Query MySQL/MariaDB directly for figures already centralized in an operational database.',
    badges: ['Database', 'Batch'],
    detail: d('database', 'MySQL')
  },
  {
    id: 'mssql',
    name: 'Microsoft SQL Server',
    categoryGroup: 'database',
    description: 'Connect to SQL Server instances powering internal reporting and analytics.',
    badges: ['Database', 'Batch'],
    detail: d('database', 'Microsoft SQL Server')
  },
  {
    id: 'oracle-db',
    name: 'Oracle Database',
    categoryGroup: 'database',
    description: 'Enterprise-grade Oracle Database connectivity for large operational data stores.',
    badges: ['Database', 'Batch'],
    detail: d('database', 'Oracle Database')
  },
  {
    id: 'snowflake',
    name: 'Snowflake',
    categoryGroup: 'database',
    description: 'Query your Snowflake warehouse directly -- no export/import step required.',
    badges: ['Database', 'API'],
    detail: d('database', 'Snowflake')
  },
  {
    id: 'databricks',
    name: 'Databricks',
    categoryGroup: 'database',
    description: 'Connect to Databricks Lakehouse tables for teams centralizing data on the platform.',
    badges: ['Database', 'API'],
    detail: d('database', 'Databricks')
  },

  // -- Files & Cloud ------------------------------------------------
  {
    id: 'excel',
    name: 'Excel',
    categoryGroup: 'files',
    description: 'The existing Bulk Upload workflow -- structured spreadsheets, mapped once and reused.',
    badges: ['Files', 'Batch'],
    detail: d('files', 'Excel')
  },
  {
    id: 'csv',
    name: 'CSV',
    categoryGroup: 'files',
    description: 'Plain-text exports from virtually any system, mapped the same way as Excel.',
    badges: ['Files', 'Batch'],
    detail: d('files', 'CSV')
  },
  {
    id: 'sftp',
    name: 'SFTP',
    categoryGroup: 'files',
    description: 'A watched folder that automatically picks up recurring scheduled exports.',
    badges: ['Files', 'Batch'],
    detail: d('files', 'SFTP', { protocols: ['SFTP'] })
  },
  {
    id: 's3',
    name: 'Amazon S3',
    categoryGroup: 'files',
    description: 'Cloud object storage -- point Enviqo at a bucket and prefix to ingest on a schedule.',
    badges: ['Files', 'Batch'],
    detail: d('files', 'Amazon S3')
  },
  {
    id: 'azure-blob',
    name: 'Azure Blob Storage',
    categoryGroup: 'files',
    description: 'Cloud object storage on Azure, ingested the same way as S3.',
    badges: ['Files', 'Batch'],
    detail: d('files', 'Azure Blob Storage')
  },
  {
    id: 'sharepoint',
    name: 'SharePoint',
    categoryGroup: 'files',
    description: 'Read from a shared SharePoint document library your team already uses.',
    badges: ['Files', 'Batch'],
    detail: d('files', 'SharePoint')
  },

  // -- Documents & Evidence ------------------------------------------------
  {
    id: 'utility-bills',
    name: 'Utility Bills',
    categoryGroup: 'documents',
    description: 'AI-read electricity, water, and gas bills -- the figure and its source, together.',
    badges: ['AI Extraction', 'Documents'],
    detail: d('documents', 'Utility Bills')
  },
  {
    id: 'invoices',
    name: 'Invoices',
    categoryGroup: 'documents',
    description: 'Extract fuel, material, and waste-disposal quantities from vendor invoices.',
    badges: ['AI Extraction', 'Documents'],
    detail: d('documents', 'Invoices')
  },
  {
    id: 'lab-reports',
    name: 'Laboratory Reports',
    categoryGroup: 'documents',
    description: 'Effluent, air quality, and emissions figures from third-party lab reports.',
    badges: ['AI Extraction', 'Documents'],
    detail: d('documents', 'Laboratory Reports')
  },
  {
    id: 'email',
    name: 'Email',
    categoryGroup: 'documents',
    description: 'A monitored inbox that automatically reads attached bills and reports as they arrive.',
    badges: ['AI Extraction', 'Real-time'],
    detail: d('documents', 'Email', { syncModes: ['Scheduled inbox poll'] })
  },

  // -- Energy & Utilities ------------------------------------------------
  {
    id: 'electricity',
    name: 'Electricity',
    categoryGroup: 'utilities',
    description: 'Grid electricity consumption, from provider billing or site sub-meters.',
    badges: ['Utilities', 'Real-time'],
    detail: d('utilities', 'Electricity')
  },
  {
    id: 'water',
    name: 'Water',
    categoryGroup: 'utilities',
    description: 'Ground, surface, and third-party water withdrawal, metered at the source.',
    badges: ['Utilities', 'Batch'],
    detail: d('utilities', 'Water')
  },
  {
    id: 'natural-gas',
    name: 'Natural Gas',
    categoryGroup: 'utilities',
    description: 'Piped natural gas consumption from provider billing or site metering.',
    badges: ['Utilities', 'Batch'],
    detail: d('utilities', 'Natural Gas')
  },
  {
    id: 'fuel-diesel',
    name: 'Fuel / Diesel',
    categoryGroup: 'utilities',
    description: 'Diesel, petrol, and LPG purchase and consumption volumes.',
    badges: ['Utilities', 'Batch'],
    detail: d('utilities', 'Fuel / Diesel')
  },
  {
    id: 'renewable-energy',
    name: 'Renewable Energy',
    categoryGroup: 'utilities',
    description: 'On-site solar/wind generation and PPA-covered renewable percentage.',
    badges: ['Utilities', 'Real-time'],
    detail: d('utilities', 'Renewable Energy')
  },

  // -- Workforce ------------------------------------------------
  {
    id: 'hrms',
    name: 'HRMS',
    categoryGroup: 'hr',
    description: 'Core HR records -- headcount, site assignment, and organizational structure.',
    badges: ['HR', 'API', 'Batch'],
    detail: d('hr', 'HRMS')
  },
  {
    id: 'payroll',
    name: 'Payroll',
    categoryGroup: 'hr',
    description: 'Payroll-linked workforce figures relevant to labor and safety reporting.',
    badges: ['HR', 'Batch'],
    detail: d('hr', 'Payroll')
  },
  {
    id: 'learning-training',
    name: 'Learning & Training',
    categoryGroup: 'hr',
    description: 'Training completion rates -- defensive driving, safety induction, and more.',
    badges: ['HR', 'Batch'],
    detail: d('hr', 'Learning & Training')
  },
  {
    id: 'safety-systems',
    name: 'Safety Systems',
    categoryGroup: 'hr',
    description: 'Incident tracking systems -- fatality, LTIFR, near-miss, and unsafe-condition counts.',
    badges: ['HR', 'API', 'Real-time'],
    detail: d('hr', 'Safety Systems')
  },

  // -- Supply Chain ------------------------------------------------
  {
    id: 'procurement',
    name: 'Procurement',
    categoryGroup: 'supply-chain',
    description: 'Purchased-material volumes and vendor records, upstream of production.',
    badges: ['Supply Chain', 'API', 'Batch'],
    detail: d('supply-chain', 'Procurement')
  },
  {
    id: 'supplier-portal',
    name: 'Supplier Portal',
    categoryGroup: 'supply-chain',
    description: 'Data your suppliers submit directly, for upstream Scope 3-adjacent reporting.',
    badges: ['Supply Chain', 'API'],
    detail: d('supply-chain', 'Supplier Portal')
  },
  {
    id: 'logistics',
    name: 'Logistics',
    categoryGroup: 'supply-chain',
    description: 'Freight distance and mode data from transportation management systems.',
    badges: ['Supply Chain', 'Batch'],
    detail: d('supply-chain', 'Logistics')
  },
  {
    id: 'warehouse-mgmt',
    name: 'Warehouse Management',
    categoryGroup: 'supply-chain',
    description: 'Warehouse energy use and space utilization from WMS platforms.',
    badges: ['Supply Chain', 'Batch'],
    detail: d('supply-chain', 'Warehouse Management')
  },

  // -- ESG Platforms ------------------------------------------------
  {
    id: 'ibm-envizi',
    name: 'IBM Envizi',
    categoryGroup: 'esg',
    description: 'Sync calculated figures with an existing IBM Envizi deployment.',
    badges: ['ESG', 'API'],
    detail: d('esg', 'IBM Envizi')
  },
  {
    id: 'ms-sustainability-manager',
    name: 'Microsoft Sustainability Manager',
    categoryGroup: 'esg',
    description: 'Interoperate with Microsoft Sustainability Manager for teams already on the platform.',
    badges: ['ESG', 'API'],
    detail: d('esg', 'Microsoft Sustainability Manager')
  },
  {
    id: 'workiva',
    name: 'Workiva',
    categoryGroup: 'esg',
    description: 'Push validated figures into Workiva for disclosure and reporting workflows.',
    badges: ['ESG', 'API'],
    detail: d('esg', 'Workiva')
  },
  {
    id: 'sap-sustainability',
    name: 'SAP Sustainability',
    categoryGroup: 'esg',
    description: 'Interoperate with SAP Sustainability Footprint Management and related modules.',
    badges: ['ESG', 'API'],
    detail: d('esg', 'SAP Sustainability')
  },
  {
    id: 'sphera',
    name: 'Sphera',
    categoryGroup: 'esg',
    description: 'Sync EHS and ESG figures with an existing Sphera deployment.',
    badges: ['ESG', 'API'],
    detail: d('esg', 'Sphera')
  }
];

export function getConnector(id: string): Connector | undefined {
  return CONNECTORS.find((c) => c.id === id);
}

export function getCategoryGroup(id: CategoryGroupId): CategoryGroup | undefined {
  return CATEGORY_GROUPS.find((g) => g.id === id);
}
