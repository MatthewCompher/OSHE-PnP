# OSHE Pick and Place: documentation site

> **Superseded (2026-11-18):** the current documentation is the MkDocs site in
> `Documentation/docs/` (config `Documentation/mkdocs.yml`). Its content was carried over and
> updated from these pages; this folder is kept for reference until the team decides to remove it.

Plain static HTML. Open `index.html` in a browser, or host the folder anywhere (GitHub Pages works).

| File | Page |
|---|---|
| `index.html` | Home / overview and status |
| `hardware.html` | V3 hardware, specs, CAD index, printing |
| `build.html` | How to build (V3, in order) |
| `electronics.html` | Electronics, pin map, safety |
| `software.html` | Software stack, Pi + Klipper setup |
| `macros.html` | G-code macros |
| `moonraker.html` | Moonraker, cameras (crowsnest), integration |
| `slicer.html` | pnpslice and the job file format |
| `vision.html` | pnpvision calibration and running jobs |
| `history.html` | V1 / V2 / V3 history |
| `about.html` | Team, roadmap, contributing, license |

- **Images:** save pictures into `images/` using the names in `images/IMAGE-LIST.md`. They
  replace the gray placeholders automatically (via `site.js`).
- **Things to confirm** are marked on the pages with yellow "⚠ Verify" boxes. Search for
  `note verify` to find them all.
- **Style:** `style.css`, Michigan Tech black and gold. It follows the reader's light/dark
  system setting. All colors are variables at the top of the file: light mode in `:root`,
  dark mode in the `prefers-color-scheme: dark` block.
- **Mobile:** below 860 px wide the sidebar becomes a slide-out menu (button in the header).
- **Callouts:** `<div class="note">` (green), `<div class="note warn">` (red),
  `<div class="note verify">` (gold).
- The header, sidebar and footer are repeated in every page. If you add a page, add it to the
  sidebar in all of them.
