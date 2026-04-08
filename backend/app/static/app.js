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

function renderMainTabs() {
  mainTabs.innerHTML = "";
  state.tabs.forEach((tab) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `tab-button ${tab.id === state.activeFeature ? "active" : ""}`;
    button.textContent = tab.name;
    button.addEventListener("click", () => {
      state.activeFeature = tab.id;
      state.activeModel = tab.models[0]?.id;
      resetForm();
      render();
    });
    mainTabs.appendChild(button);
  });
}

function renderModelTabs() {
  modelTabs.innerHTML = "";
  const tab = activeTab();
  featureSummary.textContent = tab ? tab.description : "";
  featureSummary.classList.toggle("hidden", !tab?.description);
  tab?.models.forEach((model) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `tab-button ${model.id === state.activeModel ? "active" : ""}`;
    button.textContent = model.name;
    button.title = model.description;
    button.addEventListener("click", () => {
      state.activeModel = model.id;
      resetForm(false);
      render();
    });
    modelTabs.appendChild(button);
  });
}

function renderParameters() {
  parameterGrid.innerHTML = "";
  const model = activeModel();
  if (!model) return;

  document.body.dataset.feature = state.activeFeature || "";
  tokenField.classList.toggle("hidden", !!model.token_from_env);
  tokenInput.placeholder = model.token_label;

  const showPromptField = state.activeFeature === "text_to_image";
  promptField.classList.toggle("hidden", !showPromptField);
  if (showPromptField) {
    promptLabel.textContent = model.prompt_label;
  } else {
    promptInput.value = "";
  }

  if (state.activeFeature === "image_to_video") {
    imageLimitTip.textContent = `当前模型要求上传 ${model.min_images || 1}-${model.max_images || 6} 张图片。`;
  }

  imageUploadField.classList.toggle("hidden", state.activeFeature !== "image_to_video");
  sourceField.classList.toggle("hidden", state.activeFeature === "image_to_video");

  if (state.activeFeature === "text_split") {
    sourceLabel.textContent = "输入文案";
  } else if (state.activeFeature === "text_to_image") {
    sourceLabel.textContent = "画面补充说明（可选）";
  } else {
    sourceLabel.textContent = "上传图片（支持多图）";
  }

  if (!model.supports_real_api) {
    const warning = document.createElement("div");
    warning.className = "warning full";
    warning.textContent = model.description;
    parameterGrid.appendChild(warning);
  }

  model.parameters.forEach((param) => {
    const label = document.createElement("label");
    label.className = `field ${param.type === "textarea" ? "full" : ""}`.trim();
    const span = document.createElement("span");
    span.textContent = param.label;
    label.appendChild(span);

    let input;
    if (param.type === "select") {
      input = document.createElement("select");
      param.options.forEach((option) => {
        const optionNode = document.createElement("option");
        optionNode.value = option;
        optionNode.textContent = option;
        if (option === param.default) optionNode.selected = true;
        input.appendChild(optionNode);
      });
    } else if (param.type === "boolean") {
      input = document.createElement("select");
      [
        ["true", "开启"],
        ["false", "关闭"],
      ].forEach(([value, text]) => {
        const optionNode = document.createElement("option");
        optionNode.value = value;
        optionNode.textContent = text;
        if (String(param.default) === value) optionNode.selected = true;
        input.appendChild(optionNode);
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
    }

    input.dataset.key = param.key;
    input.dataset.type = param.type;
    label.appendChild(input);
    parameterGrid.appendChild(label);
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
    const key = input.dataset.key;
    const type = input.dataset.type;
    if (type === "boolean") {
      values[key] = input.value === "true";
    } else if (type === "number") {
      let value = Number(input.value);
      if (input.min !== "") value = Math.max(Number(input.min), value);
      if (input.max !== "") value = Math.min(Number(input.max), value);
      values[key] = value;
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
  } else {
    lines.push(JSON.stringify(data, null, 2));
  }

  lines.push("");
  lines.push("-----");
  if (data?.id) lines.push(`任务ID：${data.id}`);
  if (data?.model_name) lines.push(`模型：${data.model_name}`);
  if (data?.status) lines.push(`状态：${data.status}`);

  if (remoteTaskId) {
    lines.push(`Remote Task ID: ${remoteTaskId}`);
  }

  return lines.join("\n");
}

function renderAssets(data) {
  assetGallery.innerHTML = "";

  const assets = data?.result?.assets || [];
  assets.forEach((asset) => {
    const card = document.createElement("div");
    card.className = "asset-card";
    if (asset.url) {
      card.innerHTML = `<img src="${asset.url}" alt="generated image" /><span>图片 URL</span>`;
    } else if (asset.b64_json) {
      card.innerHTML = `<img src="data:image/png;base64,${asset.b64_json}" alt="generated image" /><span>Base64 图片</span>`;
    }
    assetGallery.appendChild(card);
  });

  const providerResponse = data?.result?.provider_response;
  const videoUrl = data?.result?.video_url || providerResponse?.video_url || providerResponse?.output?.video_url || providerResponse?.data?.video_url;
  const taskId = data?.result?.task_id || providerResponse?.output?.task_id || providerResponse?.task_id || providerResponse?.data?.task_id || providerResponse?.id;
  if (videoUrl) {
    const card = document.createElement("div");
    card.className = "asset-card video-card";
    card.innerHTML = `<video controls src="${videoUrl}"></video><span>生成视频</span>`;
    assetGallery.appendChild(card);
  } else if (taskId) {
    const card = document.createElement("div");
    card.className = "asset-card";
    const taskKind = data?.feature === "text_to_image" ? "图片" : "视频";
    card.textContent = `${taskKind}任务已提交，任务 ID：${taskId}`;
    assetGallery.appendChild(card);
  }
}

function renderResult(data) {
  resultBox.textContent = formatResultText(data);
  renderAssets(data);
}

function setLoading(loading, options = {}) {
  const { title = "接口调用中", text = "正在等待模型返回结果，请稍候..." } = options;
  loadingPanel.classList.toggle("hidden", !loading);
  loadingTitle.textContent = title;
  loadingText.textContent = text;
  submitButton.disabled = loading;
  refreshTasks.disabled = loading;
}

async function submitTask(event) {
  event.preventDefault();
  const loadingOptions = state.activeFeature === "image_to_video"
    ? { title: "视频生成中", text: "模型正在处理图片并生成视频，这个过程通常比文字或图片更久。" }
    : { title: "接口调用中", text: "正在等待模型返回结果，请稍候..." };
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
    item.innerHTML = `
      <strong>${task.model_name}</strong>
      <div>功能：${task.feature}</div>
      <div>Token：${task.token_masked}</div>
      <div>状态：${task.status}</div>
      <div>时间：${task.created_at}</div>
      <span class="badge">${task.status}</span>
    `;
    item.addEventListener("click", () => renderResult(task));
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
  state.activeFeature = state.tabs[0]?.id;
  state.activeModel = state.tabs[0]?.models[0]?.id;
  render();
  await loadTasks();
}

taskForm.addEventListener("submit", submitTask);
refreshTasks.addEventListener("click", loadTasks);
imageInput.addEventListener("change", renderUploadPreview);
bootstrap().catch((error) => {
  resultBox.textContent = `初始化失败：${error.message}`;
});
