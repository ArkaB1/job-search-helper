let scrapedData = [];

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === "savePost") {
        scrapedData.push({
            timestamp: new Date().toLocaleString(),
            url: request.url,
            text: request.text
        });
        sendResponse({ success: true, count: scrapedData.length });
    }
    else if (request.action === "getCount") {
        sendResponse({ count: scrapedData.length });
    }
    else if (request.action === "downloadData") {
        if (scrapedData.length === 0) {
            sendResponse({ success: false });
            return;
        }
        let blobData = JSON.stringify(scrapedData, null, 4);
        let dataUrl = "data:application/json;charset=utf-8," + encodeURIComponent(blobData);
        let dateStr = new Date().toISOString().replace(/[:.]/g, "-");
        
        chrome.downloads.download({
            url: dataUrl,
            filename: `linkedin_dumps/scraped_posts_${dateStr}.json`,
            saveAs: false
        });
        scrapedData = []; 
        sendResponse({ success: true });
    }
    return true;
});