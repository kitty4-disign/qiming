# K12 教材知识库配置

本指南使用 DeepTutor 现有 Knowledge Center 上传和索引流程，不新增数据库、向量库或导入脚本。请以管理员身份完成初始化，并保持知识库名称与课程目录完全一致。


## 一键初始化

推荐直接用仓库脚本或 CLI 一次创建四个学段教材知识库：

`ash
# 方式一：脚本
python scripts/init_k12_knowledge_bases.py

# 方式二：CLI
deeptutor kb init-k12
`

常用参数：

- --force：即使已有索引也重建
- --skip-index：只复制教材源文件，不调用 embedding
- --provider llamaindex：指定检索引擎（默认 llamaindex）

初始化完成后，再用下面的接口验证。

## 文件映射

| 知识库名称 | 上传源文件 |
|---|---|
| `k12-ai-primary-lower` | `assets/k12-knowledge/primary-lower-ai-first-steps.md` |
| `k12-ai-primary-upper` | `assets/k12-knowledge/primary-upper-image-recognition.md` |
| `k12-ai-middle` | `assets/k12-knowledge/middle-classification-lab.md` |
| `k12-ai-high` | `assets/k12-knowledge/high-python-image-classifier.md` |

名称中的大小写和连字符必须保持不变。教育目录会按这些名称检查当前用户可见的知识库；名称不同会触发“教材知识库尚未就绪”降级提示。

## 创建与索引

1. 启动 DeepTutor 后进入侧栏的 Knowledge Center。
2. 选择“新建知识库”，创建 `k12-ai-primary-lower`。
3. 上传 `assets/k12-knowledge/primary-lower-ai-first-steps.md`，使用当前已配置的索引引擎完成索引。
4. 等待状态变为已索引或就绪，不要在索引仍运行时开始比赛演示。
5. 按同样步骤创建 `k12-ai-primary-upper`、`k12-ai-middle` 和 `k12-ai-high`，每个库只上传映射表中的对应文件。
6. 若索引失败，先在 Knowledge Center 查看错误并使用现有“重新索引”操作。不要通过改名绕过错误，也不要把四份教材合并到同一个库。

## 接口验证

使用已登录且有权访问这些知识库的会话请求：

```text
GET /api/v1/knowledge/list
```

确认响应同时满足：

- 列表中出现 `k12-ai-primary-lower`、`k12-ai-primary-upper`、`k12-ai-middle`、`k12-ai-high`；
- 每个知识库都报告已索引、就绪或当前索引引擎对应的成功状态；
- 当前演示用户能够看见这些名称，而不仅是管理员能够看见。

随后在 Knowledge Center 中分别检索每份教材的第一个学习目标，至少返回一条来源片段：

| 知识库 | 验证查询 |
|---|---|
| `k12-ai-primary-lower` | `指令为什么需要清楚的先后顺序` |
| `k12-ai-primary-upper` | `数字图片中的像素记录什么` |
| `k12-ai-middle` | `有标签数据由哪些部分组成` |
| `k12-ai-high` | `灰度图像如何表示为二维数组` |

若某个查询没有结果，检查是否上传了正确文件、索引任务是否完成、当前用户是否被授予该知识库，以及当前检索引擎是否能读取 Markdown。重新索引后再次验证，直到四个查询均至少返回一条结果。

## 教育接口验证

保存对应学段画像后请求课程启动上下文，例如：

```text
GET /api/v1/education/launch-context/image-recognition
```

小学高年级响应的 `knowledge_bases` 应包含 `k12-ai-primary-upper`，且 `warnings` 不应包含 `knowledge_base_not_ready:k12-ai-primary-upper`。其他学段按各自默认课程重复验证。若仍有警告，以当前用户调用 `/api/v1/knowledge/list` 的可见名称为准排查授权，而不是在教育接口中伪造知识库名称。
