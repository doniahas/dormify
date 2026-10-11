# Shared styles

Two files, imported exactly once from `src/index.jsx` (before `App`):

| File | Role |
|---|---|
| `tokens.css` | Design tokens as `--df-*` custom properties on `:root`: colours, font stacks, radii, shadows, shell dimensions. Harvested from the values the pages already use; declaring them changes nothing visually. |
| `global.css` | The global reset (`* { margin; padding; box-sizing }`) and the `body` font/background rules that previously lived in `App.jsx`'s inline `<style>`. |

Page styles live beside the components that use them. Pages that have been
migrated use CSS Modules; some pages still carry inline `<style>` blocks or a
plain stylesheet (`UsersPage.css`, `BuildingsPage.global.css`) and move to
CSS Modules when they are next reworked.

## Convention: CSS Modules

- Each page/component gets a sibling `Name.module.css`; import it as
  `import styles from './Name.module.css'` and reference `styles.className`.
  Vite scopes the class names, which retires the selector collisions between
  pages (`.card`, `.pill`, `.stat-card`, ...).
- Use the tokens: `color: var(--df-color-text-subtle)` rather than a literal
  `#64748b`. Add a token here when a value recurs across pages; keep one-off
  values local.
- Page-local `:root` blocks (`--page-bg`, `--inv-*`, `--ap-*`) are migrated
  onto `--df-*` tokens as each page moves; until then they coexist because
  the shared tokens use the `--df-` prefix.
- `vitest.config.mjs` keeps `css: false`; tests assert behaviour, not styles.
- No Tailwind, no CSS-in-JS: the toolchain stays plain CSS + PostCSS
  (`postcss.config.cjs`), which already handles vendor prefixes.
