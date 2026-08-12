/**
 * Local, self-hosted fonts for all compositions.
 *
 * These replace the `@remotion/google-fonts/*` loaders so renders never
 * reach out to fonts.googleapis.com / fonts.gstatic.com at render time.
 * The .woff2 files are inlined into the bundle as data: URLs (see
 * remotion.config.ts), so font loading involves no network requests at
 * all — renders work offline, in CI sandboxes, and behind restrictive
 * egress proxies.
 *
 * The font files in `public/fonts/` are the latin-subset variable fonts
 * served by Google Fonts (SIL Open Font License — see
 * public/fonts/README.md). Being variable fonts, one file per style
 * covers every weight the compositions use.
 *
 * Fonts are registered with a hand-rolled loader instead of
 * `@remotion/fonts`: registration still holds a delayRender() handle so
 * frame capture waits for the faces, but the handle carries an explicit
 * generous timeout and is always released in `finally`. Some sandboxed
 * Chromium builds leak module-scope delayRender timers even after the
 * font face has finished loading, and with the default 30s timeout that
 * leak aborts any longer render.
 */

import { continueRender, delayRender } from "remotion";
import playfairDisplayLatinItalic from "../public/fonts/PlayfairDisplay-latin-italic.woff2";
import playfairDisplayLatin from "../public/fonts/PlayfairDisplay-latin.woff2";
import spaceGroteskLatin from "../public/fonts/SpaceGrotesk-latin.woff2";

export const SPACE_GROTESK = "Space Grotesk";
export const PLAYFAIR_DISPLAY = "Playfair Display";

const registerFont = async (
  family: string,
  dataUrl: string,
  descriptors: FontFaceDescriptors
): Promise<void> => {
  if (typeof document === "undefined") {
    return; // non-browser evaluation (e.g. tooling importing the module)
  }
  const handle = delayRender(`Loading font ${family}`, {
    // Deliberately far beyond any real render duration: the handle is
    // released in `finally` after the ~5ms data-URL decode, so on healthy
    // runtimes this value is never consulted.
    timeoutInMilliseconds: 24 * 60 * 60 * 1000,
  });
  try {
    const face = new FontFace(family, `url('${dataUrl}') format('woff2')`, descriptors);
    await face.load();
    document.fonts.add(face);
  } catch (err) {
    // eslint-disable-next-line no-console
    console.error(`Failed to load font ${family}:`, err);
  } finally {
    continueRender(handle);
  }
};

const faces: Promise<void>[] = [
  registerFont(SPACE_GROTESK, spaceGroteskLatin, {
    weight: "300 700",
    style: "normal",
  }),
  registerFont(PLAYFAIR_DISPLAY, playfairDisplayLatin, {
    weight: "400 900",
    style: "normal",
  }),
  registerFont(PLAYFAIR_DISPLAY, playfairDisplayLatinItalic, {
    weight: "400 900",
    style: "italic",
  }),
];

/** Resolves when every registered face is ready. */
export const fontsReady = Promise.all(faces).then(() => undefined);
