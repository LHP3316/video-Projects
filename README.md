# AI 创作控制台演示项目

这是一个用于演示 AI 创作流程的 FastAPI + Vue 项目骨架。

当前演示重点：

1. 三个主 Tab：文字拆解、文生图、图生视频。
2. 每个主 Tab 下按大模型拆成子 Tab。
3. 每个模型子 Tab 内填写参数、提示词并提交任务；DMXAPI 接口会直接读取 `.env` 中的密钥。
4. FastAPI 提供模型配置、任务提交、任务查询接口。
5. 文字拆解、图生视频已接入 `prompt.py` 中的网站提示词模板，前端不再显示这两个 Tab 的提示词输入框；文生图保持原逻辑。
6. 文字拆解、文生图、图生视频已预留真实 API 调用。
7. 接口访问和错误会写入 `backend/logs/api_calls.log`。

## 当前模型

文字拆解：

1. DeepSeek V3.2：后端按 DeepSeek 官方 `deepseek-chat` 接口调用。
2. Qwen3.5 Plus：后端按 DashScope OpenAI 兼容接口调用。
3. GPT-4o：后端按 OpenAI Chat Completions 接口调用。

文生图：

1. 即梦文生图：走 DMXAPI `doubao-seedream-4-0-250828`。
2. OpenAI 文生图：走 DMXAPI `gpt-image-1`。
3. `qwen-image-max` / `qwen-image-2.0` 系列。

图生视频：

1. 即梦首帧生成视频：走 DMXAPI `doubao-seedance-2-0-260128`，上传 1 张图。
2. 即梦首尾帧生成视频：走 DMXAPI `doubao-seedance-2-0-250528`，上传 2 张图。
3. 可灵图生视频：走 DMXAPI `kling-v2.6`，上传 1 张图。
4. `wan2.6-i2v` / `wan2.6-i2v-flash`：首帧图生视频，当前限制上传 1 张图片。
5. `wan2.2-kf2v-flash`：首尾帧生视频，上传 2 张图片，第 1 张作为首帧，第 2 张作为尾帧。
6. `Vidu Multi-Frame`：多关键帧生视频，第 1 张作为起始帧，后续图片按顺序作为关键帧。

说明：图生视频不同平台鉴权和异步任务查询差异较大，当前先提交任务并展示平台返回内容；后续可继续补轮询查询接口。

图生视频提示词参数：

1. 前端可手动填写故事情节、角色信息、场景信息、小说原文、推文文案、章节文案前分镜信息、章节文案后分镜信息、章节文案。
2. 后端会把上述字段渲染到 `prompt.py` 的图生视频提示词模板里，再作为最终视频提示词提交给模型。
3. 图生视频提示词由系统固定模板生成，前端不再提供单独的视频提示词输入框。

## 后端运行

推荐使用项目根目录脚本：

```bash
cd /mnt/d/项目文件夹/zzdh-replica-demo
./build-frontend
./start
./status
./restart
./stop
```

说明：

1. `./start` 和 `./restart` 会先尝试执行 `./build-frontend`，把 `frontend` 构建结果同步到 `backend/app/static`，再启动/重启后端。
2. 如果机器上没有 `npm`，脚本会跳过前端构建并继续使用当前已有的静态页面。
3. `./stop` 只停止后端进程；前端当前采用静态构建发布，没有独立常驻进程。

代理配置：

1. 复制 [.env.example](D:/项目文件夹/zzdh-replica-demo/.env.example) 为项目根目录下的 `.env`。
2. 常见本地代理示例：

```bash
HTTP_PROXY=http://127.0.0.1:7890
HTTPS_PROXY=http://127.0.0.1:7890
ALL_PROXY=socks5://127.0.0.1:7891
NO_PROXY=127.0.0.1,localhost
```

3. 如果你有 OpenAI 中转网关，也可以额外配置：

```bash
OPENAI_BASE_URL=https://your-proxy.example.com
```

4. 如果你要使用 DMXAPI 的即梦 / 可灵 / OpenAI 文生图与图生视频接口，还需要配置：

```bash
DMXAPI_BASE_URL=https://www.dmxapi.cn
DMXAPI_API_KEY=你的_DMXAPI_Key
```

5. 配置完成后执行 `./restart`，后端和前端构建都会读取 `.env` 中的代理环境变量。
6. 当前项目参考 NexusAI 的思路保留了 `supervisord.conf` 代理示例，但实际推荐通过 `.env` 统一管理代理，避免重复修改脚本和 supervisord 配置。

脚本会优先使用 `supervisord`；如果当前环境没有安装 `supervisord`，会自动退回普通后台启动方式，并把 PID 写入：

```text
backend/logs/api.pid
```

日志位置：

```text
backend/logs/api.log
backend/logs/api_calls.log
```

如果你安装了 supervisor，也可以使用：

```bash
supervisord -c supervisord.conf
supervisorctl -c supervisord.conf status
supervisorctl -c supervisord.conf restart all
supervisorctl -c supervisord.conf stop all
```

手动启动方式：

```bash
cd zzdh-replica-demo/backend
python3 -m pip install -r requirements.txt
python3 -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

打开：

```text
http://127.0.0.1:8000/
```

## 前端运行

如果环境安装了 Node.js：

```bash
cd zzdh-replica-demo/frontend
npm install
npm run dev
```

前端默认代理到 `http://127.0.0.1:8000`。

## 接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | /api/health | 健康检查 |
| GET | /api/model-tabs | 获取三主 Tab 和模型子 Tab 配置 |
| POST | /api/tasks | 提交模拟任务 |
| POST | /api/video-tasks | 上传多图并提交图生视频任务 |
| GET | /api/tasks | 查看任务列表 |
| GET | /api/tasks/{task_id} | 查看任务详情 |
