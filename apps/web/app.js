const API_BASE = '/api/v1';

// State
const state = {
    token: localStorage.getItem('token') || null,
    refresh: localStorage.getItem('refresh') || null,
    tenantId: null,
    lang: localStorage.getItem('lang') || ((navigator.language || '').startsWith('de') ? 'de' : 'en'),
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
        team_members_title: 'Team Members',
        remove: 'Remove',
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
        team_members_title: 'Teammitglieder',
        remove: 'Entfernen',
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
    if (viewName === 'settings') loadTeamMembers();
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
    if (state.ws) { state.ws.onclose = null; state.ws.close(); state.ws = null; }
    // nothing of the previous account may remain visible for the next person on this device
    state.lastEventId = null;
    state.automation = null;
    ['#chat-messages', '#credentials-list', '#stream-keys-list', '#sessions-list', '#stats-content', '#team-members-list'].forEach(sel => {
        const el = $(sel); if (el) el.innerHTML = '';
    });
    const nk = $('#new-stream-key-result'); if (nk) { nk.innerHTML = ''; nk.classList.add('hidden'); }
    // back to a clean login tab: no leftover register tab / typed values for the next person
    $$('#login-form, #register-form, #team-form').forEach(f => f.reset());
    showAuthTab('login');
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
    loadTeamMembers();
    
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
        const wsUrl = `${wsProto}//${window.location.host}/ws/v1/chat?ticket=${encodeURIComponent(tReq.ticket)}`;
        
        state.ws = new WebSocket(wsUrl);
        state.ws.onmessage = (e) => {
            const data = JSON.parse(e.data);
            if (data.type === 'chat_event' && data.event) {
                state.lastEventId = Math.max(state.lastEventId || 0, data.event.id);
                renderChatMessage(data.event);
            }
        };
        // reconnect with replay (since_id) so nothing is lost while the connection was down
        state.ws.onclose = () => {
            state.ws = null;
            if (state.token && $('#view-chat').classList.contains('active')) {
                setTimeout(() => connectWs(), 3000);
            }
        };

        loadChatInbox();
    } catch (e) {}
}

async function loadChatInbox() {
    try {
        const since = state.lastEventId ? `?since_id=${state.lastEventId}` : '';
        const events = await apiFetch(`${API_BASE}/chat/inbox${since}`);
        if (!since) $('#chat-messages').innerHTML = '';
        events.forEach(ev => { state.lastEventId = Math.max(state.lastEventId || 0, ev.id); renderChatMessage(ev); });
        if (!since && !events.length) {
            $('#chat-messages').innerHTML = `<p class="help-text">${state.lang === 'de'
                ? 'Noch keine Nachrichten. Sobald ein Portal verbunden ist und du live bist, erscheinen alle Chats hier.'
                : 'No messages yet. Once a portal is connected and you are live, all chats appear here.'}</p>`;
        }
        scrollToBottom();
    } catch (e) {}
}

function renderChatMessage(msg) {
    const container = $('#chat-messages');
    const isTip = msg.event_type === 'tip';
    const div = document.createElement('div');
    div.className = `chat-message ${isTip ? 'chat-tip' : ''}`;
    
    const time = new Date(msg.ts + (msg.ts.endsWith('Z') ? '' : 'Z')).toLocaleTimeString();
    const badge = `<span class="platform-badge platform-${escapeHTML(msg.platform)}">${escapeHTML(msg.platform)}</span>`;
    const sender = escapeHTML(msg.is_outgoing ? (msg.is_automated ? 'Auto' : 'Du') : (msg.sender_name || 'System'));
    const text = escapeHTML(msg.message || (isTip ? `${msg.tokens} Tokens` : (msg.event_type === 'join' ? 'joined' : '')));
    const help = container.querySelector('.help-text');
    if (help) help.parentNode.removeChild(help);
    
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
        state.automation = auto;  // keep fields the form does not show (platform filter, goal label)
    } catch (e) {}
}

async function saveAutomation(e) {
    e.preventDefault();
    const payload = {
        greet_enabled: $('#auto-greet-enabled').checked,
        greet_template: $('#auto-greet-template').value,
        greet_cooldown_hours: parseInt($('#auto-greet-cooldown').value, 10),
        greet_platforms: (state.automation && state.automation.greet_platforms) || [],  // [] = all platforms
        tip_goal_label: (state.automation && state.automation.tip_goal_label) || null,
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
        const L = state.lang === 'de';
        const c = $('#stats-content');
        
        const plats = Object.entries(stats.plattformen || {});
        const sum = (k) => plats.reduce((acc, [, d]) => acc + (d[k] || 0), 0);
        let html = '<div class="stats-grid">';
        const card = (label, value) => `<div class="stat-card"><div class="stat-label">${label}</div><div class="stat-value">${value}</div></div>`;
        html += card(L ? 'Umsatz (30 Tage)' : 'Revenue (30 days)', `$${(stats.umsatz_usd_gesamt || 0).toFixed(2)}`);
        html += card('Tokens', sum('tokens'));
        html += card(L ? 'Aktive Chatter' : 'Active chatters', sum('aktive_chatter'));
        html += card(L ? 'Stream-Stunden' : 'Stream hours', stats.stream_stunden);
        html += card(L ? 'Umsatz / Stunde' : 'Revenue / hour', stats.umsatz_pro_stunde_usd != null ? `$${stats.umsatz_pro_stunde_usd.toFixed(2)}` : '-');
        html += `</div>`;
        if (plats.length) {
            html += `<h4>${L ? 'Pro Portal' : 'Per portal'}</h4><ul class="item-list">`;
            for (const [p, d] of plats) {
                const top = d.top_spender.map(t => `${escapeHTML(t.name)} (${t.tokens})`).join(', ');
                html += `<li><span class="platform-badge platform-${escapeHTML(p)}">${escapeHTML(p)}</span>
                    <strong>${d.tokens} Tokens · $${d.umsatz_usd.toFixed(2)}</strong> · ${d.tips} Tips · ${d.nachrichten} ${L ? 'Nachrichten' : 'messages'}
                    ${top ? `<br><small>Top: ${top}</small>` : ''}</li>`;
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

// Team Management
async function loadTeamMembers() {
    const ul = $('#team-members-list');
    if (!ul) return;
    try {
        const members = await apiFetch(`${API_BASE}/auth/team`);
        const sec = $('#team-section');
        if (sec) sec.classList.remove('hidden');
        if (!members || !members.length) { ul.innerHTML = `<li>${translations[state.lang].no_items}</li>`; return; }
        ul.innerHTML = members.map(m => `
            <li>
                <span><strong>${escapeHTML(m.email)}</strong> (${escapeHTML(m.role)})</span>
                ${m.role !== 'owner' ? `<button class="btn btn-sm btn-danger" onclick="app.removeTeamMember('${m.id}')">${translations[state.lang].remove}</button>` : ''}
            </li>
        `).join('');
    } catch (e) {
        const sec = $('#team-section');
        if (sec) sec.classList.add('hidden');
    }
}

async function addTeamMember(e) {
    e.preventDefault();
    const payload = {
        email: $('#team-email').value,
        password: $('#team-password').value,
        role: $('#team-role').value
    };
    try {
        await apiFetch(`${API_BASE}/auth/team`, { method: 'POST', body: JSON.stringify(payload) });
        showToast(state.lang === 'de' ? 'Teammitglied hinzugefügt' : 'Team member added');
        $('#team-email').value = '';
        $('#team-password').value = '';
        loadTeamMembers();
    } catch (e) {}
}

async function removeTeamMember(id) {
    try {
        await apiFetch(`${API_BASE}/auth/team/${id}`, { method: 'DELETE' });
        showToast(state.lang === 'de' ? 'Teammitglied entfernt' : 'Team member removed');
        loadTeamMembers();
    } catch (e) {}
}

// Expose to window
window.app = {
    login, register, logout, toggleLang, showAuthTab, showView,
    addCredential, createStreamKey, revokeStreamKey,
    sendChatMessage, saveAutomation, checkoutStripe, deleteAccount,
    loadTeamMembers, addTeamMember, removeTeamMember
};

// Start
document.addEventListener('DOMContentLoaded', init);
