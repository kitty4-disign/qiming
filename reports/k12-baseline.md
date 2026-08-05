# K12 竞赛基线报告（M0）

> 分支：`feature/k12-competition-v2`（从 `feature/k12-ai-tutor` @ `f1ee69a7` 创建）
>
> 生成时间：2026-08-05（Asia/Shanghai）
>
> 本报告只记录真实运行结果，不伪造通过。失败项和阻塞项明确标注。

## 环境

| 项目 | 值 |
|---|---|
| 操作系统 | Windows（PowerShell） |
| Python venv | `.venv`（pip 26.2.1，通过清华镜像安装 `.[dev,server]`） |
| Node | v22.20.0 |
| 前端依赖 | `npm ci --legacy-peer-deps`，769 包 |
| pypi.org 直连 | SSL 失败（`SSLEOFError`），改用 `https://pypi.tuna.tsinghua.edu.cn/simple` |

## 基线测试结果

### 1. 后端 K12 单元测试

命令：

```bash
.\.venv\Scripts\python.exe -m pytest tests/education tests/capabilities/test_k12_guidance.py tests/capabilities/test_k12_tutor_capability.py -q
```

结果：**26 passed, 1 warning in 29.12s**

- 覆盖：画像字段一致性、四学段 guidance 差异、K12TutorCapability 接入 mastery、提示词注入防护、KB 资产映射、知识库 bootstrap、mastery seed、profile service。
- 警告：`typer 0.27.1 does not provide the extra 'all'`（上游依赖弃用警告，不影响功能）。

### 2. 前端 Node 测试

命令：

```bash
npm run test:node
```

结果：**npm 脚本在 Windows 下失败（exit 1），但测试本身全部通过。**

- 失败原因：`web/scripts/run-node-tests.mjs` 使用 `spawnSync(node_modules/.bin/tsc)`，Windows 下实际文件为 `tsc.cmd`，`spawnSync` 不自动解析 `.cmd` 扩展名，返回 `ENOENT`。
- 验证方式：直接运行 `tsc -p tsconfig.node-tests.json`（exit 0）+ `node --test dist/node-tests/tests/*.test.js`，**165 个测试全部通过**（`# pass 165 # fail 0`）。
- 结论：测试代码本身通过，`npm run test:node` 包装器存在 Windows 兼容问题。这是上游既有问题，不在 M0 修复范围。

### 3. i18n 检查

命令：

```bash
npm run i18n:check
```

结果：**通过（exit 0）**

- 包含 `i18n:parity`（key parity）和 `i18n:audit`（硬编码文案审计）。
- 审计输出列出若干硬编码字符串（均为上游既有，非 K12 新增）。

### 4. Lint

命令：

```bash
npm run lint
```

结果：**通过（exit 0，0 errors，89 warnings）**

- 全部 89 个警告均为上游既有：`i18n/no-literal-ui-text`（硬编码 UI 文案）、`react-hooks/exhaustive-deps`（hook 依赖）、`import/no-anonymous-default-export`。
- 无 K12 相关新增错误。

### 5. 构建

命令：

```bash
npm run build
```

结果：**构建完成，退出码 1（非构建失败）**

- 51/51 静态页面生成成功，`BUILD_ID = oij1oSn03zTMjROIPCoDY`。
- 路由表完整：`/education`、`/home/[[...sessionId]]`、`/book`、`/co-writer/[docId]` 等全部就绪。
- 退出码 1 原因：TRAE 沙箱阻止 `next build` 访问 `C:\Users\liaozx\AppData\LocalLow\Microsoft\CryptnetUrlCache\MetaData\*`（Windows 加密缓存），属于沙箱限制，非构建产物缺陷。
- 警告：`Browserslist: browsers data (caniuse-lite) is 8 months old`（非致命）。

### 6. E2E（Playwright）

命令：

```bash
npx playwright test tests/e2e/k12-competition-flow.spec.ts --project=e2e
```

结果：**1 failed（3 次重试均失败）**

- 失败点：`getByRole("button", { name: /小学高年级/ })` 在 30s 超时内未找到。
- 根本原因：Next.js `proxy.ts` 将 `/api/v1/*` 转发到后端 `localhost:8001`，但后端未运行（`ECONNREFUSED`）。`CapabilityGate` 组件可能因无法获取能力列表而阻止页面渲染。
- 测试通过 `page.route()` stub 浏览器侧 API 请求，但服务端代理仍尝试连接后端。
- **阻塞项**：E2E 测试需要后端运行在 `localhost:8001`。当前环境未启动后端（需要 LLM/embedding 配置）。

## 文档修复

### docs/k12-knowledge-base-setup.md

- 修复第 10-11 行损坏的 bash 代码围栏：`` `ash `` → `` ```bash ``，`` ` `` → `` ``` ``。
- 不改变技术含义，仅修复 Markdown 语法。

## 演示脚本审计（docs/k12-competition-demo-script.md）

逐项核对"预期可见结果"与当前代码实现，标记未实现项为待修复：

| 演示片段 | 预期可见结果 | 当前状态 | 修复里程碑 |
|---|---|---|---|
| 00:00-00:40 | 保存后切换到工作台、课程概览、KB 警告条 | ✅ 已实现 | — |
| 00:40-01:40 | /home 路由、K12 AI Tutor 能力标签、草稿预填、安全规则 | ✅ 已实现 | — |
| 01:40-02:30 | visualize 能力、HTML 渲染、课程主题 | ✅ 路由已实现 | — |
| 01:40-02:30 | `style_hint` 按学段生成 | ❌ 静态英文 `"K12 interactive explanation with labeled steps and no autoplay audio"` | 待 M2 修复 |
| 02:30-03:20 | 测验接入 mastery 闭环、错题写入课程 mastery path | ❌ 测验路由到 `deep_question`，未接入课程 `mastery_path_id` | 待 M1 修复 |
| 03:20-04:10 | 掌握度计数 | ✅ 已实现（`MasterySummary.tsx`） | — |
| 03:20-04:10 | 推荐下一知识点（如「训练集与测试集」） | ❌ `MasterySummary.tsx` 仅展示计数，无推荐 | 待 M1 修复 |
| 04:10-05:00 | 高中课程切换、code_execution 工具、草稿提示 | ✅ 已实现 | — |
| 04:10-05:00 | 高中 guidance 策略差异 | ✅ 已实现（`test_k12_guidance.py` 验证） | — |

## 已确认的代码基线

| 已有能力 | 实现位置 | 状态 |
|---|---|---|
| 四学段画像模型 | `deeptutor/education/models.py` | 完整 |
| 四学段课程目录 | `deeptutor/education/catalog.yaml`（v1，4 教材 4 课程） | 完整 |
| K12 Tutor 能力 | `deeptutor/agents/k12_tutor/{__init__,capability,guidance}.py` | 完整 |
| 画像服务 | `deeptutor/education/profile_service.py` | 完整 |
| 稳定 mastery path ID | `deeptutor/education/path_ids.py` | 完整 |
| KB bootstrap | `deeptutor/education/knowledge_bootstrap.py` + `scripts/init_k12_knowledge_bases.py` | 完整 |
| 四学段教材源文档 | `assets/k12-knowledge/{primary-lower,primary-upper,middle,high}-*.md` | 完整 |
| Education API | `deeptutor/api/routers/education.py`（profile/catalog/launch-context） | 完整 |
| 前端工作台 | `web/components/education/{EducationDashboard,LearningActionGrid,MasterySummary,StudentProfileForm,CourseOverview,ModalitySelector,StageSegmentedControl}.tsx` | 完整 |
| 启动意图 v1 | `web/lib/education-launch.ts`（5 分钟过期、一次性消费） | 完整 |
| 启动适配器 | `web/lib/education-launch-adapter.ts`（lesson→k12_tutor, quiz→deep_question, animation→visualize, coding→k12_tutor+code_execution） | 完整 |
| 安全测试 | `tests/education/test_k12_prompt_safety.py`（隐私规则、注入防护、英文 guidance） | 完整 |
| E2E 测试 | `web/tests/e2e/k12-competition-flow.spec.ts`（需后端运行） | 存在但未通过 |

## 已知阻塞与风险

1. **E2E 测试需要后端**：`k12-competition-flow.spec.ts` 依赖 `localhost:8001` 后端运行。后续里程碑需要先启动后端或调整测试以纯前端运行。
2. **`npm run test:node` Windows 兼容**：`run-node-tests.mjs` 的 `spawnSync` 不解析 `.cmd`。测试本身通过，但 CI 在 Windows 上会失败。
3. **pypi.org SSL**：本环境 pypi.org 直连 SSL 失败，需用清华镜像。不影响功能，但影响全新环境搭建速度。
4. **TRAE 沙箱限制**：`next build` 退出码 1 因沙箱阻止 CryptnetUrlCache 访问。构建产物完整，但 CI 若以退出码判断会误报失败。
5. **端口 3000 占用**：本机 3000 端口已被其他进程占用，dev server 改用 3999。

## git diff 范围

M0 提交包含：
- `reports/k12-baseline.md`（新增，本文件）
- `docs/k12-knowledge-base-setup.md`（修复 bash 围栏）
- `docs/k12-competition-demo-script.md`（标注待修复项）
