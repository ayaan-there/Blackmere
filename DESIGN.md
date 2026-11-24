# Design — pinned "blue / purple / pink fintech mobile" world

The user pinned a screenshot. The roll is bypassed by that explicit brief.

## THESIS
A trading terminal that reads like a modern investment app, not a spreadsheet:
one dark-blue data hero followed by saturated portfolio-style signal cards.
It refuses the dense grey trading-desk grid as the first thing the trader sees.

## OWN-WORLD
- Page ground: soft very-light blue-grey in light mode, deep midnight navy in dark.
- Hero: navy → electric blue gradient, large rounded corners, white type, a
  three-series line chart with cyan / magenta / purple lines, gridlines and
  a four-step time axis. Small white pill for the active timeframe.
- Signal cards: 2×2 saturated blocks — deep blue, magenta, purple, teal — with
  a tiny circular glyph, a small label, a large figure, and a faint oversized
  watermark letter. Equal size, generous radius.
- Bottom pill navigation with circular items carries the timeframe switch and
  the theme toggle. Standard table panels carry the dense detail below.
- Typography: Archivo for display/headings, IBM Plex Sans for UI labels,
  IBM Plex Mono for every number. Fixed rem scale, tabular figures.

## STORY
The trader sees the index and signal immediately, reads four decisive cards,
then drills into charts and tables only when needed.

## FIRST VIEWPORT
Brand/status line, dark hero with spot + change + multi-series chart and legend,
compact KPI chips, then the four signal cards. Bottom pill nav is persistent.

## FORM
Pinned mobile-fintech card world; no seed roll (brief-pinned direction).
Desktop widens the same world instead of switching to a different design.

## SETTLED TOKENS (after build)
- Page light `#F3F5FB`, dark `#080C17`; panel light `#FFFFFF`, dark `#111A2E`.
- Hero gradient navy `#0A1A48 → #1546A8 → #082A75`, radius 22px.
- Signal cards: blue `#0E3AA8→#1246D8`, magenta `#B81BB8→#E83FD0`,
  purple `#5B2FD0→#8A5BFF`, teal `#078E9F→#16C2D4`; radius 20px, watermark glyph.
- Hero: single cyan `#35D0E0` area-line of REAL Nifty index price (Angel One
  OHLC candles, 3/5/9/15-min), real price axis and real time axis. Detail
  charts below remain PCR / VWAP / PIVOT, unchanged.
- Type: Archivo display, IBM Plex Sans labels, IBM Plex Mono numbers.
- Dock: navy pill, centered on mobile, bottom-right from 900px up.
- Positive/negative light `#12875E` / `#D13A48`, dark `#4FE0B4` / `#FF6B78`.
