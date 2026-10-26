---
name: Terminal Editorial Intelligence
colors:
  surface: '#10141a'
  surface-dim: '#10141a'
  surface-bright: '#353940'
  surface-container-lowest: '#0a0e14'
  surface-container-low: '#181c22'
  surface-container: '#1c2026'
  surface-container-high: '#262a31'
  surface-container-highest: '#31353c'
  on-surface: '#dfe2eb'
  on-surface-variant: '#bacbb9'
  inverse-surface: '#dfe2eb'
  inverse-on-surface: '#2d3137'
  outline: '#859585'
  outline-variant: '#3b4a3d'
  surface-tint: '#00e475'
  primary: '#75ff9e'
  on-primary: '#003918'
  primary-container: '#00e676'
  on-primary-container: '#00612e'
  inverse-primary: '#006d35'
  secondary: '#bac7dd'
  on-secondary: '#243142'
  secondary-container: '#3d4a5b'
  on-secondary-container: '#acb9ce'
  tertiary: '#ffdcdd'
  on-tertiary: '#67001b'
  tertiary-container: '#ffb5b9'
  on-tertiary-container: '#aa0032'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#62ff96'
  primary-fixed-dim: '#00e475'
  on-primary-fixed: '#00210b'
  on-primary-fixed-variant: '#005226'
  secondary-fixed: '#d6e3f9'
  secondary-fixed-dim: '#bac7dd'
  on-secondary-fixed: '#0f1c2c'
  on-secondary-fixed-variant: '#3b4859'
  tertiary-fixed: '#ffdadb'
  tertiary-fixed-dim: '#ffb2b7'
  on-tertiary-fixed: '#40000d'
  on-tertiary-fixed-variant: '#92002a'
  background: '#10141a'
  on-background: '#dfe2eb'
  surface-variant: '#31353c'
  surface-base: '#0D1117'
  surface-elevated: '#171D25'
  surface-accent: '#1B2838'
  border-subtle: '#2A323D'
  text-primary: '#F0F3F6'
  text-muted: '#8B949E'
  trend-positive: '#00E676'
  trend-negative: '#F43F5E'
  trend-neutral: '#FFB74D'
typography:
  headline-xl:
    fontFamily: Barlow Condensed
    fontSize: 48px
    fontWeight: '700'
    lineHeight: 52px
    letterSpacing: -0.02em
  headline-xl-mobile:
    fontFamily: Barlow Condensed
    fontSize: 36px
    fontWeight: '700'
    lineHeight: 40px
    letterSpacing: -0.01em
  headline-lg:
    fontFamily: Barlow Condensed
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 36px
    letterSpacing: -0.01em
  headline-lg-mobile:
    fontFamily: Barlow Condensed
    fontSize: 26px
    fontWeight: '600'
    lineHeight: 30px
    letterSpacing: 0em
  headline-md:
    fontFamily: Barlow Condensed
    fontSize: 22px
    fontWeight: '600'
    lineHeight: 26px
    letterSpacing: 0.01em
  body-lg:
    fontFamily: Noto Sans
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-md:
    fontFamily: Noto Sans
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  body-sm:
    fontFamily: Noto Sans
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
  data-lg:
    fontFamily: JetBrains Mono
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 24px
    letterSpacing: -0.03em
  data-md:
    fontFamily: JetBrains Mono
    fontSize: 14px
    fontWeight: '500'
    lineHeight: 18px
    letterSpacing: -0.02em
  label-caps:
    fontFamily: JetBrains Mono
    fontSize: 11px
    fontWeight: '600'
    lineHeight: 14px
    letterSpacing: 0.06em
  badge-num:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '700'
    lineHeight: 12px
    letterSpacing: 0.02em
spacing:
  gutter: 1rem
  gutter-desktop: 1.5rem
  margin: 1rem
  margin-desktop: 2rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 0.75rem
  space-lg: 1.25rem
  space-xl: 2rem
---

## Brand & Style

This design system establishes an analytical, high-velocity daily briefing interface where editorial confidence intersects with gaming telemetry and data journalism. It merges the focused immersion of PC gaming clients with the authoritative density of a financial terminal.

### Target Audience & Emotional Intent
Built for indie studio leads, game scouts, publishers, and industry analysts who monitor market volatility, discovery algorithms, and breakout velocity. The interface projects high authority, crisp informational velocity, precision, and forensic neutrality.

### Aesthetic Movement: High-Density Terminal Editorial
- **Structural Integrity:** Crisp 1px geometric bounds replace diffused elevations. The system rejects soft drop shadows and excessive blur in favor of structured data cells, ruled dividers, and razor-sharp compartmentalization.
- **Data Contrast:** Ultra-deep slate backdrops provide maximum contrast for sharp numeric trends, telegraphic status chips, and vivid market vectors (bullish breakouts vs. declining velocity).
- **Tabular Rigor:** Compact vertical rhythm prioritizing information density over decorative white space, allowing users to cross-reference multiple games, platforms, and velocity metrics without perceptual fatigue.

## Colors

The palette is engineered specifically for prolonged data legibility in high-density, low-light environments. 

### Palette Architecture
- **Primary (`#00E676`):** The kinetic pulse of the system. Used exclusively for positive delta shifts, breakout velocity badges, active filters, and primary editorial focal points.
- **Secondary (`#1B2838`):** Steam-inspired deep slate used for interactive container backgrounds, active hover states, and structural grouping.
- **Tertiary (`#F43F5E`):** Coral crimson reserved strictly for negative sentiment, falling player counts, velocity deceleration, and critical alerts.
- **Neutral (`#0D1117`):** The baseline canvas. Deep, non-reflective obsidian-slate that prevents chromatic bleed across charts and dense typography.

### Functional Color Governance
- Text hierarchy is strictly bipartite: `#F0F3F6` delivers high-contrast readability for titles and metrics, while `#8B949E` carries contextual metadata, units, and timestamps.
- Borders (`#2A323D`) maintain exactly 1px thickness to frame data cells without encroaching upon visual whitespace.
- Backgrounds remain dark across all screen states; light mode is intentionally unsupported to preserve continuous terminal contrast.

## Typography

The typographic hierarchy is split across three dedicated functional engines:

1. **Editorial Headlines (`Barlow Condensed`):** Communicates assertive journalistic authority. Condensed proportions allow high-impact headlines and narrative game titles to fit cleanly across tight analytic columns without awkward wrapping.
2. **Reading Prose & Meta (`Noto Sans`):** Provides pristine CJK/Latin universal legibility across compact paragraphs, studio attributions, and qualitative editorial summaries.
3. **Telemetry & Data Tables (`JetBrains Mono`):** Fixed-width tabular figures guarantee alignment down complex data columns, concurrent player counts, percentage deltas, review ratios, and rankings.

### Typographic Rules
- All table data cells, ranks, dates, and currency metrics must be rendered using `JetBrains Mono` with tabular lining active.
- Category slugs and column headers employ `label-caps` in full uppercase with expanded letter-spacing (`0.06em`) for rapid spatial scanning.
- Editorial narrative intros pair `headline-lg` with `body-lg` to separate commentary from raw terminal metric feeds.

## Layout & Spacing

This design system uses a fixed-width grid model anchored by analytical dashboards.

### Grid & Density Framework
- **Desktop (>= 1280px):** 12-column rigid grid with `gutter-desktop` (24px) and `margin-desktop` (32px). Maximum content containment caps at 1440px to ensure data line-lengths remain scan-efficient.
- **Tablet (768px - 1279px):** 8-column layout with 16px gutters; telemetry sidebars collapse into sticky top control ribbons.
- **Mobile (< 768px):** 4-column layout with 16px margins. Multi-metric tables convert into single-column card stacks with horizontal metric strips.

### Spacing Philosophy
Spacing values adhere strictly to a dense 4px base scale:
- `space-xs` (4px) and `space-sm` (8px) govern tight interior element relationships (badge padding, icon-to-metric offsets, row gaps).
- `space-md` (12px) and `space-lg` (20px) define card cell padding and modular group separation.
- `space-xl` (32px) is reserved for major editorial report splits and canvas section dividers.

## Elevation & Depth

Depth is established through flat tonal stratification and crisp geometric delineation rather than atmospheric drop shadows.

### Elevation Tiers
1. **Canvas Foundation (`#0D1117`):** The lowest layer, representing the viewport substrate.
2. **Structural Panels (`#171D25`):** All report cards, table bodies, and data modules sit on this level, enclosed by a uniform `1px solid #2A323D` border.
3. **Header & Hover Accents (`#1B2838`):** Interactive rows, selected filters, and sticky headers use this tone to denote active interaction states without shifting vertical geometry.

### Flat Precision Rules
- **No Drop Shadows:** Drop shadows are strictly prohibited on cards, chips, buttons, and popovers. Depth is communicated solely through surface color contrast and border illumination.
- **Border Illumination on Focus:** Active rows, hovered cards, and focused form controls transition their border color from `#2A323D` to `#00E676` or `#F0F3F6`, giving an immediate mechanical state change.
- **Translucent Overlays:** Modal dialogs and flyout drawers use `rgba(13, 17, 23, 0.85)` accompanied by a `4px` backdrop blur to isolate background clutter while keeping dashboard data silhouettes visible.

## Shapes

The design system employs a strict zero-radius (`0px`) structural geometry.

### Angular Geometry
- **Sharp Perimeters:** All containers, data modules, cards, buttons, badges, and input fields feature unrounded 90-degree corners. This enforces the technical, Bloomberg-terminal aesthetic.
- **Diagonal Accent Cuts (Optional Functional Flourish):** For top-tier breakout game cards or rank #1 callouts, a single 45-degree chamfered corner (`clip-path: polygon(...)`, 8px offset) on the top-right edge may be applied to indicate editorial status.
- **Dividers:** Horizontal and vertical dividers maintain a uniform 1px thickness without rounded ends, slicing the canvas into precise tabular compartments.

## Components

### Buttons
- **Primary Action:** Solid `#00E676` fill, `#0D1117` text (`JetBrains Mono`, 12px, weight 700, uppercase). Sharp edges, no shadow. Active state triggers a 1px inner border of `#FFFFFF`.
- **Secondary / Utility Action:** Transparent background with a `1px solid #2A323D` outline and `#F0F3F6` text. Hover changes background to `#1B2838` and border to `#8B949E`.
- **Destructive Action:** Transparent with `1px solid #F43F5E` outline and `#F43F5E` text.

### Stat Chips & Badges
- **Rank Badges:** Monospace tabular counters with a dark slate background (`#171D25`) and a crisp `1px solid #2A323D` border. Top 3 ranks feature inverted styling (`#00E676` text or solid fill).
- **Delta Velocity Chips:** Compact pill-less rectangular chips. Positive deltas use `rgba(0, 230, 118, 0.1)` background with solid `#00E676` text and a prefix `▲` glyph. Negative deltas use `rgba(244, 63, 94, 0.1)` background with `#F43F5E` text and a prefix `▼` glyph.
- **Platform Tags:** Neutral `#171D25` container with `#8B949E` label (`Steam`, `Itch.io`, `GOG`, `Epic`). Monospaced, 11px uppercase.

### Sparklines & Analytics Micro-Charts
- Rendered with 1.5px continuous paths.
- Positive trajectory renders strictly in `#00E676`; negative trajectory in `#F43F5E`.
- Chart backgrounds do not employ heavy gradient fills; they remain bare or utilize a faint 5% opacity vertical falloff to keep table rows scannable.

### Data Tables & Rows
- Table headers use `label-caps` in `#8B949E`, bordered at the base with a `1px solid #2A323D`.
- Alternate row striping is omitted. Rows indicate state solely via a hover transition to `#171D25` and an active left-edge indicator rule (`2px solid #00E676`).
- All numeric data aligns to the right; all game identities and genres align to the left.

### Input Fields & Terminal Search
- Background set to `#171D25`, text in `#F0F3F6`, bordered by `1px solid #2A323D`.
- Focus shifts border directly to `#00E676` with zero glow/shadow.
- Includes a dedicated monospaced keyboard shortcut cue on the trailing edge (e.g., `[ / ]` or `[ CMD+K ]`) rendered in `#8B949E`.

### Daily Report Cards
- Bounded by `1px solid #2A323D` on `#171D25`. 
- Incorporates a structured header block: small monospaced category tracker, headline in `Barlow Condensed`, followed by a split-pane layout: qualitative editorial assessment on the left, quantitative velocity telemetry and sparkline on the right.