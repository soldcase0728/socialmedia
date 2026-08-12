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
 */

import { loadFont } from "@remotion/fonts";
import playfairDisplayLatinItalic from "../public/fonts/PlayfairDisplay-latin-italic.woff2";
import playfairDisplayLatin from "../public/fonts/PlayfairDisplay-latin.woff2";
import spaceGroteskLatin from "../public/fonts/SpaceGrotesk-latin.woff2";

export const SPACE_GROTESK = "Space Grotesk";
export const PLAYFAIR_DISPLAY = "Playfair Display";

const faces: Promise<void>[] = [
  loadFont({
    family: SPACE_GROTESK,
    url: spaceGroteskLatin,
    format: "woff2",
    weight: "300 700",
    style: "normal",
  }),
  loadFont({
    family: PLAYFAIR_DISPLAY,
    url: playfairDisplayLatin,
    format: "woff2",
    weight: "400 900",
    style: "normal",
  }),
  loadFont({
    family: PLAYFAIR_DISPLAY,
    url: playfairDisplayLatinItalic,
    format: "woff2",
    weight: "400 900",
    style: "italic",
  }),
];

/** Resolves when every registered face is ready. */
export const fontsReady = Promise.all(faces).then(() => undefined);
