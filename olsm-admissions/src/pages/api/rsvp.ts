import type { APIRoute } from 'astro';
import {
  context, deliver, isBot, json, parseRsvp, seeOther, wantsHtml,
} from '../../lib/submissions';
import { nextEvent } from '../../config/site';

export const prerender = false;

export const POST: APIRoute = async ({ request }) => {
  const form = await request.formData();

  if (isBot(form)) {
    return wantsHtml(request) ? seeOther('/thank-you') : json({ ok: true });
  }

  const parsed = parseRsvp(form);
  if (!parsed.ok) {
    return wantsHtml(request)
      ? seeOther('/events-on-campus#rsvp')
      : json({ ok: false, errors: parsed.errors }, 400);
  }

  const v = parsed.value;
  const record = {
    'Name': v.name,
    'Email': v.email,
    'Attending': v.attending,
    'Entering grade': v.grade,
    'Heard about us': v.referralSource,
    'Event': `${nextEvent.name} — ${nextEvent.dateLong}`,
    ...context(form, request),
  };

  const { delivered } = await deliver(
    'rsvp',
    `Open house RSVP — ${v.name} (${v.attending})`,
    record,
    v.email,
  );

  if (!delivered) {
    return wantsHtml(request)
      ? seeOther('/thank-you?state=retry')
      : json({ ok: false, error: 'delivery_failed' }, 502);
  }

  return wantsHtml(request) ? seeOther('/thank-you') : json({ ok: true });
};
