import { site, contact, links, nextEvent } from '../config/site';

const ORG_ID = `${site.url}/#school`;

/** The school node. Referenced by @id from every other node on the site. */
export function schoolSchema() {
  return {
    '@type': ['HighSchool', 'EducationalOrganization'],
    '@id': ORG_ID,
    name: site.name,
    alternateName: [...site.alternateNames],
    description: site.description,
    url: site.url,
    foundingDate: site.foundingDate,
    telephone: contact.phone,
    email: contact.email,
    parentOrganization: {
      '@type': 'EducationalOrganization',
      name: site.parentOrganization,
    },
    address: {
      '@type': 'PostalAddress',
      streetAddress: contact.streetAddress,
      addressLocality: contact.addressLocality,
      addressRegion: contact.addressRegion,
      postalCode: contact.postalCode,
      addressCountry: contact.addressCountry,
    },
    sameAs: [...links.sameAs],
  };
}

export function webPageSchema(opts: { url: string; name: string; description: string }) {
  return {
    '@type': 'WebPage',
    '@id': `${opts.url}#webpage`,
    url: opts.url,
    name: opts.name,
    description: opts.description,
    isPartOf: { '@id': `${site.url}/#website` },
    about: { '@id': ORG_ID },
    publisher: { '@id': ORG_ID },
  };
}

export function websiteSchema() {
  return {
    '@type': 'WebSite',
    '@id': `${site.url}/#website`,
    url: site.url,
    name: `${site.shortName} Admissions`,
    publisher: { '@id': ORG_ID },
  };
}

/** Open house / on-campus event. */
export function eventSchema() {
  return {
    '@type': 'Event',
    '@id': `${site.url}/events-on-campus#open-house`,
    name: `${site.shortName} ${nextEvent.name}`,
    startDate: nextEvent.startDate,
    endDate: nextEvent.endDate,
    eventAttendanceMode: 'https://schema.org/OfflineEventAttendanceMode',
    eventStatus: 'https://schema.org/EventScheduled',
    description: `Open house for families considering ${site.name}. Tour the campus, meet faculty and students, and ask about admissions, tuition and boarding.`,
    location: {
      '@type': 'Place',
      name: nextEvent.locationName,
      address: {
        '@type': 'PostalAddress',
        streetAddress: contact.streetAddress,
        addressLocality: contact.addressLocality,
        addressRegion: contact.addressRegion,
        postalCode: contact.postalCode,
        addressCountry: contact.addressCountry,
      },
    },
    organizer: { '@id': ORG_ID },
    isAccessibleForFree: true,
    offers: {
      '@type': 'Offer',
      price: '0',
      priceCurrency: 'USD',
      availability: 'https://schema.org/InStock',
      url: `${site.url}${nextEvent.href}`,
      validFrom: '2026-08-01T00:00:00-04:00',
    },
  };
}

export type Faq = { question: string; answer: string };

export function faqSchema(url: string, faqs: Faq[]) {
  return {
    '@type': 'FAQPage',
    '@id': `${url}#faq`,
    mainEntity: faqs.map((f) => ({
      '@type': 'Question',
      name: f.question,
      acceptedAnswer: { '@type': 'Answer', text: f.answer },
    })),
  };
}

export function personSchema(p: { name: string; jobTitle: string; email?: string; telephone?: string }) {
  return {
    '@type': 'Person',
    name: p.name,
    jobTitle: p.jobTitle,
    ...(p.email ? { email: p.email } : {}),
    ...(p.telephone ? { telephone: p.telephone } : {}),
    worksFor: { '@id': ORG_ID },
  };
}

export function breadcrumbSchema(url: string, trail: { name: string; item: string }[]) {
  return {
    '@type': 'BreadcrumbList',
    '@id': `${url}#breadcrumb`,
    itemListElement: trail.map((t, i) => ({
      '@type': 'ListItem',
      position: i + 1,
      name: t.name,
      item: t.item,
    })),
  };
}

/** Wraps nodes in a single @graph so each page emits one script tag. */
export function graph(nodes: object[]) {
  return { '@context': 'https://schema.org', '@graph': nodes };
}
