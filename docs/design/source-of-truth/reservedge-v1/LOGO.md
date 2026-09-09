# Handoff: Reservedge identity

## The name

**Reservedge.** One word, one capital. Never *ReservEdge*, never *Reserve Edge*, never *RESERVEDGE* outside a mono eyebrow label. In running copy it is a proper noun and takes no article — "authorized through Reservedge", not "through the Reservedge".

## The mark

A bracket holding one dot.

The bracket is the approval gate: the product's core promise is that nothing about the user reaches a supplier without an explicit, itemised approval. The dot is the offer, sitting on the far side of the gate, released only once the user decides. Read as a whole it is an edge — the line the user holds, and the advantage of standing behind it.

**The bracket always opens to the right.** Mirrored, it reads as releasing the dot rather than holding it, which inverts the meaning. Do not flip, rotate, or animate the opening.

## Geometry

The glyph is drawn on a **16 × 16** grid:

```
bracket   M11 3.2 H5.6 V12.8 H11    stroke, round caps, no fill
dot       circle cx 12.7  cy 8  r 1.5   filled
```

Inside an icon container the glyph occupies **75% of the container width**, optically centred (the dot sits right of centre, so the glyph is placed on the geometric centre and not visually re-centred — the asymmetry is intentional).

| Container | Corner radius | Glyph size | Stroke (at 16-grid) | Fill |
|---|---|---|---|---|
| 80px | 22px | 46px | 1.8 | coral gradient |
| 64px | 18px | 48px | 1.8 | coral gradient |
| 48px | 14px | 27px | 1.8 | coral gradient |
| 32px | 10px | 18px | 2.0 | flat `#E85D2C` |
| 20px | 7px | 12px | 2.4 | flat `#E85D2C` |
| under 20px | — | — | — | do not use the mark; use a mono `Re` chip |

Stroke weight rises as the icon shrinks so the bracket holds its presence. The gradient is dropped below 32px, where a two-stop gradient reads as mud.

## Colour

| Use | Container | Glyph |
|---|---|---|
| App icon, marketing | `linear-gradient(140deg, #E85D2C, #F2974E)` | `#FFFFFF` |
| In-product (rail, app bar) | flat `#E85D2C` or the gradient at 30px+ | `#FFFFFF` |
| Monochrome positive | `#221F1A` | `#FFFFFF` |
| Monochrome negative | transparent, 1.5px `#E6E1D8` border | `#221F1A` |

**Never** place the mark on `--amber`, `--green`, `--info` or `--danger` fills. Those colours carry status meaning in the product and the mark would inherit it.

## Wordmark

**Schibsted Grotesk 700**, tracking `-0.03em` (`-0.02em` at 19px and below). No other weight, no italic, no outline, no all-caps.

Lockup: mark and wordmark on a shared baseline, gap = **32% of the mark's height** (11px gap at a 34px mark). Wordmark cap height aligns to the glyph's bracket height, not to the container.

**Clear space:** three quarters of the mark's height on all four sides. Nothing enters it — no nav item, no tagline, no divider.

**No tagline sits in the lockup.** If a line is needed it goes separately, in `--ws-ink-2` at body size, outside the clear space.

## Where it appears in the product

The wordmark appears in exactly **one** place per surface:

- **Web** — the dark nav rail, 28px mark + 15px wordmark + the mono `SIM` chip.
- **Mobile** — the app bar on the list screen only, 30px mark. On every other screen the back arrow takes that position and no logo is shown.

Everywhere else the mark stands alone. The name appears as running copy in one further place: the simulated receipt, "Authorized through Reservedge", with the 20px flat-coral mark. That is a provenance claim, not a logo placement.

## Assets in this bundle

| File | Use |
|---|---|
| `assets/reservedge-icon-gradient.svg` | 64px app icon, coral gradient. Master for all sizes 32px and up. |
| `assets/reservedge-icon-flat.svg` | Flat coral, for 32px and below. |
| `assets/reservedge-icon-ink.svg` | Monochrome positive. |
| `assets/reservedge-glyph.svg` | Glyph only, `currentColor` — inherits colour from CSS. Use inside your own containers. |
| `assets/reservedge-lockup-light.svg` | Horizontal lockup, ink wordmark, for light surfaces. |
| `assets/reservedge-lockup-dark.svg` | Horizontal lockup, cream wordmark, for dark surfaces. |
| `Reservedge Logo.dc.html` | Visual reference sheet — every lockup, the size ladder, clear space, the rules. |

**The two lockup SVGs carry live `<text>`.** They render correctly only where Schibsted Grotesk is available. Before any external distribution — press kit, partner assets, app store listing — convert that text to outlines. For in-product use, prefer the glyph SVG plus real text in your own type stack, so the wordmark inherits the app's font loading and stays selectable.

No raster assets are included. Generate PNG/ICO from `reservedge-icon-gradient.svg` at the sizes your platform requires; the size ladder above tells you when to switch to the flat variant.

## What has not been designed

- Vertical (stacked) lockup.
- Favicon at 16px — the mono `Re` chip is specified as the fallback but not drawn.
- Any motion treatment. The mark does not animate in these prototypes and should not until there is a reason.
