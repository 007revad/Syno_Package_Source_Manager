document.addEventListener('DOMContentLoaded', () => {
    const feedList = document.getElementById('feedList');
    const status = document.getElementById('status');
    const saveBtn = document.getElementById('saveBtn');
    const cancelBtn = document.getElementById('cancelBtn');

    let originalFeeds = [];  // last-loaded-from-server state
    let feeds = [];          // working copy the user is editing

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
        status.style.display = 'block';
    }

    function hideStatus() {
        status.style.display = 'none';
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
            });

            const slider = document.createElement('span');
            slider.className = 'slider';

            label.appendChild(input);
            label.appendChild(slider);

            row.appendChild(info);
            row.appendChild(label);
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
