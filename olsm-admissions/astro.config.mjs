// @ts-check
import { defineConfig } from 'astro/config';
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
  vite: { plugins: [tailwindcss()] },
  build: { format: 'directory' },
});
