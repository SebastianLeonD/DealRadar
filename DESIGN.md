# Design — "Market Bulletin" editorial theme

White-paper newspaper look: sharp black rules, one red accent, mono for data.

## Colors (CSS vars in styles.css)
- `--paper` #fdfcf9 / `--paper-2` #f6f4ee — backgrounds
- `--ink` #14120e / `--ink-soft` #55534d — text
- `--hairline` #d9d5ca — light borders
- `--red` #e0311b (the single accent) / `--red-dark` #b32615, `--good` #1e6b3c
- Hard offset shadows: `--shadow` 5px 5px 0 ink, `--shadow-sm` 3px

## Typography
- `--serif` Young Serif — wordmark, headlines
- `--sans` Libre Franklin — body, nav sections
- `--mono` IBM Plex Mono — data strips, prices, meta, buttons (uppercase + letter-spacing)

## Conventions
- 1.5px solid ink borders on interactive blocks; hover = translate(-1px,-1px) + shadow-sm
- "Wire" strips (mono, 10-11px, letter-spaced, uppercase) for status rows — TopBar wire, SourceLog
- Cards: 3/4 image box with ink bottom border, title then price row
- Save toggle (`.savebtn` ☆/★): boxed button top-right of the image; filled red when saved
- Stale (saved but off-sale): greyscale image, red corner-to-corner diagonal line, rotated red "NO LONGER ON SALE" ribbon — still clickable
- Fonts self-hosted via @fontsource (no external requests)
