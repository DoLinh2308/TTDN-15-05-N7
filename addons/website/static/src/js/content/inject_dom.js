/** @odoo-module */

import { get_cookie } from 'web.utils.cookies';
import { session } from '@web/session';

document.addEventListener('DOMContentLoaded', () => {
    // Transfer cookie/session data as HTML element's attributes so that CSS
    // selectors can be based on them.
    const htmlEl = document.documentElement;
    const cookieNamesToDataNames = {
        'utm_source': 'utmSource',
        'utm_medium': 'utmMedium',
        'utm_campaign': 'utmCampaign',
    };
    for (const [name, dsName] of Object.entries(cookieNamesToDataNames)) {
        const cookie = get_cookie(`odoo_${name}`);
        if (cookie) {
            // Remove leading and trailing " and '
            htmlEl.dataset[dsName] = cookie.replace(/(^["']|["']$)/g, '');
        }
    }
    const country = session.geoip_country_code;
    if (country) {
        htmlEl.dataset.country = country;
    }

    htmlEl.dataset.logged = !session.is_website_user;

    // Create CSS rules in a dedicated style tag according to the snippet
    // visibility option's computed ones (saved as data attributes).
    const styleEl = document.createElement('style');
    styleEl.id = "conditional_visibility";
    document.head.appendChild(styleEl);
    const conditionalEls = document.querySelectorAll('[data-visibility="conditional"]');
    for (const conditionalEl of conditionalEls) {
        const selectors = conditionalEl.dataset.visibilitySelectors;
        styleEl.sheet.insertRule(`${selectors} { display: none !important; }`);
    }

    // Now remove the classes that makes them always invisible
    for (const conditionalEl of conditionalEls) {
        conditionalEl.classList.remove('o_conditional_hidden');
    }
});
