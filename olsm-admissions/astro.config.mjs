// @ts-check
import { defineConfig, fontProviders } from 'astro/config';
import mdx from '@astrojs/mdx';
import sitemap from '@astrojs/sitemap';
import vercel from '@astrojs/vercel';
import tailwindcss from '@tailwindcss/vite';

// Site URL drives canonical tags, sitemap and JSON-LD @id values.
// TODO: confirm — final production hostname (olsmadmissions.com assumed).
export default defineConfig({
  site: 'https://www.olsmadmissions.com',
  output: 'static',
  trailingSlash: 'never',
  adapter: vercel(),
  integrations: [
    mdx(),
    // /thank-you is a post-submit confirmation, not a landing page.
    sitemap({ filter: (page) => !page.includes('/thank-you') }),
  ],
  // Self-hosted at build time: no third-party render-blocking stylesheet and no
  // font request leaving the visitor's browser to a second domain.
  fonts: [
    {
      provider: fontProviders.google(),
      name: 'Fraunces',
      cssVariable: '--font-fraunces',
      weights: [600],
      styles: ['normal'],
      subsets: ['latin'],
      fallbacks: ['ui-serif', 'Georgia', 'serif'],
    },
    {
      provider: fontProviders.google(),
      name: 'Source Sans 3',
      cssVariable: '--font-source-sans',
      weights: [400, 600, 700],
      styles: ['normal'],
      subsets: ['latin'],
      fallbacks: ['ui-sans-serif', 'system-ui', 'sans-serif'],
    },
  ],
  vite: { plugins: [tailwindcss()] },
  build: { format: 'directory' },
});
