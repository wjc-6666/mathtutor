# MathTutor V1.1.1

## PDF 来源访问修复

来源优先提供“打开原 PDF”：访问 `/api/documents/{docid}/pdf#page=N`，后端根据数据库中的ID查找受管books目录的原文件，以 `application/pdf` 和 inline 返回。浏览器支持时使用 PDF 实际页码定位；不是印刷页码。浏览器不支持原生 PDF 或忽略fragment时，点击“查看原页”使用 `/api/documents/{docid}/page/N`：N=1是PDF第一页，只在内存中渲染请求页为PNG，不OCR、不改写PDF或现有缓存。普通来源里的OCR文本默认折叠，检索调试仍保留它。

网页使用的运行服务必须同步重启。本次发现磁盘已为V1.1，但8000端口仍运行V1路由。停止旧服务后明确使用本项目环境启动：

```powershell
cd C:\Users\王景初\Desktop\MathTutor
.\.venv\Scripts\python.exe -m pytest -q --basetemp=.\data\pytest-temp
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir C:\Users\王景初\Desktop\MathTutor --host 127.0.0.1 --port 8000
```

检查 `/openapi.json` 的 title 为 MathTutor V1.1.1，并含 `/api/documents/{docid}/pdf` 与 `/api/documents/{docid}/page/{page}`。无需重建索引或运行任何OCR。


个人数学分析与高等代数学习助手。保留 V1 的四种 Tutor 模式、历史、来源、跨书比较、资料管理和图片确认，增量增加扫描 PDF OCR、缓存、结构片段、BM25、诊断和检索调试。默认离线运行，不需要付费 API。

**复杂数学公式识别较差，不能直接作为公式解答依据。** 点击来源的“打开原 PDF 页”核对。正文与例题编号的有限真实测试已完成；本地语义适配器 **Implemented but not verified**，不能把 hash 字符向量称为语义搜索。

## Windows 安装与已有项目升级

Python 3.11+。新建项目时建立 `.venv`、安装主依赖，并复制 `.env.example` 为 `.env`。已有 V1 **保留原 `.env`**、books 与聊天数据库；不要用示例覆盖密钥配置。

```powershell
cd C:\Users\王景初\Desktop\MathTutor
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m app.cli index
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

浏览器访问 http://127.0.0.1:8000 。停止服务用 Ctrl+C。新增主依赖是 pypdfium2 与 Pillow，用于逐页渲染；PDF 原文件只读。

升级包中的 `install_upgrade.py` 先校验原代码与包内文件，再备份被修改的代码和 SQLite，复制代码与现成 OCR 缓存；不复制测试数据库、不覆盖 `.env`、不修改 PDF、不替换聊天数据库。运行前停止原服务。安装完成后按上面命令安装依赖和重建索引。详细命令见包内 `安装说明.md`。

## 教材与 OCR

数学分析放 `books/analysis`，高等代数放 `books/algebra`；支持子目录、PDF、UTF-8 TXT、Markdown。文件名称可自定；上传同名文件会拒绝覆盖。

默认 `OCR_ENGINE=windows` 使用系统已安装的简体中文 Windows OCR（zh-Hans-CN），通过 Windows 自带 PowerShell/WinRT 调用，本次在 Windows 11 上实跑三本书。缺少该识别语言时安装 Windows 中文 OCR 语言组件。需要图像渲染依赖，不需要云端密钥。

每一页检查文字层，不以少量目录文本代替整书判断：至少 40 个非空白字符、有效文字数字比例至少 50%、私用区/替换乱码比例低于 3% 才直接使用。启发式只判断可读文字，**不能判断公式是否正确**。不足的页自动 OCR；引擎异常按页记录、继续后续页面，下次重建只重试失败页。

`data/ocr/<PDF SHA256>/<pipeline配置签名>/` 保存 inspection、manifest 和逐页 JSON：原始文字、清洗文字、原 PDF 页码、状态、错误、时间、引擎与版本。PDF hash 或引擎/渲染配置变化会使用新缓存；重启与重复索引复用完整缓存。保留原 PDF 页序号（从 1 开始）；印刷页码全部为 null，禁止推测。双页扫描仍映射为同一个原 PDF 页。

清洗处理中文间距、行尾、英文断词、可辨认的编号分隔符和高频重复边缘行；保留 raw_text，不全局删除数学标点。数字边缘行因可能属于公式而保留。正文顺序与上下标仍可能被 OCR 破坏。

可选 `OCR_ENGINE=rapidocr` 适配器需另行安装 `rapidocr-onnxruntime`；本次安装被环境限制拒绝，**未运行、未评估该引擎质量**，不要据此认为它优于已测试方案。

## Chunk 与检索

优先从明确的章、§节、定义、定理、引理、推论、编号例题分块，保留其证明/解答；长块按句子/换行结合上限与重叠拆分。分块以页为边界，跨页证明尚未自动合并。章节由 OCR 可辨标题继承，可能误识；没有明确标题时保存 null。

来源保留 source_file、book_name、subject、pdf_page_start/end、chapter、section、content_type、label、text。`book_titles.example.json` 可复制为 `book_titles.json` 手工修正书名（按原文件名映射）。

- Keyword：中文二元词/英文/编号 BM25，完整短语和编号加权，实际例题标题优先于“参看例…”引用。
- Vector：显式查看字符 hash 或已配置的语义向量。hash 有碰撞，不可解释为语义理解。
- Hybrid：真实语义配置下融合 BM25 与向量排名，再优先明确编号；hash 配置下回退 BM25，避免碰撞压过正文。返回 retrieval_backend 告知实际通道。
- Semantic：hash 配置时明确报错；需要真正本地模型。改变模型必须重建索引。

知识库管理显示 OCR 页数、失败页、进度、片段数量与 Index 状态。`ready` 只表示片段已入库，不表示内容与公式准确。检索调试直接查看 Top-K 和来源，不调用 LLM。来源按钮打开真实 Chunk JSON 或原 PDF 页图像；学科与勾选资料同样用于调试检索。

OCR 扫描通过后台任务进行，诊断约每两秒更新；首次检查文字层阶段可能暂时无页进度。大型上传仍同步处理，可优先放入 books 后使用后台扫描。单服务进程适合个人运行；不要同时启动多个进程写同一 OCR 缓存。

## 免费本地语义（可选，未验证）

本次无法安装模型依赖与下载权重，因此以下为实施步骤，未计入通过结果。

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-semantic.txt
.\.venv\Scripts\python.exe -c "from huggingface_hub import snapshot_download; snapshot_download('intfloat/multilingual-e5-small',local_dir='data/models/multilingual-e5-small')"
```

在原 `.env` 设置 `EMBEDDING_PROVIDER=local`、`LOCAL_EMBEDDING_PATH=data/models/multilingual-e5-small`，保持 `LLM_PROVIDER=offline`，重建索引。加载仅用本地文件、CPU；E5 文档/问题分别加 `passage: `、`query: ` 前缀。准备模型时需要网络，之后检索不联网；不需要 Key。默认使用 torch 权重，不要用仅含 ONNX 的转换仓库目录替代。更换同一目录内的模型权重也要删除旧索引再重建。

依据：[E5 模型说明](https://huggingface.co/intfloat/multilingual-e5-small)、[SentenceTransformer 本地加载接口](https://www.sbert.net/docs/package_reference/sentence_transformer/model.html)。

## 原有使用流程

选择学科、新建或恢复对话，选择详细讲解/启发/批改/总结。启发模式输入“再提示一点”继续；“给完整解答”展开。勾选多书时每书独立检索。历史回答保留当时来源快照；删除索引保留磁盘资料。题目图片 PNG/JPEG 最大 10 MB，识别后人工确认；资料上传最大 200 MB。

本轮不配置付费 API。未来启用真实讲解时才设置 LLM_PROVIDER、LLM_API_KEY、LLM_MODEL；图片 API 同理。已有 API provider 保留。MathJax 延续 V1 的 CDN 方式，公式排版需网络。

SQLite 为 `data/mathtutor.sqlite3`，升级添加列并保留聊天；成功的重建在事务中替换对应资料片段，嵌入失败则保留旧索引。备份时关闭服务并保存 books、data、.env。

## 验证与限制

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe tests/real_benchmark.py
```

单元/流程测试 13 项（原有 8 项未修改，新增 5 项）；真实测试依赖这三本教材和已建索引，不属于普通 pytest，保存 Top5、原文、预期页与失败/未验证结果。教材实测详见交付报告。有限例题与定义定位通过不代表全书问题都通过：一致收敛的严格定义定位仍失败，模糊语义未验证，10 页抽查的复杂公式均有明显错误。

后续优先：双页扫描分别裁切且保留原页映射；小样本评估专用公式识别；补齐本地语义验收与更广真实测试。建议继续离线核验，尚不建议将 OCR 公式直接交给 LLM 解题。

服务仅绑定本机，无多用户登录。端口占用可选 8001。更改向量配置需重建；原页打不开先检查渲染依赖。WinRT 中文引擎说明：[Windows OCR 语言接口](https://learn.microsoft.com/en-us/uwp/api/windows.media.ocr.ocrengine.availablerecognizerlanguages?view=winrt-20348)。
