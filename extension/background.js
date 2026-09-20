const IMAGE_EXTENSIONS = [
  ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tif", ".tiff", ".avif", ".svg"
];

function isLikelyImageUrl(url) {
  try {
    const parsed = new URL(url);
    if (!["http:", "https:"].includes(parsed.protocol)) return false;

    const path = parsed.pathname.toLowerCase();
    if (IMAGE_EXTENSIONS.some(ext => path.endsWith(ext))) return true;

    const format = parsed.searchParams.get("format");
    if (typeof format === "string") {
      const normalizedFormat = format.trim().toLowerCase();
      const normalizedExtension = normalizedFormat.startsWith(".")
        ? normalizedFormat
        : `.${normalizedFormat}`;

      if (IMAGE_EXTENSIONS.includes(normalizedExtension)) return true;
    }

    return false;
  } catch {
    return false;
  }
}

async function collectImageTabs() {
  const tabs = await chrome.tabs.query({});
  return tabs
    .filter(tab => typeof tab.url === 'string' && isLikelyImageUrl(tab.url))
    .map(tab => ({
      tab_id: tab.id || 0,
      title: tab.title || '',
      url: tab.url
    }));
}

chrome.action.onClicked.addListener(async () => {
  const tabs = await collectImageTabs();
  const message = {
    type: 'image_tabs',
    version: 1,
    browser: 'opera',
    request_id: crypto.randomUUID(),
    tabs
  };

  try {
    const response = await fetch('http://127.0.0.1:8765/image-tabs', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(message)
    });
    if (!response.ok) {
      throw new Error(`Desktop app returned HTTP ${response.status}`);
    }
    const acknowledgement = await response.json();
    console.log('OneTime desktop response:', acknowledgement);
  } catch (error) {
    console.error('OneTime desktop app is not running or unavailable:', error);
  }
});
