if (typeof window.aiPluginInitialized === 'undefined') {
    window.aiPluginInitialized = true;
    window.isPluginRunning = false;
    window.isPluginPaused = false;
    window.processedPosts = new Set();

    chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
        if (request.action === "ping") {
            sendResponse({ status: "alive", isRunning: window.isPluginRunning, isPaused: window.isPluginPaused, count: window.processedPosts.size });
        } else if (request.action === "toggleAgent") {
            window.isPluginRunning = request.state;
            if (window.isPluginRunning) {
                window.isPluginPaused = false;
                runPluginLoop();
            }
            sendResponse({ status: "ok" });
        } else if (request.action === "pauseAgent") {
            window.isPluginPaused = request.state;
            sendResponse({ status: "ok" });
        }
    });

    const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));
    const randomSleep = (minMs, maxMs) => sleep(Math.floor(Math.random() * (maxMs - minMs + 1)) + minMs);

    function clickMoreButtonSafely(container) {
        let buttons = container.querySelectorAll('button, span, a, [role="button"]');
        let clicked = false;
        buttons.forEach(btn => {
            // Ignore video players (prevents getting stuck on videos)
            if (btn.closest('video, .video-player, .feed-shared-video, .media-player, [data-media-type="video"], .artdeco-media-player')) return;
            
            let txt = (btn.innerText || btn.textContent || "").toLowerCase().trim();
            if (txt === '... more' || txt === '...more' || txt === '…more' || txt === 'see more' || txt === 'more') {
                try {
                    btn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
                    btn.click();
                    clicked = true;
                } catch(e) {}
            }
        });
        return clicked;
    }

    // 🎯 Captures EXACT Post URL using hidden data tags
    function extractExactPostUrl(postBox) {
        let urn = postBox.getAttribute('data-urn') || postBox.getAttribute('data-id');
        if (urn) return `https://www.linkedin.com/feed/update/${urn}/`;

        let timeStampLink = postBox.querySelector('a.update-components-actor__sub-description-link, a.app-aware-link:has(.update-components-actor__sub-description)');
        if (timeStampLink && timeStampLink.href) return timeStampLink.href.split('?')[0];

        let permalinks = postBox.querySelectorAll('a[href*="/posts/"], a[href*="activity-"], a[href*="ugcPost"]');
        if (permalinks.length > 0) return permalinks[0].href.split('?')[0];

        return window.location.href;
    }

    async function humanScrollDown(distance = 600) {
        let scrollDistance = Math.floor(Math.random() * 200) + distance;
        window.scrollBy({ top: scrollDistance, behavior: 'smooth' });
        
        let containers = document.querySelectorAll('.scaffold-layout__main, .search-results-container, main, .jobs-search-results-list');
        containers.forEach(c => { c.scrollBy({ top: scrollDistance, behavior: 'smooth' }); });

        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'PageDown', code: 'PageDown', keyCode: 34, bubbles: true }));
    }

    async function processJobsTab() {
        let jobCards = document.querySelectorAll('li.jobs-search-results__list-item, div.job-card-container, div.job-card-list');
        
        for (let card of jobCards) {
            if (!window.isPluginRunning) break;
            while (window.isPluginPaused && window.isPluginRunning) await sleep(1000);
            
            if (card.classList.contains('ai-checked')) continue;

            card.scrollIntoView({ behavior: 'smooth', block: 'center' });
            await randomSleep(500, 1000);
            
            // Click to load details in right pane
            card.click();
            await randomSleep(1500, 2500); 

            let detailsPane = document.querySelector('.jobs-search__job-details, .jobs-description, .job-details-jobs-unified-top-card, .jobs-box');
            
            if (detailsPane) {
                clickMoreButtonSafely(detailsPane);
                await randomSleep(1000, 1500); // ⏳ Wait for full text expansion!
            }

            // 🎯 GRAB INTACT TEXT NOW
            let jobText = detailsPane ? detailsPane.innerText.trim() : card.innerText.trim();
            if (jobText.length < 50) continue;

            let link = card.querySelector('a[href*="/jobs/view/"], a.job-card-list__title');
            let jobUrl = link ? link.href.split('?')[0] : window.location.href;

            if (window.processedPosts.has(jobUrl)) {
                card.classList.add('ai-checked');
                continue;
            }

            window.processedPosts.add(jobUrl);
            card.classList.add('ai-checked');
            card.style.border = "4px solid #0a66c2";

            chrome.runtime.sendMessage({
                action: "savePost",
                url: jobUrl,
                text: jobText
            });
            
            await randomSleep(1000, 2000);
        }
        
        if (window.isPluginRunning && !window.isPluginPaused) {
            await humanScrollDown(800);
            await randomSleep(2000, 4000);
        }
    }

    async function processPostsTab() {
        let postSet = new Set();
        let authorLinks = document.querySelectorAll('a[href*="/in/"], a[href*="/company/"]');
        
        authorLinks.forEach(link => {
            let parent = link.parentElement;
            while (parent && parent !== document.body) {
                if (parent.offsetHeight > 120 && parent.offsetWidth > 280 && parent.innerText.length > 40) {
                    if (parent.tagName === 'LI' || parent.tagName === 'DIV') {
                        postSet.add(parent);
                        break;
                    }
                }
                parent = parent.parentElement;
            }
        });

        if (postSet.size === 0) {
            document.querySelectorAll('li.reusable-search__result-container, div.feed-shared-update-v2').forEach(el => postSet.add(el));
        }

        let posts = Array.from(postSet);

        for (let postBox of posts) {
            if (!window.isPluginRunning) break;
            while (window.isPluginPaused && window.isPluginRunning) await sleep(1000);
            if (!window.isPluginRunning) break;

            let postUrl = extractExactPostUrl(postBox);
            let textPreview = postBox.innerText.substring(0, 80);
            let uniqueKey = postUrl.includes('/posts/') || postUrl.includes('urn:li:activity:') ? postUrl : textPreview;

            if (window.processedPosts.has(uniqueKey)) continue;

            postBox.style.border = "3px dashed #ffc107";
            postBox.scrollIntoView({ behavior: 'smooth', block: 'center' });
            await randomSleep(800, 1500);

            // 🎯 CLICK "SEE MORE" AND WAIT
            let clickedMore = clickMoreButtonSafely(postBox);
            if (clickedMore) await randomSleep(1500, 2000); // ⏳ Give it time to expand!

            // 🎯 GRAB INTACT TEXT
            let postText = postBox.innerText.trim();
            if (postText.length < 40) continue;

            window.processedPosts.add(uniqueKey);
            postBox.style.border = "4px solid #0a66c2";

            chrome.runtime.sendMessage({
                action: "savePost",
                url: postUrl,
                text: postText
            });

            await randomSleep(1500, 3000);
        }

        if (window.isPluginRunning && !window.isPluginPaused) {
            await humanScrollDown(600);
            await randomSleep(3000, 5000);
        }
    }

    async function runPluginLoop() {
        while (window.isPluginRunning) {
            try {
                while (window.isPluginPaused && window.isPluginRunning) await sleep(1000);
                if (!window.isPluginRunning) break;

                // Auto-detect which LinkedIn page we are on
                if (window.location.href.includes("linkedin.com/jobs")) {
                    await processJobsTab();
                } else {
                    await processPostsTab();
                }
            } catch (error) {
                console.error("Plugin Error:", error);
                await randomSleep(2000, 4000);
            }
        }
    }
}