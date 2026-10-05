# RetryGuard nebula entrance

The first page contains only a full-viewport animated nebula and two actions:

- **Enter workspace** opens the execution workspace at `#workspace`.
- **How it works** opens the existing explanation dialog without executing anything.

The previous hero, sculpture and scope strip are no longer mounted on the workspace page. All backend functionality and API contracts remain intact. Clicking the RetryGuard logo, or using browser Back after entering, returns to the entrance. Existing run state is retained while moving between these views. The shader unmounts and releases GPU resources on workspace entry.

## Run

```sh
python -m retryguard.web
```

Open http://127.0.0.1:8765. No Node setup is needed to use the packaged app: the built page is included. The Python server and all 22 protected source/test/configuration files are unchanged.

## Frontend structure

The frontend project root is `frontend/`, separate from the Python package.

| Path | Purpose |
| --- | --- |
| `components/ui/liquid-shader.tsx` | User-supplied nebula shader, with compatibility and lifecycle adjustments |
| `components/ui/nebula-entrance.tsx` | Two-button entrance, using Lucide icons |
| `demo.tsx` | Standalone shader demo with the supplied prop defaults |
| `components.json` | shadcn-compatible configuration and aliases |
| `styles/globals.css` | Tailwind CSS entry and theme variables |
| `style.css` | Existing workspace styles and minimal entrance styling |
| `lib/utils.ts` | Standard `cn` utility using clsx and tailwind-merge |
| `tsconfig.json` | Strict checking for new TypeScript components and `@/*` imports |
| `src.jsx` | Existing React workspace, retained in JavaScript |
| `build.mjs` | Tailwind/PostCSS and esbuild pipeline; emits the existing single HTML endpoint |

`@/components/ui` resolves to `frontend/components/ui`. This folder is a reuse and shadcn CLI convention, not a React runtime requirement. It keeps imported UI components separate from application logic and makes the supplied imports resolve consistently. The project already has TypeScript, Tailwind 4, PostCSS, Three.js, Lucide and shadcn-compatible aliases configured; no reinitialization is needed.

To restore dependencies, check types and rebuild:

```sh
cd frontend
npm ci
npm run typecheck
npm run build
```

`components.json` is configured for TypeScript, non-RSC React, Lucide icons and Tailwind v4 (empty Tailwind config path). Future shadcn additions should be run from this frontend directory, using `npx shadcn@latest add <component>` and reviewing the generated files before rebuilding. This custom single-file build must remain in place; do not replace the Python server or add asset routes. All dependencies are pinned in package-lock.json.

## Component integration decisions

- Props: `hasActiveReminders=false`, `hasUpcomingReminders=false`, `disableCenterDimming=false`. The reminder-named palette controls are retained for compatibility; they are not connected to nonexistent reminder data or execution results.
- State: only frontend navigation and the existing information dialog. No new global store, provider or backend state.
- Assets: none. The graphics are generated in GLSL; stock photographs would conflict with the requested graphics-only entrance.
- Layout: full viewport on desktop and mobile, with side-by-side actions on desktop and stacked buttons on small screens. No landing-page scroll or dashboard beneath the graphic.
- Accessibility: system reduced motion displays a static shader frame; Escape on the entrance pauses/resumes animation. The artwork is decorative and hidden from screen readers. Buttons remain keyboard accessible. The dialog supports Escape and restores focus.

The supplied ray-marching function and palette logic are retained. Compatibility adjustments include a nullable initialized React 19 ref, centered aspect-correct coordinates, a small pointer offset using the supplied mouse uniform, replacing reversed-edge `smoothstep` with its defined equivalent, capped pixel ratio, approximately 30 FPS, visibility handling, reduced motion, disposal, and a gradient fallback when WebGL is unavailable. The original GLSL's reversed-edge `smoothstep(2.5, 0.0, rz)` has undefined behavior; `1.0-smoothstep(0.0, 2.5, rz)` preserves its intended descending transition.

The nebula is conceptual artwork, not a quantum-state plot or a verification result. The interface displays backend results only after a real execution.

## Verification

`backend-lock.json` hashes all 22 protected existing Python source/test and configuration files. Every build verifies those hashes before producing `retryguard/web.html`.

`visual-test.cjs` runs Playwright against the actual Python server. It checks the two-action entrance, opening instructions, entering the workspace, shader cleanup, live execution, four verified alternatives, downloads, source constraints, stale-result clearing, rejected uploads, mobile layout, reduced motion, and browser errors. Supply an installed Chromium with `CHROMIUM_PATH`, optionally `PLAYWRIGHT_MODULE` and JSON `CHROMIUM_ARGS`.

Actual screenshots are in `previews/`; QA logs and a downloaded execution bundle are in `qa/`. Earlier metallic-sculpture code in `Chamber.jsx` is retained as unused frontend source and is not imported into the new build.

## Interactive field guide

“How it works” now opens a four-chapter experiment in `components/ui/how-it-works.tsx`:

1. **Observe:** choose success or failure in an explicitly labeled toy instrument K0=H/sqrt(2), K1=X/sqrt(2), with input |0>.
2. **Recover:** apply or remove X recovery and inspect the returned state; X·X=I explains recovery for arbitrary inputs.
3. **Bound:** adjust the cap from 1 to 8 and calculate timeout (1/2)^n, assuming independent attempts and correction after every failure. Compare with a labeled illustrative 1% threshold.
4. **Decide:** toggle source preservation to explore eligibility. No winner, numerical cost or verifier pass is invented.

The guide does not call an API or run a circuit. Its analytic illustrations are clearly separated from backend results. The final action opens the real workspace without changing its configuration or auto-running a task. Reset restores all teaching controls. Keyboard navigation, focus containment, Escape dismissal, reduced motion and mobile scrolling are supported. Real execution and verified downloads remain unchanged.
