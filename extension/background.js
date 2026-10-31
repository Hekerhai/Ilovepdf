import { openIn, TOOLS } from "./shared.js";

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({ id: "folio", title: "Open in Folio", contexts: ["link", "page"] });
    for (const tool of TOOLS) {
      chrome.contextMenus.create({ id: tool.id, parentId: "folio", title: tool.title, contexts: ["link", "page"] });
    }
  });
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  const tool = TOOLS.find((t) => t.id === info.menuItemId);
  const link = info.linkUrl || info.pageUrl || tab?.url;
  if (tool && link && /^https?:/i.test(link)) openIn(tool.path, link);
});
