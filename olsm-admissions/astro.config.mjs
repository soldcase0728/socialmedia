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
  adapter: vercel(),
  integrations: [mdx(), sitemap()],
  vite: { plugins: [tailwindcss()] },
  build: { format: 'directory' },
});
