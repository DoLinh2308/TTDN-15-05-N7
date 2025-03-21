/** @odoo-module **/

import { browser } from "../browser/browser";

/**
 * Trasnforms a key value mapping to a string formatted as url hash, e.g.
 * {a: "x", b: 2} -> "a=x&b=2"
 *
 * @param {Object} obj
 * @returns {string}
 */
export function objectToUrlEncodedString(obj) {
    return Object.entries(obj)
        .map(([k, v]) => (v ? `${k}=${encodeURIComponent(v)}` : k))
        .join("&");
}

/**
 * Gets the origin url of the page, or cleans a given one
 *
 * @param {string} [origin]: a given origin url
 * @return {string} a cleaned origin url
 */
export function getOrigin(origin) {
    if (origin) {
        // remove trailing slashes
        origin = origin.replace(/\/+$/, "");
    } else {
        const { host, protocol } = browser.location;
        origin = `${protocol}//${host}`;
    }
    return origin;
}

/**
 * @param {string} route: the relative route, or absolute in the case of cors urls
 * @param {object} [queryParams]: parameters to be appended as the url's queryString
 * @param {object} [options]
 * @param {string} [options.origin]: a precomputed origin
 */
export function url(route, queryParams, options = {}) {
    const origin = getOrigin(options.origin);
    if (!route) {
        return origin;
    }

    let queryString = objectToUrlEncodedString(queryParams || {});
    queryString = queryString.length > 0 ? `?${queryString}` : queryString;

    // Compare the wanted url against the current origin
    let prefix = ["http://", "https://", "//"].some(
        (el) => route.length >= el.length && route.slice(0, el.length) === el
    );
    prefix = prefix ? "" : origin;
    return `${prefix}${route}${queryString}`;
}
