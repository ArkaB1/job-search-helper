let isRunning = false;
let isPaused = false;

const btnStart = document.getElementById("btn-start");
const btnPause = document.getElementById("btn-pause");
const btnStop = document.getElementById("btn-stop");
const statusText = document.getElementById("status");
const counterText = document.getElementById("counter");

setInterval(() => {
    chrome.runtime.sendMessage({ action: "getCount" }, (response) => {
        if (chrome.runtime.lastError) return;
        if (response && typeof response.count !== 'undefined') {
            counterText.innerText = `Saved Posts: ${response.count}`;
        }
    });
}, 1000);

async function checkStateOnOpen() {
    let [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tab && tab.url && tab.url.includes("linkedin.com")) {
        chrome.tabs.sendMessage(tab.id, { action: "ping" }, (response) => {
            if (chrome.runtime.lastError) {
                setStoppedUI();
            } else if (response && response.isRunning) {
                isRunning = true;
                isPaused = response.isPaused || false;
                if (response.count !== undefined) counterText.innerText = `Saved Posts: ${response.count}`;
                updateUIState();
            } else {
                setStoppedUI();
            }
        });
    } else {
        setStoppedUI();
    }
}

function updateUIState() {
    if (!isRunning) {
        setStoppedUI();
    } else if (isPaused) {
        btnStart.style.display = "none";
        btnPause.style.display = "block";
        btnPause.innerText = "▶ Resume Plugin";
        btnPause.style.backgroundColor = "#10b981";
        btnStop.style.display = "block";
        statusText.innerText = "Status: ⏸ PAUSED (Scroll manually)";
    } else {
        btnStart.style.display = "none";
        btnPause.style.display = "block";
        btnPause.innerText = "⏸ Pause Plugin";
        btnPause.style.backgroundColor = "#f59e0b";
        btnStop.style.display = "block";
        statusText.innerText = "Status: Reading & saving intact posts...";
    }
}

function setStoppedUI() {
    isRunning = false;
    isPaused = false;
    btnStart.style.display = "block";
    btnPause.style.display = "none";
    btnStop.style.display = "none";
    statusText.innerText = "Status: Ready";
}

checkStateOnOpen();

btnStart.addEventListener("click", async () => {
    isRunning = true;
    isPaused = false;
    updateUIState();
    sendControlMessage({ action: "toggleAgent", state: true });
});

btnPause.addEventListener("click", async () => {
    isPaused = !isPaused;
    updateUIState();
    sendControlMessage({ action: "pauseAgent", state: isPaused });
});

btnStop.addEventListener("click", async () => {
    setStoppedUI();
    statusText.innerText = "Status: Stopped. JSON Downloaded!";
    chrome.runtime.sendMessage({ action: "downloadData" });
    sendControlMessage({ action: "toggleAgent", state: false });
});

async function sendControlMessage(msg) {
    let [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tab && tab.url.includes("linkedin.com")) {
        chrome.tabs.sendMessage(tab.id, { action: "ping" }, (response) => {
            if (chrome.runtime.lastError) {
                chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ['content.js'] }, () => {
                    chrome.tabs.sendMessage(tab.id, msg);
                });
            } else {
                chrome.tabs.sendMessage(tab.id, msg);
            }
        });
    }
}