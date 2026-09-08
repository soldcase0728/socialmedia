/**
 * Single source of truth for every fact that changes between admission cycles.
 * Swap the values here; no page markup should hard-code a date, phone or URL.
 */

export const site = {
  name: "Orchard Lake St. Mary's Preparatory",
  shortName: "St. Mary's Prep",
  alternateNames: ["St. Mary's Prep", "OLSM", "Orchard Lake St. Mary's"],
  foundingDate: '1885',
  parentOrganization: 'Orchard Lake Schools',
  url: 'https://www.olsmadmissions.com',
  tagline: 'God. Family. St. Mary’s.',
  /** One citeable sentence. Used as the default meta description. */
  description:
    "Orchard Lake St. Mary's Preparatory is a Catholic co-divisional college-preparatory high school in Orchard Lake, Michigan, founded in 1885, with a boys' division, a girls' division and a boarding program.",
} as const;

export const contact = {
  /** TODO: confirm — street address for admissions correspondence. */
  streetAddress: '3535 Indian Trail',
  addressLocality: 'Orchard Lake',
  addressRegion: 'MI',
  postalCode: '48324',
  addressCountry: 'US',
  /** One number only. TODO: confirm — direct admissions line. */
  phone: '+1-248-683-0500',
  phoneDisplay: '(248) 683-0500',
  /** TODO: confirm — monitored admissions inbox. */
  email: 'admissions@stmarysprep.com',
  /** Where inquiry + RSVP notifications are delivered. */
  notificationRecipients: ['admissions@stmarysprep.com'],
  /** TODO: confirm — sending domain verified in Resend. */
  notificationFrom: 'OLSM Admissions <no-reply@olsmadmissions.com>',
} as const;

export const links = {
  /** Applications live in Blackbaud. TODO: confirm — live application URL. */
  apply: 'https://stmarysprep.myschoolapp.com/podium/default.aspx?t=44005',
  mainSite: 'https://www.stmarysprep.com',
  /** TODO: confirm — Calendly scheduling link for shadow days. */
  shadowDayCalendly: 'https://calendly.com/olsm-admissions/shadow-day',
  privacyPolicy: '/privacy-policy',
  sameAs: [
    'https://www.stmarysprep.com',
    // TODO: confirm — official social profiles.
    'https://www.facebook.com/OLSMPrep',
    'https://www.instagram.com/olsmprep',
    'https://x.com/OLSMPrep',
    'https://www.youtube.com/@OLSMPrep',
  ],
} as const;

/** The one event promoted in the announcement bar and hero. Swap for the next one. */
export const nextEvent = {
  name: 'Fall Open House',
  /** ISO 8601 start/end, local Eastern time. TODO: confirm — exact times. */
  startDate: '2026-10-18T13:00:00-04:00',
  endDate: '2026-10-18T15:00:00-04:00',
  dateLong: 'October 18, 2026',
  dateShort: 'Oct 18',
  barText: 'Next Open House · October 18, 2026 · Save a seat',
  ctaText: 'Save a seat · Open House Oct 18',
  href: '/events-on-campus',
  /** TODO: confirm — on-campus location name for Event schema. */
  locationName: "Orchard Lake St. Mary's Preparatory",
} as const;

/** Class of 2026 proof points. TODO: confirm — fourth stat. */
export const record = {
  classYear: '2026',
  stats: [
    { value: '534', label: 'college acceptances' },
    { value: '$12.8M', label: 'in scholarships' },
    { value: '55', label: 'colleges, 21 states' },
    // TODO: confirm — fourth proof stat (e.g. average ACT, % four-year enrollment).
    { value: '—', label: 'TODO: confirm — fourth proof stat' },
  ],
} as const;

export const analytics = {
  ga4Id: import.meta.env.PUBLIC_GA4_ID ?? '',
  metaPixelId: import.meta.env.PUBLIC_META_PIXEL_ID ?? '',
} as const;

export const nav = [
  { label: 'Visit', href: '/events-on-campus' },
  { label: 'Shadow days', href: '/shadow-days' },
  { label: 'Apply process', href: '/application-process' },
  { label: 'Tuition & aid', href: '/tuition' },
  { label: 'Boarding', href: '/the-boarding-program' },
  { label: 'Co-divisional', href: '/what-is-co-divisional' },
] as const;

export const footerLinks = [
  { label: 'Application process', href: '/application-process' },
  { label: 'Key dates', href: '/key-dates' },
  { label: 'Shadow days', href: '/shadow-days' },
  { label: 'Events on campus', href: '/events-on-campus' },
  { label: 'Tuition', href: '/tuition' },
  { label: 'Financial aid', href: '/financial-aid' },
  { label: 'Scholarships', href: '/scholarships' },
  { label: 'Boarding program', href: '/the-boarding-program' },
  { label: 'Transfer students', href: '/transfer-students' },
  { label: 'International students', href: '/international-students' },
  { label: 'Admissions resources', href: '/admissions-resources' },
  { label: 'Parent experiences', href: '/parent-experiences' },
  { label: 'Meet our admissions staff', href: '/meet-our-admissions-staff' },
  { label: 'Academics', href: '/academics-codivisional' },
  { label: 'What is co-divisional?', href: '/what-is-co-divisional' },
  { label: 'Videos', href: '/videos' },
] as const;

/** Shared "How did you hear about us?" options for both forms. */
export const referralSources = [
  'A current OLSM family',
  'An alumnus',
  'A coach or teammate',
  'My parish or a priest',
  'My grade school',
  'Search engine',
  'Social media',
  'An AI assistant suggested you',
  'Mail or a flyer',
  'Other',
] as const;

export const gradeOptions = ['8', '9', '10', '11', '12'] as const;
