document.addEventListener('DOMContentLoaded', () => {
    const feedList = document.getElementById('feedList');
    const status = document.getElementById('status');
    const saveBtn = document.getElementById('saveBtn');
    const cancelBtn = document.getElementById('cancelBtn');
    const addBtn = document.getElementById('addBtn');
    const addModalOverlay = document.getElementById('addModalOverlay');
    const addModalBody = document.getElementById('addModalBody');
    const addModalClose = document.getElementById('addModalClose');
    const addModalCancel = document.getElementById('addModalCancel');
    const addModalConfirm = document.getElementById('addModalConfirm');

    let originalFeeds = [];  // last-loaded-from-server state
    let feeds = [];          // working copy the user is editing
    let catalogEntries = []; // available sources shown in the Add modal

    // Trailing-slash-insensitive comparison, matching the server-side
    // normalization used when filtering the catalog.
    function normalizeFeedUrl(url) {
        return (url || '').trim().replace(/\/+$/, '');
    }

    function callAPI(action, params = {}) {
        const urlParams = new URLSearchParams();
        urlParams.append('action', action);
        Object.keys(params).forEach(key => urlParams.append(key, params[key]));

        return fetch('api.cgi', {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: urlParams.toString()
        })
        .then(res => {
            if (!res.ok) throw new Error('Network response was not ok');
            return res.json();
        });
    }

    function showStatus(kind, message) {
        status.className = `status ${kind}`;
        status.textContent = message;
    }

    function hideStatus() {
        status.className = 'status';
        status.textContent = '';
    }

    function render() {
        if (!feeds.length) {
            feedList.innerHTML = '<p>No feeds found.</p>';
            return;
        }

        feedList.innerHTML = '';
        feeds.forEach((f, idx) => {
            const row = document.createElement('div');
            row.className = 'feed-row';

            const info = document.createElement('div');
            info.className = 'feed-info';

            const name = document.createElement('span');
            name.className = 'feed-name';
            name.textContent = f.name;

            const url = document.createElement('span');
            url.className = 'feed-url';
            url.textContent = f.feed;

            info.appendChild(name);
            info.appendChild(url);

            const label = document.createElement('label');
            label.className = 'switch';

            const input = document.createElement('input');
            input.type = 'checkbox';
            input.checked = !!f.enabled;
            input.addEventListener('change', () => {
                feeds[idx].enabled = input.checked;
                render();
            });

            const slider = document.createElement('span');
            slider.className = 'slider';

            label.appendChild(input);
            label.appendChild(slider);

            row.appendChild(info);

            // Only offer removal for disabled feeds - an enabled one
            // should be toggled off first, which also protects against
            // accidentally deleting something still live in DSM.
            const controls = document.createElement('div');
            controls.className = 'row-controls';

            if (!f.enabled) {
                const del = document.createElement('button');
                del.type = 'button';
                del.className = 'delete-row-btn';
                del.title = 'Remove this feed permanently (takes effect on Save)';
                del.textContent = 'Delete';
                del.addEventListener('click', () => {
                    feeds.splice(idx, 1);
                    render();
                    showStatus('info', `"${f.name}" removed - click Save to make it permanent`);
                });
                controls.appendChild(del);
            }

            controls.appendChild(label);
            row.appendChild(controls);
            feedList.appendChild(row);
        });
    }

    function loadFeeds() {
        feedList.innerHTML = 'Loading feeds...';
        hideStatus();
        callAPI('list')
            .then(res => {
                if (res.success) {
                    // Deep copy so originalFeeds and feeds don't share references
                    originalFeeds = JSON.parse(JSON.stringify(res.result));
                    feeds = JSON.parse(JSON.stringify(res.result));
                    render();
                } else {
                    feedList.innerHTML = '';
                    showStatus('error', res.message || 'Failed to load feeds');
                }
            })
            .catch(err => {
                feedList.innerHTML = '';
                showStatus('error', 'Failed to load feeds: ' + err.message);
            });
    }

    function openAddModal() {
        addModalOverlay.classList.add('open');
        addModalBody.innerHTML = 'Loading available sources...';
        callAPI('catalog')
            .then(res => {
                if (!res.success) {
                    addModalBody.innerHTML = `<p>${res.message || 'Failed to load available sources'}</p>`;
                    return;
                }
                // Also drop anything already sitting in the current
                // (unsaved) working copy, so a source added but not
                // yet saved doesn't show up again as "available".
                const currentFeedUrls = new Set(feeds.map(f => normalizeFeedUrl(f.feed)));
                catalogEntries = (res.result || []).filter(e => !currentFeedUrls.has(normalizeFeedUrl(e.feed)));
                renderCatalog();
            })
            .catch(err => {
                addModalBody.innerHTML = `<p>Failed to load available sources: ${err.message}</p>`;
            });
    }

    function closeAddModal() {
        addModalOverlay.classList.remove('open');
    }

    function renderCatalog() {
        if (!catalogEntries.length) {
            addModalBody.innerHTML = '<p>No additional sources are available to add.</p>';
            return;
        }

        addModalBody.innerHTML = '';
        catalogEntries.forEach((entry, idx) => {
            const row = document.createElement('div');
            row.className = 'catalog-row';

            const input = document.createElement('input');
            input.type = 'checkbox';
            input.id = `catalog-${idx}`;
            input.dataset.idx = idx;

            const label = document.createElement('label');
            label.htmlFor = `catalog-${idx}`;
            label.className = 'catalog-info';

            const name = document.createElement('span');
            name.className = 'feed-name';
            name.textContent = entry.name;

            const url = document.createElement('span');
            url.className = 'feed-url';
            url.textContent = entry.feed;

            label.appendChild(name);
            label.appendChild(url);

            row.appendChild(input);
            row.appendChild(label);
            addModalBody.appendChild(row);
        });
    }

    addBtn.addEventListener('click', openAddModal);
    addModalClose.addEventListener('click', closeAddModal);
    addModalCancel.addEventListener('click', closeAddModal);
    addModalOverlay.addEventListener('click', (e) => {
        if (e.target === addModalOverlay) closeAddModal();
    });

    addModalConfirm.addEventListener('click', () => {
        const checked = Array.from(addModalBody.querySelectorAll('input[type="checkbox"]:checked'));
        if (!checked.length) {
            closeAddModal();
            return;
        }

        checked.forEach(input => {
            const entry = catalogEntries[Number(input.dataset.idx)];
            if (!entry) return;
            feeds.push({ feed: entry.feed, name: entry.name, enabled: true });
        });

        closeAddModal();
        render();
        showStatus('info', `${checked.length} source${checked.length > 1 ? 's' : ''} added - click Save to make ${checked.length > 1 ? 'them' : 'it'} permanent`);
    });

    saveBtn.addEventListener('click', () => {
        saveBtn.disabled = true;
        cancelBtn.disabled = true;
        hideStatus();
        callAPI('save', { data: JSON.stringify(feeds) })
            .then(res => {
                if (res.success) {
                    originalFeeds = JSON.parse(JSON.stringify(feeds));
                    showStatus('success', res.message || 'Feeds saved');
                } else {
                    showStatus('error', res.message || 'Failed to save feeds');
                }
            })
            .catch(err => {
                showStatus('error', 'Failed to save feeds: ' + err.message);
            })
            .finally(() => {
                saveBtn.disabled = false;
                cancelBtn.disabled = false;
            });
    });

    cancelBtn.addEventListener('click', () => {
        feeds = JSON.parse(JSON.stringify(originalFeeds));
        render();
        showStatus('info', 'Changes discarded');
    });

    loadFeeds();
});
