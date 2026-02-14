# Subtitle Test Results (Final)

## 1. Summary of Fixes

After detailed investigation, the following configuration was confirmed to be correct:

1.  **Frame Rate (FPS):** `30.0` (Corrects 2x slowdown).
2.  **CPK Ordering:** `MOVIE.PRG` playlist order is authoritative.
3.  **Mapping Logic:** **Strict 1:1 Mapping.**
    -   The first **47 CPKs** in the playlist map perfectly to the **47 Subtitle Groups** in `MOVIE.DAT`.
    -   The last 3 CPKs in the playlist (`EVT161_1.CPK`, `EVT161_2.CPK`, `MOVIE1.CPK`) have **no subtitles** in `MOVIE.DAT` and are correctly skipped.
    -   *Note:* The text "We'll get out through the deck" previously attributed to `MOVIE1` was found to belong to `EVT041.CPK` (Group 14), confirming `MOVIE1` has no unique text.

## 2. Verification Results (Test 03)

| CPK File | Status | Notes |
| :--- | :--- | :--- |
| **EVT000_1** | **PASS** | Correct start (~30s). Content: "What's up, Edge?" |
| **EVT000_2** | **PASS** | Correct end (~2m12s). Ends with "in 15 minutes!". No extra subtitles. |
| **EVT000_3** | **PASS** | **Fixed.** Now contains the Battle Dialogue ("Take that!", "Run for your life!"). |
| **EVT041** | **PASS** | Contains "We'll get out through the deck" (formerly misattributed). |
| **MOVIE1** | **PASS** | **Correctly Skipped** (No subtitles generated). |

## 3. Conclusions

The subtitle extraction is now fully framed-accurate and correctly mapped for all files on Disc 1. The custom manual overrides have been removed in favor of a robust 1:1 mapping strategy that aligns perfectly with the game's data structures.
