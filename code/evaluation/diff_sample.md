# Sample evaluation — per-case diff

- claims scored: **20**
- runtime: 35.4s  cost: $0.6013
- per-field exact-match accuracy:
    - evidence_standard_met: 60.0%
    - valid_image: 65.0%
    - claim_status: 60.0%
    - issue_type: 40.0%
    - object_part: 90.0%
    - severity: 55.0%
- risk_flags micro: P 63.9%  R 79.3%  F1 70.8%

## claim_status (headline)

| user_id | object | gold | pred | ok |
|---|---|---|---|---|
| user_001 | car | supported | supported | ✓ |
| user_002 | car | not_enough_information | not_enough_information | ✓ |
| user_004 | car | supported | not_enough_information | ✗ |
| user_007 | car | supported | supported | ✓ |
| user_005 | car | contradicted | not_enough_information | ✗ |
| user_006 | car | not_enough_information | not_enough_information | ✓ |
| user_003 | car | supported | not_enough_information | ✗ |
| user_008 | car | contradicted | not_enough_information | ✗ |
| user_009 | laptop | supported | supported | ✓ |
| user_010 | laptop | supported | not_enough_information | ✗ |
| user_011 | laptop | supported | supported | ✓ |
| user_012 | laptop | supported | supported | ✓ |
| user_018 | laptop | supported | supported | ✓ |
| user_020 | laptop | contradicted | contradicted | ✓ |
| user_015 | package | supported | supported | ✓ |
| user_030 | package | supported | not_enough_information | ✗ |
| user_031 | package | supported | supported | ✓ |
| user_032 | package | not_enough_information | not_enough_information | ✓ |
| user_033 | package | contradicted | not_enough_information | ✗ |
| user_034 | package | contradicted | not_enough_information | ✗ |

## Per-case misses (only cases with at least one wrong field)

**user_001** (car):
  - severity: `medium` → `high`

**user_002** (car):
  - valid_image: `true` → `false`
  - issue_type: `broken_part` → `dent`
  - risk_flags: -claim_mismatch

**user_004** (car):
  - evidence_standard_met: `true` → `false`
  - claim_status: `supported` → `not_enough_information`
  - issue_type: `crack` → `glass_shatter`
  - severity: `medium` → `high`
  - risk_flags: +claim_mismatch,manual_review_required

**user_007** (car):
  - issue_type: `broken_part` → `glass_shatter`

**user_005** (car):
  - evidence_standard_met: `true` → `false`
  - valid_image: `true` → `false`
  - claim_status: `contradicted` → `not_enough_information`
  - issue_type: `scratch` → `unknown`
  - severity: `low` → `unknown`

**user_006** (car):
  - valid_image: `true` → `false`
  - issue_type: `unknown` → `crack`
  - risk_flags: +manual_review_required,non_original_image -wrong_angle

**user_003** (car):
  - evidence_standard_met: `true` → `false`
  - valid_image: `true` → `false`
  - claim_status: `supported` → `not_enough_information`
  - risk_flags: +claim_mismatch,manual_review_required

**user_008** (car):
  - evidence_standard_met: `true` → `false`
  - claim_status: `contradicted` → `not_enough_information`
  - issue_type: `broken_part` → `unknown`
  - object_part: `front_bumper` → `hood`
  - severity: `high` → `unknown`

**user_009** (laptop):
  - issue_type: `crack` → `glass_shatter`
  - severity: `medium` → `high`

**user_010** (laptop):
  - evidence_standard_met: `true` → `false`
  - valid_image: `true` → `false`
  - claim_status: `supported` → `not_enough_information`
  - severity: `medium` → `unknown`
  - risk_flags: +claim_mismatch,manual_review_required

**user_011** (laptop):
  - issue_type: `stain` → `water_damage`

**user_018** (laptop):
  - issue_type: `crack` → `glass_shatter`
  - severity: `medium` → `high`

**user_030** (package):
  - evidence_standard_met: `true` → `false`
  - claim_status: `supported` → `not_enough_information`
  - risk_flags: +claim_mismatch,manual_review_required

**user_032** (package):
  - issue_type: `unknown` → `missing_part`
  - risk_flags: +claim_mismatch,user_history_risk -cropped_or_obstructed,damage_not_visible

**user_033** (package):
  - evidence_standard_met: `true` → `false`
  - valid_image: `true` → `false`
  - claim_status: `contradicted` → `not_enough_information`
  - issue_type: `unknown` → `none`
  - object_part: `unknown` → `box`
  - severity: `low` → `unknown`
  - risk_flags: -claim_mismatch

**user_034** (package):
  - evidence_standard_met: `true` → `false`
  - valid_image: `true` → `false`
  - claim_status: `contradicted` → `not_enough_information`
  - issue_type: `none` → `torn_packaging`
  - severity: `none` → `unknown`
  - risk_flags: +non_original_image -damage_not_visible
