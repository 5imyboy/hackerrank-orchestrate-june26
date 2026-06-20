# Sample evaluation — per-case diff

- claims scored: **20**
- runtime: 33.2s  cost: $0.5789
- per-field exact-match accuracy:
    - evidence_standard_met: 80.0%
    - valid_image: 85.0%
    - claim_status: 80.0%
    - issue_type: 60.0%
    - object_part: 90.0%
    - severity: 55.0%
- risk_flags micro: P 80.0%  R 69.0%  F1 74.1%

## claim_status (headline)

| user_id | object | gold | pred | ok |
|---|---|---|---|---|
| user_001 | car | supported | supported | ✓ |
| user_002 | car | not_enough_information | supported | ✗ |
| user_004 | car | supported | supported | ✓ |
| user_007 | car | supported | supported | ✓ |
| user_005 | car | contradicted | contradicted | ✓ |
| user_006 | car | not_enough_information | contradicted | ✗ |
| user_003 | car | supported | supported | ✓ |
| user_008 | car | contradicted | contradicted | ✓ |
| user_009 | laptop | supported | supported | ✓ |
| user_010 | laptop | supported | supported | ✓ |
| user_011 | laptop | supported | supported | ✓ |
| user_012 | laptop | supported | supported | ✓ |
| user_018 | laptop | supported | supported | ✓ |
| user_020 | laptop | contradicted | contradicted | ✓ |
| user_015 | package | supported | supported | ✓ |
| user_030 | package | supported | supported | ✓ |
| user_031 | package | supported | supported | ✓ |
| user_032 | package | not_enough_information | supported | ✗ |
| user_033 | package | contradicted | contradicted | ✓ |
| user_034 | package | contradicted | supported | ✗ |

## issue_type (headline)

| user_id | object | gold | pred | ok |
|---|---|---|---|---|
| user_001 | car | dent | dent | ✓ |
| user_002 | car | broken_part | scratch | ✗ |
| user_004 | car | crack | crack | ✓ |
| user_007 | car | broken_part | crack | ✗ |
| user_005 | car | scratch | none | ✗ |
| user_006 | car | unknown | crack | ✗ |
| user_003 | car | dent | dent | ✓ |
| user_008 | car | broken_part | none | ✗ |
| user_009 | laptop | crack | crack | ✓ |
| user_010 | laptop | broken_part | broken_part | ✓ |
| user_011 | laptop | stain | stain | ✓ |
| user_012 | laptop | dent | dent | ✓ |
| user_018 | laptop | crack | crack | ✓ |
| user_020 | laptop | none | none | ✓ |
| user_015 | package | crushed_packaging | crushed_packaging | ✓ |
| user_030 | package | torn_packaging | torn_packaging | ✓ |
| user_031 | package | water_damage | water_damage | ✓ |
| user_032 | package | unknown | missing_part | ✗ |
| user_033 | package | unknown | none | ✗ |
| user_034 | package | none | torn_packaging | ✗ |

## Per-case misses (only cases with at least one wrong field)

**user_001** (car):
  - severity: `medium` → `high`

**user_002** (car):
  - evidence_standard_met: `false` → `true`
  - claim_status: `not_enough_information` → `supported`
  - issue_type: `broken_part` → `scratch`
  - severity: `unknown` → `medium`
  - risk_flags: -manual_review_required,wrong_object

**user_007** (car):
  - issue_type: `broken_part` → `crack`

**user_005** (car):
  - issue_type: `scratch` → `none`
  - severity: `low` → `none`
  - risk_flags: +damage_not_visible -claim_mismatch

**user_006** (car):
  - valid_image: `true` → `false`
  - claim_status: `not_enough_information` → `contradicted`
  - issue_type: `unknown` → `crack`
  - risk_flags: +manual_review_required,non_original_image -wrong_angle

**user_003** (car):
  - risk_flags: -blurry_image

**user_008** (car):
  - evidence_standard_met: `true` → `false`
  - issue_type: `broken_part` → `none`
  - object_part: `front_bumper` → `hood`
  - severity: `high` → `none`

**user_009** (laptop):
  - severity: `medium` → `high`

**user_018** (laptop):
  - severity: `medium` → `high`

**user_032** (package):
  - evidence_standard_met: `false` → `true`
  - valid_image: `false` → `true`
  - claim_status: `not_enough_information` → `supported`
  - issue_type: `unknown` → `missing_part`
  - severity: `unknown` → `medium`
  - risk_flags: +user_history_risk -cropped_or_obstructed,damage_not_visible

**user_033** (package):
  - evidence_standard_met: `true` → `false`
  - valid_image: `true` → `false`
  - issue_type: `unknown` → `none`
  - object_part: `unknown` → `box`
  - severity: `low` → `none`
  - risk_flags: -claim_mismatch

**user_034** (package):
  - claim_status: `contradicted` → `supported`
  - issue_type: `none` → `torn_packaging`
  - severity: `none` → `medium`
  - risk_flags: +non_original_image -damage_not_visible
