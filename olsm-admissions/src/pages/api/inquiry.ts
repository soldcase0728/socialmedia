import type { APIRoute } from 'astro';
import {
  context, deliver, isBot, json, parseInquiry, seeOther, wantsHtml,
} from '../../lib/submissions';

export const prerender = false;

export const POST: APIRoute = async ({ request }) => {
  const form = await request.formData();

  // Honeypot: accept, drop, say nothing.
  if (isBot(form)) {
    return wantsHtml(request) ? seeOther('/thank-you') : json({ ok: true });
  }

  const parsed = parseInquiry(form);
  if (!parsed.ok) {
    return wantsHtml(request)
      ? seeOther('/#inquiry')
      : json({ ok: false, errors: parsed.errors }, 400);
  }

  const v = parsed.value;
  const record = {
    'Parent': `${v.parentFirstName} ${v.parentLastName}`,
    'Student': v.studentFirstName,
    'Entering grade': v.grade,
    'Preferred contact': v.contactMethod,
    'Email': v.email,
    'Phone': v.phone,
    'Heard about us': v.referralSource,
    'Message': v.message,
    ...context(form, request),
  };

  const { delivered } = await deliver(
    'inquiry',
    `Inquiry — ${v.parentLastName} family, grade ${v.grade}`,
    record,
    v.email || undefined,
  );

  if (!delivered) {
    return wantsHtml(request)
      ? seeOther('/thank-you?state=retry')
      : json({ ok: false, error: 'delivery_failed' }, 502);
  }

  return wantsHtml(request) ? seeOther('/thank-you') : json({ ok: true });
};
