/* Shared UI helpers */
(function () {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  function escapeHTML(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function formatBytes(bytes) {
    const value = Number(bytes) || 0;
    if (value < 1024) return value + " B";
    if (value < 1024 * 1024) return (value / 1024).toFixed(1) + " KB";
    if (value < 1024 * 1024 * 1024) return (value / 1024 / 1024).toFixed(1) + " MB";
    return (value / 1024 / 1024 / 1024).toFixed(2) + " GB";
  }

  function formatTime(iso) {
    if (!iso) return "—";
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return "—";
    const now = Date.now();
    const diff = now - date.getTime();
    if (diff >= 0 && diff < 60 * 1000) return "刚刚";
    if (diff >= 0 && diff < 60 * 60 * 1000) return Math.floor(diff / 60000) + " 分钟前";
    if (diff >= 0 && diff < 24 * 60 * 60 * 1000) return Math.floor(diff / 3600000) + " 小时前";
    const pad = (n) => String(n).padStart(2, "0");
    return date.getFullYear() + "-" + pad(date.getMonth() + 1) + "-" + pad(date.getDate()) +
      " " + pad(date.getHours()) + ":" + pad(date.getMinutes());
  }

  let toastTimer = null;
  function toast(message, type = "") {
    const el = $("#toast");
    if (!el) return;
    el.textContent = message;
    el.className = "toast show" + (type ? " " + type : "");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      el.className = "toast" + (type ? " " + type : "");
    }, 3200);
  }

  async function fetchJSON(url, options = {}) {
    const response = await fetch(url, options);
    let data = null;
    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      data = await response.json().catch(() => null);
    }
    if (!response.ok) {
      let detail = data && data.detail;
      if (Array.isArray(detail)) {
        detail = detail.map((item) => item.msg || JSON.stringify(item)).join("；");
      }
      throw new Error(detail || "请求失败（HTTP " + response.status + "）");
    }
    return data;
  }

  function openDialog(id) {
    const dialog = typeof id === "string" ? document.getElementById(id) : id;
    if (dialog && !dialog.open) dialog.showModal();
    return dialog;
  }

  function closeDialog(dialog) {
    if (dialog && dialog.open) dialog.close();
  }

  function initDialogs() {
    $$("[data-close-dialog]").forEach((button) => {
      button.addEventListener("click", () => closeDialog(button.closest("dialog")));
    });
    $$("dialog").forEach((dialog) => {
      dialog.addEventListener("click", (event) => {
        if (event.target === dialog) closeDialog(dialog);
      });
    });
  }

  function initSidebar() {
    const body = document.body;
    const open = () => body.classList.add("nav-open");
    const close = () => body.classList.remove("nav-open");
    const button = $("#menu-btn");
    const scrim = $("#sidebar-scrim");
    if (button) button.addEventListener("click", open);
    if (scrim) scrim.addEventListener("click", close);
    $$(".nav-item").forEach((item) => item.addEventListener("click", close));
    window.addEventListener("keydown", (event) => {
      if (event.key === "Escape") close();
    });
  }

  const STATUS_META = {
    ready: { label: "已就绪", cls: "status-ready" },
    processing: { label: "处理中", cls: "status-processing" },
    failed: { label: "失败", cls: "status-failed" },
  };

  async function refreshHealth() {
    const dot = $("#model-dot");
    const text = $("#model-status");
    if (!dot || !text) return;
    try {
      const health = await fetchJSON("/api/health");
      const embedding = health.embedding || {};
      const reranker = health.reranker || {};
      const configured = Object.values(health.llm || {}).filter((item) => item.configured).length;
      let label;
      let cls = "ok";
      if (reranker.error) {
        label = "重排模型未就绪，请下载模型";
        cls = "err";
      } else if (embedding.loaded && reranker.enabled === false) {
        label = "向量模型就绪 · 重排已关闭";
      } else if (embedding.loaded && reranker.loaded) {
        label = "本地向量与重排模型就绪";
      } else {
        label = "模型加载中…";
        cls = "warn";
      }
      if (configured === 0) {
        label += " · 未配置 API Key";
        if (cls === "ok") cls = "warn";
      }
      text.textContent = label;
      text.title = "向量：" + (embedding.model || "-") + " · 重排：" + (reranker.model || "-");
      dot.className = "pulse-dot " + cls;
    } catch (error) {
      text.textContent = "无法连接后端服务";
      text.title = String(error.message || error);
      dot.className = "pulse-dot err";
    }
  }

  /* ------------------------------ lightweight markdown ------------------------------ */
  function inlineFormat(text) {
    let output = text;
    output = output.replace(/`([^`]+)`/g, "<code>$1</code>");
    output = output.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    output = output.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
      '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
    output = output.replace(/\[(\d{1,2})\]/g, '<button class="cite" type="button" data-cite="$1">[$1]</button>');
    return output;
  }

  function renderMarkdown(raw) {
    if (!raw) return "";
    let text = escapeHTML(raw);
    const codeBlocks = [];
    text = text.replace(/```[a-zA-Z0-9_-]*\n?([\s\S]*?)```/g, (_, code) => {
      const index = codeBlocks.length;
      codeBlocks.push(code.replace(/\n$/, ""));
      return "\n\u0000CODEBLOCK" + index + "\u0000\n";
    });

    const lines = text.split("\n");
    const html = [];
    let paragraph = [];
    let list = null;

    const flushParagraph = () => {
      if (paragraph.length) {
        html.push("<p>" + inlineFormat(paragraph.join("<br>")) + "</p>");
        paragraph = [];
      }
    };
    const closeList = () => {
      if (list) {
        html.push("</" + list + ">");
        list = null;
      }
    };

    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) {
        flushParagraph();
        closeList();
        continue;
      }
      if (trimmed.startsWith("\u0000CODEBLOCK")) {
        flushParagraph();
        closeList();
        html.push(trimmed);
        continue;
      }
      const heading = trimmed.match(/^(#{1,4})\s+(.*)$/);
      if (heading) {
        flushParagraph();
        closeList();
        const level = Math.min(4, heading[1].length + 2);
        html.push("<h" + level + ">" + inlineFormat(heading[2]) + "</h" + level + ">");
        continue;
      }
      const quote = trimmed.match(/^&gt;\s?(.*)$/);
      if (quote) {
        flushParagraph();
        closeList();
        html.push("<blockquote>" + inlineFormat(quote[1]) + "</blockquote>");
        continue;
      }
      const ordered = trimmed.match(/^\d+[.)]\s+(.*)$/);
      if (ordered) {
        flushParagraph();
        if (list !== "ol") { closeList(); html.push("<ol>"); list = "ol"; }
        html.push("<li>" + inlineFormat(ordered[1]) + "</li>");
        continue;
      }
      const bullet = trimmed.match(/^[-*•]\s+(.*)$/);
      if (bullet) {
        flushParagraph();
        if (list !== "ul") { closeList(); html.push("<ul>"); list = "ul"; }
        html.push("<li>" + inlineFormat(bullet[1]) + "</li>");
        continue;
      }
      closeList();
      paragraph.push(line);
    }
    flushParagraph();
    closeList();

    let output = html.join("");
    output = output.replace(/\u0000CODEBLOCK(\d+)\u0000/g, (_, index) => {
      return "<pre><code>" + (codeBlocks[Number(index)] || "") + "</code></pre>";
    });
    return output;
  }

  /* ------------------------------ SSE ------------------------------ */
  async function consumeSSE(response, onEvent) {
    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      buffer = buffer.replace(/\r\n/g, "\n");
      let boundary = buffer.indexOf("\n\n");
      while (boundary !== -1) {
        const raw = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        let event = "message";
        const dataLines = [];
        for (const line of raw.split("\n")) {
          if (line.startsWith("event:")) event = line.slice(6).trim();
          else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
        }
        if (dataLines.length) {
          try {
            onEvent(event, JSON.parse(dataLines.join("\n")));
          } catch (error) {
            console.error("Bad SSE payload", raw, error);
          }
        }
        boundary = buffer.indexOf("\n\n");
      }
    }
  }

  function debounce(fn, wait) {
    let timer = null;
    return function (...args) {
      clearTimeout(timer);
      timer = setTimeout(() => fn.apply(this, args), wait);
    };
  }

  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text);
    }
    return new Promise((resolve, reject) => {
      const area = document.createElement("textarea");
      area.value = text;
      area.style.position = "fixed";
      area.style.opacity = "0";
      document.body.appendChild(area);
      area.select();
      try {
        document.execCommand("copy");
        resolve();
      } catch (error) {
        reject(error);
      } finally {
        area.remove();
      }
    });
  }

  window.App = {
    $, $$, escapeHTML, formatBytes, formatTime, toast, fetchJSON,
    openDialog, closeDialog, initDialogs, initSidebar, refreshHealth,
    renderMarkdown, consumeSSE, debounce, copyText, STATUS_META,
  };

  document.addEventListener("DOMContentLoaded", () => {
    initSidebar();
    initDialogs();
    refreshHealth();
    setInterval(refreshHealth, 30000);
  });
})();