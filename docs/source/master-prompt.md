# Master Implementation Prompt: AI-Powered Website Intelligence & Business Classification System

## 1. Your Role

Act as a Senior Python Backend Engineer, Web Crawling Specialist, AI/LLM Engineer, Database Architect, and Full-Stack Developer.

Build a production-oriented **AI-Powered Website Intelligence & Business Classification System** that processes 60,000+ website URLs and converts them into structured, searchable, evidence-backed business intelligence.

Before writing code, inspect the existing repository and requirements. Reuse existing components where appropriate. Do not replace working architecture without a clear reason.

**Critical implementation rule:** Work phase by phase. Start with repository assessment and Phase 1 only. Do not implement the entire platform in one massive change.

## 2. Main Objective

The system must determine what each website's business does and store the findings in a structured database.

For each website, aim to extract:

- Website URL and normalized domain
- Company or organization name
- Short business description
- Primary business type
- Business model
- Primary and secondary industries
- Niche and sub-niche
- Products and services
- Target customers and markets
- B2B, B2C, B2B2C, marketplace, SaaS, agency, manufacturer, distributor, retailer, or other applicable model
- Geographic markets and service locations, where supported by evidence
- Source pages and supporting text for extracted facts
- Confidence scores and evidence quality
- Crawl status, classification status, timestamps, and error details

Do not infer unsupported facts. When evidence is insufficient, return an explicit status such as `insufficient_evidence` or `unclassified`.

## 3. Required Crawling Strategy

Use the following combined strategy:

**Focused crawling + sitemap-assisted discovery + HTTP-first fetching + structured-data extraction + conditional Playwright fallback.**

These techniques have different responsibilities and must not be treated as interchangeable.

### A. Focused crawling — decide WHICH pages to visit

Do not crawl every URL on every website. Prioritize pages that are most likely to reveal what the business does.

Start with the homepage, then discover and rank relevant internal pages.

Recommended page priority:

1. Homepage
2. About / Company / Who We Are
3. Products / Product Categories
4. Services / Solutions
5. Industries / Markets / Who We Serve
6. Contact / Locations, when useful for identifying geography
7. Other relevant pages when existing evidence is insufficient

Avoid spending the page budget on login pages, account pages, carts, checkout pages, irrelevant blog posts, duplicate URLs, and unrelated resources.

The crawler should stop when it has enough useful evidence or reaches its configurable page budget.

Start with a configurable budget of approximately **5–10 useful pages per website**. Make this adjustable, and allow the crawler to stop earlier when sufficient evidence is available.

### B. Sitemap-assisted discovery — find candidate pages

- Check `robots.txt` for sitemap references.
- Attempt common sitemap locations when appropriate.
- Parse sitemap indexes and sitemap URLs.
- Use internal links when sitemap data is missing or incomplete.
- Rank discovered pages using URL paths, page titles, link text, and relevance to business information.
- Deduplicate canonical URLs and equivalent internal URLs.
- Do not crawl an entire sitemap blindly; feed candidates into the focused page-selection process.

### C. HTTP-first fetching — choose the cheapest suitable retrieval method

Use a standard asynchronous HTTP client, preferably `httpx` or `aiohttp`, as the first attempt.

For each candidate page:

1. Fetch the page using HTTP.
2. Handle redirects, response codes, content types, timeouts, and encoding.
3. Extract HTML text, metadata, headings, links, and structured data.
4. Evaluate whether the result contains meaningful business information.
5. If the content is sufficient, use it without launching a browser.
6. If the page is a JavaScript shell, has very little meaningful content, or otherwise fails configurable content-quality checks, consider the browser fallback.

A successful HTTP status code alone does not mean the page contains useful content.

Content-quality checks should consider meaningful text length, title, headings, paragraphs, business-related terms, and whether the page appears to contain rendered content rather than an empty application shell.

### D. Conditional Playwright fallback — render only when necessary

Use Playwright only when the HTTP response cannot provide sufficient useful content and browser rendering is likely to improve it.

- Keep browser rendering disabled by default until the fallback condition is met.
- Use timeouts and resource limits.
- Avoid loading unnecessary images, media, advertisements, and third-party resources where feasible.
- Apply the same domain rate limits and crawl policies as the HTTP crawler.
- Record whether a page was retrieved through HTTP or browser rendering.
- If browser rendering fails, record the failure and continue according to retry and recovery policies.

Do not use Playwright for every page by default. The goal is to control processing time and resource usage without sacrificing classification quality.

### E. Structured-data extraction

Before relying exclusively on AI, extract useful machine-readable information where available:

- JSON-LD
- Schema.org organization and local-business fields
- Page title and meta description
- Open Graph metadata
- Canonical URL
- Relevant product or service structured data

Treat structured data as supporting evidence, not unquestionable truth. Validate it and preserve its source.

### F. Required overall pipeline

Implement the system using this sequence:

1. URL ingestion
2. URL normalization and deduplication
3. URL validation and safe-target checks
4. Persistent job creation and queueing
5. Sitemap-assisted and internal-link discovery
6. Focused page prioritization
7. HTTP-first fetching
8. Content-quality evaluation
9. Conditional Playwright fallback
10. Structured-data and text extraction
11. Content cleaning, normalization, and deduplication
12. Evidence collection
13. AI business-fact extraction
14. Business classification and taxonomy mapping
15. Schema validation and confidence calculation
16. Database persistence and indexing
17. Dashboard, search, filtering, review, and exports

## 4. Recommended Technical Architecture

Use a modular, asynchronous, queue-based architecture.

Recommended default stack, subject to the existing repository:

- **Backend API:** Python and FastAPI
- **Database:** PostgreSQL
- **Database migrations:** Alembic or an equivalent migration tool
- **Job queue:** Celery with Redis, or an appropriate existing durable queue
- **HTTP crawler:** `httpx` or `aiohttp`
- **HTML extraction:** BeautifulSoup and a readability-style content extractor
- **Browser fallback:** Playwright
- **Data validation:** Pydantic and JSON Schema
- **Frontend:** Next.js and React, if a frontend is not already present
- **Raw content and exports:** local/object storage, depending on deployment
- **Logging and monitoring:** structured logs, metrics, job tracking, and error reporting

Do not add every technology automatically. First inspect the repository, identify what is already installed, and explain any material stack changes before making them.

Keep the following components logically separate:

- API and URL ingestion
- URL normalization and validation
- Crawl orchestration and queue management
- HTTP fetching
- Browser rendering
- Sitemap and link discovery
- Content extraction and cleaning
- AI extraction and classification
- Taxonomy management
- Evidence and confidence calculation
- Persistence and search
- Dashboard and exports

## 5. URL Management and Job Processing

The system must accept URLs through CSV, Excel, API, and manual entry where supported.

Implement:

- URL normalization
- Duplicate detection
- Domain extraction
- Invalid URL handling
- Existing-record detection
- Optional recrawl of previously processed websites
- Batch import summaries
- Persistent job records
- Retry handling
- Failure reasons
- Job status and progress tracking

Use explicit lifecycle states, for example:

`pending → queued → crawling → extracting → classifying → completed`

Include appropriate failure, retry, cancelled, and insufficient-evidence states.

Make job transitions observable and recoverable after worker restarts. Do not rely exclusively on in-memory state.

## 6. Crawl Safety, Domain Controls, and Reliability

Implement conservative, transparent crawling. Do not design the crawler around aggressive IP rotation or evading website restrictions.

Required controls:

- Respect applicable robots.txt directives and relevant legal, contractual, and site-access restrictions.
- Use a descriptive User-Agent, such as `WebsiteIntelligenceBot/1.0 (+https://your-company.example/crawler)`, with a real contact or policy URL in production.
- Apply configurable per-domain request rates and concurrency limits.
- Use timeouts, exponential backoff, and retry limits.
- Slow down or stop when a domain returns repeated `429`, `403`, or other blocking responses.
- Track domain health, response latency, failures, and last successful fetch.
- Use stable, reputable outbound networking.
- Do not bypass CAPTCHAs, authentication, access controls, or anti-bot protections.
- Validate URLs and every redirect target to mitigate SSRF.
- Block localhost, private, link-local, and restricted network targets unless explicitly required and safely authorized.
- Limit response size, content types, decompression, redirect depth, and browser resource usage.
- Prevent crawl loops, duplicate fetches, and unbounded link discovery.

Use domain-level backoff and scheduling so one problematic site does not block the entire batch.

## 7. Content Processing and Evidence

Store cleaned, useful content separately from crawl metadata. Where appropriate, retain raw HTML or extracted text in controlled storage with configurable retention.

Implement:

- HTML boilerplate removal
- Navigation/footer noise reduction
- Duplicate content detection
- Canonical URL handling
- Content hashing
- Extraction-quality checks
- Reprocessing only when content changes or an explicit recrawl is requested

Every important business fact should have traceable evidence.

An evidence record should include:

- Website identifier
- Source page URL
- Field or claim supported
- Extracted value or supporting snippet
- Retrieval timestamp
- Extraction method
- Evidence quality
- Relevant confidence information

Do not treat an AI-generated statement as source evidence. Evidence must originate from retrieved website content or other explicitly approved sources.

## 8. AI Extraction and Classification

Keep business-fact extraction separate from taxonomy classification.

### Stage A: Business-fact extraction

Extract supported facts from the cleaned pages and return schema-constrained JSON.

Example structure:

```json
{
  "company_name": null,
  "business_description": null,
  "business_type": null,
  "business_model": [],
  "industries": [],
  "niches": [],
  "products_services": [],
  "target_customers": [],
  "geographic_markets": [],
  "evidence": [],
  "insufficient_evidence": true
}
```

Treat this as an illustrative schema. Define and version the actual production schema with Pydantic or JSON Schema.

The model must distinguish explicit facts from uncertain inferences. Missing information should be represented as null, an empty list, or a defined uncertainty state rather than fabricated.

### Stage B: Taxonomy classification

Map the extracted facts to controlled business classification categories.

The taxonomy should support:

- Industry
- Sub-industry
- Niche and sub-niche
- Business type
- Business model
- Target market
- Products and services categories

Store taxonomy categories in a versioned, maintainable data source. Prefer stable category IDs over free-form labels.

The AI may recommend a new category for human review, but must not silently invent or create taxonomy categories during normal classification.

### Local LLM requirement

The initial system should support a local LLM so that classification does not require a paid external AI API.

- Design a provider abstraction so the model can be changed without rewriting the pipeline.
- Support a local runtime such as Ollama during development, with a compatible production inference server if needed.
- Benchmark an appropriate local instruction model, such as a Qwen-family model, against representative websites before selecting the final model.
- Validate structured output, handle malformed responses, and retry safely.
- Make the model name and generation settings configurable.
- Keep AI workers separate from crawl workers.
- Measure throughput, memory usage, classification quality, and cost before scaling.

Do not assume that a local model will be accurate enough without evaluation. Optional cloud escalation may be added later, but it must be explicitly configurable and must not be required for the initial system.

## 9. Confidence and Human Review

Do not rely solely on the model's self-reported confidence.

Calculate confidence using available signals, including:

- Evidence quality and specificity
- Number and relevance of useful pages examined
- Agreement between different source pages
- Completeness of extracted fields
- Taxonomy match quality
- Validation failures or contradictions
- Whether the claim is explicit or inferred

Define configurable thresholds for:

- High-confidence automatic acceptance
- Medium-confidence review
- Low-confidence or insufficient-evidence classification

Keep the confidence method transparent and versioned. Provide a review workflow for uncertain or conflicting results.

## 10. Database and Search

Design a normalized PostgreSQL schema with appropriate indexes and migrations.

Consider separate entities for:

- Websites
- Crawl jobs
- Discovered pages
- Page fetch attempts
- Extracted content or content references
- Business profiles
- Classification results
- Taxonomy categories
- Evidence records
- Errors and retry history
- Review decisions

Store raw crawl status separately from AI classification status. A website can crawl successfully but remain unclassified, or crawl partially and still provide useful evidence.

Include timestamps, content hashes, model/version information, taxonomy version, and processing metadata.

Support searching and filtering by company, domain, industry, niche, business model, products/services, geography, status, and confidence.

## 11. Dashboard and Export

Provide an interface to:

- Upload CSV or Excel URL lists
- Review import and deduplication results
- Start and monitor batches
- View crawl and classification progress
- Search and filter classified businesses
- Open a website's extracted profile
- Inspect source pages and supporting evidence
- Review low-confidence classifications
- Retry failed jobs
- Export results

Support CSV, Excel, and JSON exports.

Include, where available:

- Original URL
- Normalized domain
- Company name
- Business description
- Business type
- Business model
- Primary industry
- Secondary industries
- Niche and sub-niche
- Products and services
- Target markets
- Geographic markets
- Confidence
- Evidence references
- Crawl status
- Classification status
- Last processed timestamp
- Error or review status

Ensure exports can handle large datasets without loading all records into memory at once.

## 12. Scale and Performance

The target is at least 60,000 websites.

At five fetched pages per website, the workload is approximately 300,000 page fetches. Treat this as a planning estimate, not a fixed crawl requirement.

Implement:

- Bounded concurrency
- Independent crawl and AI worker pools
- Queue backpressure
- Persistent scheduling
- Per-domain rate limits
- Idempotent jobs
- Content-hash-based reprocessing
- Retry and recovery logic
- Batch-level progress
- Metrics for success rate, latency, errors, and throughput

Do not assume a particular worker count, IP count, or processing time will be sufficient without measuring the workload.

Benchmark with a representative pilot before increasing concurrency. Scale gradually while monitoring target-site responses and system resources.

## 13. Testing Requirements

Create automated tests for:

- URL normalization and deduplication
- URL validation and redirect safety
- Sitemap parsing
- Internal-link discovery
- Focused page ranking
- HTTP-first retrieval
- Detection of insufficient or JavaScript-dependent content
- Playwright fallback decisions
- HTML extraction and cleaning
- Structured-data extraction
- Content hashing and duplicate detection
- Domain throttling and backoff
- Retry and failure states
- AI schema validation
- Taxonomy mapping
- Evidence association
- Confidence calculation
- Database persistence and job recovery
- CSV, Excel, and JSON exports

Use controlled website fixtures to test normal HTML, redirects, errors, empty responses, duplicate pages, sitemap files, structured data, and JavaScript-rendered content.

Tests must not depend on aggressively crawling real websites. Mock external network calls where appropriate.

Run the relevant tests after each implementation phase and report actual results. Do not claim a test passed unless it was executed and passed.

## 14. Implementation Phases

### Phase 1 — Repository assessment and URL ingestion

First inspect the repository and requirements. Report:

- Current repository structure
- Existing framework and dependencies
- Existing features that can be reused
- Gaps against this master prompt
- Proposed database entities and job lifecycle
- Exact files to create or modify
- Phase 1 implementation plan and tests

Then implement only Phase 1:

- URL ingestion
- URL normalization
- Deduplication
- Basic URL safety validation
- PostgreSQL persistence and migrations, if consistent with the existing architecture
- Persistent job creation
- Tests for the implemented functionality

Run the tests and summarize actual results before proceeding.

### Phase 2 — Focused hybrid crawler

Implement:

- HTTP-first asynchronous fetching
- Sitemap-assisted discovery
- Internal-link discovery and page ranking
- Configurable 5–10 useful-page budget
- Content-quality evaluation
- Conditional Playwright fallback
- Structured-data extraction
- Domain-level rate limiting and backoff
- Safe redirect and target validation
- Retry handling and persistent crawl statuses
- Controlled fixture-based tests

Return cleaned, deduplicated, AI-ready website content with source URLs and extraction metadata.

### Phase 3 — AI extraction and classification

Implement:

- Local LLM integration
- Versioned structured-output schemas
- Business-fact extraction
- Controlled taxonomy mapping
- Evidence association
- Validation and insufficient-evidence handling
- Confidence calculation
- Model/version tracking
- AI-specific retries and tests

### Phase 4 — Search, review, and export

Implement:

- Business-profile queries
- Filters and pagination
- Evidence display
- Low-confidence review workflow
- Retry controls
- CSV, Excel, and JSON export
- Dashboard integration and tests

### Phase 5 — Hardening and scaling

Implement and verify:

- Observability
- Security review
- Queue recovery
- Database indexing
- Resource limits
- Performance benchmarks
- Deployment configuration
- Backup and retention policies
- Representative pilot results
- Gradual scale-up plan

## 15. Pilot and Acceptance Criteria

Begin with a small, representative set of approximately 100 websites. Expand to 500–1,000 only after validating reliability and output quality, then increase in controlled stages.

Measure:

- Website crawl success rate
- Useful-content retrieval rate
- Relevant-page discovery quality
- Browser fallback frequency
- Classification accuracy against manually reviewed examples
- Evidence correctness
- Confidence calibration
- Insufficient-evidence rate
- Processing latency
- Retry and failure rates
- Resource usage and throughput

Do not claim the system is production-ready or capable of processing all 60,000 websites within a particular time until benchmarks support that claim.

## 16. Coding Rules

- Inspect before modifying.
- Reuse working code where possible.
- Follow existing project conventions.
- Use modular, typed, maintainable code.
- Keep configuration outside source code.
- Never commit credentials or secrets.
- Add migrations for schema changes.
- Avoid unnecessary dependencies.
- Keep crawler, AI, API, and frontend responsibilities separate.
- Provide meaningful logs and actionable error messages.
- Make jobs idempotent and recoverable.
- Do not silently swallow exceptions.
- Do not invent implementation results, test results, or benchmark figures.
- Keep each phase reviewable and runnable before starting the next phase.

## 17. Your First Action

**Start with Phase 1 only.**

Inspect the existing repository and requirements, identify the current architecture and gaps, and provide a concise implementation plan. Then implement URL ingestion, normalization, deduplication, safe validation, database persistence, persistent job creation, and relevant tests.

Do not start Phase 2 until Phase 1 is implemented, tested, and its actual results have been reported.

The ultimate objective is a reliable Website Intelligence platform that identifies what businesses do from their websites, with traceable evidence and scalable processing—not a crawler that merely downloads pages.