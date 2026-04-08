const state = {
  tabs: [],
  activeFeature: null,
  activeModel: null,
};

const mainTabs = document.querySelector("#mainTabs");
const modelTabs = document.querySelector("#modelTabs");
const featureSummary = document.querySelector("#featureSummary");
const taskForm = document.querySelector("#taskForm");
const submitButton = document.querySelector("#submitButton");
const parameterGrid = document.querySelector("#parameterGrid");
const tokenField = document.querySelector("#tokenField");
const tokenInput = document.querySelector("#tokenInput");
const sourceInput = document.querySelector("#sourceInput");
const promptInput = document.querySelector("#promptInput");
const promptField = document.querySelector("#promptField");
const promptLabel = document.querySelector("#promptLabel");
const sourceLabel = document.querySelector("#sourceLabel");
const sourceField = document.querySelector("#sourceField");
const imageUploadField = document.querySelector("#imageUploadField");
const imageInput = document.querySelector("#imageInput");
const imageLimitTip = document.querySelector("#imageLimitTip");
const uploadPreview = document.querySelector("#uploadPreview");
const resultBox = document.querySelector("#resultBox");
const loadingPanel = document.querySelector("#loadingPanel");
const loadingTitle = document.querySelector("#loadingTitle");
const loadingText = document.querySelector("#loadingText");
const taskList = document.querySelector("#taskList");
const refreshTasks = document.querySelector("#refreshTasks");
const assetGallery = document.querySelector("#assetGallery");

function activeTab() {
  return state.tabs.find((item) => item.id === state.activeFeature);
}

function activeModel() {
  const tab = activeTab();
  return tab?.models.find((item) => item.id === state.activeModel);
}

function normalizeStatus(value) {
  return String(value || "").trim().toLowerCase().replace(/\s+/g, "_");
}

function sleep(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function renderMainTabs() {
  mainTabs.innerHTML = "";
  state.tabs.forEach((tab) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `tab-button ${tab.id === state.activeFeature ? "active" : ""}`;
    button.textContent = tab.name;
    button.addEventListener("click", () => {
      state.activeFeature = tab.id;
      state.activeModel = tab.models[0]?.id || null;
      resetForm();
      render();
    });
    mainTabs.appendChild(button);
  });
}

function renderModelTabs() {
  modelTabs.innerHTML = "";
  const tab = activeTab();
  featureSummary.textContent = tab?.description || "";
  featureSummary.classList.toggle("hidden", !tab?.description);

  (tab?.models || []).forEach((model) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `tab-button ${model.id === state.activeModel ? "active" : ""}`;
    button.textContent = model.name;
    button.title = model.description || "";
    button.addEventListener("click", () => {
      state.activeModel = model.id;
      resetForm(false);
      render();
    });
    modelTabs.appendChild(button);
  });
}

function setSourceLabel() {
  if (state.activeFeature === "text_split") {
    sourceLabel.textContent = "输入文案";
  } else if (state.activeFeature === "text_to_image") {
    sourceLabel.textContent = "画面补充说明（可选）";
  } else {
    sourceLabel.textContent = "上传图片";
  }
}

function createParameterInput(param) {
  let input;
  if (param.type === "select") {
    input = document.createElement("select");
    (param.options || []).forEach((option) => {
      const node = document.createElement("option");
      node.value = option;
      node.textContent = option;
      if (String(option) === String(param.default)) node.selected = true;
      input.appendChild(node);
    });
  } else if (param.type === "boolean") {
    input = document.createElement("select");
    [["true", "开启"], ["false", "关闭"]].forEach(([value, label]) => {
      const node = document.createElement("option");
      node.value = value;
      node.textContent = label;
      if (String(Boolean(param.default)) === String(value === "true")) {
        node.selected = true;
      }
      input.appendChild(node);
    });
  } else if (param.type === "textarea") {
    input = document.createElement("textarea");
    input.rows = 4;
    input.value = param.default ?? "";
    input.placeholder = param.placeholder || "";
  } else {
    input = document.createElement("input");
    input.type = param.type === "number" ? "number" : (param.type === "password" ? "password" : "text");
    input.value = param.default ?? "";
    if (param.type === "number") {
      input.step = "any";
      if (param.min !== undefined) input.min = param.min;
      if (param.max !== undefined) input.max = param.max;
    }
    if (param.placeholder) input.placeholder = param.placeholder;
  }
  input.dataset.key = param.key;
  input.dataset.type = param.type;
  return input;
}

function renderParameters() {
  parameterGrid.innerHTML = "";
  const model = activeModel();
  if (!model) return;

  document.body.dataset.feature = state.activeFeature || "";
  tokenField.classList.toggle("hidden", Boolean(model.token_from_env));
  tokenInput.placeholder = model.token_label || "填写当前模型的 API Token";

  const showPromptField = state.activeFeature === "text_to_image";
  promptField.classList.toggle("hidden", !showPromptField);
  if (showPromptField) {
    promptLabel.textContent = model.prompt_label || "文生图提示词";
  } else {
    promptInput.value = "";
  }

  imageUploadField.classList.toggle("hidden", state.activeFeature !== "image_to_video");
  sourceField.classList.toggle("hidden", state.activeFeature === "image_to_video");
  setSourceLabel();

  if (state.activeFeature === "image_to_video") {
    imageLimitTip.textContent = `当前模型要求上传 ${model.min_images || 1}-${model.max_images || 6} 张图片，你已选择 ${imageInput.files.length} 张。`;
  }

  if (!model.supports_real_api && model.description) {
    const warning = document.createElement("div");
    warning.className = "warning full";
    warning.textContent = model.description;
    parameterGrid.appendChild(warning);
  }

  (model.parameters || []).forEach((param) => {
    const field = document.createElement("label");
    field.className = `field ${param.type === "textarea" ? "full" : ""}`.trim();

    const title = document.createElement("span");
    title.textContent = param.label;
    field.appendChild(title);

    field.appendChild(createParameterInput(param));
    parameterGrid.appendChild(field);
  });
}

function resetForm(clearToken = true) {
  if (clearToken) tokenInput.value = "";
  sourceInput.value = "";
  promptInput.value = "";
  imageInput.value = "";
  uploadPreview.innerHTML = "";
  assetGallery.innerHTML = "";
}

function collectParameters() {
  const values = {};
  parameterGrid.querySelectorAll("[data-key]").forEach((input) => {
    const { key, type } = input.dataset;
    if (type === "boolean") {
      values[key] = input.value === "true";
    } else if (type === "number") {
      const raw = Number(input.value);
      if (Number.isNaN(raw)) {
        values[key] = input.value;
      } else {
        let value = raw;
        if (input.min !== "") value = Math.max(Number(input.min), value);
        if (input.max !== "") value = Math.min(Number(input.max), value);
        values[key] = value;
      }
    } else {
      values[key] = input.value;
    }
  });
  return values;
}

function formatResultText(data) {
  const result = data?.result || {};
  const remoteTaskId = result.task_id || data?.remote_task_id;
  const lines = [];

  if (data?.feature === "text_split" && result.raw) {
    lines.push(result.raw);
  } else if (result.message) {
    lines.push(result.message);
  } else if (data?.message) {
    lines.push(data.message);
  } else if (data?.detail) {
    lines.push(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail, null, 2));
  } else {
    lines.push(JSON.stringify(data, null, 2));
  }

  lines.push("");
  lines.push("-----");
  if (data?.id) lines.push(`任务ID：${data.id}`);
  if (data?.model_name) lines.push(`模型：${data.model_name}`);
  if (data?.status) lines.push(`状态：${data.status}`);
  if (remoteTaskId) lines.push(`远端任务ID：${remoteTaskId}`);
  return lines.join("\n");
}

function appendImageCard(asset) {
  const card = document.createElement("div");
  card.className = "asset-card";

  const image = document.createElement("img");
  if (asset.url) {
    image.src = asset.url;
  } else if (asset.b64_json) {
    image.src = `data:image/png;base64,${asset.b64_json}`;
  } else {
    return;
  }
  image.alt = "generated image";
  card.appendChild(image);

  const label = document.createElement("span");
  label.textContent = asset.url ? "图片 URL" : "Base64 图片";
  card.appendChild(label);
  assetGallery.appendChild(card);
}

function appendVideoCard(videoUrl) {
  const card = document.createElement("div");
  card.className = "asset-card video-card";
  const video = document.createElement("video");
  video.controls = true;
  video.src = videoUrl;
  card.appendChild(video);
  const label = document.createElement("span");
  label.textContent = "生成视频";
  card.appendChild(label);
  assetGallery.appendChild(card);
}

function appendTaskHint(taskId, feature) {
  if (!taskId) return;
  const card = document.createElement("div");
  card.className = "asset-card";
  card.textContent = `${feature === "text_to_image" ? "图片" : "视频"}任务已提交，任务 ID：${taskId}`;
  assetGallery.appendChild(card);
}

function renderAssets(data) {
  assetGallery.innerHTML = "";

  const result = data?.result || {};
  const providerResponse = result.provider_response || {};
  const assets = result.assets || [];
  assets.forEach(appendImageCard);

  const videoUrl =
    result.video_url ||
    data?.video_url ||
    providerResponse.video_url ||
    providerResponse.output?.video_url ||
    providerResponse.data?.video_url ||
    result.query_payload?.content?.video_url;

  const taskId =
    result.task_id ||
    data?.remote_task_id ||
    providerResponse.output?.task_id ||
    providerResponse.task_id ||
    providerResponse.data?.task_id ||
    providerResponse.id;

  if (videoUrl) {
    appendVideoCard(videoUrl);
  } else if (taskId) {
    appendTaskHint(taskId, data?.feature);
  }
}

function renderResult(data) {
  resultBox.textContent = formatResultText(data);
  renderAssets(data);
}

function setLoading(loading, options = {}) {
  const title = options.title || "接口调用中";
  const text = options.text || "正在等待模型返回结果，请稍候...";
  loadingPanel.classList.toggle("hidden", !loading);
  loadingTitle.textContent = title;
  loadingText.textContent = text;
  submitButton.disabled = loading;
  refreshTasks.disabled = loading;
}

async function fetchTaskRecord(taskId) {
  const response = await fetch(`/api/tasks/${encodeURIComponent(taskId)}`);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data?.detail || data?.message || "任务查询失败");
  }
  return data;
}

async function pollVideoTaskUntilFinished(task) {
  const localTaskId = task?.id || task?.local_task_id;
  const remoteTaskId = task?.result?.task_id || task?.remote_task_id;
  if (!localTaskId && !remoteTaskId) return task;

  const maxAttempts = Math.max(1, Number(task?.parameters?.max_attempts || 12));
  const pollInterval = Math.max(3, Number(task?.parameters?.poll_interval || 8));
  let latestTask = task;

  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    loadingTitle.textContent = "视频生成中";
    loadingText.textContent = `任务已提交，正在查询第 ${attempt}/${maxAttempts} 次结果。`;

    if (attempt > 1) {
      await sleep(pollInterval * 1000);
    }

    const response = await fetch(`/api/video-tasks/${encodeURIComponent(localTaskId || remoteTaskId)}/result`);
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data?.detail || data?.message || "视频结果查询失败");
    }

    if (localTaskId) {
      latestTask = await fetchTaskRecord(localTaskId);
      renderResult(latestTask);
      await loadTasks();
      const status = normalizeStatus(latestTask.status);
      if (latestTask?.result?.video_url || status === "succeeded" || status === "failed") {
        return latestTask;
      }
    } else {
      const status = normalizeStatus(data?.status);
      if (data?.video_url || status === "succeeded" || status === "failed") {
        return data;
      }
    }
  }

  loadingText.textContent = "已达到查询上限，可稍后点击刷新任务继续查看。";
  return latestTask;
}

async function submitTask(event) {
  event.preventDefault();

  const loadingOptions =
    state.activeFeature === "image_to_video"
      ? {
          title: "视频生成中",
          text: "模型正在处理图片并生成视频，这个过程通常比文字或图片更久。",
        }
      : {
          title: "接口调用中",
          text: "正在等待模型返回结果，请稍候...",
        };

  setLoading(true, loadingOptions);
  resultBox.textContent = "处理中...";
  assetGallery.innerHTML = "";

  try {
    let response;
    if (state.activeFeature === "image_to_video") {
      const model = activeModel();
      const imageCount = imageInput.files.length;
      const minImages = model?.min_images || 1;
      const maxImages = model?.max_images || 6;
      if (imageCount < minImages || imageCount > maxImages) {
        resultBox.textContent = `当前模型要求上传 ${minImages}-${maxImages} 张图片，你选择了 ${imageCount} 张。`;
        return;
      }

      const formData = new FormData();
      formData.append("model_id", state.activeModel);
      formData.append("token", tokenInput.value);
      formData.append("prompt", "");
      formData.append("parameters", JSON.stringify(collectParameters()));
      [...imageInput.files].forEach((file) => formData.append("files", file));
      response = await fetch("/api/video-tasks", { method: "POST", body: formData });
    } else {
      const payload = {
        feature: state.activeFeature,
        model_id: state.activeModel,
        token: tokenInput.value,
        prompt: state.activeFeature === "text_to_image" ? promptInput.value : "",
        source_text: sourceInput.value,
        parameters: collectParameters(),
      };
      response = await fetch("/api/tasks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    }

    const data = await response.json();
    renderResult(data);
    await loadTasks();

    if (
      state.activeFeature === "image_to_video" &&
      response.ok &&
      data?.result?.task_id &&
      !data?.result?.video_url &&
      ["queued", "running"].includes(normalizeStatus(data?.status || data?.result?.task_status))
    ) {
      await pollVideoTaskUntilFinished(data);
    }
  } catch (error) {
    resultBox.textContent = `前端请求失败：${error.message}`;
  } finally {
    setLoading(false);
  }
}

async function loadTasks() {
  const response = await fetch("/api/tasks");
  const tasks = await response.json();
  taskList.innerHTML = "";

  if (!tasks.length) {
    taskList.textContent = "暂无任务。";
    return;
  }

  tasks.slice(0, 8).forEach((task) => {
    const item = document.createElement("div");
    item.className = "task-item";

    const title = document.createElement("strong");
    title.textContent = task.model_name;
    item.appendChild(title);

    const lines = [
      `功能：${task.feature}`,
      `Token：${task.token_masked}`,
      `状态：${task.status}`,
      `时间：${task.created_at}`,
    ];
    lines.forEach((text) => {
      const row = document.createElement("div");
      row.textContent = text;
      item.appendChild(row);
    });

    const badge = document.createElement("span");
    badge.className = "badge";
    badge.textContent = task.status;
    item.appendChild(badge);

    item.addEventListener("click", async () => {
      renderResult(task);
      if (task.feature === "image_to_video" && task.result?.task_id && task.status === "running") {
        setLoading(true, { title: "视频生成中", text: "正在继续查询该任务的生成结果..." });
        try {
          await pollVideoTaskUntilFinished(task);
        } catch (error) {
          resultBox.textContent = `前端请求失败：${error.message}`;
        } finally {
          setLoading(false);
        }
      }
    });

    taskList.appendChild(item);
  });
}

function renderUploadPreview() {
  uploadPreview.innerHTML = "";
  const model = activeModel();
  const imageCount = imageInput.files.length;
  const minImages = model?.min_images || 1;
  const maxImages = model?.max_images || 6;
  imageLimitTip.textContent = `当前模型要求上传 ${minImages}-${maxImages} 张图片，你已选择 ${imageCount} 张。`;

  [...imageInput.files].forEach((file) => {
    const img = document.createElement("img");
    img.src = URL.createObjectURL(file);
    img.onload = () => URL.revokeObjectURL(img.src);
    uploadPreview.appendChild(img);
  });
}

function render() {
  renderMainTabs();
  renderModelTabs();
  renderParameters();
}

async function bootstrap() {
  const response = await fetch("/api/model-tabs");
  state.tabs = await response.json();
  state.activeFeature = state.tabs[0]?.id || null;
  state.activeModel = state.tabs[0]?.models[0]?.id || null;
  render();
  await loadTasks();
}

taskForm.addEventListener("submit", submitTask);
refreshTasks.addEventListener("click", loadTasks);
imageInput.addEventListener("change", renderUploadPreview);

bootstrap().catch((error) => {
  resultBox.textContent = `初始化失败：${error.message}`;
});
