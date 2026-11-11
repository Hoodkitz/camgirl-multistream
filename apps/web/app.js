const API_BASE = '/api/v1';

// State
const state = {
    token: localStorage.getItem('token') || null,
    refresh: localStorage.getItem('refresh') || null,
    tenantId: null,
    lang: localStorage.getItem('lang') || 'en',
    ws: null,
    platforms: ['chaturbate', 'bongacams', 'stripchat', 'camsoda'],
    tenant: null
};

// I18n
const translations = {
    en: {
        login_title: 'Login / Register',
        login_tab: 'Login',
        register_tab: 'Register',
        email: 'E-Mail',
        password: 'Password',
        password_new: 'Password (min. 10 characters)',
        login_btn: 'Login',
        tenant_name: 'Studio / Model name',
        register_btn: 'Create account',
        logout: 'Logout',
        nav_dashboard: 'Dashboard',
        nav_chat: 'Chat Inbox',
        nav_automation: 'Automation',
        nav_stats: 'Stats',
        nav_settings: 'Settings',
        credentials_title: 'Platform Credentials',
        add: 'Add',
        stream_keys_title: 'Stream Keys',
        create: 'Create',
        live_sessions_title: 'Live Sessions',
        send: 'Send',
        automation_title: 'Automation Settings',
        enable_greet: 'Enable Greeting',
        greet_template: 'Template ({username}, {platform})',
        greet_cooldown: 'Cooldown (hours)',
        tip_goal: 'Tip Goal (Tokens)',
        obs_webhook: 'OBS Webhook URL (HTTPS)',
        save: 'Save',
        stats_title: 'Statistics',
        subscription: 'Subscription',
        upgrade_pro: 'Upgrade to Pro',
        danger_zone: 'Danger Zone',
        delete_account: 'Delete Account',
        delete_warning: 'This action is irreversible. All data will be physically deleted.',
        confirm_name: 'Type Tenant Name to confirm:',
        delete_btn: 'Permanently Delete',
        revoke: 'Revoke',
        reauth_prompt: 'Please enter your password to confirm the deletion:',
        no_items: 'No items found.'
    },
    de: {
        login_title: 'Anmelden / Registrieren',
        login_tab: 'Anmelden',
        register_tab: 'Registrieren',
        email: 'E-Mail',
        password: 'Passwort',
        password_new: 'Passwort (mind. 10 Zeichen)',
        login_btn: 'Anmelden',
        tenant_name: 'Studio- / Modelname',
        register_btn: 'Konto erstellen',
        logout: 'Abmelden',
        nav_dashboard: 'Übersicht',
        nav_chat: 'Chat-Postfach',
        nav_automation: 'Automatisierung',
        nav_stats: 'Statistiken',
        nav_settings: 'Einstellungen',
        credentials_title: 'Plattform-Zugangsdaten',
        add: 'Hinzufügen',
        stream_keys_title: 'Stream-Schlüssel',
        create: 'Erstellen',
        live_sessions_title: 'Live-Sitzungen',
        send: 'Senden',
        automation_title: 'Automatisierungseinstellungen',
        enable_greet: 'Begrüßung aktivieren',
        greet_template: 'Vorlage ({username}, {platform})',
        greet_cooldown: 'Abklingzeit (Stunden)',
        tip_goal: 'Spendenziel (Tokens)',
        obs_webhook: 'OBS Webhook URL (HTTPS)',
        save: 'Speichern',
        stats_title: 'Statistiken',
        subscription: 'Abonnement',
        upgrade_pro: 'Auf Pro upgraden',
        danger_zone: 'Gefahrenzone',
        delete_account: 'Konto löschen',
        delete_warning: 'Diese Aktion ist unumkehrbar. Alle Daten werden physisch gelöscht.',
        confirm_name: 'Mandantenname zur Bestätigung eingeben:',
        delete_btn: 'Endgültig löschen',
        revoke: 'Widerrufen',
        reauth_prompt: 'Bitte Passwort eingeben, um die Löschung zu bestätigen:',
        no_items: 'Keine Einträge gefunden.'
    }
};

// Utils

function escapeHTML(str) {
    if (!str) return '';
    return str.toString().replace(/[&<>'"]/g, 
        tag => ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            "'": '&#39;',
            '"': '&quot;'
        }[tag] || tag)
    );
}

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

function showToast(msg, type = 'success') {
    const t = $('#toast');
    t.textContent = msg;
    t.className = `toast ${type}`;
    setTimeout(() => t.classList.add('hidden'), 3000);
}

function saveTokens(res) {
    state.token = res.access_token;
    state.refresh = res.refresh_token;
    localStorage.setItem('token', state.token);
    localStorage.setItem('refresh', state.refresh);
}

let refreshing = null;
async function tryRefresh() {
    if (!state.refresh) return false;
    refreshing = refreshing || fetch(`${API_BASE}/auth/refresh`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: state.refresh })
    }).then(async r => { if (!r.ok) return false; saveTokens(await r.json()); return true; })
      .catch(() => false).finally(() => { setTimeout(() => { refreshing = null; }, 0); });
    return refreshing;
}

async function apiFetch(endpoint, options = {}, retried = false) {
    const headers = { 'Content-Type': 'application/json' };
    if (state.token) headers['Authorization'] = `Bearer ${state.token}`;

    try {
        const res = await fetch(endpoint, { ...options, headers: { ...headers, ...options.headers } });
        if (!res.ok) {
            if (res.status === 401 && !retried && !endpoint.includes('/auth/') && await tryRefresh()) {
                return apiFetch(endpoint, options, true);
            }
            if (res.status === 401 && !endpoint.includes('/auth/')) { logout(); throw new Error('Unauthorized'); }
            const err = await res.json().catch(() => ({ detail: res.statusText }));
            throw new Error(err.detail || 'API Error');
        }
        return res.status !== 204 ? await res.json() : null;
    } catch (e) {
        showToast(e.message, 'error');
        throw e;
    }
}

// i18n
function updateLang() {
    $$('[data-i18n]').forEach(el => {
        const key = el.getAttribute('data-i18n');
        if (translations[state.lang][key]) {
            if (el.tagName === 'INPUT' && el.type !== 'submit' && el.type !== 'checkbox') {
                // not fully covering placeholder translation here for simplicity, focusing on innerText
            }
            el.innerText = translations[state.lang][key];
        }
    });
    $('#lang-btn').innerText = state.lang === 'en' ? 'DE' : 'EN';
}

function toggleLang() {
    state.lang = state.lang === 'en' ? 'de' : 'en';
    localStorage.setItem('lang', state.lang);
    updateLang();
}

// Navigation & Auth Flow
function showAuthTab(tab) {
    $$('.tab-btn').forEach(b => b.classList.remove('active'));
    $$('.auth-form').forEach(f => f.classList.remove('active'));
    $(`.tab-btn[onclick*="${tab}"]`).classList.add('active');
    $(`#${tab}-form`).classList.add('active');
}

function showView(viewName) {
    $$('.nav-btn').forEach(b => b.classList.remove('active'));
    $$('.content-view').forEach(v => v.classList.remove('active'));
    $(`.nav-btn[onclick*="${viewName}"]`).classList.add('active');
    $(`#view-${viewName}`).classList.add('active');
    
    if (viewName === 'chat' && !state.ws) connectWs();
}

async function init() {
    updateLang();
    if (state.token) {
        try {
            state.tenant = await apiFetch(`${API_BASE}/tenants/me`);
            state.tenantId = state.tenant.id;
            showApp();
        } catch (e) {
            logout();
        }
    } else {
        $('#auth-section').classList.add('active');
        $('#main-section').classList.remove('active');
    }
}

async function login(e) {
    e.preventDefault();
    try {
        const res = await apiFetch(`${API_BASE}/auth/login`, {
            method: 'POST',
            body: JSON.stringify({ email: $('#login-email').value, password: $('#login-password').value })
        });
        saveTokens(res);
        $('#login-password').value = '';
        init();
    } catch (e) {}
}

async function register(e) {
    e.preventDefault();
    try {
        const res = await apiFetch(`${API_BASE}/auth/register`, {
            method: 'POST',
            body: JSON.stringify({ tenant_name: $('#reg-name').value, email: $('#reg-email').value,
                                   password: $('#reg-password').value })
        });
        saveTokens(res);
        $('#reg-password').value = '';
        init();
    } catch (e) {}
}

function logout() {
    state.token = null;
    state.refresh = null;
    localStorage.removeItem('refresh');
    state.tenantId = null;
    state.tenant = null;
    localStorage.removeItem('token');
    if (state.ws) { state.ws.close(); state.ws = null; }
    $('#auth-section').classList.add('active');
    $('#main-section').classList.remove('active');
}

function showApp() {
    $('#auth-section').classList.remove('active');
    $('#main-section').classList.add('active');
    $('#user-info').textContent = `${state.tenant.name} (${state.tenant.tier})`;
    
    // Init platform selects
    const pSelect = $('#chat-platform-select');
    pSelect.innerHTML = state.platforms.map(p => `<option value="${p}">${p}</option>`).join('');
    
    loadDashboard();
    loadAutomation();
    loadStats();
    
    $('#subscription-status').textContent = `Current Tier: ${state.tenant.tier}`;
}

// Dashboard Features
async function loadDashboard() {
    loadCredentials();
    loadStreamKeys();
    loadSessions();
}

async function loadCredentials() {
    try {
        const creds = await apiFetch(`${API_BASE}/credentials`);
        const ul = $('#credentials-list');
        if (!creds.length) { ul.innerHTML = `<li>${translations[state.lang].no_items}</li>`; return; }
        ul.innerHTML = creds.map(c => `
            <li>
                <span><strong>${escapeHTML(c.platform)}</strong>: ${escapeHTML(c.account_username)} ${c.ingest_url ? `(${escapeHTML(c.ingest_url)})` : ''}</span>
                <span class="platform-badge ${c.enabled ? 'platform-camsoda' : 'platform-bongacams'}">${c.enabled ? 'Active' : 'Inactive'}</span>
            </li>
        `).join('');
    } catch (e) {}
}

async function addCredential(e) {
    e.preventDefault();
    const payload = {
        platform: $('#cred-platform').value,
        account_username: $('#cred-username').value,
        stream_key: $('#cred-streamkey').value,
        ingest_url: $('#cred-ingest').value || null
    };
    try {
        await apiFetch(`${API_BASE}/credentials`, { method: 'POST', body: JSON.stringify(payload) });
        showToast('Credential added');
        e.target.reset();
        loadCredentials();
    } catch (e) {}
}

async function loadStreamKeys() {
    try {
        const keys = await apiFetch(`${API_BASE}/streams/keys`);
        const ul = $('#stream-keys-list');
        if (!keys.length) { ul.innerHTML = `<li>${translations[state.lang].no_items}</li>`; return; }
        ul.innerHTML = keys.map(k => `
            <li>
                <span>${escapeHTML(k.label)} ${k.revoked ? '(Revoked)' : ''}</span>
                ${!k.revoked ? `<button class="btn btn-sm btn-outline" onclick="app.revokeStreamKey('${k.id}')">${translations[state.lang].revoke}</button>` : ''}
            </li>
        `).join('');
    } catch (e) {}
}

async function createStreamKey(e) {
    e.preventDefault();
    try {
        const res = await apiFetch(`${API_BASE}/streams/keys`, {
            method: 'POST',
            body: JSON.stringify({ label: $('#sk-label').value })
        });
        const alert = $('#new-stream-key-result');
        alert.innerHTML = `<strong>Key:</strong> ${res.stream_key}<br><strong>RTMP:</strong> ${res.rtmp_url}<br><em>Save the key now, it won't be shown again!</em>`;
        alert.classList.remove('hidden');
        $('#sk-label').value = '';
        loadStreamKeys();
    } catch (e) {}
}

async function revokeStreamKey(id) {
    try {
        await apiFetch(`${API_BASE}/streams/keys/${id}`, { method: 'DELETE' });
        loadStreamKeys();
        showToast('Key revoked');
    } catch (e) {}
}

async function loadSessions() {
    try {
        const sessions = await apiFetch(`${API_BASE}/streams/sessions`);
        const ul = $('#sessions-list');
        if (!sessions.length) { ul.innerHTML = `<li>${translations[state.lang].no_items}</li>`; return; }
        ul.innerHTML = sessions.map(s => `
            <li>
                <span>Started: ${new Date(s.started_at).toLocaleString()} | Targets: ${escapeHTML(s.targets.length)}</span>
                <span class="platform-badge platform-${s.ended_at ? 'bongacams' : 'camsoda'}">${s.ended_at ? 'Ended' : 'Live'}</span>
            </li>
        `).join('');
    } catch (e) {}
}

// Chat WebSocket
async function connectWs() {
    if (state.ws) return;
    try {
        const tReq = await apiFetch(`${API_BASE}/ws/ticket`, { method: 'POST' });
        const wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${wsProto}//${window.location.host}${API_BASE}/ws/chat?ticket=${tReq.ticket}`;
        
        state.ws = new WebSocket(wsUrl);
        state.ws.onmessage = (e) => {
            const data = JSON.parse(e.data);
            if (data.type === 'chat' || data.type === 'tip') {
                renderChatMessage(data);
            }
        };
        state.ws.onclose = () => { state.ws = null; };
        
        // Setup ping
        setInterval(() => {
            if (state.ws && state.ws.readyState === WebSocket.OPEN) {
                state.ws.send(JSON.stringify({ type: 'ping' }));
            }
        }, 25000);
        
        loadChatInbox();
    } catch (e) {}
}

async function loadChatInbox() {
    try {
        const events = await apiFetch(`${API_BASE}/chat/inbox`);
        $('#chat-messages').innerHTML = '';
        events.reverse().forEach(renderChatMessage);
        scrollToBottom();
    } catch (e) {}
}

function renderChatMessage(msg) {
    const container = $('#chat-messages');
    const isTip = msg.event_type === 'tip';
    const div = document.createElement('div');
    div.className = `chat-message ${isTip ? 'chat-tip' : ''}`;
    
    const time = new Date(msg.timestamp).toLocaleTimeString();
    const badge = `<span class="platform-badge platform-${msg.platform}">${msg.platform}</span>`;
    const sender = escapeHTML(msg.sender.username || 'System');
    const text = escapeHTML(msg.payload.message || (isTip ? `Tipped ${msg.payload.tokens_spent} tokens` : ''));
    
    div.innerHTML = `
        <div class="chat-meta">
            <span>${badge} <strong>${sender}</strong></span>
            <span>${time}</span>
        </div>
        <div class="chat-text">${text}</div>
    `;
    container.appendChild(div);
    scrollToBottom();
}

function scrollToBottom() {
    const c = $('#chat-messages');
    c.scrollTop = c.scrollHeight;
}

async function sendChatMessage(e) {
    e.preventDefault();
    const platform = $('#chat-platform-select').value;
    const text = $('#chat-input-text').value;
    try {
        await apiFetch(`${API_BASE}/chat/reply`, {
            method: 'POST',
            body: JSON.stringify({ platform, text })
        });
        $('#chat-input-text').value = '';
        // Note: Actual display relies on WS echoing or reload, optimistically showing requires more logic
        showToast('Message queued');
    } catch (e) {}
}

// Automation
async function loadAutomation() {
    try {
        const auto = await apiFetch(`${API_BASE}/automation`);
        $('#auto-greet-enabled').checked = auto.greet_enabled;
        $('#auto-greet-template').value = auto.greet_template;
        $('#auto-greet-cooldown').value = auto.greet_cooldown_hours;
        $('#auto-tip-goal').value = auto.tip_goal_tokens || '';
        $('#auto-obs-webhook').value = auto.obs_webhook_url || '';
    } catch (e) {}
}

async function saveAutomation(e) {
    e.preventDefault();
    const payload = {
        greet_enabled: $('#auto-greet-enabled').checked,
        greet_template: $('#auto-greet-template').value,
        greet_cooldown_hours: parseInt($('#auto-greet-cooldown').value, 10),
        greet_platforms: state.platforms, // Simplified
        tip_goal_tokens: $('#auto-tip-goal').value ? parseInt($('#auto-tip-goal').value, 10) : null,
        obs_webhook_url: $('#auto-obs-webhook').value || null
    };
    try {
        await apiFetch(`${API_BASE}/automation`, { method: 'PUT', body: JSON.stringify(payload) });
        showToast('Automation saved');
    } catch (e) {}
}

// Stats
async function loadStats() {
    try {
        const stats = await apiFetch(`${API_BASE}/stats/overview`);
        const c = $('#stats-content');
        
        let html = '<div class="stats-grid">';
        html += `<div class="stat-card"><div class="stat-label">Total Tokens</div><div class="stat-value">${stats.total_tokens}</div></div>`;
        html += `<div class="stat-card"><div class="stat-label">Fiat Equivalent (USD)</div><div class="stat-value">$${stats.total_fiat_usd.toFixed(2)}</div></div>`;
        html += `<div class="stat-card"><div class="stat-label">Total Chatter</div><div class="stat-value">${stats.total_chatter}</div></div>`;
        html += `</div>`;
        
        if (Object.keys(stats.per_platform).length > 0) {
            html += '<h4>Per Platform Tokens</h4><ul class="item-list">';
            for (const [p, data] of Object.entries(stats.per_platform)) {
                html += `<li><span class="platform-badge platform-${p}">${p}</span> <strong>${data.tokens} tokens</strong></li>`;
            }
            html += '</ul>';
        }
        
        c.innerHTML = html;
    } catch (e) {}
}

// Settings
async function checkoutStripe(tier = 'pro') {
    try {
        const res = await apiFetch(`${API_BASE}/billing/checkout`, { method: 'POST', body: JSON.stringify({ tier }) });
        window.location.href = res.url;
    } catch (e) {}
}

async function deleteAccount(e) {
    e.preventDefault();
    const confirmName = $('#delete-confirm-name').value;

    // Re-authentication: the server only deletes with a login younger than 5 minutes
    const password = prompt(translations[state.lang].reauth_prompt);
    if (!password) { showToast('Re-authentication required', 'error'); return; }

    try {
        saveTokens(await apiFetch(`${API_BASE}/auth/reauth`, {
            method: 'POST',
            body: JSON.stringify({ password })
        }));

        await apiFetch(`${API_BASE}/tenants/me`, {
            method: 'DELETE',
            headers: { 'X-Confirm-Delete': confirmName }
        });
        showToast('Account deleted');
        setTimeout(() => logout(), 1000);
    } catch (e) {}
}

// Expose to window
window.app = {
    login, register, logout, toggleLang, showAuthTab, showView,
    addCredential, createStreamKey, revokeStreamKey,
    sendChatMessage, saveAutomation, checkoutStripe, deleteAccount
};

// Start
document.addEventListener('DOMContentLoaded', init);
