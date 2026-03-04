// Filename: /frontend/lib/textUtils.ts
// Shared text utilities — single source of truth

export const linkifyText = (text: string): string => {
    const urlPattern = /(https?:\/\/[^\s<]+)/g;
    return text.replace(urlPattern, (url) => {
        const cleanUrl = url.replace(/[.,;:!?)]+$/, '');
        return `<a href="${cleanUrl}" target="_blank" rel="noopener noreferrer" class="text-blue-400 hover:text-blue-300 underline break-all">${cleanUrl}</a>`;
    });
};
