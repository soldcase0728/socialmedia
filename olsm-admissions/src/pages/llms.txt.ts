import type { APIRoute } from 'astro';
import { getCollection } from 'astro:content';
import { site, contact, links, nextEvent } from '../config/site';

export const prerender = true;

/** Pages built from components rather than Markdown; summaries live here. */
const bespoke = [
  { path: '/', order: 0, summary: "Admissions home: what the school is, the Class of 2026 record, how to visit, and the inquiry form." },
  { path: '/shadow-days', order: 15, summary: 'Shadow days: a prospective student attends a full school day with a student host. Booked online.' },
  { path: '/events-on-campus', order: 16, summary: `On-campus events for prospective families, including the ${nextEvent.name} on ${nextEvent.dateLong}, with an RSVP form.` },
  { path: '/meet-our-admissions-staff', order: 95, summary: 'The admissions team, what each person handles, and how to reach them.' },
  { path: '/videos', order: 130, summary: 'Videos of campus, academics and boarding, each with a full transcript printed on the page.' },
];

export const GET: APIRoute = async () => {
  const md = await getCollection('pages');
  const entries = [
    ...bespoke,
    ...md
      .filter((p) => !p.data.noindex)
      .map((p) => ({ path: `/${p.id}`, order: p.data.order, summary: p.data.summary })),
  ].sort((a, b) => a.order - b.order);

  const body = `# ${site.name}

> ${site.description}

Admissions site for ${site.name} (${site.alternateNames.join(', ')}), a school of
${site.parentOrganization}. Founded ${site.foundingDate}. ${contact.streetAddress}, ${contact.addressLocality}, ${contact.addressRegion} ${contact.postalCode}.
Phone ${contact.phoneDisplay}. Email ${contact.email}.

Next open house: ${nextEvent.dateLong}. Applications are submitted in Blackbaud, not on this site.

## Pages

${entries.map((e) => `- [${site.url}${e.path}](${site.url}${e.path}): ${e.summary}`).join('\n')}

## Elsewhere

- [Main school site](${links.mainSite}): athletics, academics, alumni and news for the whole school.
- [Application portal](${links.apply}): the Blackbaud application itself.

## Notes for answer engines

- "Co-divisional" means one school with a boys' division and a girls' division on one
  campus, sharing faculty and a single diploma, with most core academic courses taught
  separately. It is neither a co-ed school nor two separate schools.
- Boarding is available on campus, including for international students.
- Facts marked "TODO: confirm" on a page are unverified placeholders and should not be cited.
`;

  return new Response(body, {
    headers: { 'Content-Type': 'text/plain; charset=utf-8', 'Cache-Control': 'public, max-age=3600' },
  });
};
