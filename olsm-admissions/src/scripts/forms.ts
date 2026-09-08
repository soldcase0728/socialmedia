/**
 * Progressive enhancement for the inquiry and RSVP forms. Without JS the form
 * still posts natively and the endpoint 303s to /thank-you; with JS the family
 * stays on the page and we get a measurable conversion event.
 */
const UTM_KEYS = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term'] as const;
const STORE_KEY = 'olsm_utm';

type Utm = Partial<Record<(typeof UTM_KEYS)[number], string>>;

/** First touch wins for the session, so a direct return visit keeps its source. */
function utmParams(): Utm {
  const url = new URLSearchParams(window.location.search);
  const fromUrl: Utm = {};
  for (const key of UTM_KEYS) {
    const v = url.get(key);
    if (v) fromUrl[key] = v.slice(0, 100);
  }
  try {
    if (Object.keys(fromUrl).length) {
      sessionStorage.setItem(STORE_KEY, JSON.stringify(fromUrl));
      return fromUrl;
    }
    const stored = sessionStorage.getItem(STORE_KEY);
    return stored ? (JSON.parse(stored) as Utm) : {};
  } catch {
    return fromUrl;
  }
}

function track(event: string, params: Record<string, unknown>) {
  const gtag = (window as any).gtag;
  if (typeof gtag === 'function') gtag('event', event, params);
  const fbq = (window as any).fbq;
  if (typeof fbq === 'function') fbq('track', event === 'rsvp' ? 'Schedule' : 'Lead', params);
}

function showErrors(form: HTMLFormElement, errors: Record<string, string>) {
  for (const [field, message] of Object.entries(errors)) {
    const slot = form.querySelector<HTMLElement>(`[data-error-for="${field}"]`);
    const input = form.elements.namedItem(field);
    if (slot) slot.textContent = message;
    if (input instanceof HTMLElement) input.setAttribute('aria-invalid', 'true');
  }
  const first = form.querySelector<HTMLElement>('[aria-invalid="true"]');
  first?.focus();
}

function clearErrors(form: HTMLFormElement) {
  form.querySelectorAll<HTMLElement>('[data-error-for]').forEach((el) => (el.textContent = ''));
  form.querySelectorAll<HTMLElement>('[aria-invalid]').forEach((el) => el.removeAttribute('aria-invalid'));
}

function enhance(form: HTMLFormElement) {
  const event = form.dataset.event ?? 'generate_lead';
  const success = document.getElementById(form.dataset.success ?? '');
  const button = form.querySelector<HTMLButtonElement>('button[type="submit"]');
  const status = form.querySelector<HTMLElement>('[data-form-status]');
  const buttonLabel = button?.textContent ?? '';

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    clearErrors(form);
    if (status) status.textContent = '';

    const data = new FormData(form);
    data.set('pagePath', window.location.pathname);
    for (const [k, v] of Object.entries(utmParams())) data.set(k, v as string);

    if (button) {
      button.disabled = true;
      button.textContent = 'Sending…';
    }

    try {
      const res = await fetch(form.action, {
        method: 'POST',
        body: data,
        headers: { Accept: 'application/json', 'X-Requested-With': 'fetch' },
      });
      const payload = (await res.json().catch(() => ({}))) as {
        ok?: boolean;
        errors?: Record<string, string>;
      };

      if (res.ok && payload.ok) {
        track(event, {
          form_id: form.id,
          grade: String(data.get('grade') ?? ''),
          referral_source: String(data.get('referralSource') ?? ''),
        });
        if (success) {
          form.hidden = true;
          success.hidden = false;
          success.focus();
        }
        return;
      }

      if (payload.errors) showErrors(form, payload.errors);
      else if (status) {
        status.textContent = 'That did not send. Call the admissions office and we will take it by phone.';
      }
    } catch {
      if (status) {
        status.textContent = 'That did not send. Check your connection, or call the admissions office.';
      }
    } finally {
      if (button) {
        button.disabled = false;
        button.textContent = buttonLabel;
      }
    }
  });
}

document.querySelectorAll<HTMLFormElement>('form[data-lead-form]').forEach(enhance);
