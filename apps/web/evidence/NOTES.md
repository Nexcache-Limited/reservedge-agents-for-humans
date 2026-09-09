# UI-01 evidence notes

Captured against local WP-06 (`127.0.0.1:8000`) and Vite (`localhost:5173`). Screenshots and JSON under this directory stay uncommitted.

## Screens

| File | Viewport | Stage |
| --- | --- | --- |
| `inbox-narrow-320.png` | 320 CSS px (CSS harness) | UX-01 empty inbox |
| `inbox-live-320.png` | 320 CSS px (live React) | UX-01 empty inbox |
| `a1-live-320.png` | 320 CSS px (live React) | A1 PI review + confirm |
| `a2-live-320.png` | 320 CSS px (live React) | A2 Gate 1 |
| `offers-a3-live-320.png` / `a3-accept-live-320.png` | 320 CSS px (live React) | Compare + A3 |
| `receipt-live-320.png` | 320 CSS px (live React) | Simulated receipt |
| `offers-200pct.png` | 1280 window @ Chrome 200% page zoom | Compare harness before pinch |
| `offers-200pct-pinch.png` | same + `Emulation.setPageScaleFactor(2)` | Visual viewport crop |
| `viewport-measurements.json` | Chrome CDP | Executable overflow + zoom |
| `live-320-measurements.json` | Chrome CDP vs Vite | Live React overflow |
| `live-http-golden.json` | WP-06 HTTP | A1–A4 + exact A4 replay |

## Keyboard / focus / live regions

Executable evidence is in `src/screens/a11y.ui01.test.tsx` and `src/screens/approvals.ui01.test.tsx`. At 200% page zoom, focus on “Select SkyShield” had outline `rgb(23, 27, 32) solid 2px`.

## Reduced motion

`apps/web/src/styles.css` disables transitions/animations under `prefers-reduced-motion: reduce`, in addition to the UI-00 kit rule for primitives. WP-07 progress lanes reuse the same reduced-motion rule; they do not add fake timers or percentages.

## Process-local SSE

`GET /v1/simulations/airport-parking/intents/{intent_id}/events` is an in-memory progress stream. Restarting the API process discards the buffer. The dispatch snapshot remains authoritative for ranking.

## Contrast

UI-00 token contrast tests remain the source of truth. Product wrappers do not introduce new colors.

## Viewport / overflow

`src/screens/a11y.ui01.test.tsx` renders every required screen at a 320 CSS-pixel host and asserts `scrollWidth <= clientWidth`. `pnpm --filter @itaa/web test:viewport` repeats the measurement in Chrome (`Emulation.setDeviceMetricsOverride` width=320, DSF=1). Live React (Vite) repeats it in `live-320-measurements.json`.

Measured 320 CSS px (harness and live React): every required screen `scrollWidth = clientWidth = 320`.

## 200% zoom mechanism

Not `deviceScaleFactor=2` and not a 2× screenshot.

1. Chrome user-data-dir `default_zoom_level = ln(2)/ln(1.2) ≈ 3.8018` (Chromium 200% page-zoom step, same scale Cmd+Plus uses). In a 1280×900 window this produced a **640 CSS-pixel** layout viewport (`innerWidth` 640, `clientWidth` 640, `scrollWidth` 640). Host `devicePixelRatio` was 2 because the display is 2×; that is not the zoom mechanism. Screenshot: `offers-200pct.png`.
2. Then CDP `Emulation.setPageScaleFactor(2)` applied pinch-zoom: `visualViewport.scale` became 2 while the CSS layout viewport stayed 640. That visual viewport crops the screenshot (`offers-200pct-pinch.png`); it is not document overflow.

## Live WP-06 HTTP evidence (after WP-06-R2+A1)

Default `itaa_api.app:app` ranks canonical fixture offers. Catalog lookup in the UI is by supplier token so unique Offer IDs still resolve comparison attributes.

Locked vector (keyed by supplier token, not Offer ID):

| Supplier | scoreMicros | rank | recommended |
| --- | --- | --- | --- |
| SkyShield | 671000 | 1 | true |
| ParkDirect | 660000 | 2 | false |
| TerminalFlex | 535000 | 3 | false |

Downside USD 29.00 versus ParkDirect. Recapture against a fresh API after rebase onto `7047799`:

- `live-http-golden.json`: SkyShield 671000 / ParkDirect 660000 / TerminalFlex 535000, totals 14800 / 11900 / 16900, recommended SkyShield, unique Offer IDs (`of_000…0f`, not fixture `of_…a2`), exact A4 replay.
- `offers-a3-live-320.png` + `a3-accept-live-text.json`: live React at 320 CSS px shows 671,000 / 660,000 / 535,000, USD 29.00, and A3 SkyShield **USD 148.00** with EV charging from the supplier-token catalog.

UI01-AC04 is no longer blocked on seeded economics.
