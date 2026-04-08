<template>
  <div class="app">
    <header class="hero">
      <div>
        <p class="eyebrow">FastAPI + Vue 演示骨架</p>
        <h1>AI 创作控制台</h1>
        <p class="hero-text">
          三个主 Tab：文字拆解、文生图、图生视频。文字拆解与图生视频使用系统内置提示词模板，用户只需填写正文、参数和图片。
        </p>
      </div>
      <div class="status-card">
        <strong>演示模式</strong>
        <p>当前前端会优先展示结构化结果，而不是整段 JSON。</p>
      </div>
    </header>

    <main class="layout">
      <section class="panel">
        <div class="tabs">
          <button
            v-for="tab in tabs"
            :key="tab.id"
            type="button"
            class="tab-button"
            :class="{ active: tab.id === activeFeature }"
            @click="selectFeature(tab.id)"
          >
            {{ tab.name }}
          </button>
        </div>

        <div v-if="activeTab?.description" class="feature-summary">{{ activeTab?.description }}</div>

        <div class="tabs model-tabs">
          <button
            v-for="model in activeTab?.models || []"
            :key="model.id"
            type="button"
            class="tab-button"
            :class="{ active: model.id === activeModel }"
            @click="activeModel = model.id"
          >
            {{ model.name }}
          </button>
        </div>

        <form class="form-grid" @submit.prevent="submitTask">
          <label v-if="!activeModelOption?.token_from_env" class="field full">
            <span>Token / API Key</span>
            <input v-model="form.token" type="password" :placeholder="activeModelOption?.token_label" />
          </label>

          <label v-if="activeFeature !== 'image_to_video'" class="field full">
            <span>{{ sourceLabel }}</span>
            <textarea v-model="form.source_text" rows="5" placeholder="例如：少年站在雨夜街道中央，远处传来脚步声。" />
          </label>

          <label v-else class="field full">
            <span>{{ sourceLabel }}</span>
            <input type="file" accept="image/*" multiple @change="handleFiles" />
            <small>{{ imageLimitTip }}</small>
          </label>

          <label v-if="showPromptField" class="field full">
            <span>{{ activeModelOption?.prompt_label || "提示词" }}</span>
            <textarea v-model="form.prompt" rows="4" placeholder="填写文生图提示词" />
          </label>

          <div class="parameter-grid full">
            <label
              v-for="param in activeModelOption?.parameters || []"
              :key="param.key"
              :class="['field', { full: param.type === 'textarea' }]"
            >
              <span>{{ param.label }}</span>
              <select v-if="param.type === 'select'" v-model="form.parameters[param.key]">
                <option v-for="option in param.options" :key="option" :value="option">{{ option }}</option>
              </select>
              <select v-else-if="param.type === 'boolean'" v-model="form.parameters[param.key]">
                <option :value="true">开启</option>
                <option :value="false">关闭</option>
              </select>
              <textarea
                v-else-if="param.type === 'textarea'"
                v-model="form.parameters[param.key]"
                rows="4"
                :placeholder="param.placeholder || ''"
              />
              <input
                v-else
                v-model="form.parameters[param.key]"
                :type="param.type === 'number' ? 'number' : (param.type === 'password' ? 'password' : 'text')"
              />
            </label>
          </div>

          <button type="submit" class="primary-button full" :disabled="isLoading">
            {{ isLoading ? "处理中..." : "提交任务" }}
          </button>
        </form>
      </section>

      <aside class="panel side-panel">
        <div class="side-title">
          <h2>任务结果</h2>
          <button class="ghost-button" type="button" :disabled="isLoading" @click="loadTasks">刷新</button>
        </div>
        <div v-if="isLoading" class="loading-panel">
          <div class="loading-spinner"></div>
          <div>
            <strong>{{ loadingTitle }}</strong>
            <p>{{ loadingText }}</p>
          </div>
        </div>
        <div class="result-box">{{ formattedResultText }}</div>
        <div class="asset-gallery">
          <div v-for="asset in renderedAssets" :key="asset.src" class="asset-card">
            <img v-if="asset.type === 'image'" :src="asset.src" alt="generated image" />
            <video v-else controls :src="asset.src" />
            <span>{{ asset.label }}</span>
          </div>
        </div>
        <h3>最近任务</h3>
        <div class="task-list">
          <div v-for="task in tasks" :key="task.id" class="task-item" @click="selectTask(task)">
            <strong>{{ task.model_name }}</strong>
            <div>功能：{{ task.feature }}</div>
            <div>Token：{{ task.token_masked }}</div>
            <div>时间：{{ task.created_at }}</div>
            <span class="badge">{{ task.status }}</span>
          </div>
        </div>
      </aside>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";

type FeatureTab = {
  id: string;
  name: string;
  description: string;
  models: ModelOption[];
};

type ModelOption = {
  id: string;
  name: string;
  token_label: string;
  token_from_env?: boolean;
  prompt_label: string;
  default_prompt?: string;
  min_images?: number;
  max_images?: number;
  parameters: Array<{
    key: string;
    label: string;
    type: string;
    default: unknown;
    options?: string[];
    placeholder?: string;
  }>;
};

const tabs = ref<FeatureTab[]>([]);
const activeFeature = ref("");
const activeModel = ref("");
const tasks = ref<any[]>([]);
const resultText = ref("提交任务后，这里会展示结果。");
const isLoading = ref(false);
const loadingTitle = ref("接口调用中");
const loadingText = ref("正在等待模型返回结果，请稍候...");
const selectedFiles = ref<File[]>([]);
const lastTask = ref<any>(null);
const form = reactive({
  token: "",
  prompt: "",
  source_text: "",
  parameters: {} as Record<string, unknown>,
});

const activeTab = computed(() => tabs.value.find((tab) => tab.id === activeFeature.value));
const activeModelOption = computed(() => activeTab.value?.models.find((model) => model.id === activeModel.value));
const showPromptField = computed(() => activeFeature.value === "text_to_image");
const sourceLabel = computed(() => {
  if (activeFeature.value === "text_split") return "输入文案";
  if (activeFeature.value === "text_to_image") return "画面补充说明";
  return "上传图片（支持多图）";
});
const imageLimitTip = computed(() => {
  if (activeFeature.value !== "image_to_video") return "";
  const minImages = activeModelOption.value?.min_images || 1;
  const maxImages = activeModelOption.value?.max_images || 6;
  return `当前模型要求上传 ${minImages}-${maxImages} 张图片，你已选择 ${selectedFiles.value.length} 张。`;
});
const renderedAssets = computed(() => {
  const assets = lastTask.value?.result?.assets || [];
  const list: Array<{ type: string; src: string; label: string }> = assets
    .map((asset: any) => {
      if (asset.url) return { type: "image", src: asset.url, label: "图片 URL" };
      if (asset.b64_json) return { type: "image", src: `data:image/png;base64,${asset.b64_json}`, label: "Base64 图片" };
      return null;
    })
    .filter(Boolean) as Array<{ type: string; src: string; label: string }>;
  const provider = lastTask.value?.result?.provider_response;
  const videoUrl = lastTask.value?.result?.video_url || provider?.video_url || provider?.output?.video_url || provider?.data?.video_url;
  if (videoUrl) list.push({ type: "video", src: videoUrl, label: "生成视频" });
  return list;
});
const formattedResultText = computed(() => {
  const task = lastTask.value;
  if (!task) return resultText.value;

  const result = task.result || {};
  const lines: string[] = [];
  if (task.feature === "text_split" && result.raw) {
    lines.push(result.raw);
  } else if (result.message) {
    lines.push(result.message);
  } else {
    lines.push(JSON.stringify(task, null, 2));
  }

  lines.push("");
  lines.push("-----");
  if (task.id) lines.push(`任务ID：${task.id}`);
  if (task.model_name) lines.push(`模型：${task.model_name}`);
  if (task.status) lines.push(`状态：${task.status}`);
  return lines.join("\n");
});

function selectFeature(id: string) {
  const tab = tabs.value.find((item) => item.id === id);
  activeFeature.value = id;
  activeModel.value = tab?.models[0]?.id || "";
}

watch(
  activeModelOption,
  (model) => {
    form.parameters = {};
    model?.parameters.forEach((param) => {
      form.parameters[param.key] = param.default;
    });
    if (activeFeature.value !== "text_to_image") {
      form.prompt = "";
    }
  },
  { immediate: true }
);

async function loadTabs() {
  const response = await fetch("/api/model-tabs");
  tabs.value = await response.json();
  activeFeature.value = tabs.value[0]?.id || "";
  activeModel.value = tabs.value[0]?.models[0]?.id || "";
}

async function submitTask() {
  isLoading.value = true;
  if (activeFeature.value === "image_to_video") {
    loadingTitle.value = "视频生成中";
    loadingText.value = "模型正在处理图片并生成视频，这个过程通常比文字或图片更久。";
  } else {
    loadingTitle.value = "接口调用中";
    loadingText.value = "正在等待模型返回结果，请稍候...";
  }
  let response: Response;
  resultText.value = "处理中...";
  try {
    if (activeFeature.value === "image_to_video") {
      const minImages = activeModelOption.value?.min_images || 1;
      const maxImages = activeModelOption.value?.max_images || 6;
      if (selectedFiles.value.length < minImages || selectedFiles.value.length > maxImages) {
        resultText.value = `当前模型要求上传 ${minImages}-${maxImages} 张图片，你选择了 ${selectedFiles.value.length} 张。`;
        return;
      }
      const body = new FormData();
      body.append("model_id", activeModel.value);
      body.append("token", form.token);
      body.append("prompt", "");
      body.append("parameters", JSON.stringify(form.parameters));
      selectedFiles.value.forEach((file) => body.append("files", file));
      response = await fetch("/api/video-tasks", { method: "POST", body });
    } else {
      response = await fetch("/api/tasks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          feature: activeFeature.value,
          model_id: activeModel.value,
          token: form.token,
          prompt: activeFeature.value === "text_to_image" ? form.prompt : "",
          source_text: form.source_text,
          parameters: form.parameters,
        }),
      });
    }
    const data = await response.json();
    lastTask.value = data;
    resultText.value = data?.result?.message || "调用完成";
    await loadTasks();
  } catch (error: any) {
    resultText.value = `前端请求失败：${error.message}`;
  } finally {
    isLoading.value = false;
  }
}

function selectTask(task: any) {
  lastTask.value = task;
  resultText.value = task?.result?.message || "已加载任务结果";
}

function handleFiles(event: Event) {
  const input = event.target as HTMLInputElement;
  selectedFiles.value = Array.from(input.files || []);
}

async function loadTasks() {
  const response = await fetch("/api/tasks");
  tasks.value = await response.json();
}

onMounted(async () => {
  await loadTabs();
  await loadTasks();
});
</script>
