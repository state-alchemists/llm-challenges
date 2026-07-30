# Text Utils Fixes

## Findings & Changes
- Fixed `slugify` to lowercase characters before testing for alnum/space/hyphen (`src/text_utils.py:16-21`).
- Fixed consecutive hyphen collapsing in `slugify` using standard library `re.sub(r"-+", "-", joined)` (`src/text_utils.py:22`).
- Fixed `truncate` to correctly compute the truncation boundary factoring in the length of the suffix (`src/text_utils.py:27-36`).

## Backlinks
- [HUD Index](../index.md)
