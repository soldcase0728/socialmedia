import { contact, site } from '../config/site';

export type FieldErrors = Record<string, string>;

export type Parsed<T> =
  | { ok: true; value: T }
  | { ok: false; errors: FieldErrors };

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
/** Ten digits, however the family typed them. */
const DIGITS = /\d/g;

export function clean(v: FormDataEntryValue | null, max = 500): string {
  return typeof v === 'string' ? v.trim().slice(0, max) : '';
}

export function isEmail(v: string): boolean {
  return EMAIL.test(v);
}

export function isPhone(v: string): boolean {
  const digits = v.match(DIGITS)?.length ?? 0;
  return digits >= 10 && digits <= 15;
}

/** A filled honeypot means a bot. Accept silently; never tell it why. */
export function isBot(form: FormData): boolean {
  return clean(form.get('company')) !== '';
}

export type Inquiry = {
  parentFirstName: string;
  parentLastName: string;
  studentFirstName: string;
  grade: string;
  contactMethod: 'email' | 'phone';
  email: string;
  phone: string;
  referralSource: string;
  message: string;
};

export function parseInquiry(form: FormData): Parsed<Inquiry> {
  const errors: FieldErrors = {};
  const value: Inquiry = {
    parentFirstName: clean(form.get('parentFirstName'), 80),
    parentLastName: clean(form.get('parentLastName'), 80),
    studentFirstName: clean(form.get('studentFirstName'), 80),
    grade: clean(form.get('grade'), 12),
    contactMethod: clean(form.get('contactMethod')) === 'phone' ? 'phone' : 'email',
    email: clean(form.get('email'), 160),
    phone: clean(form.get('phone'), 40),
    referralSource: clean(form.get('referralSource'), 120),
    message: clean(form.get('message'), 2000),
  };

  if (!value.parentFirstName) errors.parentFirstName = 'Add a first name.';
  if (!value.parentLastName) errors.parentLastName = 'Add a last name.';
  if (!value.studentFirstName) errors.studentFirstName = "Add the student's first name.";
  if (!value.grade) errors.grade = 'Pick the grade the student is entering.';

  if (value.contactMethod === 'phone') {
    if (!isPhone(value.phone)) errors.phone = 'Add a phone number with area code.';
  } else if (!isEmail(value.email)) {
    errors.email = 'Add an email address we can reply to.';
  }

  return Object.keys(errors).length ? { ok: false, errors } : { ok: true, value };
}

export type Rsvp = {
  name: string;
  email: string;
  attending: number;
  grade: string;
  referralSource: string;
};

export function parseRsvp(form: FormData): Parsed<Rsvp> {
  const errors: FieldErrors = {};
  const attendingRaw = clean(form.get('attending'), 4);
  const attending = Number.parseInt(attendingRaw, 10);
  const value: Rsvp = {
    name: clean(form.get('name'), 120),
    email: clean(form.get('email'), 160),
    attending: Number.isFinite(attending) ? attending : 0,
    grade: clean(form.get('grade'), 12),
    referralSource: clean(form.get('referralSource'), 120),
  };

  if (!value.name) errors.name = 'Add a name.';
  if (!isEmail(value.email)) errors.email = 'Add an email address we can reply to.';
  if (!(value.attending >= 1 && value.attending <= 20)) {
    errors.attending = 'How many people are coming?';
  }
  if (!value.grade) errors.grade = 'Pick the grade the student is entering.';

  return Object.keys(errors).length ? { ok: false, errors } : { ok: true, value };
}

/** UTM + referrer, carried in hidden fields so attribution survives to the CRM. */
export function context(form: FormData, request: Request) {
  return {
    submittedAt: new Date().toISOString(),
    pagePath: clean(form.get('pagePath'), 200),
    utmSource: clean(form.get('utm_source'), 100),
    utmMedium: clean(form.get('utm_medium'), 100),
    utmCampaign: clean(form.get('utm_campaign'), 100),
    utmContent: clean(form.get('utm_content'), 100),
    referrer: request.headers.get('referer') ?? '',
  };
}

function rows(record: Record<string, unknown>): string {
  return Object.entries(record)
    .map(([k, v]) => `<tr><td style="padding:4px 12px 4px 0;color:#5b5350">${k}</td><td style="padding:4px 0"><strong>${escapeHtml(String(v ?? ''))}</strong></td></tr>`)
    .join('');
}

function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!,
  );
}

async function sendEmail(subject: string, record: Record<string, unknown>, replyTo?: string) {
  const key = import.meta.env.RESEND_API_KEY;
  if (!key) {
    console.info('[submissions] RESEND_API_KEY unset; email skipped:', subject);
    return;
  }
  const res = await fetch('https://api.resend.com/emails', {
    method: 'POST',
    headers: { Authorization: `Bearer ${key}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      from: contact.notificationFrom,
      to: [...contact.notificationRecipients],
      subject,
      ...(replyTo ? { reply_to: replyTo } : {}),
      html: `<div style="font-family:system-ui,sans-serif;color:#1e1a1a">
        <h2 style="font-size:18px;margin:0 0 12px">${escapeHtml(subject)}</h2>
        <table style="border-collapse:collapse;font-size:14px">${rows(record)}</table>
        <p style="margin-top:16px;color:#5b5350;font-size:12px">Sent by ${escapeHtml(site.url)}</p>
      </div>`,
    }),
  });
  if (!res.ok) throw new Error(`Resend responded ${res.status}: ${await res.text()}`);
}

async function appendRow(type: string, record: Record<string, unknown>) {
  const url = import.meta.env.SHEET_WEBHOOK_URL;
  if (!url) {
    console.info('[submissions] SHEET_WEBHOOK_URL unset; sheet append skipped:', type);
    return;
  }
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ type, ...record }),
  });
  if (!res.ok) throw new Error(`Sheet webhook responded ${res.status}`);
}

/**
 * Email and sheet are delivered independently: one failing must not lose the
 * lead in the other. The family only sees an error if both fail.
 */
export async function deliver(
  type: 'inquiry' | 'rsvp',
  subject: string,
  record: Record<string, unknown>,
  replyTo?: string,
): Promise<{ delivered: boolean }> {
  const results = await Promise.allSettled([
    sendEmail(subject, record, replyTo),
    appendRow(type, record),
  ]);
  const failures = results.filter((r) => r.status === 'rejected');
  for (const f of failures) console.error(`[submissions] ${type} delivery failed:`, (f as PromiseRejectedResult).reason);
  return { delivered: failures.length < results.length };
}

export function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' },
  });
}

/** Non-JS submits arrive as document navigations; send those to /thank-you. */
export function wantsHtml(request: Request): boolean {
  const accept = request.headers.get('accept') ?? '';
  return accept.includes('text/html') && request.headers.get('x-requested-with') !== 'fetch';
}

export function seeOther(location: string): Response {
  return new Response(null, { status: 303, headers: { Location: location, 'Cache-Control': 'no-store' } });
}
