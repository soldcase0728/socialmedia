import { defineCollection, z } from 'astro:content';
import { glob } from 'astro/loaders';

/**
 * Every prose page the admissions office edits. One Markdown file per URL;
 * the filename is the path. Structured bits (FAQs, the visit CTA, quick facts)
 * live in frontmatter so they can carry schema and styling.
 */
const pages = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/pages' }),
  schema: z.object({
    title: z.string(),
    /** One citeable sentence. Becomes the meta description. */
    description: z.string(),
    eyebrow: z.string(),
    h1: z.string(),
    /** First sentence answers the question the title asks. */
    standfirst: z.string(),
    /** Short label/value pairs rendered as a facts rail. */
    facts: z.array(z.object({ label: z.string(), value: z.string() })).default([]),
    faqs: z.array(z.object({ question: z.string(), answer: z.string() })).default([]),
    cta: z.enum(['visit', 'inquiry', 'apply', 'none']).default('visit'),
    order: z.number().default(50),
    /** One-line summary used by llms.txt. */
    summary: z.string(),
    noindex: z.boolean().default(false),
  }),
});

export const collections = { pages };
