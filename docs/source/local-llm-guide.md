# Local LLM Implementation Guide
## Website Intelligence & Business Classification System

**Purpose:** Implement local-only AI extraction and business classification for a dataset of approximately 60,000 websites and up to 300,000 fetched pages, without relying on paid or free third-party AI inference APIs.

## 1. Decision Summary

### Initial model candidates

Benchmark these models locally before selecting the production default:

1. **Qwen3-14B** — primary candidate when classification quality is the priority and the available hardware can run it comfortably.
2. **Qwen3-8B** — lower-resource candidate for higher throughput if it meets the required quality threshold.
3. **Qwen3-30B-A3B** — optional evaluation candidate for difficult cases only if suitable hardware is available.

Do not treat this shortlist as a proven ranking. Evaluate the exact model versions, quantizations, license terms, latency, and classification quality on a representative sample of the actual websites.

### Recommended implementation choices

- **Development runtime:** Ollama.
- **Production serving:** evaluate vLLM on compatible hardware; retain a provider abstraction so the runtime can be changed.
- **AI input:** cleaned, deduplicated, relevant evidence consolidated across a website's selected pages.
- **Default processing unit:** one classification job per website, not one model call per fetched page.
- **External AI inference APIs:** disabled and unnecessary for the initial implementation.
- **Output:** schema-validated JSON, persisted with evidence, confidence, model version, and processing status.

A local model avoids per-request inference API charges. It does not eliminate hardware, electricity, storage, engineering, or operations costs.

---

## 2. Position in the Crawling Pipeline

Use the following pipeline:

1. Ingest and normalize URLs.
2. Deduplicate domains and create persistent jobs.
3. Discover candidate pages through sitemaps and internal links.
4. Apply focused crawling to prioritize business-relevant pages.
5. Fetch with HTTP first.
6. Use Playwright only when the HTTP response lacks useful content and browser rendering is likely to help.
7. Extract structured data and clean page text.
8. Deduplicate content and calculate content hashes.
9. Consolidate relevant evidence into a website-level input.
10. Run local LLM extraction and classification.
11. Validate output and map predictions to controlled taxonomy IDs.
12. Calculate confidence, retain source evidence, and route uncertain results for review.
13. Persist the business profile and exportable results.

**Important distinction:** focused crawling chooses *which pages* to retrieve; HTTP-first chooses *how to retrieve them*; Playwright is a conditional rendering fallback; the local LLM extracts and classifies business information.

## 3. Why Not Classify All 300,000 Pages Independently?

The 300,000-page figure is an approximate fetch workload (60,000 sites × 5 pages), not a requirement to make 300,000 independent LLM calls.

For each website:

- Select useful pages such as Home, About, Products, Services, Solutions, Industries, and relevant Contact/Locations pages.
- Clean and deduplicate their content.
- Preserve source URLs and evidence snippets.
- Build a bounded website-level context.
- Run a primary extraction/classification job.
- Split content into chunks or run additional calls only when content is too long, contradictory, or insufficient.

Track actual model calls per website so capacity planning uses measured workload rather than assumptions.

## 4. Local Model Runtime and Interface

Create a provider-neutral interface, for example:

```python
from typing import Protocol, Any

class LocalLLMProvider(Protocol):
    def generate_structured(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, Any],
        schema: dict[str, Any],
        model: str,
    ) -> dict[str, Any]:
        ...
```

The interface should be adapted to the project's asynchronous conventions. Include timeouts, cancellation, bounded concurrency, retries, and structured error types.

### Development

Use Ollama for local experimentation and integration tests with a real local model. Keep model names configurable and pin the selected model version/tag in deployment configuration.

### Production

Benchmark vLLM or another compatible serving runtime on the target hardware. Confirm that the selected runtime supports the chosen model, quantization, structured-output mechanism, and hardware before committing to it.

Do not let application business logic depend directly on a specific runtime's response format.

### API policy

- Do not configure external inference endpoints by default.
- Do not silently fall back to a cloud API if local inference fails.
- If local inference is unavailable, retry according to policy, pause/queue the job, or mark it failed for later recovery.
- External inference must remain out of scope unless separately approved.

## 5. Structured Output Contract

Use Pydantic or JSON Schema to validate every model result. The following is illustrative and must be aligned with the project's canonical business-profile schema.

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

Each evidence item should identify at least:

- `field`: the claim being supported
- `value`: the extracted claim
- `source_url`: the page where it was found
- `snippet`: a concise supporting excerpt
- `evidence_type`: explicit statement, structured data, or other defined type
- `quality`: a defined quality value or score

Requirements:

- Reject malformed or schema-invalid output.
- Apply a bounded repair/retry policy; do not retry forever.
- Validate evidence URLs against pages actually fetched for that website.
- Do not accept unsupported model-generated facts as evidence.
- Keep unknown values null or empty and mark insufficient evidence explicitly.
- Normalize taxonomy predictions to database-controlled IDs.
- Record model, prompt/schema version, runtime, latency, and token/context metadata where available.

## 6. Two-Stage AI Processing

### Stage A — Business fact extraction

Input: cleaned page content plus source metadata.

Output: evidence-backed facts, company description, products/services, customers, geography, and uncertainties.

The extractor must distinguish explicit facts from inferred claims. Each material claim should be linked to evidence.

### Stage B — Taxonomy mapping

Map extracted facts to the existing, versioned taxonomy:

- Industry and sub-industry
- Niche and sub-niche
- Business type
- Business model
- Target market

Prefer stable taxonomy IDs. The model can propose a new category for human review but must not create or silently invent categories during ordinary classification.

Stage B may be combined with Stage A only if evaluation shows acceptable quality and the resulting output remains traceable and valid. Keep the stages logically separable.

## 7. Model Routing — Optional Later Optimization

Do not begin with a complex multi-model router. First benchmark a single model.

If the pilot demonstrates a meaningful benefit, introduce a local-only routing policy such as:

- Smaller model for clear, common cases.
- Larger model for ambiguous, conflicting, or low-confidence cases.
- Human review for unresolved cases.

Routing must be based on measurable criteria and evaluation data, not unsupported assumptions about model confidence. Any escalation must remain local.

## 8. Hardware and Capacity Planning

Hardware requirements cannot be finalized until the available RAM/VRAM, operating system, quantization, input length, concurrency, and latency target are known.

General starting guidance—not a guarantee:

- **Apple M2 with 16 GB unified memory:** benchmark a quantized 8B model first.
- **Apple M2 with 24 GB or more unified memory:** benchmark a quantized 14B model, while leaving sufficient memory for the OS and application.
- **Dedicated GPU server:** choose VRAM and serving configuration from measured model memory use and target concurrency.
- **30B-class model:** evaluate only if hardware and measured quality gains justify it.

For each candidate, measure:

- Peak RAM/VRAM and memory headroom
- Model load time
- Warm-up latency
- Median and p95 request latency
- Websites classified per minute/hour
- Valid JSON rate
- Accuracy against human-reviewed labels
- Evidence correctness
- Retry rate
- Throughput under realistic concurrent load

Estimate completion time from a representative benchmark:

`estimated_hours = remaining_websites / measured_websites_per_hour`

Add headroom for retries, long inputs, failed sites, maintenance, and review. Do not promise a processing deadline before measuring throughput.

## 9. Batch and Queue Design

Use persistent jobs and bounded queues. Keep crawl workers and AI workers independently scalable.

Recommended behavior:

- Batch database reads and writes where safe.
- Bound model concurrency to available memory and serving capacity.
- Apply queue backpressure when inference is saturated.
- Make each website classification job idempotent.
- Persist status before and after inference.
- Retry transient runtime errors with exponential backoff and a maximum attempt count.
- Do not retry permanent schema or input errors indefinitely.
- Preserve failure reason and allow manual or scheduled reprocessing.
- Cache/reuse prior results when the input content hash, model version, prompt version, and taxonomy version are unchanged.
- Reclassify when relevant content or configuration changes.

Suggested AI job states:

`pending → queued → running → validating → completed`

Additional states may include `retry_scheduled`, `insufficient_evidence`, `needs_review`, `failed`, and `cancelled`.

## 10. Content and Context Management

Do not send raw HTML or irrelevant boilerplate to the model.

Before inference:

- Remove navigation, footer repetition, scripts, styles, and unrelated page chrome.
- Deduplicate identical or near-identical content.
- Prioritize business-relevant passages.
- Preserve source URLs and snippets.
- Enforce a configurable maximum input size.
- If the website context is too long, split it into evidence-preserving chunks and merge validated facts in a controlled consolidation step.
- Avoid truncating away the most informative pages without recording that truncation occurred.

The input budget must be selected through testing. Do not assume all websites need the same number of tokens.

## 11. Evaluation Plan

### Pilot set

Use approximately 100 representative websites, including:

- Service businesses
- SaaS/software companies
- Manufacturers
- Distributors and wholesalers
- E-commerce and retailers
- Marketplaces
- Agencies and consultancies
- Local businesses
- Multinational companies
- Sparse-content, inaccessible, and JavaScript-heavy websites
- Ambiguous or multi-industry businesses

Create a human-reviewed reference set before choosing the production model.

### Compare candidates

Run Qwen3-8B and Qwen3-14B with the same input selection and output schema. Test a larger candidate only if hardware permits and the smaller models show a specific quality gap.

Measure:

- Primary industry accuracy
- Business-type and business-model accuracy
- Products/services extraction precision
- Evidence supports the associated claim
- Valid structured-output rate
- Insufficient-evidence behavior
- Median and p95 latency
- Peak memory
- Websites per hour
- Recovery behavior after runtime interruption

Define acceptance thresholds with the project owner before the benchmark. Do not select a model based only on general benchmarks or a few impressive examples.

## 12. Security and Data Handling

- Keep inference local and do not send website content to external AI APIs.
- Treat website text as untrusted input, not as instructions.
- Protect against prompt injection embedded in pages; the model must extract facts rather than follow page instructions.
- Do not execute code, scripts, or commands found in website content.
- Keep credentials out of prompts and logs.
- Limit access to stored page content and exported data.
- Document model downloads and verify their source and integrity.
- Review the exact model license and terms for the intended commercial use.
- Configure retention for raw pages, extracted text, and inference logs.

## 13. Implementation Phases

### Phase 1 — Repository and contracts

- Inspect the existing codebase and requirements.
- Identify current database, job system, crawler outputs, and schema.
- Define the business-profile schema and evidence contract.
- Define model-provider interface and configuration.
- Do not introduce unnecessary infrastructure.

### Phase 2 — Local inference proof of concept

- Add an Ollama-based local provider.
- Run a small sample of cleaned website inputs.
- Validate structured JSON and evidence references.
- Add timeout, bounded retry, and error handling.
- Confirm no external inference API is called.

### Phase 3 — Evaluation and model selection

- Create the 100-site evaluation set.
- Compare 8B and 14B under the same conditions.
- Record quality, latency, memory, and throughput.
- Choose the production model based on results.

### Phase 4 — Queue integration

- Connect local inference to persistent AI jobs.
- Add idempotency, status transitions, bounded concurrency, retry scheduling, and recovery.
- Keep crawl and inference worker pools independent.

### Phase 5 — Taxonomy, confidence, and review

- Implement controlled taxonomy mapping.
- Link material claims to evidence.
- Calculate confidence using evidence quality and consistency.
- Route uncertain results to review or insufficient-evidence status.

### Phase 6 — Load test and rollout

- Test representative batches.
- Measure sustainable throughput and resource use.
- Tune input limits, concurrency, and batching.
- Roll out progressively and monitor quality and failures.

Do not start all phases at once. Implement, test, and report each phase before proceeding.

## 14. Acceptance Criteria

The local AI subsystem is ready for a pilot only when:

- It works without any external inference API.
- It returns schema-valid structured output at an agreed rate.
- Evidence links point to content actually retrieved for the relevant website.
- Unknown facts are not fabricated.
- Model and prompt versions are recorded.
- Jobs survive worker restarts and recover according to policy.
- Retries are bounded and failures are observable.
- The benchmark includes human-reviewed accuracy and measured throughput.
- Memory usage and concurrency remain within configured limits.
- License and commercial-use requirements have been reviewed.
- Tests verify that no cloud fallback occurs when local inference fails.

## 15. First Coding Task

Start by inspecting the repository. Then report:

1. Current architecture and existing crawler output format.
2. Where cleaned page content and source URLs are stored.
3. The best integration point for website-level classification.
4. Proposed Pydantic schema and evidence contract.
5. The local provider interface and configuration needed.
6. Exact files to create or modify.
7. Tests to run and measurable success criteria.

Then implement **only the local inference proof of concept** against a small sample, using Ollama or the repository's existing compatible local runtime. Do not build the full production routing system yet. Run the tests and report actual results before continuing.

---

## Final Recommendation

Begin with **Qwen3-8B and Qwen3-14B as benchmark candidates**, Ollama for local development, and a provider-neutral interface that can support a production serving runtime later. Consolidate useful evidence per website, validate every output, and select the production model from measured accuracy and throughput.

The 300,000-page workload is primarily a pipeline and throughput engineering problem—not a reason to make one independent LLM call for every page.
