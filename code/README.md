# Multi-Modal Evidence Review — Solution

Verifies damage claims (car / laptop / package) by reasoning over the submitted
images together with the support-chat transcript, the user's claim history, and
the minimum image-evidence requirements. Each claim becomes **one Claude Opus
4.8 vision call** that returns the 14 required output fields; the result is then
clamped to the contract's allowed values and written to `output.csv`.

## How it works

```
claims.csv ─┐
user_history.csv ─┤  build a "case" per claim  ─►  one Claude Opus 4.8
evidence_requirements.csv ─┤  (transcript + history +     vision call
images/ ─┘     requirements + base64 images)   (adaptive thinking,
                                                 prompt-cached rules)
                                                        │
                                                        ▼
                                   parse JSON ─► clamp to allowed enums
                                                        │
                                                        ▼
                                                   output.csv (14 cols)
```

### Why this design
- **One call per claim** (not per image): the model compares multiple photos in
  context — needed for cases like mismatched front/full vehicle shots.
- **Rules in a cached system prompt:** the large constant rule block is sent with
  `cache_control`, so its input tokens are billed once and reused across claims.
- **Images are primary truth:** the prompt ranks visual evidence above the
  transcript; user history only adds `risk_flags`, never overrides the image.
- **Prompt-injection safe:** transcript text and any text *inside* images are
  treated as untrusted data; instruction-like image text triggers
  `text_instruction_present` (see sample case_020, test cases 008/036/048/055).
- **Determinism layer:** every enum field is clamped to the allowed list and
  invented values snap to `unknown`, so the CSV is always contract-valid.

## Layout

```
code/
├── main.py                       # entry point: claims.csv -> output.csv
├── requirements.txt
├── .env.example                  # copy to .env, add ANTHROPIC_API_KEY
├── claim_pipeline/
│   ├── schema.py                 # allowed values + Pydantic output model
│   ├── data.py                   # CSV loading, lookups, image base64 encoding
│   ├── prompt.py                 # system prompt + per-claim message builder
│   ├── client.py                 # Anthropic vision call (stream, retry, usage)
│   ├── normalize.py              # clamp model output to allowed enums
│   └── runner.py                 # concurrency + cost estimation
└── evaluation/
    ├── main.py                   # score the pipeline on sample_claims.csv
    └── evaluation_report.md      # operational analysis (cost/latency/limits)
```

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r code/requirements.txt

cp code/.env.example code/.env      # then edit code/.env and add your key
# or: export ANTHROPIC_API_KEY=sk-ant-...
```

The key is read from the environment only (via `code/.env` or the shell). It is
never hardcoded, and `.env` is git-ignored.

## Run

```bash
# Evaluate on the labeled sample first (prints accuracy + confusion + flag F1):
python code/evaluation/main.py

# Produce predictions for the full test set:
python code/main.py                 # writes output.csv at the repo root

# Helpful flags:
python code/main.py --limit 5       # smoke test on the first 5 claims
python code/main.py --workers 8     # more concurrent API calls
python code/main.py --claims dataset/claims.csv --out output.csv
```

## Output columns (in order)

`user_id, image_paths, user_claim, claim_object, evidence_standard_met,
evidence_standard_met_reason, risk_flags, issue_type, object_part, claim_status,
claim_status_justification, supporting_image_ids, valid_image, severity`

## Cost, latency & rate limits

- ~64 model calls total (20 sample + 44 test), one per claim, ~1–2 images each.
- Concurrency via a thread pool (`--workers`, default 6) with SDK + in-loop retry
  and exponential backoff for 429/5xx.
- Prompt caching on the rules block reduces repeated input-token cost.
- Live per-run token usage and a USD cost estimate are printed at the end of each
  run. Full analysis is in [`evaluation/evaluation_report.md`](evaluation/evaluation_report.md).

## Model

`claude-opus-4-8` with adaptive thinking and streaming. Override the model by
editing `MODEL` in `claim_pipeline/client.py`.
