<!-- Auto-extracted text copy of AI_Website_Intelligence_Crawler_Requirements_Proposal.docx (the original .docx is authoritative; tables are converted to plain markdown). Section numbers (e.g. "# 6. Crawling Requirements") match the original. -->

INTERNAL REQUIREMENTS & PROPOSAL  |  AI WEBSITE INTELLIGENCE CRAWLER

**AI-Powered Website Intelligence**
**&**** Business Classification System**

Requirements Document & Technical Proposal

**Internal Use  •  60,000+ Website URLs  •  AI-Assisted Classification ****&**** Excel Export**

| **Primary Goal: **Convert a large raw website URL dataset into structured, searchable business intelligence: company type, products, services, industry, niche, target market, evidence and crawl status, with reliable Excel export for analysis and business-development use. |
| --- |

| **Item** | **Details** |
| --- | --- |
| Document Type | Internal Requirements / Proposal |
| Primary Dataset | 60,000+ Website URLs |
| Primary Users | Management, Business Development, Research / Data Team |
| Recommended Data Store | PostgreSQL |
| Primary Output | Structured database + Excel / CSV / JSON export |
| Recommended Approach | Crawl → Extract → Classify → Validate → Store → Search → Export |

# 1. Executive Summary

The objective is to build an internal AI-powered web crawling and business-classification platform that can process 60,000 or more company website URLs. The system will crawl the most informative pages of each website, extract clean business content, use an AI model to understand what the company does, and convert that information into standardized, searchable records.

The system is not intended to crawl every page of every website. It should prioritize the homepage and high-value business pages such as About, Services, Products, Solutions and Industries. This keeps processing cost, crawl time and LLM usage under control while preserving enough context for accurate classification.

| **Core Principle: **The crawler should collect information; the content-processing layer should clean and organize it; the AI model should understand and classify it. These responsibilities should remain separate for scalability, accuracy and cost control. |
| --- |

# 2. Business Objectives

Determine what each company does in a consistent and machine-readable format.

Classify companies as Product-Based, Service-Based, Product + Service, SaaS, Marketplace, E-Commerce, Manufacturer, Distributor, Agency, Consulting, Platform or Other.

Identify products, services, primary industry, business niche, sub-niches and useful tags.

Determine target customer type and business model such as B2B, B2C, B2B2C or D2C where sufficient evidence exists.

Provide confidence scores and source evidence so AI classifications can be reviewed.

Allow users to search, filter and export structured business data to Excel for segmentation, research and business-development campaigns.

Create a reusable foundation for future lead scoring, sales intelligence and personalized outreach.

# 3. High-Level Processing Workflow

Import / receive website URLs.

Normalize domains and remove obvious duplicates.

Validate URL availability, redirects and HTTP status.

Fetch homepage and discover relevant internal links.

Prioritize business pages such as About, Services, Products, Solutions and Industries.

Extract meaningful text and remove boilerplate / duplicate content.

Prepare a consolidated website business profile.

Run AI classification using a controlled taxonomy and structured JSON output.

Validate AI response, calculate/store confidence and evidence.

Persist structured results in PostgreSQL.

Expose results through dashboard, filters and Excel / CSV / JSON export.

# 4. Input & URL Management Requirements

The system should support bulk and incremental ingestion so the initial 60,000+ URLs can be processed and new URLs can be added later without re-importing the complete dataset.

| **Capability** | **Requirement** |
| --- | --- |
| Excel / CSV Import | Bulk upload of URLs with optional external ID or source/reference fields. |
| Database Import | Allow URLs to be loaded directly from an existing database or staging table. |
| API Submission | Support individual and bulk URL submission in a later phase. |
| Manual Entry | Allow administrators to add one or more URLs for testing or reprocessing. |
| Deduplication | Normalize protocol, www prefix, trailing slash and obvious alternate URL forms. |
| Source Tracking | Retain original URL, source file/batch and source record ID when available. |

# 5. Website Validation & Status

URL format validity

DNS/domain resolution

HTTP/HTTPS availability

Redirect destination

SSL/TLS error

HTTP status code

Timeout / connection failure

Parked or for-sale domain

Under-construction or empty website

Blocked / access denied

Duplicate domain or canonical equivalent

Recommended high-level URL statuses: Pending, Active, Invalid, Unreachable, Redirected, Blocked, Parked, Under Construction, Crawled, Failed and Requires Review.

# 6. Crawling Requirements

## 6.1 Priority Pages

The crawler should focus on pages most useful for understanding the business rather than attempting a full-site crawl.

| **Priority** | **Typical Page Types / Signals** |
| --- | --- |
| Always | Homepage |
| High | About, About Us, Company, Who We Are, Our Story |
| High | Services, Solutions, Capabilities, Expertise, What We Do |
| High | Products, Platform, Software, Features |
| Medium | Industries, Markets, Sectors, Solutions by Industry |
| Medium | Customers, Case Studies, Portfolio, Pricing, Partners, Contact |

## 6.2 Page Discovery Logic

Relevant pages should be discovered using more than URL patterns. The crawler should use navigation text, anchor text, page title, headings, sitemap data and simple heuristics to identify likely About, Services, Product and Industry pages even when paths are non-standard.

## 6.3 Crawl Depth & Limits

Recommended MVP limit: approximately 5-10 useful pages per website. The system should avoid spending crawl budget on low-value pages such as blog archives, tags, author pages, legal policies, careers and search results unless needed for a specific classification.

# 7. Content Extraction & Cleaning

The crawler should not send raw HTML directly to the AI model. Business-relevant content should be extracted and compressed first.

| **Retain** | **Remove / De-prioritize** |
| --- | --- |
| Page title and meta description | CSS / JavaScript source |
| H1/H2/H3 headings | Repeated navigation and footer text |
| Meaningful paragraphs and lists | Cookie banners and popups |
| Product / service names | Ads and tracking text |
| CTA and descriptive labels | Long legal boilerplate |
| Structured data / schema when useful | Duplicate text across pages |

# 8. AI Business Analysis & Classification

The AI layer should receive a concise, consolidated representation of the selected pages and return strict structured JSON. Free-form narrative responses should not be used as the primary data contract.

| **Field Group** | **Expected Output** |
| --- | --- |
| Company Identity | Company name, website, concise company description |
| Business Type | Product-Based, Service-Based, Product + Service, SaaS, Marketplace, E-Commerce, Manufacturer, Distributor, Retailer, Consulting, Agency, Platform, Non-Profit, Education, Government, Other |
| Business Model | B2B, B2C, B2B2C, D2C, subscription, marketplace, consulting, agency, manufacturing, wholesale, retail |
| Industry / Niche | Primary industry, primary niche, secondary niches, searchable tags |
| Products | Product name, category, short description, target customer where available |
| Services | Service name, category, short description, target audience where available |
| Target Market | Customer segments and industries served |
| Geography | Country, city/region, office location and markets served where explicitly available |
| Evidence | Source page URL and supporting text/snippet reference |
| Confidence | Overall and/or field-level confidence score |

# 9. Controlled Industry & Niche Taxonomy

A configurable taxonomy is strongly recommended. The AI should map companies into defined industry categories instead of inventing a new label for every website. This prevents fragmentation such as "Software Services", "IT Services", "Software Development" and "Technology Services" being treated as unrelated categories.

| **Industry** | **Example Niches / Sub-Niches** |
| --- | --- |
| Technology | Software Development, Mobile Apps, AI/ML, Cybersecurity, Cloud, SaaS |
| Healthcare | Hospitals, Clinics, Telemedicine, Healthcare Software, Medical Devices |
| Finance | Banking, FinTech, Accounting, Insurance, Payments |
| Retail | E-Commerce, Fashion, Electronics, Grocery, Specialty Retail |
| Professional Services | Consulting, Legal, HR, Marketing, Accounting |
| Manufacturing | Industrial, Automotive, Consumer Goods, Equipment |
| Real Estate | Brokerage, Property Management, PropTech, Construction |
| Education | Schools, Training, EdTech, Universities |
| Other | Additional configurable categories as required |

# 10. Confidence & Evidence Requirements

AI output should be reviewable. Important classifications should include confidence and, where practical, evidence indicating which page or statement supported the conclusion.

| **Confidence Range** | **Interpretation** | **Action** |
| --- | --- | --- |
| 90-100% | High confidence | Accept automatically unless validation rules fail |
| 70-89% | Acceptable | Store normally; optionally sample for QA |
| Below 70% | Low confidence | Mark for review or re-analysis |

| **Evidence Example: **Service = AI Development; Source = /services/artificial-intelligence; supporting page text indicates the company develops custom generative AI solutions for enterprise customers. |
| --- |

# 11. Recommended System Architecture

A queue-based architecture is recommended so the crawler can scale horizontally and failed websites do not block the overall batch.

| **Layer** | **Recommended Responsibility / Technology** |
| --- | --- |
| Input / API | Excel/CSV import, API, manual submission |
| Normalization | Canonical domain normalization and duplicate handling |
| Queue | Redis + Celery (Python) or BullMQ (Node.js) |
| Crawler Workers | Lightweight HTTP fetch first; Playwright only when rendering is required |
| Extraction | BeautifulSoup / readability-style extraction / DOM heuristics |
| AI Layer | Provider abstraction supporting OpenAI, Anthropic, Gemini or other models |
| Validation | JSON schema validation, taxonomy mapping, confidence rules |
| Database | PostgreSQL |
| Backend API | FastAPI or NestJS |
| Admin UI | Next.js / React / Tailwind |
| Export | Excel, CSV and JSON generation |

# 12. Scale, Queueing & Cost Optimization

At 60,000 websites, processing must be asynchronous. If an average of five pages is analyzed per site, the platform may inspect approximately 300,000 pages. Cost control depends on reducing content before LLM processing and avoiding headless-browser rendering when simple HTTP retrieval is sufficient.

Use standard HTTP fetching first; fall back to Playwright for JavaScript-heavy sites.

Limit crawl depth and page count per domain.

Remove boilerplate and duplicate text before AI analysis.

Consolidate page content and send one classification request per website where possible.

Store prompt/model version, token usage and AI cost metrics for future optimization.

Use domain-level concurrency and rate limits to reduce blocking.

Retry transient failures with backoff; do not allow one failed website to stop a batch.

# 13. Excel Export Requirements

Excel export is a core requirement. Users should be able to export all processed records or only the currently filtered dataset. The export should be structured for business analysis, segmentation and handoff to BD/marketing teams without requiring manual cleanup.

## 13.1 Main Export Sheet - Website Intelligence

| **Excel Column** | **Required** | **Description** |
| --- | --- | --- |
| Record ID | Yes | Unique internal record ID. |
| Source / Batch | Recommended | Original import batch, source file or dataset name. |
| Original URL | Yes | URL exactly as received. |
| Normalized Website | Yes | Canonical website/domain used for processing. |
| Final / Redirect URL | Recommended | Resolved destination after redirects. |
| Company Name | Yes | Detected company or organization name. |
| Website Status | Yes | Active, unreachable, blocked, parked, etc. |
| HTTP Status | Recommended | Final HTTP response code when available. |
| Company Description | Yes | Concise AI-generated description of what the company does. |
| Primary Business Type | Yes | Product, Service, Hybrid, SaaS, Marketplace, etc. |
| Secondary Business Type | Optional | Additional business type when relevant. |
| Business Model | Yes | B2B, B2C, B2B2C, D2C, etc. |
| Primary Industry | Yes | Controlled top-level industry. |
| Primary Niche | Yes | Main business niche. |
| Secondary Niches | Recommended | Comma-separated additional niche classifications. |
| Products | Yes | Comma-separated product names or "None Identified". |
| Product Categories | Recommended | Normalized product categories. |
| Services | Yes | Comma-separated service names or "None Identified". |
| Service Categories | Recommended | Normalized service categories. |
| Target Customers | Recommended | SMBs, enterprises, consumers, healthcare providers, etc. |
| Customer Industries | Optional | Industries explicitly targeted by the company. |
| Headquarters Country | Recommended | Detected headquarters country where available. |
| Headquarters City / Region | Optional | Detected city or region. |
| Markets Served | Optional | Countries/regions served, if explicitly stated. |
| General Email | Optional | Public general/sales email if extracted. |
| Phone | Optional | Public company phone number if extracted. |
| LinkedIn URL | Optional | Public company LinkedIn URL. |
| Other Social URLs | Optional | Other relevant public social profiles. |
| Technology Tags | Optional | WordPress, Shopify, React, etc. if technology detection is enabled. |
| Business Keywords / Tags | Yes | Searchable AI-generated or normalized tags. |
| Overall Confidence % | Yes | Overall classification confidence. |
| Classification Review Status | Recommended | Auto Accepted, Needs Review, Manually Approved, Corrected. |
| Evidence Summary | Recommended | Short summary of why the business was classified this way. |
| Evidence URLs | Recommended | Key source page URLs used by the AI. |
| Pages Crawled Count | Yes | Number of pages successfully analyzed. |
| Pages Attempted Count | Recommended | Number of page fetches attempted. |
| Crawl Status | Yes | Completed, Partial, Failed, Blocked, etc. |
| Crawl Error / Notes | Recommended | Failure reason or special processing notes. |
| AI Model | Recommended | Model used for classification. |
| Prompt Version | Recommended | Version of classification prompt / schema. |
| Last Crawled At | Yes | Date/time of last crawl. |
| Last Analyzed At | Yes | Date/time of AI analysis. |
| Manual Notes | Optional | Internal reviewer notes. |

## 13.2 Optional Supporting Sheets

| **Sheet** | **Purpose / Suggested Columns** |
| --- | --- |
| Products | One row per company product: Record ID, Company, Website, Product Name, Category, Description, Target Customer, Source URL, Confidence. |
| Services | One row per service: Record ID, Company, Website, Service Name, Category, Description, Target Audience, Source URL, Confidence. |
| Crawled Pages | One row per crawled page: Website ID, Page URL, Page Type, Title, HTTP Status, Crawl Status, Content Length, Error, Crawled At. |
| Errors / Failed URLs | Only failed or partial records with error category, error message, retry count and last attempt date. |
| Taxonomy Reference | Controlled list of industries, niches, business types and business models used by the classification engine. |

## 13.3 Excel Export Functional Rules

Allow export of all records or the currently filtered result set.

Support XLSX as the primary business export format and CSV as a lightweight alternative.

Use one row per company in the main sheet; store products/services as delimited summaries there and optionally provide normalized supporting sheets.

Use proper date/time cell types and numeric confidence values instead of text where possible.

Freeze the header row and enable Excel filters on the main sheet.

Apply readable column widths and wrap long description/evidence cells.

Do not merge cells in data sheets because this complicates filtering and downstream processing.

Support large exports without loading the complete dataset into application memory at once (streaming/chunked export).

Include export timestamp and applied filters in a small metadata section or separate Export Info sheet.

Prevent spreadsheet formula injection by safely escaping values that begin with =, +, - or @ when sourced from websites.

# 14. Data Model / Database Requirements

| **Entity** | **Core Data** |
| --- | --- |
| Websites | Original URL, normalized domain, redirect URL, availability, HTTP status, crawl status, last crawl. |
| Companies | Company name, description, business type/model, industry, niche, location, confidence, review status. |
| Products | Company ID, product name, category, description, source page, confidence. |
| Services | Company ID, service name, category, description, source page, confidence. |
| Website Pages | Website ID, page URL, page type, title, cleaned text, crawl result. |
| AI Analysis | Model, prompt version, analysis timestamp, token/cost metrics, JSON response, confidence. |
| Taxonomy | Industry, niche, business type, business model and tag definitions. |
| Export Jobs | Requested filters, format, status, generated file reference, timestamp. |

# 15. Dashboard, Search & Filtering

The internal dashboard should focus on operational visibility and practical data use rather than complex analytics in the first release.

| **Area** | **Requirements** |
| --- | --- |
| Summary KPIs | Total URLs, processed, pending, failed, active, blocked, product-based, service-based, hybrid. |
| Industry Distribution | Counts by industry, niche and business type. |
| Search | Website, company name, keyword, product or service search. |
| Filters | Industry, niche, business type, model, country, product/service, confidence, crawl status, review status. |
| Record Review | Open a company, inspect source pages/evidence, edit classification and approve/reprocess. |
| Export | Export current filter result to Excel / CSV / JSON. |

# 16. Failure Handling, Retry & Re-Crawling

Retry transient HTTP/network failures with controlled backoff.

Use browser rendering only when lightweight retrieval does not produce usable content.

Record blocked/CAPTCHA sites rather than attempting aggressive bypass.

Retain detailed failure reason and retry count.

Allow manual requeue of failed or low-confidence websites.

Design for optional re-crawling after a configurable period so company classifications can be refreshed.

# 17. Responsible Crawling & Security

Use rate limits and domain-level concurrency controls.

Define organizational policy for robots.txt handling and respect applicable legal/contractual constraints.

Identify the crawler with a controlled user-agent when appropriate.

Do not execute downloaded site code outside the browser sandbox required for rendering.

Do not store unnecessary credentials, cookies or personal data.

Do not attempt CAPTCHA/security bypass in the standard workflow.

Validate/sanitize extracted website values before displaying or exporting them.

# 18. Recommended MVP Scope

| **MVP Capability** | **Included** |
| --- | --- |
| Bulk import 60K+ URLs | Yes |
| URL normalization & validation | Yes |
| Homepage + important-page discovery | Yes |
| 5-10 page crawl limit | Yes |
| Content cleaning | Yes |
| Company description | Yes |
| Product / Service / Hybrid classification | Yes |
| Products & services extraction | Yes |
| Industry / niche taxonomy | Yes |
| B2B/B2C classification | Yes |
| Location extraction where available | Yes |
| Evidence + confidence | Yes |
| PostgreSQL storage | Yes |
| Admin dashboard & filters | Yes |
| Manual review / correction | Yes |
| Excel / CSV / JSON export | Yes |
| Technology detection | Phase 2 |
| Lead scoring / sales intelligence | Phase 2 |
| CRM integration | Phase 2 |
| Periodic re-crawl automation | Phase 2 |

# 19. Success / Acceptance Criteria

The system can ingest and queue at least 60,000 website records without manual batching.

The majority of active, publicly accessible websites can be crawled without full browser rendering.

The system can distinguish product, service and hybrid businesses with reviewable evidence.

Products and services are extracted into structured fields rather than only free-form summaries.

Every processed company receives an industry/niche classification or an explicit low-confidence/unclassified status.

Failed websites do not interrupt the broader batch and retain actionable failure reasons.

Users can search/filter processed records and export the filtered dataset to a well-structured Excel workbook.

Excel output contains the agreed columns, uses one company per main-sheet row and supports large dataset exports.

AI model/prompt version and analysis timestamps are retained for auditability and reprocessing.

# 20. Recommended Rollout Approach

Before processing the full 60,000+ dataset, the recommended approach is to validate the crawler and taxonomy against a representative pilot of approximately 500-1,000 websites. The pilot should include different countries, industries, site technologies, small/large sites and both product- and service-based companies.

| **Stage** | **Purpose** |
| --- | --- |
| Pilot Crawl | Validate page discovery, blocking rates, content extraction and runtime. |
| Classification QA | Manually review a sample and identify taxonomy/prompt gaps. |
| Refinement | Adjust taxonomy, extraction rules, confidence thresholds and AI prompt. |
| Scale Test | Run a larger batch to validate throughput and cost. |
| Full Processing | Process remaining URLs with monitoring, retries and export checkpoints. |

# 21. Final Recommendation

The project should be treated as an internal Website Intelligence and Business Classification platform, not merely a web crawler. The immediate value is the ability to transform an unstructured URL list into a clean, searchable and exportable business dataset. The architecture should remain intentionally modular so crawling, AI models, taxonomy rules and export logic can evolve independently.

| **Recommended Product Direction: **Build the MVP around Crawl → Understand → Classify → Validate → Store → Search → Excel Export. Once the 60K dataset is clean and reliable, the same foundation can be extended into lead scoring, opportunity detection, sales intelligence and personalized outreach. |
| --- |

# Appendix A - Example Main Excel Row

| **Column** | **Example Value** |
| --- | --- |
| Website | https://example.com |
| Company Name | Example Technologies |
| Company Description | Custom software and AI solutions provider for enterprise clients. |
| Primary Business Type | Service-Based |
| Business Model | B2B |
| Primary Industry | Technology |
| Primary Niche | Software Development |
| Products | None Identified |
| Services | Web Development; Mobile App Development; AI Development |
| Target Customers | SMBs; Enterprises |
| Headquarters Country | United States |
| Business Keywords / Tags | software development; AI; mobile apps; cloud |
| Overall Confidence % | 94 |
| Evidence URLs | /about; /services; /ai-development |
| Pages Crawled Count | 5 |
| Crawl Status | Completed |
| Classification Review Status | Auto Accepted |