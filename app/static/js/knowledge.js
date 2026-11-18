/* Knowledge base file management */
(function () {
  "use strict";

  const { $, $$, escapeHTML, formatBytes, formatTime, toast, fetchJSON,
    openDialog, closeDialog, debounce, STATUS_META } = window.App;

  const state = {
    records: [],
    filter: "all",
    query: "",
    loading: false,
    pollTimer: null,
    errorDocId: null,
  };

  const tbody = $("#file-tbody");
  const table = $(".file-table");
  const empty = $("#table-empty");
  const uploadZone = $("#upload-zone");
  const fileInput = $("#file-input");
  const uploadStatus = $("#upload-status");
  const uploadText = $("#upload-status-text");
  const uploadPercent = $("#upload-status-percent");
  const uploadBar = $("#upload-progress-bar");
  const filterTabs = $("#filter-tabs");

  const TYPE_CLASS = {
    pdf: "pdf", docx: "doc", doc: "doc", pptx: "ppt", ppt: "ppt",
    xlsx: "xls", xls: "xls", csv: "xls", md: "md", markdown: "md",
    txt: "txt", html: "html", htm: "html",
  };
  const TYPE_LABEL = {
    pdf: "PDF", docx: "DOC", doc: "DOC", pptx: "PPT", ppt: "PPT",
    xlsx: "XLS", xls: "XLS", csv: "CSV", md: "MD", markdown: "MD",
    txt: "TXT", html: "HTML", htm: "HTML",
  };

  function filteredRecords() {
    const query = state.query.trim().toLowerCase();
    return state.records.filter((record) => {
      if (state.filter !== "all" && record.status !== state.filter) return false;
      if (query && !record.name.toLowerCase().includes(query)) return false;
      return true;
    });
  }

  function updateStats() {
    const records = state.records;
    const ready = records.filter((record) => record.status === "ready").length;
    const processing = records.filter((record) => record.status === "processing").length;
    const failed = records.filter((record) => record.status === "failed").length;
    const chunks = records.reduce((total, record) => total + (record.chunks || 0), 0);

    $("#stat-total").textContent = records.length;
    $("#stat-ready").textContent = ready;
    $("#stat-chunks").textContent = chunks.toLocaleString("zh-CN");
    $("#stat-attention").textContent = processing + failed;

    $("#count-all").textContent = records.length;
    $("#count-ready").textContent = ready;
    $("#count-processing").textContent = processing;
    $("#count-failed").textContent = failed;
  }

  function iconHTML(record) {
    const type = (record.extension || "").replace(".", "").toLowerCase();
    const cls = TYPE_CLASS[type] || "other";
    const label = TYPE_LABEL[type] || type.slice(0, 4).toUpperCase() || "FILE";
    return '<span class="file-icon type-' + cls + '">' + escapeHTML(label) + "</span>";
  }

  function statusHTML(record) {
    const meta = STATUS_META[record.status] || STATUS_META.processing;
    return '<span class="status-badge ' + meta.cls + '">' + meta.label + "</span>";
  }

  function rowHTML(record) {
    const error = record.error
      ? '<button class="file-error" type="button" data-action="error" data-id="' + record.id + '" title="点击查看错误详情">' + escapeHTML(record.error) + "</button>"
      : "";
    const chunks = record.status === "ready"
      ? '<span class="chunk-count">' + Number(record.chunks || 0).toLocaleString("zh-CN") + "</span>"
      : '<span class="muted-dash">—</span>';

    const retry = record.status === "failed"
      ? '<button class="row-btn" type="button" data-action="retry" data-id="' + record.id + '" title="重试解析" aria-label="重试解析">' +
        '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21 12a9 9 0 1 1-2.64-6.36"/><path d="M21 3v6h-6"/></svg></button>'
      : "";
    const errorButton = record.status === "failed"
      ? '<button class="row-btn" type="button" data-action="error" data-id="' + record.id + '" title="查看错误" aria-label="查看错误">' +
        '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 8v4M12 16h.01"/></svg></button>'
      : "";
    const download = record.status !== "processing"
      ? '<a class="row-btn" href="/api/documents/' + encodeURIComponent(record.id) + '/download" title="下载原文" aria-label="下载原文">' +
        '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4v12M7 11l5 5 5-5"/><path d="M5 20h14"/></svg></a>'
      : "";

    return '<tr data-id="' + record.id + '">' +
      "<td><div class=\"file-cell\">" + iconHTML(record) +
      '<div class="file-meta"><span class="file-name" title="' + escapeHTML(record.name) + '">' + escapeHTML(record.name) + "</span>" +
      '<span class="file-sub">' + escapeHTML((record.extension || "").replace(".", "").toUpperCase()) + " · " + formatBytes(record.size) + "</span>" +
      error + "</div></div></td>" +
      "<td>" + statusHTML(record) + "</td>" +
      "<td>" + chunks + "</td>" +
      "<td>" + formatBytes(record.size) + "</td>" +
      "<td>" + formatTime(record.updated_at || record.created_at) + "</td>" +
      '<td class="td-actions"><div class="row-actions">' +
      retry + errorButton + download +
      '<button class="row-btn danger" type="button" data-action="delete" data-id="' + record.id + '" title="删除文件" aria-label="删除文件">' +
      '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6"/><path d="M10 11v5M14 11v5"/></svg></button>' +
      "</div></td></tr>";
  }

  function renderTable() {
    updateStats();
    const records = filteredRecords();
    tbody.innerHTML = records.map(rowHTML).join("");

    const emptyState = records.length === 0;
    table.style.display = emptyState ? "none" : "";
    empty.hidden = !emptyState;

    if (emptyState) {
      const hasAny = state.records.length > 0;
      $("#empty-title").textContent = hasAny ? "没有匹配的文件" : "知识库还是空的";
      $("#empty-copy").textContent = hasAny
        ? "换一个关键词或筛选条件试试。"
        : "上传第一份文档，几分钟后就能在这里提问。";
      $("#empty-upload-btn").style.display = hasAny ? "none" : "";
    }
  }

  async function loadDocuments(options = {}) {
    if (state.loading) return;
    state.loading = true;
    try {
      const data = await fetchJSON("/api/documents");
      state.records = data.items || [];
      renderTable();
      schedulePoll();
    } catch (error) {
      if (!options.silent) toast(error.message || "加载文件列表失败", "error");
    } finally {
      state.loading = false;
    }
  }

  function schedulePoll() {
    clearTimeout(state.pollTimer);
    if (!state.records.some((record) => record.status === "processing")) return;
    state.pollTimer = setTimeout(() => loadDocuments({ silent: true }), 2000);
  }

  /* ------------------------------ upload ------------------------------ */
  function showUploadStatus(text, percent) {
    uploadStatus.hidden = false;
    uploadText.textContent = text;
    uploadPercent.textContent = Math.round(percent) + "%";
    uploadBar.style.width = Math.max(0, Math.min(100, percent)) + "%";
  }

  function hideUploadStatus(delay = 2200) {
    setTimeout(() => {
      uploadStatus.hidden = true;
      uploadBar.style.width = "0%";
    }, delay);
  }

  function uploadFiles(files) {
    const list = Array.from(files || []);
    if (!list.length) return;
    const maxMb = Number(uploadZone.dataset.maxUploadMb) || 50;
    if (list.some((file) => file.size > maxMb * 1024 * 1024)) {
      toast("单个文件不能超过 " + maxMb + " MB", "error");
      return;
    }

    const formData = new FormData();
    list.forEach((file) => formData.append("files", file));

    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/documents");
    xhr.responseType = "json";
    showUploadStatus("正在上传 " + list.length + " 个文件…", 0);

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        showUploadStatus("正在上传 " + list.length + " 个文件…", (event.loaded / event.total) * 100);
      }
    };

    xhr.onload = () => {
      const data = xhr.response || {};
      if (xhr.status >= 200 && xhr.status < 300) {
        const count = (data.items || []).length;
        showUploadStatus("已提交 " + count + " 个文件，后台正在解析…", 100);
        if (data.errors && data.errors.length) {
          toast(data.errors.map((item) => item.name + "：" + item.message).join("；"), "error");
        } else {
          toast("已添加 " + count + " 个文件，正在解析", "success");
        }
        hideUploadStatus(2600);
        loadDocuments({ silent: true });
      } else {
        let message = (data && data.detail) || "上传失败";
        if (Array.isArray(message)) message = message.map((item) => item.msg || "").join("；");
        showUploadStatus("上传失败", 0);
        hideUploadStatus(3000);
        toast(message, "error");
      }
    };

    xhr.onerror = () => {
      showUploadStatus("上传失败，请检查服务是否运行", 0);
      hideUploadStatus(3000);
      toast("上传失败，请检查后端服务", "error");
    };

    xhr.send(formData);
    fileInput.value = "";
  }

  /* ------------------------------ actions ------------------------------ */
  function confirmAction(title, copy, okText = "确认删除") {
    return new Promise((resolve) => {
      $("#confirm-title").textContent = title;
      $("#confirm-copy").textContent = copy;
      const ok = $("#confirm-ok");
      ok.textContent = okText;
      const dialog = openDialog("confirm-dialog");

      const cleanup = () => {
        ok.removeEventListener("click", onOk);
        dialog.removeEventListener("close", onClose);
      };
      const onOk = () => { cleanup(); closeDialog(dialog); resolve(true); };
      const onClose = () => { cleanup(); resolve(false); };
      ok.addEventListener("click", onOk);
      dialog.addEventListener("close", onClose);
    });
  }

  async function deleteRecord(record) {
    const confirmed = await confirmAction(
      "删除「" + record.name + "」",
      "删除后，该文件的所有向量分块会一并移除，且无法恢复。"
    );
    if (!confirmed) return;
    try {
      await fetchJSON("/api/documents/" + encodeURIComponent(record.id), { method: "DELETE" });
      toast("已删除 " + record.name, "success");
      state.records = state.records.filter((item) => item.id !== record.id);
      renderTable();
    } catch (error) {
      toast(error.message || "删除失败", "error");
    }
  }

  async function retryRecord(record) {
    try {
      await fetchJSON("/api/documents/" + encodeURIComponent(record.id) + "/retry", { method: "POST" });
      toast("已重新提交解析任务", "success");
      record.status = "processing";
      record.error = null;
      renderTable();
      schedulePoll();
      setTimeout(() => loadDocuments({ silent: true }), 900);
    } catch (error) {
      toast(error.message || "重试失败", "error");
    }
  }

  function showError(record) {
    state.errorDocId = record.id;
    $("#error-title").textContent = record.name;
    $("#error-pre").textContent = record.error || "没有更多错误信息。";
    openDialog("error-dialog");
  }

  /* ------------------------------ events ------------------------------ */
  function bindEvents() {
    uploadZone.addEventListener("click", (event) => {
      if (event.target === fileInput) return;
      fileInput.click();
    });
    uploadZone.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        fileInput.click();
      }
    });
    fileInput.addEventListener("change", () => uploadFiles(fileInput.files));

    ["dragenter", "dragover"].forEach((name) => {
      uploadZone.addEventListener(name, (event) => {
        event.preventDefault();
        uploadZone.classList.add("is-dragging");
      });
    });
    ["dragleave", "drop"].forEach((name) => {
      uploadZone.addEventListener(name, (event) => {
        event.preventDefault();
        uploadZone.classList.remove("is-dragging");
      });
    });
    uploadZone.addEventListener("drop", (event) => {
      if (event.dataTransfer && event.dataTransfer.files) uploadFiles(event.dataTransfer.files);
    });

    filterTabs.addEventListener("click", (event) => {
      const button = event.target.closest("[data-filter]");
      if (!button) return;
      state.filter = button.dataset.filter;
      $$(".filter-tab").forEach((item) => item.classList.toggle("active", item === button));
      renderTable();
    });

    $("#file-search").addEventListener("input", debounce((event) => {
      state.query = event.target.value || "";
      renderTable();
    }, 120));

    tbody.addEventListener("click", (event) => {
      const action = event.target.closest("[data-action]");
      if (!action) return;
      const record = state.records.find((item) => item.id === action.dataset.id);
      if (!record) return;
      if (action.dataset.action === "delete") deleteRecord(record);
      else if (action.dataset.action === "retry") retryRecord(record);
      else if (action.dataset.action === "error") showError(record);
    });

    $("#refresh-btn").addEventListener("click", async () => {
      await loadDocuments();
      toast("文件列表已刷新");
    });

    $("#empty-upload-btn").addEventListener("click", () => fileInput.click());

    $("#error-retry-btn").addEventListener("click", () => {
      const record = state.records.find((item) => item.id === state.errorDocId);
      closeDialog($("#error-dialog"));
      if (record) retryRecord(record);
    });
  }

  function init() {
    bindEvents();
    loadDocuments();
  }

  document.addEventListener("DOMContentLoaded", init);
})();