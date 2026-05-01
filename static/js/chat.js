(function () {
  const config = window.TherapInHandConfig;
  if (!config) return;

  const messagesEl = document.getElementById("chatMessages");
  const formEl = document.getElementById("chatForm");
  const inputEl = document.getElementById("messageInput");
  const sendBtnEl = document.getElementById("sendBtn");
  const statusEl = document.getElementById("chatStatus");
  const chatTitleEl = document.getElementById("chatTitle");
  const historyItemsEl = document.getElementById("historyItems");
  const newChatBtnEl = document.getElementById("newChatBtn");
  const sidebarToggleEl = document.getElementById("sidebarToggle");
  const sidebarEl = document.getElementById("chatSidebar");
  const authHelpers = window.TherapInHandFetch;

  let isSending = false;
  let activeRequestId = null;
  let activeChatId = config.initialSessionId || null;
  let chats = [];
  let editingChatId = null;
  const renderedKeys = new Set();
  const sidebarMedia = window.matchMedia("(max-width: 1080px)");
  const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

  function chatDetailUrl(chatId) {
    return (config.chatDetailUrlTemplate || "").replace("__CHAT_ID__", encodeURIComponent(chatId));
  }

  function chatRenameUrl(chatId) {
    return (config.chatRenameUrlTemplate || "").replace("__CHAT_ID__", encodeURIComponent(chatId));
  }

  function escapeHtml(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function setStatus(text) {
    if (statusEl) statusEl.textContent = text;
  }

  function setSendingState(nextState) {
    isSending = nextState;
    if (sendBtnEl) sendBtnEl.disabled = nextState;
    if (inputEl) inputEl.disabled = nextState;
    if (sendBtnEl) sendBtnEl.textContent = nextState ? "Sending..." : "Send";
    if (formEl) formEl.setAttribute("aria-busy", nextState ? "true" : "false");
    setStatus(nextState ? "TherapInHand is typing..." : "Ready");
  }

  function autoResizeTextarea() {
    if (!inputEl) return;
    inputEl.style.height = "auto";
    inputEl.style.height = `${Math.min(inputEl.scrollHeight, 200)}px`;
  }

  function isNearBottom() {
    return messagesEl.scrollHeight - messagesEl.scrollTop - messagesEl.clientHeight < 120;
  }

  function scrollToBottom(force = false) {
    if (!messagesEl) return;
    if (force || isNearBottom()) {
      messagesEl.scrollTo({
        top: messagesEl.scrollHeight,
        behavior: prefersReducedMotion.matches ? "auto" : "smooth",
      });
    }
  }

  function createMessageRow(role, text, options = {}) {
    const row = document.createElement("div");
    row.className = `message-row ${role}${options.loading ? " is-loading" : ""}`;

    const bubble = document.createElement("div");
    bubble.className = `message-bubble${options.loading ? " loading" : ""}`;

    if (options.loading) {
      bubble.innerHTML = `
        <span>TherapInHand is typing</span>
        <span class="typing-dots" aria-hidden="true">
          <span></span><span></span><span></span>
        </span>
      `;
    } else {
      bubble.textContent = text || "";
    }

    row.appendChild(bubble);
    return row;
  }

  function appendMessage(role, text, options = {}) {
    const messageKey = options.messageKey || `${role}:${text}`;
    if (!options.loading && renderedKeys.has(messageKey)) {
      return null;
    }
    const row = createMessageRow(role, text, options);
    if (!options.loading) {
      renderedKeys.add(messageKey);
    }
    messagesEl.appendChild(row);
    scrollToBottom(true);
    return row;
  }

  function emptyStateMarkup() {
    return `
      <div class="empty-state">
        <div class="empty-state-mark">TH</div>
        <h3>Start a new conversation</h3>
        <p>Share what feels most important right now. The chat stays calm, remembers the thread, and keeps the same safety-focused support underneath.</p>
      </div>
    `;
  }

  function renderHistory(history) {
    messagesEl.innerHTML = "";
    renderedKeys.clear();
    if (!Array.isArray(history) || !history.length) {
      messagesEl.innerHTML = emptyStateMarkup();
      return;
    }

    history.forEach((item) => {
      const userText = item.user_message || item.user?.text || "";
      const botText = item.bot_response || item.assistant?.text || "";
      if (userText) appendMessage("user", userText, { messageKey: `user:${item.id || userText}` });
      if (botText) appendMessage("bot", botText, { messageKey: `bot:${item.id || botText}` });
    });
  }

  async function streamText(element, text) {
    const words = String(text || "").split(/\s+/).filter(Boolean);
    element.textContent = "";
    if (!words.length) return;
    const shouldStick = isNearBottom();
    for (let index = 0; index < words.length; index += 1) {
      element.textContent += `${index ? " " : ""}${words[index]}`;
      scrollToBottom(shouldStick);
      await new Promise((resolve) => setTimeout(resolve, Math.min(40, 14 + words[index].length * 1.5)));
    }
  }

  function syncSidebarMode() {
    if (!sidebarEl) return;
    if (sidebarMedia.matches) {
      sidebarEl.classList.add("collapsed");
    } else {
      sidebarEl.classList.remove("collapsed");
    }
  }

  function relativeGroupLabel(isoDate) {
    const date = isoDate ? new Date(isoDate) : new Date();
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const compared = new Date(date.getFullYear(), date.getMonth(), date.getDate());
    const diffDays = Math.round((today - compared) / 86400000);
    if (diffDays <= 0) return "Today";
    if (diffDays === 1) return "Yesterday";
    return "Older";
  }

  function keepActiveChatVisible() {
    if (!historyItemsEl || !activeChatId || sidebarMedia.matches) return;
    const activeItem = historyItemsEl.querySelector(`.history-item[data-chat-id="${activeChatId}"]`);
    activeItem?.scrollIntoView({ block: "nearest", behavior: prefersReducedMotion.matches ? "auto" : "smooth" });
  }

  function renderChatList() {
    if (!historyItemsEl) return;
    if (!Array.isArray(chats) || !chats.length) {
      historyItemsEl.innerHTML = `
        <div class="history-empty">
          <strong>No saved chats yet</strong>
          <div>Start one from the composer and it will appear here.</div>
        </div>
      `;
      return;
    }

    const groups = { Today: [], Yesterday: [], Older: [] };
    chats.forEach((chat) => {
      groups[relativeGroupLabel(chat.updated_at || chat.created_at)].push(chat);
    });

    historyItemsEl.innerHTML = Object.entries(groups)
      .filter(([, groupChats]) => groupChats.length)
      .map(([label, groupChats]) => `
        <section class="history-group">
          <h3>${label}</h3>
          <div class="history-items">
            ${groupChats.map((chat) => `
              <article class="history-item ${chat.id === activeChatId ? "active" : ""}" data-chat-id="${chat.id}">
                <button type="button" class="history-main" data-action="open" data-chat-id="${chat.id}">
                  <strong>${escapeHtml(chat.title || "New chat")}</strong>
                  <span>${new Date(chat.updated_at || chat.created_at || Date.now()).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}</span>
                </button>
                ${editingChatId === chat.id ? `
                  <form class="history-rename-form" data-action="save-rename" data-chat-id="${chat.id}">
                    <input class="history-rename-input" name="title" value="${escapeHtml(chat.title || "New chat")}" maxlength="160" />
                    <div class="history-actions">
                      <button type="submit" class="history-icon">Save</button>
                      <button type="button" class="history-icon" data-action="cancel-rename" data-chat-id="${chat.id}">Cancel</button>
                    </div>
                  </form>
                ` : `
                <div class="history-actions">
                  <button type="button" class="history-icon" data-action="rename" data-chat-id="${chat.id}" aria-label="Rename chat">Rename</button>
                  <button type="button" class="history-icon danger" data-action="delete" data-chat-id="${chat.id}" aria-label="Delete chat">Delete</button>
                </div>
                `}
              </article>
            `).join("")}
          </div>
        </section>
      `).join("");
    window.requestAnimationFrame(keepActiveChatVisible);
  }

  async function loadChats() {
    const response = await fetch(config.chatsUrl, { credentials: "same-origin" });
    const data = await response.json();
    chats = Array.isArray(data.chats) ? data.chats : [];
    activeChatId = data.active_chat_id || activeChatId;
    renderChatList();
  }

  function updateTitleFromChats() {
    const active = chats.find((item) => item.id === activeChatId);
    if (chatTitleEl) {
      chatTitleEl.textContent = active?.title || "New chat";
    }
  }

  async function loadActiveChat(chatId, options = {}) {
    if (!chatId) return;
    activeChatId = chatId;
    setStatus(options.initial ? "Loading chat..." : "Switching chat...");
    const response = await fetch(chatDetailUrl(chatId), { credentials: "same-origin" });
    const data = await response.json();
    renderHistory(data.history || []);
    if (data.chat) {
      const nextChat = data.chat;
      const index = chats.findIndex((item) => item.id === nextChat.id);
      if (index >= 0) chats[index] = nextChat;
      else chats.unshift(nextChat);
      updateTitleFromChats();
    }
    renderChatList();
    setStatus("Ready");
    scrollToBottom(true);
  }

  async function createNewChat() {
    setStatus("Creating chat...");
    const response = await fetch(config.newChatUrl, {
      method: "POST",
      credentials: "same-origin",
      headers: authHelpers.csrfHeaders({ "Content-Type": "application/json" })
    });
    const data = await response.json();
    if (data.chat) {
      activeChatId = data.chat.id;
      chats.unshift(data.chat);
      chats = chats.filter((chat, index, arr) => arr.findIndex((item) => item.id === chat.id) === index);
      renderChatList();
      updateTitleFromChats();
      renderHistory([]);
      setStatus("Ready");
      inputEl.focus();
    }
  }

  async function deleteChat(chatId) {
    if (!window.confirm("Delete this chat permanently?")) return;
    setStatus("Deleting chat...");
    const response = await fetch(chatDetailUrl(chatId), {
      method: "DELETE",
      credentials: "same-origin",
      headers: authHelpers.csrfHeaders()
    });
    const data = await response.json();
    chats = chats.filter((chat) => chat.id !== chatId);
    if (data.chat) {
      activeChatId = data.active_chat_id;
      const exists = chats.some((chat) => chat.id === data.chat.id);
      if (!exists) chats.unshift(data.chat);
      await loadChats();
      await loadActiveChat(activeChatId);
    } else {
      renderChatList();
      renderHistory([]);
      setStatus("Ready");
    }
  }

  async function renameChat(chatId) {
    editingChatId = chatId;
    renderChatList();
    window.requestAnimationFrame(() => {
      historyItemsEl?.querySelector(`.history-rename-form[data-chat-id="${chatId}"] .history-rename-input`)?.focus();
    });
  }

  async function commitRenameChat(chatId, nextTitle) {
    const current = chats.find((chat) => chat.id === chatId);
    if (!nextTitle) return;
    const response = await fetch(chatRenameUrl(chatId), {
      method: "PATCH",
      credentials: "same-origin",
      headers: authHelpers.csrfHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ title: nextTitle })
    });
    const data = await response.json();
    if (data.chat) {
      editingChatId = null;
      chats = chats.map((chat) => chat.id === chatId ? data.chat : chat);
      renderChatList();
      updateTitleFromChats();
    }
  }

  async function sendMessage(event) {
    event.preventDefault();
    if (isSending) return;

    const text = inputEl.value.trim();
    if (!text) return;

    const requestId = crypto.randomUUID();
    activeRequestId = requestId;
    if (messagesEl.querySelector(".empty-state")) {
      messagesEl.innerHTML = "";
    }
    appendMessage("user", text, { messageKey: `user:${requestId}` });
    inputEl.value = "";
    autoResizeTextarea();
    setSendingState(true);

    const loadingRow = appendMessage("bot", "", { loading: true, messageKey: `loading:${requestId}` });

    try {
      const response = await fetch(config.chatUrl, {
        method: "POST",
        headers: authHelpers.csrfHeaders({ "Content-Type": "application/json" }),
        credentials: "same-origin",
        body: JSON.stringify({ message: text, client_message_id: requestId, chat_id: activeChatId }),
      });
      const data = await response.json();
      if (activeRequestId !== requestId) return;
      if (data.duplicate && response.status === 202) {
        if (loadingRow) loadingRow.remove();
        setStatus("Still processing...");
        return;
      }

      const bubble = loadingRow?.querySelector(".message-bubble");
      if (bubble) {
        bubble.classList.remove("loading");
        bubble.textContent = "";
        await streamText(bubble, data.response || "I am here with you. Could you say that another way?");
        renderedKeys.add(`bot:${data.message_id || requestId}`);
      }
      activeChatId = data.chat_id || data.session_id || activeChatId;
      await loadChats();
      updateTitleFromChats();
      setStatus("Ready");
    } catch (error) {
      if (loadingRow) loadingRow.remove();
      appendMessage("bot", "I am having trouble connecting right now. Please try again in a moment.", { messageKey: `error:${requestId}` });
      setStatus("Connection issue");
    } finally {
      if (activeRequestId === requestId) {
        activeRequestId = null;
      }
      setSendingState(false);
      inputEl.focus();
    }
  }

  historyItemsEl?.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-action]");
    if (!button) return;
    const chatId = button.getAttribute("data-chat-id");
    const action = button.getAttribute("data-action");
    if (!chatId || !action) return;
    if (action === "open") await loadActiveChat(chatId);
    if (action === "delete") await deleteChat(chatId);
    if (action === "rename") await renameChat(chatId);
    if (action === "cancel-rename") {
      editingChatId = null;
      renderChatList();
    }
  });

  historyItemsEl?.addEventListener("submit", async (event) => {
    const form = event.target.closest('.history-rename-form');
    if (!form) return;
    event.preventDefault();
    const chatId = form.getAttribute('data-chat-id');
    const title = form.querySelector('.history-rename-input')?.value.trim();
    if (!chatId || !title) return;
    await commitRenameChat(chatId, title);
  });

  newChatBtnEl?.addEventListener("click", createNewChat);
  sidebarToggleEl?.addEventListener("click", () => {
    sidebarEl?.classList.toggle("collapsed");
  });
  formEl?.addEventListener("submit", sendMessage);
  inputEl?.addEventListener("input", autoResizeTextarea);
  inputEl?.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      formEl.requestSubmit();
    }
  });

  async function init() {
    autoResizeTextarea();
    syncSidebarMode();
    setStatus("Loading workspace...");
    await loadChats();
    updateTitleFromChats();
    await loadActiveChat(activeChatId, { initial: true });
    inputEl.focus();
  }

  sidebarMedia.addEventListener?.("change", syncSidebarMode);

  init().catch(() => {
    renderHistory([]);
    setStatus("Ready");
  });
})();
