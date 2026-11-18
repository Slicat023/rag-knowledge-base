/* Chat page */
(function () {
  "use strict";

  const { $, $$, escapeHTML, toast, fetchJSON, openDialog, closeDialog,
    renderMarkdown, consumeSSE, copyText } = window.App;

  const PROVIDER_LABELS = { qwen: "通义千问", deepseek: "DeepSeek" };
  const STORAGE_KEY = "zhiku.chat.v1";
  const PROVIDER_KEY = "zhiku.provider";
  const MAX_STORED = 30;

  const state = {
    messages: [],
    provider: document.body.dataset.defaultLlm || "qwen",
    streaming: false,
    controller: null,
    currentAssistantId: null,
  };
  const elements = new Map();

  const thread = $("#messages");
  const hero = $("#chat-hero");
  const scroller = $("#chat-scroll");
  const input = $("#chat-input");
  const form = $("#chat-form");
  const sendBtn = $("#send-btn");
  const charCount = $("#char-count");
  const composerModel = $("#composer-model");

  function uid() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    return "m-" + Date.now() + "-" + Math.random().toString(16).slice(2);
  }

  /* ------------------------------ persistence ------------------------------ */
  function save() {
    try {
      const payload = state.messages.slice(-MAX_STORED).map((message) => ({
        id: message.id,
        role: message.role,
        content: message.content,
        sources: message.sources || [],
        error: message.error || null,
        stopped: Boolean(message.stopped),
        provider: message.provider || null,
        model: message.model || null,
        elapsed: message.elapsed || null,
        createdAt: message.createdAt || Date.now(),
      }));
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
    } catch (error) {
      console.warn("Could not persist chat", error);
    }
  }

  function restore() {
    try {
      const raw = sessionStorage.getItem(STORAGE_KEY);
      if (!raw) return;
      const messages = JSON.parse(raw);
      if (!Array.isArray(messages)) return;
      state.messages = messages.map((message) => ({
        ...message,
        pending: false,
        error: message.error || null,
      }));
    } catch (error) {
      console.warn("Could not restore chat", error);
    }
  }

  /* ------------------------------ rendering ------------------------------ */
  function providerLabel(provider) {
    return PROVIDER_LABELS[provider] || provider || "模型";
  }

  function setHeroVisibility() {
    if (!hero) return;
    hero.classList.toggle("is-hidden", state.messages.length > 0);
  }

  function formatScore(score) {
    if (typeof score !== "number" || Number.isNaN(score)) return "";
    return "相关度 " + Math.round(Math.max(0, Math.min(1, score)) * 100) + "%";
  }

  function messageMeta(message) {
    const parts = [];
    if (message.role === "assistant") {
      if (message.provider) parts.push(providerLabel(message.provider) + (message.model ? " · " + message.model : ""));
      if (message.elapsed) parts.push(message.elapsed + "s");
    } else {
      parts.push(window.App.formatTime(new Date(message.createdAt || Date.now()).toISOString()));
    }
    return parts.join(" · ");
  }

  function renderSources(message) {
    if (!message.sources || !message.sources.length) return "";
    return '<div class="sources">' + message.sources.map((source) => {
      const page = source.page ? " · 第 " + source.page + " 页" : "";
      return '<button class="source-chip" type="button" data-source-index="' + source.index + '" data-message-id="' + escapeHTML(message.id) + '">' +
        '<span class="source-num">' + source.index + "</span>" +
        '<span class="source-name">' + escapeHTML(source.file_name) + page + "</span>" +
        "</button>";
    }).join("") + "</div>";
  }

  function bubbleHTML(message) {
    if (message.role === "user") {
      return escapeHTML(message.content || "").replace(/\n/g, "<br>");
    }
    if (message.pending && !message.content) {
      return '<div class="typing" aria-label="正在生成"><i></i><i></i><i></i></div>';
    }
    let html = message.content ? renderMarkdown(message.content) : "";
    if (message.error) {
      const retry = '<button class="retry-btn" type="button" data-retry="' + escapeHTML(message.id) + '">↻ 重试</button>';
      const errorText = message.content
        ? '<p class="inline-error">' + escapeHTML(message.error) + "</p>"
        : '<p class="inline-error">' + escapeHTML(message.error) + "</p>";
      html += errorText + retry;
    }
    if (message.stopped && !message.content) {
      html = '<p class="inline-muted">已停止生成。</p>';
    }
    return html;
  }

  function createMessageElement(message) {
    const row = document.createElement("div");
    row.className = "message " + message.role + (message.error ? " error" : "");
    row.dataset.id = message.id;

    if (message.role === "assistant") {
      const avatar = document.createElement("div");
      avatar.className = "avatar";
      avatar.textContent = "知";
      row.appendChild(avatar);
    }

    const body = document.createElement("div");
    body.className = "message-body";

    const bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.innerHTML = bubbleHTML(message);
    body.appendChild(bubble);

    const sources = document.createElement("div");
    sources.className = "message-sources";
    sources.innerHTML = renderSources(message);
    body.appendChild(sources);

    const meta = document.createElement("div");
    meta.className = "message-meta";
    const label = document.createElement("span");
    label.textContent = messageMeta(message);
    meta.appendChild(label);
    if (message.role === "assistant" && message.content) {
      const copy = document.createElement("button");
      copy.type = "button";
      copy.dataset.copy = message.id;
      copy.textContent = "复制";
      meta.appendChild(copy);
    }
    body.appendChild(meta);
    row.appendChild(body);

    elements.set(message.id, { row, bubble, sources, meta });
    return row;
  }

  function renderAll() {
    thread.innerHTML = "";
    elements.clear();
    state.messages.forEach((message) => thread.appendChild(createMessageElement(message)));
    setHeroVisibility();
  }

  function updateMessage(message) {
    if (!state.messages.some((item) => item.id === message.id)) return;
    let refs = elements.get(message.id);
    if (!refs) {
      const element = createMessageElement(message);
      thread.appendChild(element);
      refs = elements.get(message.id);
    }
    if (!refs) return;
    refs.row.classList.toggle("error", Boolean(message.error));
    refs.bubble.innerHTML = bubbleHTML(message);
    refs.sources.innerHTML = renderSources(message);

    let copy = refs.meta.querySelector("[data-copy]");
    if (message.role === "assistant" && message.content && !copy) {
      copy = document.createElement("button");
      copy.type = "button";
      copy.dataset.copy = message.id;
      copy.textContent = "复制";
      refs.meta.appendChild(copy);
    }
    refs.meta.querySelector("span").textContent = messageMeta(message);
  }

  function isNearBottom() {
    return scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight < 140;
  }

  function scrollToBottom(force = false) {
    if (force || isNearBottom()) {
      requestAnimationFrame(() => {
        scroller.scrollTop = scroller.scrollHeight;
      });
    }
  }

  /* ------------------------------ source dialog ------------------------------ */
  function openSources(message, targetIndex) {
    const body = $("#source-dialog-body");
    if (!body) return;
    if (!message.sources || !message.sources.length) {
      toast("这条回答没有可展示的引用来源");
      return;
    }
    body.innerHTML = message.sources.map((source) => {
      const page = source.page ? " · 第 " + source.page + " 页" : "";
      const score = formatScore(source.score);
      const breadcrumb = source.section_path
        ? '<div class="source-card-path">' + escapeHTML(source.section_path) +
          (source.table_caption ? " · " + escapeHTML(source.table_caption) : "") + "</div>"
        : "";
      const download = source.doc_id
        ? '<a class="source-download" href="/api/documents/' + encodeURIComponent(source.doc_id) + '/download">下载原文 ↗</a>'
        : "";
      return '<article class="source-card' + (Number(targetIndex) === source.index ? " is-target" : "") + '" data-source-card="' + source.index + '">' +
        '<div class="source-card-head">' +
        '<span class="source-card-num">' + source.index + "</span>" +
        '<span class="source-card-title">' + escapeHTML(source.file_name) + page + "</span>" +
        '<span class="source-card-score">' + (score || "") + "</span>" +
        "</div>" + breadcrumb +
        '<p class="source-card-text">' + escapeHTML(source.text || source.snippet || "") + "</p>" +
        '<div class="source-card-foot">' + download + "</div>" +
        "</article>";
    }).join("");
    openDialog("source-dialog");
    if (targetIndex) {
      const target = body.querySelector('[data-source-card="' + targetIndex + '"]');
      if (target) setTimeout(() => target.scrollIntoView({ block: "center", behavior: "smooth" }), 80);
    }
  }

  /* ------------------------------ streaming ------------------------------ */
  function setStreaming(streaming) {
    state.streaming = streaming;
    sendBtn.classList.toggle("is-streaming", streaming);
    sendBtn.setAttribute("aria-label", streaming ? "停止生成" : "发送问题");
    input.disabled = false;
  }

  function historyBefore(index) {
    return state.messages.slice(0, index)
      .filter((message) => message.role && message.content && !message.error)
      .slice(-12)
      .map((message) => ({ role: message.role, content: message.content }));
  }

  async function requestAnswer(question, history, assistant) {
    state.controller = new AbortController();
    setStreaming(true);
    state.currentAssistantId = assistant.id;
    updateMessage(assistant);
    scrollToBottom(true);

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: state.controller.signal,
        body: JSON.stringify({
          message: question,
          history: history,
          provider: state.provider,
        }),
      });

      if (!response.ok) {
        let detail = "请求失败（HTTP " + response.status + "）";
        try {
          const data = await response.json();
          if (data.detail) {
            detail = Array.isArray(data.detail)
              ? data.detail.map((item) => item.msg || JSON.stringify(item)).join("；")
              : data.detail;
          }
        } catch (error) { /* ignore */ }
        throw new Error(detail);
      }

      await consumeSSE(response, (event, payload) => {
        if (event === "sources") {
          assistant.sources = payload.sources || [];
          assistant.provider = payload.provider;
          assistant.model = payload.model;
          updateMessage(assistant);
          scrollToBottom();
        } else if (event === "delta") {
          assistant.content += payload.text || "";
          updateMessage(assistant);
          scrollToBottom();
        } else if (event === "done") {
          assistant.pending = false;
          assistant.elapsed = payload.elapsed;
          updateMessage(assistant);
          save();
          scrollToBottom();
        } else if (event === "error") {
          assistant.pending = false;
          assistant.error = payload.message || "生成失败";
          updateMessage(assistant);
          toast(assistant.error, "error");
          save();
        }
      });

      if (assistant.pending) {
        assistant.pending = false;
        if (!assistant.content && !assistant.error) {
          assistant.error = "回答意外中断，请点击重试。";
        }
        updateMessage(assistant);
        save();
      }
    } catch (error) {
      if (error.name === "AbortError") {
        assistant.pending = false;
        assistant.stopped = true;
        if (!assistant.content) assistant.content = "";
        updateMessage(assistant);
        save();
        toast("已停止生成");
      } else {
        assistant.pending = false;
        assistant.error = error.message || "网络请求失败";
        updateMessage(assistant);
        toast(assistant.error, "error");
        save();
      }
    } finally {
      state.streaming = false;
      state.controller = null;
      state.currentAssistantId = null;
      setStreaming(false);
      input.focus();
      save();
    }
  }

  async function sendMessage(text) {
    text = (text || "").trim();
    if (!text || state.streaming) return;

    const history = historyBefore(state.messages.length);
    const userMessage = {
      id: uid(),
      role: "user",
      content: text,
      createdAt: Date.now(),
    };
    const assistant = {
      id: uid(),
      role: "assistant",
      content: "",
      pending: true,
      sources: [],
      createdAt: Date.now(),
    };
    state.messages.push(userMessage, assistant);
    thread.appendChild(createMessageElement(userMessage));
    thread.appendChild(createMessageElement(assistant));
    setHeroVisibility();
    save();
    scrollToBottom(true);
    await requestAnswer(text, history, assistant);
  }

  /* ------------------------------ events ------------------------------ */
  function selectProvider(provider) {
    const button = document.querySelector('.model-pill[data-provider="' + provider + '"]');
    if (!button || button.disabled) return;
    state.provider = provider;
    $$(".model-pill").forEach((item) => item.classList.toggle("active", item.dataset.provider === provider));
    composerModel.textContent = providerLabel(provider);
    localStorage.setItem(PROVIDER_KEY, provider);
  }

  function initProvider() {
    const stored = localStorage.getItem(PROVIDER_KEY);
    const target = stored || state.provider;
    const button = document.querySelector('.model-pill[data-provider="' + target + '"]');
    if (button && !button.disabled) {
      selectProvider(target);
    } else {
      const first = $$(".model-pill").find((item) => !item.disabled);
      if (first) selectProvider(first.dataset.provider);
      else composerModel.textContent = "未配置模型";
    }
    $$(".model-pill").forEach((button) => {
      button.addEventListener("click", () => selectProvider(button.dataset.provider));
    });
  }

  function autoResize() {
    input.style.height = "auto";
    const height = Math.min(input.scrollHeight, 160);
    input.style.height = height + "px";
    charCount.textContent = input.value.length + " / 4000";
  }

  function bindEvents() {
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      if (state.streaming) {
        if (state.controller) state.controller.abort();
        return;
      }
      const text = input.value;
      input.value = "";
      autoResize();
      sendMessage(text);
    });

    input.addEventListener("input", autoResize);
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey && !event.isComposing && event.keyCode !== 229) {
        event.preventDefault();
        form.requestSubmit();
      }
    });

    $$("#suggestions [data-question]").forEach((button) => {
      button.addEventListener("click", () => {
        input.value = button.dataset.question || "";
        autoResize();
        form.requestSubmit();
      });
    });

    thread.addEventListener("click", (event) => {
      const copy = event.target.closest("[data-copy]");
      if (copy) {
        const message = state.messages.find((item) => item.id === copy.dataset.copy);
        if (message && message.content) {
          copyText(message.content).then(() => toast("已复制回答", "success")).catch(() => toast("复制失败", "error"));
        }
        return;
      }

      const retry = event.target.closest("[data-retry]");
      if (retry) {
        retryMessage(retry.dataset.retry);
        return;
      }

      const cite = event.target.closest("[data-cite]");
      if (cite) {
        const row = cite.closest(".message");
        const message = state.messages.find((item) => item.id === row.dataset.id);
        if (message) openSources(message, Number(cite.dataset.cite));
        return;
      }

      const chip = event.target.closest("[data-source-index]");
      if (chip) {
        const message = state.messages.find((item) => item.id === chip.dataset.messageId);
        if (message) openSources(message, Number(chip.dataset.sourceIndex));
      }
    });

    $("#clear-chat").addEventListener("click", () => {
      if (!state.messages.length) return;
      if (window.confirm("确定清空当前对话吗？此操作不可恢复。")) {
        if (state.controller) state.controller.abort();
        state.messages = [];
        elements.clear();
        thread.innerHTML = "";
        sessionStorage.removeItem(STORAGE_KEY);
        setHeroVisibility();
        toast("对话已清空");
        refreshKbTip();
      }
    });

    $("#source-dialog").addEventListener("close", () => {
      $("#source-dialog-body").innerHTML = "";
    });
  }

  function retryMessage(messageId) {
    const index = state.messages.findIndex((item) => item.id === messageId);
    if (index < 0) return;
    let userIndex = index - 1;
    while (userIndex >= 0 && state.messages[userIndex].role !== "user") userIndex -= 1;
    if (userIndex < 0) return;
    const question = state.messages[userIndex].content;
    state.messages = state.messages.slice(0, userIndex);
    renderAll();
    save();
    sendMessage(question);
  }

  async function refreshKbTip() {
    const tip = $("#kb-empty-tip");
    if (!tip) return;
    try {
      const health = await fetchJSON("/api/health");
      const docs = health.documents || {};
      tip.hidden = docs.ready > 0;
      if (docs.ready === 0 && docs.processing > 0) {
        tip.textContent = "知识库文档正在解析和向量化，请稍候…";
      } else if (docs.ready === 0) {
        tip.innerHTML = '知识库还没有可用文件。<a href="/knowledge">去添加第一份文档 →</a>';
      }
    } catch (error) {
      tip.hidden = true;
    }
  }

  function init() {
    restore();
    renderAll();
    initProvider();
    bindEvents();
    autoResize();
    refreshKbTip();
    if (state.messages.length) scrollToBottom(true);
    else input.focus();
  }

  document.addEventListener("DOMContentLoaded", init);
})();