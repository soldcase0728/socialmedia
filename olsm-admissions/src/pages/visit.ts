import type { APIRoute } from 'astro';

export const prerender = false;

/**
 * Short path for QR codes and print. Redirects to the events page and keeps
 * every query param, so UTM tags survive the hop.
 */
export const GET: APIRoute = ({ url }) => {
  const target = new URL('/events-on-campus', url.origin);
  target.search = url.search;
  return new Response(null, {
    status: 302,
    headers: { Location: target.pathname + target.search, 'Cache-Control': 'no-store' },
  });
};
