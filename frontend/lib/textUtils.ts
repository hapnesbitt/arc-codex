// Filename: /frontend/lib/textUtils.ts
// Shared text utilities — single source of truth
//
// v2 — XSS fix:
//   URL is encoded via encodeURI before insertion into href attribute.
//   Link text is HTML-entity-escaped so a URL containing <, >, or "
//   cannot break out of the attribute or inject markup into the DOM.

export const linkifyText = (text: string): string => {
    const urlPattern = /(https?:\/\/[^\s<]+)/g;
    return text.replace(urlPattern, (url) => {
        // Strip trailing punctuation that's likely not part of the URL
        const cleanUrl = url.replace(/[.,;:!?)]+$/, '');

        // Encode the URL for safe href insertion — prevents attribute injection
        let safeHref: string;
        try {
            safeHref = encodeURI(decodeURI(cleanUrl));
        } catch {
            // If the URL is malformed, fall back to escaping it as text only
            return escapeHtml(cleanUrl);
        }

        // Escape the display text so <, >, " can't inject markup
        const safeText = escapeHtml(cleanUrl);

        return `<a href="${safeHref}" target="_blank" rel="noopener noreferrer" class="text-blue-400 hover:text-blue-300 underline break-all">${safeText}</a>`;
    });
};

// Escapes HTML special characters for safe insertion into HTML content
const escapeHtml = (text: string): string =>
    text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
