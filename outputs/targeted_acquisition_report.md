# Targeted exploratory acquisition report

## Scope
- Generated at (UTC): `2026-04-20T20:33:19.388382+00:00`
- Logic version: `targeted_skeptical_queue.v1`
- Freeze anchor: `KES-final` (id=8, uuid=freeze-20260408T142800Z)
- Freeze runs: `[11, 18, 20, 22, 23, 24]`
- Staging label: `Exploratory candidate for validation - not paper-safe by default`

## Safe insertion points in current pipeline
- `resolve-targets` for converting seed channels/handles into stable IDs.
- `run-batch` for controlled acquisition from curated target lists.
- This queue script as a pre-acquisition and pre-coding targeting layer.
- Human coding + adjudication + freeze refresh required before paper-facing claims.

## Candidate selection heuristics (deterministic)
- Skepticism and proof-demand lexical hits in comment text.
- Top-rank position preference (rank <= 3, especially rank = 1).
- AI-discourse context via comment text or video metadata mentions.
- Channel prior from frozen resolved data (skepticism-rich channels).
- Engagement and disagreement context to prioritize informative cases.
- Dedup safeguard by `(video_id, normalized_comment_text)` before ranking.

## Output counts
- Total comments in DB: `33467`
- Candidate threads exported: `400`
- Candidate videos exported: `200`
- Candidate channels represented: `43`
- Newly acquired channels/videos/comments in this run: `0` (this package generated a targeted queue from local data only).
- Exploratory material already outside selected freeze runs: `88` channels, `248` videos, `4869` comments.

## Top 10 candidate videos

| rank | run_id | channel_niche | video_id | video_score | candidate_threads | skeptical_or_proof_threads |
|---:|---:|---|---|---:|---:|---:|
| 1 | 25 | Tech | @aitechdailyshorts_video_1 | 10.966 | 1 | 1 |
| 2 | 26 | Tech | @WesRoth_video_1 | 10.966 | 1 | 1 |
| 3 | 18 | Tech | opghSX24clM | 10.495 | 7 | 4 |
| 4 | 21 | Tech | UC_EXAMPLE_TECH_001_video_1 | 10.466 | 1 | 1 |
| 5 | 11 | Tech | j5h9dBtWZXM | 10.292 | 3 | 3 |
| 6 | 11 | Tech | oO9GLC2iKy8 | 10.077 | 6 | 5 |
| 7 | 11 | Tech | WSCbyIMXwS4 | 9.992 | 4 | 3 |
| 8 | 17 | Lifestyle | 3KRoJHT8zF8 | 9.678 | 5 | 5 |
| 9 | 27 | Tech | @WesRoth_video_2 | 9.532 | 3 | 2 |
| 10 | 11 | Tech | JHF2t-S2nm0 | 9.406 | 2 | 1 |

## Top 10 candidate threads

| rank | run_id | video_id | comment_db_id | comment_rank | thread_score | reasons |
|---:|---:|---|---:|---:|---:|---|
| 1 | 25 | @aitechdailyshorts_video_1 | 33418 | 1 | 10.200 | skepticism lexical cue; proof-demand lexical cue; top-ranked comment; higher engagement |
| 2 | 26 | @WesRoth_video_1 | 33423 | 1 | 10.200 | skepticism lexical cue; proof-demand lexical cue; top-ranked comment; higher engagement |
| 3 | 21 | UC_EXAMPLE_TECH_001_video_1 | 23595 | 1 | 9.700 | skepticism lexical cue; proof-demand lexical cue; top-ranked comment; higher engagement |
| 4 | 11 | j5h9dBtWZXM | 3401 | 1 | 8.110 | proof-demand lexical cue; top-ranked comment; AI mention in comment; higher engagement |
| 5 | 27 | @WesRoth_video_2 | 33464 | 17 | 8.000 | skepticism lexical cue; proof-demand lexical cue; higher engagement |
| 6 | 23 | gtlRgIq-KtI | 26707 | 1 | 7.947 | skepticism lexical cue; top-ranked comment; AI mention in comment |
| 7 | 11 | bzWI3Dil9Ig | 5649 | 2 | 7.866 | skepticism lexical cue; top-ranked comment; AI mention in comment; higher engagement |
| 8 | 23 | Pw5M2_oTVV8 | 26736 | 1 | 7.861 | skepticism lexical cue; top-ranked comment; AI mention in comment |
| 9 | 11 | JHF2t-S2nm0 | 4682 | 2 | 7.847 | skepticism lexical cue; top-ranked comment; AI mention in video metadata; historically skepticism-rich channel; higher engagement |
| 10 | 11 | WSCbyIMXwS4 | 3103 | 3 | 7.677 | skepticism lexical cue; top-ranked comment; AI mention in comment; higher engagement |

## Validation boundary
- These outputs are exploratory candidate queues only and must not be used as validated evidence.
- Any paper-facing update requires human coding, disagreement handling, adjudication, and freeze linkage.
